"""Build project-based tracks using a measured descending force ladder."""

import argparse
import shutil
from pathlib import Path

from tools.build_challenge_v2 import build
from xunyuan_eval.io import read_json, write_json
from xunyuan_eval.sensors import LIDAR, FRONT_CAMERA


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=Path('challenges/v3'))
    p.add_argument('--robot-source', type=Path, default=Path('challenges/v2/robot'))
    p.add_argument('--calibration', type=Path, required=True)
    p.add_argument('--seed', type=int)
    a = p.parse_args()
    calibration = read_json(a.calibration)
    cap = calibration['calibration_cap_N']
    levels = sorted({r['force_N'] for r in calibration['push_trials'] if 0 < r['force_N'] <= cap}, reverse=True)[:4]
    if len(levels) != 4 or not calibration['baseline_all_passed']:
        raise ValueError('校准结果需要有效无推力对照和至少四档推力')
    build(a.output, a.robot_source, a.seed)
    reference = read_json(a.output / 'reference.json')
    reference.update(schema_version='3.0', reference_id='xunyuan-v3-five-routes-20261126' if a.seed is None else f'xunyuan-v3-seed-{a.seed}',
        force_levels_N=levels, friction_levels=[.1, .2, .4, .8], nominal_friction=.8,
        disturbance_weights={'push': 10, 'friction': 10}, test_order='highest_difficulty_first_all_tiers',
        calibration='calibration.json')
    reference['disturbance']['pulse_duration_s'] = calibration['pulse_duration_s']
    write_json(a.output / 'reference.json', reference)
    write_json(a.output / 'calibration.json', calibration)
    interface = {'schema_version': '3.0', 'protocol': 'xunyuan-project-v1',
        'navigation_sensors': ['front_rgb', 'lidar_points'], 'lidar': LIDAR,
        'front_rgb': FRONT_CAMERA,
        'policy_frequency_hz': 50, 'physics_frequency_hz': 200,
        'reader_image': {'shape': [360, 640, 3], 'dtype': 'uint8', 'color': 'RGB', 'frequency_hz': 5}}
    write_json(a.output / 'model_interface.json', interface)
    from tools.make_project_example import manifest
    write_json(a.output / 'submission.example.json', manifest())
    if a.seed is None:
        for i in range(1, 6):
            preview = a.robot_source.parent / 'maps' / f'map{i:02d}.png'
            if preview.exists():
                shutil.copy2(preview, a.output / 'maps' / preview.name)
    print('Push levels from high to low:', levels)


if __name__ == '__main__':
    main()
