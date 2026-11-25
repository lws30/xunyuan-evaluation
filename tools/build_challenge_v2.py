"""Build five MuJoCo maps, route tasks, and drawing previews."""
from pathlib import Path
import argparse
import copy
import json
import math
import random
import shutil
import xml.etree.ElementTree as ET


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def build(output,robot_source,seed=None):
    output.mkdir(parents=True,exist_ok=True)
    robot=output/'robot';robot.mkdir(exist_ok=True)
    if robot_source.resolve()!=robot.resolve():
        shutil.copy2(robot_source/'s10_source.xml',robot/'s10_source.xml')
        shutil.copytree(robot_source/'meshes',robot/'meshes',dirs_exist_ok=True)
        for filename in ['LICENSE-BSD-3-Clause.txt','source.json']:
            if (robot_source/filename).exists():shutil.copy2(robot_source/filename,robot/filename)
    metadata=robot_source/('control_reference.json' if (robot_source/'control_reference.json').exists() else 'control.json')
    meta=json.loads(metadata.read_text())
    control={key:meta[key] for key in ['leg_joint_names','wheel_joint_names','default_joint_pos','leg_scale','wheel_scale','wheel_clip']}
    write(robot/'control.json',control)
    sequences=[['left','straight','right','left','right'],['straight','straight','left','right','left'],
               ['right','left','straight','right','straight'],['left','right','right','straight','left'],
               ['straight','left','right','left','straight']]
    routes=[]
    for k,turns in enumerate(sequences,1):
        rid=f'map{k:02d}';rng=random.Random(str(seed)+'_'+rid);heading=0.; current=[0.,0.]; path=[current.copy()];sections=[];roads=[];junctions=[]
        for i,turn in enumerate(turns):
            length=6 if seed is None else rng.uniform(5,8)
            node=[current[0]+length*math.cos(heading),current[1]+length*math.sin(heading)]
            kind='Y' if turn!='straight' and (i+k)%2==0 else 'T'
            amount=math.pi/4 if kind=='Y' else math.pi/2
            new_heading=heading+({'left':amount,'right':-amount,'straight':0}[turn])
            exit_point=[node[0]+1.8*math.cos(new_heading),node[1]+1.8*math.sin(new_heading)]
            roads.append([current.copy(),node.copy()])
            path.extend([node.copy(),exit_point.copy()]);sections.extend([i,i])
            alternate=heading+(-amount if turn=='left' else amount)
            branch=[node[0]+3*math.cos(alternate),node[1]+3*math.sin(alternate)]
            roads.append([node.copy(),branch])
            roads.append([node.copy(),exit_point.copy()])
            junctions.append({'id':f'J{i+1:02d}','kind':kind,'turn':turn,'center_xy':node,'exit_xy':exit_point})
            current=exit_point;heading=new_heading
        goal=[current[0]+3*math.cos(heading),current[1]+3*math.sin(heading)]
        roads.append([current.copy(),goal.copy()]);path.append(goal);sections.append(5)
        outbound=copy.deepcopy(path)
        path.extend(copy.deepcopy(outbound[-2::-1]));sections.extend([5]*(len(outbound)-1))
        reverse=[{'left':'right','right':'left','straight':'straight'}[turn] for turn in turns[::-1]]
        task={'schema_version':'2.0','route_id':rid,'front_camera':'front','right_camera':'right',
              'outbound':[{'junction':f'J{i+1:02d}','turn':turn} for i,turn in enumerate(turns)],
              'at_end':'turn_around','return':[{'junction':f'J{5-i:02d}','turn':turn} for i,turn in enumerate(reverse)],
              'finish':'return_to_start','timeout_s':600}
        write(output/'tasks'/f'{rid}.json',task)
        # Grid boundaries produce solid corridor walls around the union of all roads.
        step=.5;width=1.5
        def distance(p,a,b):
            d=[b[0]-a[0],b[1]-a[1]];norm=d[0]**2+d[1]**2
            t=max(0,min(1,((p[0]-a[0])*d[0]+(p[1]-a[1])*d[1])/norm))
            return math.hypot(p[0]-a[0]-t*d[0],p[1]-a[1]-t*d[1])
        all_points=[p for road in roads for p in road]
        lo=[math.floor((min(p[j] for p in all_points)-2)/step) for j in range(2)]
        hi=[math.ceil((max(p[j] for p in all_points)+2)/step) for j in range(2)]
        cells=set()
        for x in range(lo[0],hi[0]+1):
            for y in range(lo[1],hi[1]+1):
                p=[(x+.5)*step,(y+.5)*step]
                if min(distance(p,*road) for road in roads)<=width/2 or any(math.dist(p,j['center_xy'])<1.25 for j in junctions):
                    cells.add((x,y))
        root=ET.parse(robot/'s10_source.xml').getroot();root.set('model',rid)
        for compiler in root.findall('compiler'):
            if 'meshdir' in compiler.attrib:compiler.set('meshdir','../robot/meshes')
        ET.SubElement(root,'option',timestep='.005',gravity='0 0 -9.81',integrator='implicitfast',cone='elliptic',impratio='10')
        vis=ET.SubElement(root,'visual');ET.SubElement(vis,'global',offwidth='640',offheight='360')
        ET.SubElement(vis,'headlight',ambient='.5 .5 .5',diffuse='.7 .7 .7')
        world=root.find('worldbody')
        ET.SubElement(world,'light',pos='0 0 8',directional='true',dir='0 0 -1',castshadow='false')
        ET.SubElement(world,'geom',name='floor',type='plane',size='80 80 .1',rgba='.27 .3 .3 1',friction='.8 .01 .001')
        base=world.find("body[@name='base_link']")
        ET.SubElement(base,'camera',name='front',pos='.28 0 .12',xyaxes='0 -1 0 0 0 1',fovy='70')
        ET.SubElement(base,'camera',name='right',pos='0 -.18 .12',xyaxes='-1 0 0 0 0 1',fovy='70')
        wall_id=0
        for x,y in sorted(cells):
            for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                if (x+dx,y+dy) in cells:continue
                cx=(x+.5+.5*dx)*step;cy=(y+.5+.5*dy)*step
                size=[.035,step/2,.65] if dx else [step/2,.035,.65]
                ET.SubElement(world,'geom',name=f'wall_{wall_id}',type='box',pos=f'{cx} {cy} .65',size=' '.join(map(str,size)),rgba='.55 .58 .6 1',friction='.6 .01 .001')
                wall_id+=1
        for name,p,color in [('start',path[0],'.1 .75 .2 1'),('turnaround',goal,'.95 .65 .05 1')]:
            ET.SubElement(world,'geom',name=name,type='cylinder',pos=f'{p[0]} {p[1]} .003',size='.35 .003',rgba=color,contype='0',conaffinity='0')
        actuator=ET.SubElement(root,'actuator')
        for name in control['leg_joint_names']:
            ET.SubElement(actuator,'position',name='act_'+name,joint=name,kp='20',kv='2',forcelimited='true',forcerange='-50 50')
        for name in control['wheel_joint_names']:
            ET.SubElement(actuator,'velocity',name='act_'+name,joint=name,kv='.8',forcelimited='true',forcerange='-14 14')
        path_xml=output/'maps'/f'{rid}.xml';path_xml.parent.mkdir(exist_ok=True)
        ET.indent(root);ET.ElementTree(root).write(path_xml,encoding='unicode')
        route={'id':rid,'model':f'maps/{rid}.xml','task':f'tasks/{rid}.json','path_xy':path,'section_for_edge':sections,
               'junctions':junctions,'cell_size_m':step,'driveable_cells':[list(cell) for cell in sorted(cells)],'spawn_xy':[0.,0.],
               'road_segments':roads,'outbound_turns':turns,'return_turns':reverse}
        routes.append(route)
        # SVG map shares exactly the centerlines used to build the physical map.
        scale=24;pad=50;xmin=lo[0]*step;ymax=hi[1]*step
        w=int((hi[0]-lo[0]+1)*step*scale+2*pad);h=int((hi[1]-lo[1]+1)*step*scale+2*pad)
        xy=lambda p:(pad+(p[0]-xmin)*scale,pad+(ymax-p[1])*scale)
        svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="#f5f6f7"/>']
        for x,y in cells:
            a,b=xy([x*step,(y+1)*step]);svg.append(f'<rect x="{a}" y="{b}" width="{step*scale}" height="{step*scale}" fill="#d7dce0"/>')
        polygon=' '.join(f'{a},{b}' for a,b in map(xy,outbound))
        svg.append(f'<polyline points="{polygon}" fill="none" stroke="#2468c4" stroke-width="3"/>')
        for j in junctions:
            a,b=xy(j['center_xy']);svg.append(f'<circle cx="{a}" cy="{b}" r="5" fill="#2468c4"/><text x="{a+8}" y="{b-8}" font-family="sans-serif" font-size="12">{j["id"]} {j["kind"]}: {j["turn"]}</text>')
        for label,p,color in [('START / RETURN',path[0],'#198539'),('TURN AROUND',goal,'#bd6e00')]:
            a,b=xy(p);svg.append(f'<circle cx="{a}" cy="{b}" r="6" fill="{color}"/><text x="{a+8}" y="{b+18}" font-family="sans-serif" font-size="12">{label}</text>')
        svg.append(f'<text x="20" y="25" font-family="sans-serif" font-size="18">{rid}: 5 junctions + return</text></svg>')
        (output/'maps'/f'{rid}.svg').write_text(''.join(svg))
    reference={'schema_version':'2.0','reference_id':'xunyuan-v2-five-routes-20261125' if seed is None else f'xunyuan-v2-five-routes-seed-{seed}',
        'weights':{'route':30,'disturbance':20,'recognition':20,'report':30},'force_levels_N':[.5,1,3,5],
        'disturbance':{'pulses_per_attempt':3,'pulse_duration_s':.2,'application_point':'base_center_of_mass','direction':'random_left_or_right',
                       'progress_fractions':[.2,.45,.7],'progress_jitter_fraction':.04},
        'rules':{'timeout_s':600,'sample_dt_s':.005,'max_gap_s':.0075,'start_radius_m':.4,'checkpoint_radius_m':.3,
                 'maximum_speed_mps':4,'step_position_slack_m':.01,'fall_angle_rad':math.pi/4,'disturbance_path_limit_m':.5,
                 'deviation_bands':[{'distance_m':.15,'credit':1},{'distance_m':.3,'credit':.75},{'distance_m':.5,'credit':.5}]},'routes':routes}
    write(output/'reference.json',reference)
    write(output/'submission.example.json',{'schema_version':'2.0','team':'your-team','policy':'policy.onnx','reader':'reader.onnx','report':'report.pdf'})
    print('Built five maps and tasks in',output)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('challenges/v2'))
    p.add_argument('--robot-source',type=Path,default=Path('challenges/v2/robot'));p.add_argument('--seed',type=int,help='随机调整直道路段长度');a=p.parse_args();build(a.output,a.robot_source,a.seed)
