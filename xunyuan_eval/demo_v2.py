"""Generate ideal route records for trying the v2 scoring commands."""
import copy
import math
from pathlib import Path
from .demo import sample
from .io import read_json,write_json
from .recorder import TraceRecorder


def rows_for_route(route):
    rows=[sample(0,*route['path_xy'][0])]
    index=0
    for a,b in zip(route['path_xy'],route['path_xy'][1:]):
        n=max(1,math.ceil(math.dist(a,b)/.015))
        for i in range(1,n+1):
            index+=1;u=i/n
            rows.append(sample(index*.005,a[0]+u*(b[0]-a[0]),y=a[1]+u*(b[1]-a[1]),speed=3))
    return rows


def create_demo(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    reference=read_json(root/'challenges/v2/reference.json')
    duration=reference['disturbance']['pulse_duration_s']
    run={'schema_version':'2.0','reference_id':reference['reference_id'],'team':'scoring-example','routes':[],'disturbance':[],
         'video_predictions':'video_predictions.json'}
    for route in reference['routes']:
        base=rows_for_route(route)
        for force in [0]+reference['force_levels_N']:
            name=f'traces/{route["id"]}_{force}.jsonl'
            with TraceRecorder(output/name) as recorder:
                for original in base:
                    row=copy.deepcopy(original)
                    active=any(start+1e-9<row['time_s']<=start+duration+1e-9 for start in [1.,3.,5.])
                    row['force_world_N']=[0,force if active else 0,0]
                    recorder.append(row)
            item={'route_id':route['id'],'termination':'completed','trace':name}
            if force:
                item.update(force_N=force,force_record=f'forces/{route["id"]}_{force}.json')
                write_json(output/item['force_record'],{'force_N':force,'pulses':[{'start_s':start,'duration_s':duration,'force_world_N':[0,force,0]} for start in [1.,3.,5.]]})
                run['disturbance'].append(item)
            else:run['routes'].append(item)
    events=[];detections=[]
    for video in ['test01','test02']:
        for i in range(12):
            identity=f'{video}/E{i+1:02d}';t=i*3+1
            event={'id':identity,'video_id':video,'start_s':t,'end_s':t+1,'readable':True,
                   'kind':'digits' if i<6 else 'temperature_display','answer':'00127' if i<6 else '31.4',
                   'boxes':[{'time_s':t,'box_xyxy':[.4,.4,.6,.6]}]}
            events.append(event)
            detections.append({'video_id':video,'time_s':t,'box_xyxy':[.4,.4,.6,.6],'status':'ok','confidence':1,
                               'value':event['answer'],'unit':None if i<6 else 'C'})
    write_json(output/'video_reference.json',{'events':events,'temperature_tolerance_C':'.1'})
    write_json(output/'video_predictions.json',{'detections':detections})
    write_json(output/'reference.json',reference);write_json(output/'run.json',run)
    return output/'run.json'
