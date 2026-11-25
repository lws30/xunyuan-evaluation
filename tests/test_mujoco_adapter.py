"""Optional real-physics API regression; core CI does not install MuJoCo."""

import unittest

try:
    import mujoco
except ImportError:
    mujoco = None

from xunyuan_eval.mujoco_recorder import MuJoCoSampler
from xunyuan_eval.validation import validate_sample


@unittest.skipIf(mujoco is None, "Optional MuJoCo installation not present")
class MuJoCoAdapterTests(unittest.TestCase):
    def setUp(self):
        self.model = mujoco.MjModel.from_xml_string('''
        <mujoco><worldbody><geom name="floor" type="plane" size="3 3 .1"/>
        <body name="base_link" pos="0 0 .2"><freejoint/>
          <geom name="body" size=".1 .1 .1" type="box"/>
          <body name="wheel" pos="0 0 -.1"><geom type="sphere" size=".1"/></body>
        </body></worldbody></mujoco>''')
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)
        self.sampler = MuJoCoSampler(self.model, root_body="base_link", terrain_geom_names=["floor"],
                                     allowed_terrain_body_names=["wheel"],
                                     boundary_check=lambda points: any(abs(p[1]) > 2 for p in points))

    def test_actual_geometry_and_velocity(self):
        self.data.qvel[0] = .5
        self.data.qvel[5] = .2
        mujoco.mj_forward(self.model, self.data)
        row = self.sampler.sample(self.data, action_valid=True)
        validate_sample(row)
        self.assertEqual(len(row["envelope_points_m"]), 16)
        self.assertAlmostEqual(min(p[2] for p in row["envelope_points_m"]), 0)
        self.assertAlmostEqual(max(p[2] for p in row["envelope_points_m"]), .3)
        self.assertAlmostEqual(row["speed_mps"], .5)
        self.assertAlmostEqual(row["yaw_rate_rps"], .2)

    def test_body_contact_is_forbidden_and_action_flag_retained(self):
        self.data.qpos[2] = .05
        mujoco.mj_forward(self.model, self.data)
        row = self.sampler.sample(self.data, action_valid=False)
        self.assertGreater(row["forbidden_contacts"], 0)
        self.assertFalse(row["action_valid"])


if __name__ == "__main__":
    unittest.main()
