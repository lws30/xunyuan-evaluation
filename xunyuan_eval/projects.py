"""Run participant projects through a persistent JSON-lines subprocess."""

import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

from .io import FormatError, contained, digest, read_json

PROTOCOL = 'xunyuan-project-v1'
SENSORS = {'front_rgb', 'lidar_points'}
EXCLUDED = {'.git', '.venv', '__pycache__', '.pytest_cache'}


def validate_detections(rows):
    from .io import number
    for row in rows:
        number(row.get('confidence'), 'confidence', 0)
        box = row.get('box_xyxy')
        if not isinstance(box, list) or len(box) != 4:
            raise FormatError('识别结果需要 box_xyxy 四个坐标')
        for value in box:
            number(value, 'box coordinate', 0)
        if not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1 or row['confidence'] > 1:
            raise FormatError('识别坐标和可信度需要在 0 至 1 之间')
        if row.get('status') == 'ok':
            if not isinstance(row.get('value'), str) or not (row.get('unit') is None or row.get('unit') == 'C'):
                raise FormatError('读数需要文字 value，温度单位为 C，普通数字单位为 null')
        elif row.get('status') == 'abstain':
            if not isinstance(row.get('reason'), str) or not row['reason'].strip():
                raise FormatError('看不清时请提供 reason')
        else:
            raise FormatError('识别 status 应为 ok 或 abstain')
    return rows


def smoke_projects(path):
    import numpy as np
    data, checked = check_projects(path)
    with ProjectSession(checked['navigation'], data['navigation'], 'navigation') as policy:
        policy.reset()
        feed = {'instructions': np.ones((1, 11), np.int64), 'imu': np.array([[0, 0, 0, 0, 0, -1]], np.float32),
                'joint_position': np.zeros((1, 16), np.float32), 'joint_velocity': np.zeros((1, 16), np.float32),
                'previous_action': np.zeros((1, 16), np.float32), 'sensor_time_s': np.array([0.]), 'time_s': np.array([0.])}
        if 'front_rgb' in data['navigation']['sensors']:
            feed['front_rgb'] = np.zeros((1, 3, 144, 256), np.float32)
        if 'lidar_points' in data['navigation']['sensors']:
            feed['lidar_points'] = np.array([[1., 0, 0]], np.float32)
        action = policy.infer(['action'], feed)[0]
        if not np.isfinite(action).all() or np.max(np.abs(action)) > 1:
            raise FormatError('导航示例输出不符合动作范围')
    with ProjectSession(checked['recognition'], data['recognition'], 'recognition') as reader:
        reader.reset()
        validate_detections(reader.read_frame(np.zeros((360, 640, 3), np.uint8), 0, 'smoke'))
    return {'valid': True, 'smoke_passed': True, 'sensors': data['navigation']['sensors']}


def project_files(directory):
    files = []
    for path in sorted(directory.rglob('*')):
        if any(part in EXCLUDED for part in path.relative_to(directory).parts):
            continue
        if path.is_symlink():
            raise FormatError('项目文件请直接放入提交包，不能使用符号链接：' + str(path))
        if path.is_file():
            files.append(path)
    return files


