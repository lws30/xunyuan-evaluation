"""End-to-end execution of submitted navigation and recognition projects."""

import math
from pathlib import Path

from .challenge_v2 import validate_video_reference
from .challenge_v3 import evaluate, validate_reference
from .io import FormatError, contained, digest, read_json, write_json
from .onnx_runtime_v2 import robot_attempt, recognize_videos
from .projects import ProjectSession, bundle_hashes, check_projects


def run_projects(submission, challenge, output, videos=None, video_reference=None,
                 route_id=None, max_seconds=None, seed=20261126, split='train'):
    if max_seconds is not None and (not math.isfinite(max_seconds) or max_seconds <= 0):
        raise FormatError('试跑时长必须大于 0')
    data, files = check_projects(submission)
    challenge = Path(challenge); output = Path(output)
    if any(output.resolve().is_relative_to(files[kind]) for kind in ['navigation', 'recognition']):
        raise FormatError('评测结果请保存到两个项目文件夹之外')
    reference = validate_reference(read_json(challenge / 'reference.json'))
    routes = [r for r in reference['routes'] if route_id is None or r['id'] == route_id]
    if not routes:
        raise FormatError('没有这张地图')
    truth = manifest = None
    hashes = {'reference': digest(challenge / 'reference.json')}
    if video_reference and not videos:
        raise FormatError('请同时提供视频目录')
    if videos:
        videos = Path(videos)
        video_reference = Path(video_reference) if video_reference else videos / 'train/reference.json'
        if split == 'test' and video_reference == videos / 'train/reference.json':
            raise FormatError('正式测试需要组织方提供测试答案')
        truth = validate_video_reference(read_json(video_reference))
        manifest = read_json(videos / 'manifest.json')
        selected = [v for v in manifest['videos'] if v['id'].startswith(split)]
        expected_count = 8 if split == 'train' else 2
        ids = {v['id'] for v in selected}
        if len(selected) != expected_count or len(ids) != expected_count or {e['video_id'] for e in truth['events']} != ids:
            raise FormatError('视频与答案需要对应：训练 8 段，测试 2 段')
        if any(sum(e['video_id'] == vid for e in truth['events']) != 12 for vid in ids):
            raise FormatError('每段视频需要 12 个标牌答案')
        for item in selected:
            if digest(contained(videos / split, item['file'])) != item['sha256']:
                raise FormatError('视频校验值不一致')
        hashes.update(video_manifest=digest(videos / 'manifest.json'), video_reference=digest(video_reference))
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'reference.json', reference)
    run = {'schema_version': '3.0', 'reference_id': reference['reference_id'], 'team': data['team'],
           'routes': [], 'disturbance': [], 'friction': [], 'seed': seed,
           'sensors': data['navigation']['sensors'], 'submission_sha256': bundle_hashes(data, files),
           'input_sha256': hashes, 'model_errors': [], 'video_split': split}
    for route in routes:
        attempts = [('normal', 0, reference['nominal_friction'], 'routes')]
        attempts += [(f'force_{force}', force, reference['nominal_friction'], 'disturbance') for force in reference['force_levels_N']]
        attempts += [(f'friction_{mu}', 0, mu, 'friction') for mu in reference['friction_levels']]
        for name, force, mu, group in attempts:
            try:
                with ProjectSession(files['navigation'], data['navigation'], 'navigation',
                                    output / 'logs' / f'{route["id"]}_{name}.log') as policy:
                    attempt = robot_attempt(policy, challenge, reference, route, output / route['id'] / name,
                                            force, max_seconds, seed, friction=mu)
                attempt.pop('result')
                for key in ['trace', 'force_record']:
                    attempt[key] = str(Path(attempt[key]).relative_to(output.resolve()))
                if group == 'friction':
                    attempt['friction'] = mu
                run[group].append(attempt)
            except (FormatError, OSError) as exc:
                run['model_errors'].append({'route_id': route['id'], 'attempt': name, 'error': str(exc)})
            # All tiers run independently, from highest difficulty to lowest, after a fresh reset.
            write_json(output / 'run.json', run)
    if videos:
        try:
            with ProjectSession(files['recognition'], data['recognition'], 'recognition', output / 'logs/recognition.log') as reader:
                recognize_videos(reader, videos, manifest, output / 'video_predictions.json', split)
        except (FormatError, OSError) as exc:
            write_json(output / 'video_predictions.json', {'detections': []})
            run['video_error'] = str(exc)
        run['video_predictions'] = 'video_predictions.json'
    write_json(output / 'run.json', run)
    report = evaluate(run, reference, output, truth)
    report.update(submission_sha256=run['submission_sha256'], input_sha256=hashes, seed=seed,
                  model_errors=run['model_errors'], video_split=split, score_kind='practice' if split == 'train' else 'test')
    if run.get('video_error'):
        report['video_error'] = run['video_error']
    write_json(output / 'report.json', report)
    return report
