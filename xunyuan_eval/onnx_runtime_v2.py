"""Execute submitted ONNX models in MuJoCo and on recorded videos."""
import json
import math
import random
import time
from threading import Timer
from pathlib import Path

from .io import FormatError, contained, digest, read_json, write_json

POLICY_INPUTS={'front_rgb':('tensor(float)',[1,3,144,256]),'imu':('tensor(float)',[1,6]),
 'joint_position':('tensor(float)',[1,16]),'joint_velocity':('tensor(float)',[1,16]),
 'previous_action':('tensor(float)',[1,16]),'instructions':('tensor(int64)',[1,11]),'memory':('tensor(float)',[1,128])}
POLICY_OUTPUTS={'action':('tensor(float)',[1,16]),'memory_out':('tensor(float)',[1,128])}
READER_INPUTS={'image':('tensor(float)',[1,3,360,640]),'memory':('tensor(float)',[1,128])}
READER_OUTPUTS={'boxes':('tensor(float)',[1,16,4]),'tokens':('tensor(int64)',[1,16,16]),
 'kinds':('tensor(int64)',[1,16]),'confidence':('tensor(float)',[1,16]),'readable':('tensor(bool)',[1,16]),'memory_out':('tensor(float)',[1,128])}
TOKENS=['']+list('0123456789')+['-','.','+']


class ModelTimeout(FormatError):
    pass


def timed_inference(session, outputs, feed, timeout_s=.5):
    import onnxruntime as ort
    options=ort.RunOptions()
    timer=Timer(timeout_s,setattr,args=(options,'terminate',True))
    timer.daemon=True
    started=time.monotonic();timer.start()
    try:
        values=session.run(outputs,feed,run_options=options)
        if time.monotonic()-started>timeout_s:
            raise ModelTimeout('模型单次推理超时')
        return values
    except ModelTimeout:
        raise
    except Exception as exc:
        if options.terminate:
            raise ModelTimeout('模型单次推理超时') from exc
        raise FormatError('ONNX 模型运行失败：'+str(exc)) from exc
    finally:
        timer.cancel()


def model_session(path,inputs,outputs):
    import onnx
    import onnxruntime as ort
    try:
        graph=onnx.load(str(path),load_external_data=False)
        def tensors(graph):
            yield from graph.initializer
            for node in graph.node:
                for attribute in node.attribute:
                    if attribute.type==onnx.AttributeProto.TENSOR:
                        yield attribute.t
                    elif attribute.type==onnx.AttributeProto.TENSORS:
                        yield from attribute.tensors
                    elif attribute.type==onnx.AttributeProto.GRAPH:
                        yield from tensors(attribute.g)
                    elif attribute.type==onnx.AttributeProto.GRAPHS:
                        for child in attribute.graphs:
                            yield from tensors(child)
        if any(t.data_location==onnx.TensorProto.EXTERNAL for t in tensors(graph.graph)):
            raise FormatError('请把模型和权重导出到一个 ONNX 文件中')
        options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
        session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    except FormatError:
        raise
    except Exception as exc:
        raise FormatError('无法加载 ONNX 模型：'+str(exc)) from exc
    input_names={row.name for row in session.get_inputs()}
    output_names={row.name for row in session.get_outputs()}
    required_inputs={'front_rgb','instructions'} if 'front_rgb' in inputs else {'image'}
    if not required_inputs<=input_names or not input_names<=set(inputs):
        raise FormatError('ONNX 输入名称与 v2 接口不一致')
    if not (set(outputs)-{'memory_out'})<=output_names or not output_names<=set(outputs):
        raise FormatError('ONNX 输出名称与 v2 接口不一致')
    if ('memory' in input_names)!=('memory_out' in output_names):
        raise FormatError('使用记忆时，需要同时提供 memory 和 memory_out')
    if 'memory' in input_names:
        state_in=next(row for row in session.get_inputs() if row.name=='memory')
        state_out=next(row for row in session.get_outputs() if row.name=='memory_out')
        if state_in.shape!=state_out.shape:raise FormatError('记忆输入和输出的大小需要一致')
    for actual,expected in [(session.get_inputs(),inputs),(session.get_outputs(),outputs)]:
        for row in actual:
            kind,shape=expected[row.name]
            if row.name in {'memory','memory_out'}:
                valid=(row.type==kind and len(row.shape)==2 and row.shape[0]==1 and type(row.shape[1]) is int and 1<=row.shape[1]<=8192)
            else:
                valid=row.type==kind and row.shape==shape
            if not valid:
                raise FormatError(f'ONNX {row.name}: 大小或数据类型与接口不一致')
    return session


