import copy
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from xunyuan_eval.io import FormatError, read_json, write_json
from xunyuan_eval.projects import check_projects, package_projects, smoke_projects, ProjectSession

try:
    import numpy as np
except ImportError:
    np = None


@unittest.skipIf(np is None, '需要 NumPy')
class ProjectSubmissionTests(unittest.TestCase):
    def setUp(self):
        from tools.make_project_example import build
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = build(self.root / 'team')
        self.data = read_json(self.path)

    def test_two_projects_start_load_weights_and_answer_predictions(self):
        result = smoke_projects(self.path)
        self.assertTrue(result['smoke_passed'])

    def test_lidar_only_and_fused_projects_do_not_require_visual_input(self):
        for sensors in [['lidar_points'], ['front_rgb', 'lidar_points']]:
            self.data['navigation']['sensors'] = sensors
            write_json(self.path, self.data)
            self.assertEqual(smoke_projects(self.path)['sensors'], sensors)

    def test_each_project_requires_agent_instructions(self):
        (self.root / 'team/recognition/AGENT.md').unlink()
        with self.assertRaisesRegex(FormatError, 'AGENT.md'):
            check_projects(self.path)

    def test_weight_suffix_is_not_restricted_to_onnx(self):
        for suffix in ['pt', 'pth', 'bin', 'safetensors']:
            target = self.root / f'team/navigation/weights/model.{suffix}'
            target.write_bytes(b'model weights')
            self.data['navigation']['weights'] = [f'weights/model.{suffix}']
            write_json(self.path, self.data)
            check_projects(self.path)

    def test_packaging_keeps_source_instructions_requirements_and_weights(self):
        package_projects(self.path, self.root / 'team.zip')
        with zipfile.ZipFile(self.root / 'team.zip') as archive:
            names = set(archive.namelist())
            for kind in ['navigation', 'recognition']:
                for name in ['AGENT.md', 'requirements.txt', 'run.py', 'weights/model.npz']:
                    self.assertIn(kind + '/' + name, names)
            archive.extractall(self.root / 'unpacked')
        check_projects(self.root / 'unpacked/submission.json')
        (self.root / 'unpacked/navigation/run.py').write_text('changed code')
        with self.assertRaisesRegex(FormatError, '校验值'):
            check_projects(self.root / 'unpacked/submission.json')

    def test_project_directory_cannot_escape_submission(self):
        self.data['navigation']['directory'] = '../other'
        write_json(self.path, self.data)
        with self.assertRaises(FormatError):
            check_projects(self.path)

    def test_runtime_timeout_terminates_stuck_project(self):
        script = self.root / 'team/navigation/run.py'
        script.write_text("import json,sys,time\nfor line in sys.stdin:\n r=json.loads(line)\n if r['op']=='init':print(json.dumps({'request_id':r['request_id'],'ready':True}),flush=True)\n else:time.sleep(30)\n")
        session = ProjectSession(script.parent, self.data['navigation'], 'navigation')
        self.addCleanup(session.close)
        started = time.monotonic()
        with self.assertRaisesRegex(FormatError, '超时'):
            session.request({'op': 'predict'}, .05)
        self.assertIsNotNone(session.proc.poll())
        self.assertLess(time.monotonic() - started, 2)


try:
    import mujoco
except ImportError:
    mujoco = None


@unittest.skipIf(np is None or mujoco is None, '需要 MuJoCo 和 NumPy')
class SensorTests(unittest.TestCase):
    def test_scan_matches_real_wall_and_omits_robot_geometry(self):
        from xunyuan_eval.sensors import Lidar
        model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
          <body name="base_link" pos="0 0 1"><freejoint/>
          <geom type="sphere" size=".1" group="1" mass="1"/></body>
          <geom type="box" pos="2 0 1" size=".1 5 5" group="0"/>
        </worldbody></mujoco>''')
        data = mujoco.MjData(model); mujoco.mj_forward(model, data)
        points = Lidar(model).scan(data)
        self.assertGreater(len(points), 0)
        self.assertTrue(np.allclose(points[:, 0], 1.7, atol=1e-5))

    def test_actual_contact_friction_changes_at_all_four_levels(self):
        from xunyuan_eval.sensors import set_ground_friction, contact_friction
        path = Path(__file__).resolve().parents[1] / 'challenges/v3/maps/map01.xml'
        model = mujoco.MjModel.from_xml_path(str(path)); data = mujoco.MjData(model)
        config = read_json(path.parent.parent / 'robot/control.json')
        for name, value in zip(config['leg_joint_names'] + config['wheel_joint_names'], config['default_joint_pos']):
            data.qpos[model.jnt_qposadr[model.joint(name).id]] = value
        data.ctrl[:12] = config['default_joint_pos'][:12]
        for _ in range(500):
            mujoco.mj_step(model, data)
        for mu in [.1, .2, .4, .8]:
            set_ground_friction(model, mu); mujoco.mj_forward(model, data)
            actual = contact_friction(model, data)
            self.assertTrue(actual)
            self.assertTrue(all(abs(v-mu) < 1e-8 for v in actual))


if __name__ == '__main__':
    unittest.main()
