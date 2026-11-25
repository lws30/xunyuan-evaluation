"""Create two runnable participant projects with weights and AGENT.md."""

import argparse
from pathlib import Path

from xunyuan_eval.io import write_json


def manifest(weight_format='npz'):
    def project(kind):
        result = {'directory': kind, 'command': ['{python}', 'run.py'],
                  'weights': [f'weights/model.{weight_format}'], 'requirements': 'requirements.txt'}
        if kind == 'navigation':
            result['sensors'] = ['front_rgb']
        return result
    return {'schema_version': '3.0', 'team': 'project-example', 'navigation': project('navigation'),
            'recognition': project('recognition'), 'report': 'report.pdf'}


def report_pdf():
    stream = b'BT /F1 16 Tf 60 730 Td (Participant project example) Tj ET'
    objects = [b'<</Type/Catalog/Pages 2 0 R>>', b'<</Type/Pages/Kids[3 0 R]/Count 1>>',
        b'<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>',
        b'<</Length ' + str(len(stream)).encode() + b'>>stream\n' + stream + b'\nendstream',
        b'<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>']
    result = bytearray(b'%PDF-1.4\n'); offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result)); result.extend(f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(result); result.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets:
        result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer<</Size 6/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


WORKER = '''import json
import sys
from pathlib import Path
import numpy as np

weights = None
kind = None

def reply(request, **values):
    print(json.dumps(dict(request_id=request['request_id'], **values)), flush=True)

for line in sys.stdin:
    request = json.loads(line)
    try:
        if request['op'] == 'init':
            kind = request['kind']
            if Path('weights/model.pt').exists():
                import torch
                weights = torch.load('weights/model.pt', map_location='cpu', weights_only=True)
                weights = {name: tensor.numpy() for name, tensor in weights.items()}
            else:
                with np.load('weights/model.npz', allow_pickle=False) as data:
                    weights = {name: data[name] for name in data.files}
            reply(request, ready=True)
        elif request['op'] == 'reset':
            # Clear model history here before each route or video.
            reply(request, ready=True)
        elif request['op'] == 'predict' and kind == 'navigation':
            with np.load(request['observation'], allow_pickle=False) as observation:
                # front_rgb: HWC uint8; lidar_points (when selected): N x 3 metres.
                # Read instructions in order after visually detecting each new junction.
                instructions = observation['instructions']
                if not any(name in observation for name in ['front_rgb', 'lidar_points']):
                    raise ValueError('missing navigation sensor')
                action = weights['action'].tolist()
            reply(request, action=action)
        elif request['op'] == 'predict' and kind == 'recognition':
            image = np.load(request['image'], allow_pickle=False)  # HWC uint8 RGB
            # Replace this empty-reader example with your detector and OCR.
            # Each result: box_xyxy, confidence, status, value, unit.
            reply(request, detections=[])
        else:
            raise ValueError('unknown request')
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        reply(request, error=str(exc))
'''


def build(output, weight_format='npz'):
    import numpy as np
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for kind in ['navigation', 'recognition']:
        root = output / kind
        (root / 'weights').mkdir(parents=True)
        (root / 'run.py').write_text(WORKER)
        (root / 'requirements.txt').write_text('numpy>=1.26\n' + ('torch>=2.0\n' if weight_format == 'pt' else ''))
        values = {'action': np.zeros(16, np.float32)} if kind == 'navigation' else {'confidence_bias': np.zeros(1, np.float32)}
        if weight_format == 'pt':
            import torch
            torch.save({k: torch.from_numpy(v) for k, v in values.items()}, root / 'weights/model.pt')
        else:
            np.savez(root / 'weights/model.npz', **values)
        (root / 'AGENT.md').write_text(f'''# {kind} 项目复现说明

1. 使用 Python 3.11，在本目录执行 `python -m pip install -r requirements.txt`。
2. 权重位于 `weights/model.{weight_format}`，已经放入提交包。
3. 启动命令是 `python run.py`。每行读取一个 JSON 请求，每行回复一个 JSON，保留 request_id。
4. 本示例按 xunyuan-project-v1 协议处理 init、reset、predict。启动加载权重，reset 清空历史。
5. 导航从 observation 指定的 NPZ 读取指令、传感器和关节状态，输出 16 个动作；识别从 image 指定的 NPY 读取 RGB 图像，输出 detections。
6. 在仓库根目录执行 `python -m xunyuan_eval check-submission --submission {output.as_posix()}/submission.json --smoke`，预期返回 valid=true、smoke_passed=true。
7. 示例导航输出零动作，识别输出空结果。替换 run.py 中的推理部分与权重即可接入自己的模型。
''', encoding='utf-8')
    (output / 'report.pdf').write_bytes(report_pdf())
    write_json(output / 'submission.json', manifest(weight_format))
    return output / 'submission.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--format', choices=['npz', 'pt'], default='npz')
    a = p.parse_args()
    print(build(a.output, a.format))
