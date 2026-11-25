"""Check S10 collision sampling and four physical force levels."""
import argparse
import math
from pathlib import Path
import numpy as np
import mujoco
from xunyuan_eval.io import read_json,write_json
from xunyuan_eval.mujoco_recorder import MuJoCoSampler


def check(challenge,output):
    control=read_json(challenge/'robot/control.json')
    reference=read_json(challenge/'reference.json');route=reference['routes'][0]
    path=challenge/route['model'];forces=[]
    for force in reference['force_levels_N']:
        model=mujoco.MjModel.from_xml_path(str(path));data=mujoco.MjData(model)
        root=model.body('base_link').id
        data.qpos[2]=3.
        names=control['leg_joint_names']+control['wheel_joint_names']
        for name,value in zip(names,control['default_joint_pos']):data.qpos[model.jnt_qposadr[model.joint(name).id]]=value
        data.ctrl[:12]=control['default_joint_pos'][:12]
        mujoco.mj_forward(model,data)
        mass=float(model.body_subtreemass[root]);steps=round(.2/model.opt.timestep)
        for _ in range(steps):
            data.xfrc_applied[root,:3]=[force,0,0]
            mujoco.mj_step(model,data)
        mujoco.mj_forward(model,data);mujoco.mj_subtreeVel(model,data)
        measured=float(data.subtree_linvel[root,0]);expected=force*.2/mass
        if not math.isclose(measured,expected,rel_tol=.02,abs_tol=1e-5):
            raise RuntimeError('Applied force does not match measured momentum')
        forces.append({'force_N':force,'duration_s':.2,'impulse_Ns':force*.2,
                       'expected_center_of_mass_velocity_mps':expected,'measured_center_of_mass_velocity_mps':measured})
    model=mujoco.MjModel.from_xml_path(str(path));data=mujoco.MjData(model)
    wall=model.geom('wall_0').id;data.qpos[:3]=model.geom_pos[wall]
    mujoco.mj_forward(model,data)
    sampler=MuJoCoSampler(model,root_body='base_link',terrain_geom_names=['floor'],
        allowed_terrain_body_names=['fl_wheel','fr_wheel','hl_wheel','hr_wheel'],boundary_check=lambda points:False)
    row=sampler.sample(data,action_valid=True)
    wall_contacts=sum(int(int(c.geom1)==wall or int(c.geom2)==wall) for c in data.contact)
    if row['forbidden_contacts']<=0 or wall_contacts<=0:raise RuntimeError('Wall collision was not recorded')
    result={'passed':True,'robot':'S10','mujoco_version':mujoco.__version__,'forces':forces,
            'wall_collision_contacts':wall_contacts,'forbidden_contacts':row['forbidden_contacts']}
    write_json(output,result);print(result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--challenge',type=Path,default=Path('challenges/v2'))
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();check(a.challenge,a.output)