def initial_memory(session):
    import numpy as np
    size=next((row.shape[1] for row in session.get_inputs() if row.name=='memory'),1)
    return np.zeros((1,size),np.float32)


def check_submission(path):
    path=Path(path);data=read_json(path)
    if not isinstance(data,dict) or data.get('schema_version')!='2.0' or not isinstance(data.get('team'),str) or not data['team'].strip():
        raise FormatError('Submission needs schema_version 2.0 and team')
    root=path.resolve().parent
    files={key:contained(root,data[key]) for key in ['policy','reader','report']}
    if any(files[key].suffix.lower()!='.onnx' for key in ['policy','reader']):raise FormatError('Submit policy and reader as ONNX files')
    with files['report'].open('rb') as stream:
        if stream.read(5)!=b'%PDF-':raise FormatError('Report must be a PDF file')
    if 'sha256' in data:
        if not isinstance(data['sha256'],dict) or any(data['sha256'].get(k)!=digest(p) for k,p in files.items()):
            raise FormatError('提交包中的文件校验值不一致')
    policy=model_session(files['policy'],POLICY_INPUTS,POLICY_OUTPUTS)
    reader=model_session(files['reader'],READER_INPUTS,READER_OUTPUTS)
    return data,files,policy,reader


def contract():
    import copy
    description=copy.deepcopy({'schema_version':'2.0','policy':{'inputs':POLICY_INPUTS,'outputs':POLICY_OUTPUTS},
            'reader':{'inputs':READER_INPUTS,'outputs':READER_OUTPUTS},'text_tokens':TOKENS,
            'instructions':{'left':1,'straight':2,'right':3,'turn_around':4},
            'image_values':'RGB float32, 0 to 1','control_hz':50,'physics_hz':200,'front_camera_hz':10,'video_fps':5,'maximum_inference_s':.5,
            'action':'normalized -1 to 1; first 12 leg position offsets, last 4 wheel speeds',
            'memory':'optional; zero at the start of every route attempt or video',
            'policy_required_inputs':['front_rgb','instructions'],
            'policy_optional_inputs':['imu','joint_position','joint_velocity','previous_action','memory'],
            'reader_optional_inputs':['memory']})
    for part in ['policy','reader']:
        description[part]['inputs']['memory'][1][1]='N'
        description[part]['outputs']['memory_out'][1][1]='N'
    description['memory_size_range']=[1,8192]
    return description


