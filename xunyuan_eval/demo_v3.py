"""Generate ideal records to inspect v3 score calculations."""

import copy
from pathlib import Path

from .demo_v2 import rows_for_route
from .io import read_json, write_json
from .recorder import TraceRecorder


def create_demo(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    reference = read_json(Path(__file__).resolve().parents[1] / 'challenges/v3/reference.json')
    duration = reference['disturbance']['pulse_duration_s']
    run = {'schema_version': '3.0', 'reference_id': reference['reference_id'], 'team': 'scoring-example',
           'routes': [], 'disturbance': [], 'friction': [], 'video_predictions': 'video_predictions.json'}
    for route in reference['routes']:
        attempts = [('normal', 0, reference['nominal_friction'], 'routes')]
        attempts += [(f'force_{f}', f, reference['nominal_friction'], 'disturbance') for f in reference['force_levels_N']]
        attempts += [(f'friction_{mu}', 0, mu, 'friction') for mu in reference['friction_levels']]
        for name, force, mu, group in attempts:
            filename = f'traces/{route["id"]}_{name}.jsonl'
            with TraceRecorder(output / filename) as recorder:
                for original in rows_for_route(route):
                    row = copy.deepcopy(original)
                    active = any(start + 1e-9 < row['time_s'] <= start + duration + 1e-9 for start in [1., 3., 5.])
                    row['force_world_N'] = [0, force if active else 0, 0]
                    row['ground_contact_friction'] = [mu] * 4
                    recorder.append(row)
            item = {'route_id': route['id'], 'termination': 'completed', 'trace': filename}
            if force:
                item.update(force_N=force, force_record=f'forces/{route["id"]}_{force}.json')
                write_json(output / item['force_record'], {'force_N': force, 'pulses': [
                    {'start_s': t, 'duration_s': duration, 'force_world_N': [0, force, 0]} for t in [1., 3., 5.]]})
            if group == 'friction':
                item['friction'] = mu
            run[group].append(item)
    events = []; detections = []
    for video in ['test01', 'test02']:
        for i in range(12):
            t = i * 3 + 1
            event = {'id': f'{video}/E{i+1:02d}', 'video_id': video, 'start_s': t, 'end_s': t + 1,
                'readable': True, 'kind': 'digits' if i < 6 else 'temperature_display',
                'answer': '00127' if i < 6 else '31.4', 'boxes': [{'time_s': t, 'box_xyxy': [.4, .4, .6, .6]}]}
            events.append(event)
            detections.append({'video_id': video, 'time_s': t, 'box_xyxy': [.4, .4, .6, .6], 'status': 'ok',
                'confidence': 1, 'value': event['answer'], 'unit': None if i < 6 else 'C'})
    write_json(output / 'video_reference.json', {'events': events, 'temperature_tolerance_C': '.1'})
    write_json(output / 'video_predictions.json', {'detections': detections})
    write_json(output / 'reference.json', reference)
    write_json(output / 'run.json', run)
    return output / 'run.json'
