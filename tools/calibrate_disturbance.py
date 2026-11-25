"""Measure descending pushes and ground friction using a trained S10 controller."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

from xunyuan_eval.io import digest, read_json, write_json
from xunyuan_eval.sensors import contact_friction, set_ground_friction


class Controller:
    def __init__(self, policy, metadata):
        self.meta = read_json(metadata)
        if self.meta.get('actor_schema') != 's10-v7-53':
            raise ValueError('此校准适配器使用 s10-v7-53 控制器')
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(str(policy), sess_options=options, providers=['CPUExecutionProvider'])
        self.defaults = np.asarray(self.meta['default_joint_pos'], np.float32)
        self.reset()

    def reset(self):
        self.history = np.zeros((1, self.meta['observation_dim']), np.float32)
        self.previous = np.zeros((1, 16), np.float32)
        self.fresh = True

    def action(self, model, data, body, qadr, vadr, speed):
        rotation = data.xmat[body].reshape(3, 3)
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0)
        frame = np.concatenate((rotation.T @ velocity[:3], rotation.T @ np.array([0, 0, -1]),
            data.qpos[qadr][:12] - self.defaults[:12], data.qvel[vadr][:12] * .05,
            data.qvel[vadr][12:] * .05, self.previous[0], [speed, 0, 0])).astype(np.float32)
        hi = fi = 0
        for term in self.meta['frame_terms']:
            n = term['dim']; block = self.history[:, hi:hi + n * self.meta['history']]
            if self.fresh:
                block[:] = np.tile(frame[fi:fi+n], (1, self.meta['history']))
            else:
                block[:, :-n] = block[:, n:].copy(); block[:, -n:] = frame[fi:fi+n]
            hi += n * self.meta['history']; fi += n
        self.fresh = False
        action = self.session.run(['actions'], {'obs': self.history})[0]
        if action.shape != (1, 16) or not np.isfinite(action).all() or np.max(np.abs(action)) > 1.00001:
            raise ValueError('控制器输出无效')
        self.previous[:] = action
        return action[0]


def trial(challenge, controller, force, friction, side, start, duration=.5, speed=.4):
    model = mujoco.MjModel.from_xml_path(str(challenge / 'maps/map01.xml'))
    data = mujoco.MjData(model)
    config = read_json(challenge / 'robot/control.json')
    names = config['leg_joint_names'] + config['wheel_joint_names']
    qadr = [model.jnt_qposadr[model.joint(n).id] for n in names]
    vadr = [model.jnt_dofadr[model.joint(n).id] for n in names]
    base = model.body('base_link').id
    data.qpos[qadr] = config['default_joint_pos']; data.qpos[2] = .44
    data.ctrl[:12] = config['default_joint_pos'][:12]
    for _ in range(200):
        mujoco.mj_step(model, data)
    data.time = 0.; mujoco.mj_forward(model, data)
    set_ground_friction(model, friction)
    controller.reset()
    maximum_tilt = deviation = impulse = pre_tilt = 0.
    observed_mu = set(); reason = None; rows = []
    # Freeze a lateral world direction at the start, matching a push from one side.
    direction = np.array([0., float(side), 0.])
    for i in range(round(7 / model.opt.timestep)):
        if i % 4 == 0:
            action = controller.action(model, data, base, qadr, vadr, speed)
            data.ctrl[:12] = controller.defaults[:12] + action[:12] * np.asarray(config['leg_scale'])
            data.ctrl[12:] = action[12:] * config['wheel_scale']
        data.xfrc_applied[base] = 0
        if start-1e-9 <= data.time < start + duration-1e-9:
            data.xfrc_applied[base, :3] = direction * force
            impulse += force * model.opt.timestep
        mujoco.mj_step(model, data); mujoco.mj_forward(model, data)
        tilt = math.acos(float(np.clip(data.xmat[base].reshape(3, 3)[2, 2], -1, 1)))
        rotation = data.xmat[base].reshape(3, 3)
        roll = math.atan2(float(rotation[2, 1]), float(rotation[2, 2]))
        pitch = math.asin(float(np.clip(-rotation[2, 0], -1, 1)))
        maximum_tilt = max(maximum_tilt, tilt)
        deviation = max(deviation, abs(float(data.xpos[base, 1])))
        mus = contact_friction(model, data)
        observed_mu.update(round(mu, 6) for mu in mus)
        if any(abs(mu-friction) > 1e-7 for mu in mus):
            raise ValueError('实际接触摩擦与目标值不一致')
        if data.time < start:
            pre_tilt = max(pre_tilt, tilt)
        # Capacity probes continue past a competition boundary violation, to measure recovery/fall.
        rows.append({'time_s': round(float(data.time), 6), 'position_m': data.xpos[base].tolist(),
                     'tilt_deg': math.degrees(tilt), 'force_world_N': data.xfrc_applied[base, :3].tolist()})
        if max(abs(roll), abs(pitch)) > math.pi / 4:
            reason = 'fall'; break
    if reason is None and deviation > .5:
        reason = 'path_deviation'
    return {'force_N': force, 'friction': friction, 'side': side, 'push_start_s': start,
            'pulse_duration_s': duration, 'impulse_applied_Ns': impulse,
            'command_speed_mps': speed, 'survived': reason is None, 'failure': reason,
            'elapsed_s': float(data.time), 'maximum_tilt_deg': math.degrees(maximum_tilt),
            'maximum_lateral_deviation_m': deviation, 'pre_push_maximum_tilt_deg': math.degrees(pre_tilt),
            'final_position_m': data.xpos[base].tolist(), 'observed_contact_friction': sorted(observed_mu)}, rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--policy', type=Path, required=True)
    p.add_argument('--metadata', type=Path)
    p.add_argument('--challenge', type=Path, default=Path('challenges/v2'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('请使用新的校准输出目录')
    a.output.mkdir(parents=True)
    metadata = a.metadata or a.policy.with_suffix('.json')
    controller = Controller(a.policy, metadata)
    records = []
    force_grid = [200, 160, 120, 100, 80, 60, 40, 20, 5, 0]
    for force in force_grid:
        for side in [-1, 1]:
            for start in [2.5, 3., 3.5]:
                result, rows = trial(a.challenge, controller, force, .8, side, start)
                name = f'force_{force}_side_{side}_start_{start}.jsonl'
                with (a.output / name).open('w') as stream:
                    for row in rows:
                        stream.write(json.dumps(row) + '\n')
                result['trace'] = name; records.append(result)
        subset = [r for r in records if r['force_N'] == force]
        print('force', force, 'survived', sum(r['survived'] for r in subset), '/', len(subset), flush=True)
    friction_records = []
    for mu in [.1, .2, .4, .8]:
        for start in [2.5, 3., 3.5]:
            result, rows = trial(a.challenge, controller, 0, mu, 1, start)
            name = f'friction_{mu}_repeat_{start}.jsonl'
            with (a.output / name).open('w') as stream:
                for row in rows:
                    stream.write(json.dumps(row) + '\n')
            result['trace'] = name; friction_records.append(result)
        subset = [r for r in friction_records if r['friction'] == mu]
        print('friction', mu, 'survived', sum(r['survived'] for r in subset), '/', len(subset), flush=True)
    effects = []
    for mu in [.1, .2, .4, .8]:
        for side in [-1, 1]:
            result, rows = trial(a.challenge, controller, 40, mu, side, 3.)
            name = f'friction_effect_{mu}_side_{side}.jsonl'
            with (a.output / name).open('w') as stream:
                for row in rows:
                    stream.write(json.dumps(row) + '\n')
            result['trace'] = name; effects.append(result)
    baseline = [r for r in records if r['force_N'] == 0]
    if not all(r['survived'] for r in baseline):
        raise ValueError('无推力对照未通过，不能据此确定推力上限')
    # The cap is the lowest tested force that fails every repeated baseline probe.
    failures = [f for f in force_grid if f and not any(r['survived'] for r in records if r['force_N'] == f)]
    maximum = min(failures) if failures else max(force_grid)
    result = {'schema_version': '3.0', 'controller_sha256': digest(a.policy),
        'metadata_sha256': digest(metadata), 'robot_mass_kg': 18.987425,
        'mujoco_version': mujoco.__version__, 'command_speed_mps': .4, 'pulse_duration_s': .5,
        'force_scan_descending_N': force_grid, 'trials_per_force': 6,
        'calibration_cap_N': maximum, 'cap_definition': 'lowest tested force at which all six baseline probes fail',
        'baseline_all_passed': True, 'push_trials': records, 'friction_trials': friction_records,
        'friction_effect_diagnostic': effects, 'calibration_tool_sha256': digest(Path(__file__)),
        'friction_effect_method': 'same 40 N push on each ground; diagnostic separate from friction scoring',
        'trace_sha256': {r['trace']: digest(a.output / r['trace']) for r in records + friction_records + effects}}
    write_json(a.output / 'calibration.json', result)
    print('calibration cap', maximum, 'N', flush=True)


if __name__ == '__main__':
    main()