def robot_attempt(session,challenge_root,reference,route,output,force_N=0,max_seconds=None,seed=20261125):
    import cv2
    import mujoco
    import numpy as np
    from .mujoco_recorder import MuJoCoSampler
    from .recorder import TraceRecorder
    from .challenge_v2 import score_route
    challenge_root=Path(challenge_root);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    model=mujoco.MjModel.from_xml_path(str(challenge_root/route['model']));data=mujoco.MjData(model)
    model.vis.map.znear=.01/model.stat.extent
    control=read_json(challenge_root/'robot/control.json')
    names=control['leg_joint_names']+control['wheel_joint_names']
    qadr=[int(model.jnt_qposadr[model.joint(name).id]) for name in names]
    vadr=[int(model.jnt_dofadr[model.joint(name).id]) for name in names]
    defaults=np.asarray(control['default_joint_pos'],dtype=np.float32)
    data.qpos[qadr]=defaults;data.ctrl[:12]=defaults[:12];data.ctrl[12:]=0
    for _ in range(500):mujoco.mj_step(model,data)
    data.time=0.;mujoco.mj_forward(model,data)
    cells={tuple(cell) for cell in route['driveable_cells']};step=route['cell_size_m']
    def outside(points):return any((math.floor(p[0]/step),math.floor(p[1]/step)) not in cells for p in points)
    sampler=MuJoCoSampler(model,root_body='base_link',terrain_geom_names=['floor'],
        allowed_terrain_body_names=['fl_wheel','fr_wheel','hl_wheel','hr_wheel'],boundary_check=outside)
    renderer=mujoco.Renderer(model,144,256)
    option=mujoco.MjvOption();option.geomgroup[1]=0
    policy_inputs={row.name for row in session.get_inputs()}
    policy_outputs=['action']+(['memory_out'] if any(row.name=='memory_out' for row in session.get_outputs()) else [])
    task=read_json(challenge_root/route['task'])
    codes={'left':1,'straight':2,'right':3}
    instructions=np.array([[codes[t['turn']] for t in task['outbound']]+[4]+[codes[t['turn']] for t in task['return']]],np.int64)
    memory=initial_memory(session);previous=np.zeros((1,16),np.float32);image=np.zeros((1,3,144,256),np.float32)
    body=model.body('base_link').id;rows=[];states=[];pulses=[];edge=0;points=route['path_xy']
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])];total=sum(lengths);done_distance=0.
    pulse_start=None;pulse_vector=None;next_pulse=0;frame=-1;inference_count=0;termination='timeout';reason='timeout'
    next_status=1.;base0=data.xpos[body].copy();deadline=min(reference['rules']['timeout_s'],max_seconds) if max_seconds is not None else reference['rules']['timeout_s']
    rng=random.Random(str(seed)+'_'+route['id']+'_'+str(force_N))
    jitter=reference['disturbance'].get('progress_jitter_fraction',.04)
    pulse_positions=[f+rng.uniform(-jitter,jitter) for f in reference['disturbance']['progress_fractions']]
    def sample(legal=True):
        row=sampler.sample(data,action_valid=legal)
        row['position_m']=[round(x,6) for x in row['position_m']]
        row['envelope_points_m']=[[round(x,6) for x in p] for p in row['envelope_points_m']]
        row['force_world_N']=data.xfrc_applied[body,:3].tolist()
        return row
    def summary(row,status):
        return {'time_s':round(row['time_s'],6),'status':status,
                'relative_position_m':[round(float(x),6) for x in data.xpos[body]-base0],
                'roll_rad':round(row['roll_rad'],6),'pitch_rad':round(row['pitch_rad'],6),
                'collision':bool(row['forbidden_contacts'])}
    try:
        with TraceRecorder(output/'physics.jsonl') as recorder:
            row=sample();rows.append(row);recorder.append(row)
            initial_failure=('collision' if row['forbidden_contacts'] else 'out_of_bounds' if row['out_of_bounds'] else
                             'fall' if max(abs(row['roll_rad']),abs(row['pitch_rad']))>reference['rules']['fall_angle_rad'] else None)
            if not initial_failure and math.dist(row['position_m'][:2],points[0])>reference['rules']['start_radius_m']:initial_failure='wrong_start'
            if initial_failure:reason=initial_failure;termination='safety_stop'
            states.append(summary(row,-1 if initial_failure else 0))
            while not initial_failure and data.time<deadline-1e-9:
                if frame%4==3 or frame<0:
                    if inference_count%5==0:
                        renderer.update_scene(data,camera='front',scene_option=option)
                        image=renderer.render().transpose(2,0,1)[None].astype(np.float32)/255
                    rotation=data.xmat[body].reshape(3,3)
                    velocity=np.zeros(6);mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_BODY,body,velocity,0)
                    imu=np.r_[rotation.T@velocity[:3],rotation.T@np.array([0,0,-1])][None].astype(np.float32)
                    feed={'front_rgb':image,'imu':imu,'joint_position':data.qpos[qadr][None].astype(np.float32),
                          'joint_velocity':data.qvel[vadr][None].astype(np.float32),'previous_action':previous,
                          'instructions':instructions,'memory':memory}
                    try:
                        values=timed_inference(session,policy_outputs,{key:value for key,value in feed.items() if key in policy_inputs})
                        action=values[0];memory_out=values[1] if len(values)>1 else memory
                    except ModelTimeout:
                        reason='model_timeout';termination='crashed';break
                    except FormatError:
                        reason='model_error';termination='crashed';break
                    legal=np.isfinite(action).all() and np.isfinite(memory_out).all() and np.max(np.abs(action))<=1.00001
                    if not legal:
                        row=sample(False)
                        # Keep a strictly increasing final timestamp.
                        mujoco.mj_step(model,data);mujoco.mj_forward(model,data);row=sample(False)
                        rows.append(row);recorder.append(row);reason='illegal_action';termination='safety_stop';break
                    previous=action.astype(np.float32);memory=memory_out.astype(np.float32)
                    data.ctrl[:12]=defaults[:12]+action[0,:12]*np.asarray(control['leg_scale'])
                    data.ctrl[12:]=action[0,12:]*control['wheel_scale'];inference_count+=1
                position=data.xpos[body,:2]
                if edge<len(points)-1 and math.dist(position,points[edge+1])<=reference['rules']['checkpoint_radius_m']:
                    done_distance+=lengths[edge];edge+=1
                progress=done_distance
                if edge<len(lengths):
                    v=np.array(points[edge+1])-points[edge]
                    progress+=float(np.clip((position-np.array(points[edge]))@v/(v@v),0,1))*lengths[edge]
                if force_N and pulse_start is None and next_pulse<3 and progress/total>=pulse_positions[next_pulse]:
                    pulse_start=float(data.time);rotation=data.xmat[body].reshape(3,3)
                    direction=rotation[:2,1].copy();direction/=np.linalg.norm(direction)
                    pulse_vector=np.r_[direction*rng.choice([-1,1])*force_N,0.]
                    pulses.append({'start_s':pulse_start,'force_world_N':pulse_vector.tolist(),'duration_s':0.})
                    next_pulse+=1
                data.xfrc_applied[body]=0.
                if pulse_start is not None:
                    if data.time-pulse_start<reference['disturbance']['pulse_duration_s']-1e-9:
                        data.xfrc_applied[body,:3]=pulse_vector;pulses[-1]['duration_s']+=model.opt.timestep
                    else:pulse_start=None
                mujoco.mj_step(model,data);mujoco.mj_forward(model,data);frame+=1
                row=sample();rows.append(row);recorder.append(row)
                failure=('collision' if row['forbidden_contacts'] else 'out_of_bounds' if row['out_of_bounds'] else
                         'fall' if max(abs(row['roll_rad']),abs(row['pitch_rad']))>reference['rules']['fall_angle_rad'] else None)
                reached=edge==len(points)-1
                if data.time+1e-9>=next_status or failure or reached:
                    states.append(summary(row,-1 if failure else 1 if reached else 0))
                    next_status=math.floor(data.time+1e-8)+1
                if failure:reason=failure;termination='safety_stop';break
                if reached:reason='completed';termination='completed';break
    finally:renderer.close()
    final=summary(rows[-1],1 if termination=='completed' else -1)
    if states and abs(states[-1]['time_s']-final['time_s'])<1e-8:
        states[-1]=final
    else:
        states.append(final)
    write_json(output/'states.json',{'states':states,'termination':termination,'reason':reason})
    write_json(output/'forces.json',{'force_N':force_N,'pulses':pulses})
    judged=score_route(rows,route,reference['rules'],termination)
    if force_N and (len(pulses)!=3 or any(abs(p['duration_s']-reference['disturbance']['pulse_duration_s'])>1e-8 for p in pulses)):
        judged['passed']=False
    judged['runtime_reason']=reason
    write_json(output/'result.json',judged)
    return {'route_id':route['id'],'force_N':force_N,'termination':termination,'trace':str((output/'physics.jsonl').resolve()),
            'force_record':str((output/'forces.json').resolve()),'result':judged}