def contained_directory(root, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise FormatError('项目目录需要使用相对路径')
    rel = Path(name)
    root = Path(root).resolve()
    target = (root / rel).resolve()
    if rel.is_absolute() or '..' in rel.parts or target == root or not target.is_relative_to(root) or not target.is_dir():
        raise FormatError('项目目录不存在或超出提交包：' + name)
    return target


def check_projects(path):
    path = Path(path).resolve()
    data = read_json(path)
    if not isinstance(data, dict) or data.get('schema_version') != '3.0':
        raise FormatError('项目提交清单的 schema_version 应为 3.0')
    if not isinstance(data.get('team'), str) or not data['team'].strip():
        raise FormatError('请填写队伍名称 team')
    root = path.parent
    report = contained(root, data.get('report'))
    if not report.is_file() or report.read_bytes()[:5] != b'%PDF-':
        raise FormatError('请提供 PDF 报告')
    checked = {'report': report}
    for kind in ['navigation', 'recognition']:
        spec = data.get(kind)
        if not isinstance(spec, dict):
            raise FormatError('请提供 ' + kind + ' 项目配置')
        directory = contained_directory(root, spec.get('directory'))
        if not directory.is_dir():
            raise FormatError('找不到项目目录：' + kind)
        agent = contained(directory, 'AGENT.md')
        if not agent.is_file() or not agent.read_text(encoding='utf-8').strip():
            raise FormatError(kind + ' 文件夹必须提供 AGENT.md')
        requirements = contained(directory, spec.get('requirements'))
        if not requirements.is_file():
            raise FormatError(kind + ' 缺少依赖文件')
        weights = spec.get('weights')
        if not isinstance(weights, list) or not weights:
            raise FormatError(kind + ' 请列出权重文件 weights')
        for weight in weights:
            target = contained(directory, weight)
            if not target.is_file() or target.stat().st_size == 0:
                raise FormatError('找不到权重文件：' + str(weight))
        command = spec.get('command')
        if not isinstance(command, list) or not command or any(not isinstance(s, str) or not s for s in command):
            raise FormatError(kind + ' 的 command 应为命令参数列表')
        if kind == 'navigation':
            sensors = spec.get('sensors')
            if not isinstance(sensors, list) or not sensors or len(set(sensors)) != len(sensors) or any(s not in SENSORS for s in sensors):
                raise FormatError('导航 sensors 可选 front_rgb、lidar_points，至少选一个')
        checked[kind] = directory
        project_files(directory)
    if checked['navigation'] == checked['recognition'] or any(
        a.is_relative_to(b) for a, b in [(checked['navigation'], checked['recognition']),
                                       (checked['recognition'], checked['navigation'])]):
        raise FormatError('导航和识别请放在两个独立文件夹')
    if 'sha256' in data:
        actual = bundle_hashes(data, checked)
        if actual != data['sha256']:
            raise FormatError('提交文件校验值不一致')
    return data, checked


def bundle_hashes(data, checked):
    hashes = {data['report']: digest(checked['report'])}
    for kind in ['navigation', 'recognition']:
        directory = checked[kind]
        for path in project_files(directory):
            key = (Path(data[kind]['directory']) / path.relative_to(directory)).as_posix()
            hashes[key] = digest(path)
    return hashes


def package_projects(path, output):
    import copy
    data, checked = check_projects(path)
    output = Path(output).resolve()
    if output.exists():
        raise FormatError('请使用新的提交包文件名')
    if any(output.is_relative_to(checked[k]) for k in ['navigation', 'recognition']):
        raise FormatError('提交包请保存到两个项目文件夹之外')
    data = copy.deepcopy(data)
    data['sha256'] = bundle_hashes(data, checked)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(checked['report'], data['report'])
        for kind in ['navigation', 'recognition']:
            for source in project_files(checked[kind]):
                archive.write(source, (Path(data[kind]['directory']) / source.relative_to(checked[kind])).as_posix())
        archive.writestr('submission.json', json.dumps(data, ensure_ascii=False, indent=2))
    return {'package': str(output), 'sha256': digest(output)}


class ProjectSession:
    """Arrays are passed in one NPZ file; stdout carries one JSON reply per request."""

    def __init__(self, directory, spec, kind, log_path=None, startup_timeout=60):
        self.directory = Path(directory).resolve()
        self.spec = spec
        self.kind = kind
        self.temp = tempfile.TemporaryDirectory(prefix='xunyuan-project-')
        self.work = Path(self.temp.name)
        self.proc = None
        self.log = None
        self.replies = queue.Queue()
        self.serial = 0
        try:
            if log_path:
                log_path = Path(log_path)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                self.log = log_path.open('ab')
            else:
                self.log = (self.work / 'stderr.log').open('ab')
            local_python = self.directory / '.venv/bin/python'
            interpreter = str(local_python) if local_python.is_file() else sys.executable
            command = [s.replace('{python}', interpreter) for s in spec['command']]
            self.proc = subprocess.Popen(command, cwd=self.directory, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.log, text=True, encoding='utf-8', bufsize=1,
                start_new_session=True)
            threading.Thread(target=self._receive, daemon=True).start()
            from .sensors import FRONT_CAMERA, LIDAR
            calibration = {'front_rgb': FRONT_CAMERA, 'lidar_points': LIDAR}
            reply = self.request({'op': 'init', 'protocol': PROTOCOL, 'kind': kind,
                                  'sensors': spec.get('sensors', []),
                                  'sensor_config': {s: calibration[s] for s in spec.get('sensors', [])}}, startup_timeout)
            if reply.get('ready') is not True:
                raise FormatError(kind + ' 启动后需要返回 ready=true')
        except Exception:
            self.close()
            raise

    def _receive(self):
        try:
            while True:
                line = self.proc.stdout.readline(4 * 1024 * 1024 + 1)
                if not line:
                    self.replies.put(FormatError(self.kind + ' 运行程序已退出'))
                    return
                if len(line) > 4 * 1024 * 1024 or not line.endswith('\n'):
                    self.replies.put(FormatError('单条模型回复过长'))
                    return
                try:
                    reply = json.loads(line)
                    if not isinstance(reply, dict):
                        raise ValueError('reply must be an object')
                    self.replies.put(reply)
                except (ValueError, TypeError):
                    self.replies.put(FormatError('模型标准输出需要每行一个 JSON；日志请写到标准错误'))
                    return
        except (OSError, ValueError):
            self.replies.put(FormatError(self.kind + ' 连接已关闭'))

    def request(self, message, timeout=.5):
        self.serial += 1
        message = dict(message, request_id=self.serial)
        try:
            self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            self.proc.stdin.flush()
            reply = self.replies.get(timeout=timeout)
        except queue.Empty as exc:
            self.close()
            raise FormatError(self.kind + ' 模型回复超时') from exc
        except (BrokenPipeError, OSError, ValueError) as exc:
            raise FormatError(self.kind + ' 模型进程无法继续运行') from exc
        if isinstance(reply, Exception):
            raise reply
        if reply.get('request_id') != self.serial:
            raise FormatError('模型回复的 request_id 与请求不一致')
        if reply.get('error'):
            raise FormatError(self.kind + '：' + str(reply['error']))
        return reply

    def reset(self):
        reply = self.request({'op': 'reset'}, 5)
        if reply.get('ready') is not True:
            raise FormatError('reset 后需要返回 ready=true')

    def get_inputs(self):
        names = ['instructions', 'imu', 'joint_position', 'joint_velocity', 'previous_action'] + self.spec.get('sensors', [])
        return [SimpleNamespace(name=name) for name in names]

    def get_outputs(self):
        return [SimpleNamespace(name='action')]

    def infer(self, outputs, feed, timeout_s=.5):
        import numpy as np
        path = self.work / 'observation.npz'
        arrays = dict(feed)
        if 'front_rgb' in arrays:
            arrays['front_rgb'] = np.rint(np.clip(arrays['front_rgb'][0].transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)
        for key in ['instructions', 'imu', 'joint_position', 'joint_velocity', 'previous_action']:
            if key in arrays:
                arrays[key] = arrays[key][0]
        np.savez(path, **arrays)
        reply = self.request({'op': 'predict', 'observation': str(path)}, timeout_s)
        raw = reply.get('action')
        if not isinstance(raw, list) or len(raw) != 16 or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in raw):
            raise FormatError('导航 action 需要包含 16 个数值')
        action = np.asarray(raw, dtype=np.float32)
        if action.shape != (16,):
            raise FormatError('导航 action 需要包含 16 个动作值')
        return [action[None]]

    def read_frame(self, rgb, time_s, video_id):
        import numpy as np
        path = self.work / 'image.npy'
        np.save(path, rgb)
        reply = self.request({'op': 'predict', 'image': str(path), 'time_s': time_s,
                              'video_id': video_id}, .5)
        rows = reply.get('detections')
        if not isinstance(rows, list) or len(rows) > 16:
            raise FormatError('识别回复需要 detections 列表，每帧最多 16 个标牌')
        for row in rows:
            if not isinstance(row, dict):
                raise FormatError('每个标牌结果需要是一个 JSON 对象')
        return [dict(row, time_s=time_s, video_id=video_id) for row in rows]

    def close(self):
        if self.proc is not None:
            if self.proc.poll() is None:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.proc.wait(timeout=5)
            for stream in [self.proc.stdin, self.proc.stdout]:
                if stream:
                    stream.close()
        if self.log is not None:
            self.log.close()
        self.temp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
