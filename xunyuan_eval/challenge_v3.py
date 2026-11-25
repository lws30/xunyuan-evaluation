"""Project-based scoring: routes 30, pushes 10, friction 10, readings 20."""

import copy
import math
from pathlib import Path

from . import challenge_v2
from .io import FormatError, contained, digest, number
from .validation import load_trace


def compatible_reference(reference):
    result = copy.deepcopy(reference)
    result['schema_version'] = '2.0'
    result['force_levels_N'] = sorted(result['force_levels_N'])
    return result


def validate_reference(reference):
    if not isinstance(reference, dict) or reference.get('schema_version') != '3.0':
        raise FormatError('需要 v3 赛道规则')
    challenge_v2.validate_reference(compatible_reference(reference))
    if reference['force_levels_N'] != sorted(reference['force_levels_N'], reverse=True):
        raise FormatError('推力档位需要从大到小排列')
    friction = reference.get('friction_levels')
    if not isinstance(friction, list) or len(friction) != 4:
        raise FormatError('需要四档地面摩擦系数')
    for mu in friction:
        if number(mu, 'friction', 0) == 0:
            raise FormatError('摩擦系数必须大于 0')
    if friction != sorted(set(friction)):
        raise FormatError('摩擦测试从最滑到最不滑排列')
    if reference.get('disturbance_weights') != {'push': 10, 'friction': 10}:
        raise FormatError('扰动分为推力 10 分、摩擦 10 分')
    nominal = number(reference.get('nominal_friction'), 'nominal friction', 0)
    if nominal <= 0:
        raise FormatError('正常地面摩擦系数必须大于 0')
    return reference


def evaluate(run, reference, root, video_reference=None):
    validate_reference(reference)
    if not isinstance(run, dict) or run.get('schema_version') != '3.0':
        raise FormatError('需要 v3 运行记录')
    root = Path(root)
    legacy_run = dict(run, schema_version='2.0')
    result = challenge_v2.evaluate(legacy_run, compatible_reference(reference), root, video_reference)
    # The v2 helper verifies every recorded force independently; v3 scores each tier independently.
    outcomes = {(x['route_id'], x['force_N']): x['attempt'] for x in result['details']['disturbance']}
    pushes = []
    for route in reference['routes']:
        for force in reference['force_levels_N']:
            attempt = outcomes[(route['id'], force)]
            passed = bool(attempt and attempt['passed'])
            pushes.append({'route_id': route['id'], 'force_N': force, 'score': .5 if passed else 0,
                           'maximum': .5, 'reason': attempt['reason'] if attempt else 'missing', 'attempt': attempt})
    friction_items = run.get('friction', [])
    if not isinstance(friction_items, list):
        raise FormatError('friction 需要是运行列表')
    items = {}
    expected_routes = {r['id'] for r in reference['routes']}
    used = {contained(root, name) for name in result['trace_sha256']}
    for item in friction_items:
        if not isinstance(item, dict) or item.get('route_id') not in expected_routes:
            raise FormatError('摩擦测试地图不正确')
        mu = item.get('friction')
        if isinstance(mu, bool) or mu not in reference['friction_levels']:
            raise FormatError('摩擦档位不正确')
        key = (item['route_id'], mu)
        if key in items:
            raise FormatError('摩擦测试重复')
        path = contained(root, item.get('trace'))
        if path in used:
            raise FormatError('每次测试需要独立的仿真记录')
        used.add(path); items[key] = item
    frictions = []
    for route in reference['routes']:
        for mu in reference['friction_levels']:
            item = items.get((route['id'], mu))
            outcome = None
            if item:
                rows = load_trace(root, item['trace'])
                outcome = challenge_v2.score_route(rows, route, reference['rules'], item['termination'])
                observed = []
                valid = True
                for row in rows:
                    mus = row.get('ground_contact_friction')
                    if not isinstance(mus, list) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in mus):
                        valid = False; break
                    observed.extend(mus)
                    force = row.get('force_world_N')
                    if not isinstance(force, list) or len(force) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1e-8 for v in force):
                        valid = False; break
                valid = valid and bool(observed) and all(abs(v-mu) < 1e-6 for v in observed)
                outcome['friction_record_verified'] = valid
                outcome['passed'] = outcome['passed'] and valid
                if not valid and outcome['reason'] == 'completed':
                    outcome['reason'] = 'friction_record_mismatch'
                result['trace_sha256'][item['trace']] = digest(contained(root, item['trace']))
            passed = bool(outcome and outcome['passed'])
            frictions.append({'route_id': route['id'], 'friction': mu, 'score': .5 if passed else 0,
                              'maximum': .5, 'reason': outcome['reason'] if outcome else 'missing', 'attempt': outcome})
    push_score = sum(r['score'] for r in pushes)
    friction_score = sum(r['score'] for r in frictions)
    result['schema_version'] = '3.0'
    if video_reference is not None and run.get('video_predictions') and run.get('video_split') == 'train':
        from .io import read_json
        result['scores']['recognition'] = challenge_v2.score_video(
            read_json(contained(root, run['video_predictions'])), video_reference, include_answers=True)
    result['scores']['disturbance'] = {'score': push_score + friction_score, 'maximum': 20,
        'push': {'score': push_score, 'maximum': 10}, 'friction': {'score': friction_score, 'maximum': 10}}
    result['navigation_control_score'] = result['scores']['route']['score'] + push_score + friction_score
    result['automated_score'] = result['navigation_control_score'] + result['scores']['recognition']['score']
    result['details']['disturbance'] = pushes
    result['details']['friction'] = frictions
    if 'sensors' in run:
        result['sensors'] = run['sensors']
        result['sensor_mode'] = 'fusion' if len(run['sensors']) == 2 else 'vision' if 'front_rgb' in run['sensors'] else 'lidar'
    return result