def recognize_videos(session,videos_root,manifest,output,split='test',video_id=None):
    import cv2
    import numpy as np
    reader_inputs={row.name for row in session.get_inputs()}
    reader_outputs=[key for key in READER_OUTPUTS if any(row.name==key for row in session.get_outputs())]
    detections=[]
    selected=[v for v in manifest['videos'] if v['id'].startswith(split) and (video_id is None or v['id']==video_id)]
    if not selected:raise FormatError('没有找到指定的视频')
    for item in selected:
        path=contained(Path(videos_root)/split,item['file'])
        if digest(path)!=item['sha256']:raise FormatError('视频文件校验值不一致')
        cap=cv2.VideoCapture(str(path));fps=cap.get(cv2.CAP_PROP_FPS);index=0
        memory=initial_memory(session)
        if not cap.isOpened() or fps<=0:raise FormatError('Cannot read test video')
        while True:
            ok,frame=cap.read()
            if not ok:break
            image=cv2.cvtColor(cv2.resize(frame,(640,360)),cv2.COLOR_BGR2RGB).transpose(2,0,1)[None].astype(np.float32)/255
            feed={'image':image,'memory':memory}
            values=timed_inference(session,reader_outputs,{key:value for key,value in feed.items() if key in reader_inputs})
            boxes,tokens,kinds,confidence,readable=values[:5]
            memory_out=values[5] if len(values)>5 else memory
            if not np.isfinite(memory_out).all():raise FormatError('Invalid reader memory')
            memory=memory_out.astype(np.float32)
            if not np.isfinite(boxes).all() or not np.isfinite(confidence).all():raise FormatError('Non-finite reader output')
            for k in range(16):
                kind=int(kinds[0,k]);conf=float(confidence[0,k])
                if kind==0 or conf<.5:continue
                if kind not in {1,2} or not 0<=conf<=1:raise FormatError('Invalid reader class or confidence')
                token_ids=tokens[0,k].tolist()
                if any(t<0 or t>=len(TOKENS) for t in token_ids):raise FormatError('Invalid text token')
                end=token_ids.index(0) if 0 in token_ids else len(token_ids)
                value=''.join(TOKENS[t] for t in token_ids[:end])
                detection={'video_id':item['id'],'time_s':index/fps,'box_xyxy':boxes[0,k].astype(float).tolist(),
                           'confidence':conf,'status':'ok' if readable[0,k] else 'abstain'}
                if readable[0,k]:detection.update(value=value,unit='C' if kind==2 else None)
                else:detection['reason']='display_unreadable'
                detections.append(detection)
            index+=1
        cap.release()
        if index!=round(item['duration_s']*item['fps']) or abs(fps-item['fps'])>1e-6:
            raise FormatError('视频帧数或帧率与清单不一致')
    write_json(output,{'detections':detections})
    return output


