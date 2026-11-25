"""Verify force impulse, active friction, collisions and LiDAR in the actual tracks."""

import argparse
import math
from pathlib import Path

import mujoco
import numpy as np

from xunyuan_eval.io import read_json, write_json
from xunyuan_eval.sensors import Lidar, contact_friction, set_ground_friction
from xunyuan_eval.mujoco_recorder import MuJoCoSampler


def check(challenge, output):
    ref = read_json(challenge / 'reference.json')
    config = read_json(challenge / 'robot/control.json')
    path = challenge / ref['routes'][0]['model']
    duration = ref['disturbance']['pulse_duration_s']
    forces = []
    for force in ref['force_levels_N']:
        model = mujoco.MjModel.from_xml_path(str(path)); data = mujoco.MjData(model)
        base = model.body('base_link').id
        data.qpos[2] = 3.
        for name, value in zip(config['leg_joint_names'] + config['wheel_joint_names'], config['default_joint_pos']):
            data.qpos[model.jnt_qposadr[model.joint(name).id]] = value
        data.ctrl[:12] = config['default_joint_pos'][:12]
        mujoco.mj_forward(model, data)
        mass = float(model.body_subtreemass[base])
        for _ in range(round(duration / model.opt.timestep)):
            data.xfrc_applied[base, :3] = [force, 0, 0]
            mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data); mujoco.mj_subtreeVel(model, data)
        measured = float(data.subtree_linvel[base, 0]); expected = force * duration / mass
        if not math.isclose(measured, expected, rel_tol=.02, abs_tol=1e-5):
            raise RuntimeError('受力后的质心动量与施力不一致')
        forces.append({'force_N': force, 'duration_s': duration, 'impulse_Ns': force * duration,
                       'expected_velocity_change_mps': expected, 'measured_velocity_change_mps': measured})
    frictions = []
    for mu in ref['friction_levels']:
        model = mujoco.MjModel.from_xml_path(str(path)); data = mujoco.MjData(model)
        for name, value in zip(config['leg_joint_names'] + config['wheel_joint_names'], config['default_joint_pos']):
            data.qpos[model.jnt_qposadr[model.joint(name).id]] = value
        data.ctrl[:12] = config['default_joint_pos'][:12]
        for _ in range(500):
            mujoco.mj_step(model, data)
        set_ground_friction(model, mu); mujoco.mj_forward(model, data)
        values = contact_friction(model, data)
        if not values or any(abs(x-mu) > 1e-8 for x in values):
            raise RuntimeError('轮地实际接触摩擦系数不正确')
        frictions.append({'configured_mu': mu, 'active_contact_mu': values})
    scans = []
    for route in ref['routes']:
        model = mujoco.MjModel.from_xml_path(str(challenge / route['model'])); data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        points = Lidar(model).scan(data)
        if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
            raise RuntimeError('雷达扫描没有产生有效点云')
        scans.append({'route_id': route['id'], 'point_count': len(points), 'maximum_range_m': float(np.linalg.norm(points, axis=1).max())})
    wall = model.geom('wall_0').id; data.qpos[:3] = model.geom_pos[wall]
    mujoco.mj_forward(model, data)
    sampler = MuJoCoSampler(model, root_body='base_link', terrain_geom_names=['floor'],
                           allowed_terrain_body_names=['fl_wheel','fr_wheel','hl_wheel','hr_wheel'], boundary_check=lambda points: False)
    row = sampler.sample(data, action_valid=True)
    wall_contacts = sum(int(int(c.geom1) == wall or int(c.geom2) == wall) for c in data.contact)
    if not wall_contacts or row['forbidden_contacts'] <= 0:
        raise RuntimeError('撞墙没有被正确记录')
    result = {'passed': True, 'mujoco_version': mujoco.__version__, 'robot_mass_kg': mass,
              'forces': forces, 'friction': frictions, 'lidar': scans, 'wall_collision_contacts': wall_contacts}
    write_json(output, result)
    print('Force impulse, four active friction levels, five LiDAR maps and wall collision verified.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--challenge', type=Path, default=Path('challenges/v3'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); check(a.challenge, a.output)