def run_submission(submission,challenge,output,videos=None,video_reference=None,route_id=None,max_seconds=None,seed=20261125):
    from .challenge_v2 import evaluate,validate_reference,validate_video_reference
    if max_seconds is not None and (not math.isfinite(max_seconds) or max_seconds<=0):
        raise FormatError('试跑时长必须大于 0')
    if bool(videos)!=bool(video_reference):
        raise FormatError('评测视频时，请同时提供视频目录和答案文件')
    challenge=Path(challenge);output=Path(output)
    reference=validate_reference(read_json(challenge/'reference.json'))
    selected=[r for r in reference['routes'] if route_id is None or r['id']==route_id]
    if not selected:raise FormatError('Unknown route')
    truth=None;manifest=None;video_hashes={}
    if videos:
        truth=validate_video_reference(read_json(video_reference))
        manifest=read_json(Path(videos)/'manifest.json')
        test_items=[v for v in manifest['videos'] if v['id'].startswith('test')]
        ids={v['id'] for v in test_items}
        if len(test_items)!=2 or len(ids)!=2 or len(truth['events'])!=24:
            raise FormatError('完整识别测评需要两段测试视频、24个标牌答案')
        if {e['video_id'] for e in truth['events']}!=ids or any(sum(e['video_id']==vid for e in truth['events'])!=12 for vid in ids):
            raise FormatError('测试视频与答案编号不一致')
        for item in test_items:
            path=contained(Path(videos)/'test',item['file'])
            if digest(path)!=item['sha256']:raise FormatError('测试视频校验值不一致')
        video_hashes={'video_manifest':digest(Path(videos)/'manifest.json'),'video_reference':digest(video_reference)}
    submission,files,policy,reader=check_submission(submission)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'reference.json',reference)
    run={'schema_version':'2.0','reference_id':reference['reference_id'],'team':submission['team'],'routes':[],'disturbance':[],
         'model_sha256':{k:digest(files[k]) for k in ['policy','reader']},'seed':seed,
         'submission_sha256':{k:digest(v) for k,v in files.items()},
         'input_sha256':dict(video_hashes,reference=digest(output/'reference.json'))}
    for route in selected:
        normal=robot_attempt(policy,challenge,reference,route,output/route['id']/'normal',max_seconds=max_seconds,seed=seed)
        normal['trace']=str(Path(normal['trace']).relative_to(output.resolve()))
        normal.pop('result');normal.pop('force_record');normal.pop('force_N')
        run['routes'].append(normal)
        for force in reference['force_levels_N']:
            attempt=robot_attempt(policy,challenge,reference,route,output/route['id']/f'force_{force}',force,max_seconds,seed)
            passed=attempt['result']['passed'];attempt.pop('result')
            for key in ['trace','force_record']:
                attempt[key]=str(Path(attempt[key]).relative_to(output.resolve()))
            run['disturbance'].append(attempt)
            if not passed:break
    if videos:
        try:
            path=recognize_videos(reader,videos,manifest,output/'video_predictions.json')
        except (FormatError,OSError) as exc:
            path=output/'video_predictions.json'
            write_json(path,{'detections':[]});run['video_error']=str(exc)
        run['video_predictions']=path.name
    write_json(output/'run.json',run)
    report=evaluate(run,reference,output,truth)
    report['model_sha256']=run['model_sha256'];report['seed']=seed
    report['input_sha256']=run['input_sha256'];report['submission_sha256']=run['submission_sha256']
    if run.get('video_error'):report['video_error']=run['video_error']
    write_json(output/'report.json',report)
    return report


def package_models(submission_path,output):
    import zipfile
    submission,files,_,_=check_submission(submission_path)
    output=Path(output)
    if output.exists():raise FormatError('Choose a new package filename')
    manifest={'schema_version':'2.0','team':submission['team'],'policy':'policy.onnx','reader':'reader.onnx','report':'report.pdf',
              'sha256':{key:digest(path) for key,path in files.items()}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for key,path in files.items():archive.write(path,manifest[key])
        archive.writestr('submission.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return {'package':str(output),'sha256':digest(output)}
