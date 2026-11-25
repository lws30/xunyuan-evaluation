"""Generate right-camera reading videos and their training labels."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse
import hashlib
import json
import math
import random
import secrets
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH,HEIGHT,FPS=640,360,5
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'


def content(seed,custom=None):
    rng=random.Random(seed)
    conditions=['clear']+['blur']*4+['motion']*3+['partial']*2+['unreadable']*2
    rng.shuffle(conditions)
    events=[]
    camera_height=rng.uniform(.65,.78);lookahead=rng.uniform(.15,.45)
    for i,condition in enumerate(conditions):
        kind='digits' if i<6 else 'temperature_display'
        value=(rng.choice(['','-'])+f'{rng.randrange(100000):05d}') if kind=='digits' else f'{rng.randrange(-200,1201)/10:.1f}'
        if custom is not None:
            item=custom[i];kind=item['kind'];value=item['value']
        im=Image.new('RGB',(256,96),'#d7d2bc');draw=ImageDraw.Draw(im)
        draw.rectangle((2,2,253,93),outline='#746f61',width=2)
        text=value+(' C' if kind!='digits' else '')
        font=ImageFont.truetype(FONT,36)
        bounds=draw.textbbox((0,0),text,font=font)
        draw.text(((256-(bounds[2]-bounds[0]))/2,48-(bounds[3]-bounds[1])/2-bounds[1]),text,font=font,fill='#252421')
        if condition=='unreadable':
            draw.rectangle((12,15,244,82),fill='#8d8981')
        elif condition=='partial':
            draw.rectangle((10,47,246,51),fill='#6f6c62')
        x=4+i*8+rng.uniform(-1,1)
        if abs(x-3*round(x/3))<.2:x+=.35
        width=rng.uniform(.18,.24)
        events.append({'wall_x_m':x,'wall_height_m':rng.uniform(.6,.94),'width_m':width,'height_m':width*96/256,
                       'camera_height_m':camera_height,'camera_lookahead':lookahead,'id':f'E{i+1:02d}','kind':kind,'answer':value,'readable':condition!='unreadable',
                       'condition':condition,'start_s':25+i*48,'end_s':33+i*48,'image':np.array(im)[:,:,::-1].copy()})
    return events


def make_scene(events,folder):
    import mujoco
    import xml.etree.ElementTree as ET
    root=ET.Element('mujoco');ET.SubElement(root,'compiler',angle='radian')
    vis=ET.SubElement(root,'visual');ET.SubElement(vis,'global',offwidth=str(WIDTH),offheight=str(HEIGHT))
    ET.SubElement(vis,'headlight',ambient='.65 .65 .65',diffuse='.5 .5 .5')
    asset=ET.SubElement(root,'asset');world=ET.SubElement(root,'worldbody')
    ET.SubElement(world,'camera',name='right',pos='0 0 .72',xyaxes=f'-1 {-events[0]["camera_lookahead"]} 0 0 0 1',fovy='50')
    ET.SubElement(world,'light',pos='50 0 3',dir='0 0 -1',directional='true',castshadow='false')
    ET.SubElement(world,'geom',name='floor',type='plane',size='120 4 .1',rgba='.28 .3 .31 1')
    for y in [-1,1]:
        ET.SubElement(world,'geom',type='box',pos=f'50 {y} .8',size='55 .04 .8',rgba='.52 .55 .57 1')
    for x in range(0,105,3):
        ET.SubElement(world,'geom',type='box',pos=f'{x} -.95 .8',size='.015 .015 .8',rgba='.34 .36 .38 1')
    for z in [.18,1.35]:
        ET.SubElement(world,'geom',type='cylinder',pos=f'50 -.9 {z}',size='.035 55',euler='0 1.57079632679 0',rgba='.25 .29 .3 1')
    for i,event in enumerate(events):
        filename=folder/f'panel_{i:02d}.png';cv2.imwrite(str(filename),event['image'])
        ET.SubElement(asset,'texture',name=f'tex{i}',type='2d',file=str(filename.resolve()),vflip='true')
        ET.SubElement(asset,'material',name=f'mat{i}',texture=f'tex{i}',texuniform='false',rgba='1 1 1 1')
        # Small paper label, 18 cm wide, on the right wall.
        x=event['wall_x_m'];w=event['width_m'];h=event['height_m'];z=event['wall_height_m']
        vertices=[[-w/2,0,-h/2],[w/2,0,-h/2],[w/2,0,h/2],[-w/2,0,h/2]]
        ET.SubElement(asset,'mesh',name=f'panelmesh{i}',inertia='shell',vertex=' '.join(str(v) for xyz in vertices for v in xyz),
                      face='0 2 1 0 3 2',texcoord='1 0 0 0 0 1 1 1')
        ET.SubElement(world,'geom',name=f'panel{i}',type='mesh',mesh=f'panelmesh{i}',material=f'mat{i}',pos=f'{x} -.955 {z}',contype='0',conaffinity='0')
        event['world_center']=[x,-.955,z]
    model=mujoco.MjModel.from_xml_string(ET.tostring(root,encoding='unicode'))
    model.vis.map.znear=.005/model.stat.extent
    data=mujoco.MjData(model);mujoco.mj_forward(model,data)
    return model,data


class Camera:
    def __init__(self,events,folder):
        import mujoco
        self.mj=mujoco;self.model,self.data=make_scene(events,folder)
        self.renderer=mujoco.Renderer(self.model,HEIGHT,WIDTH)
        self.camera=mujoco.MjvCamera();mujoco.mjv_defaultCamera(self.camera)
        self.camera.distance=1
        self.eye_height=events[0]['camera_height_m']
        self.forward=np.array([events[0]['camera_lookahead'],-1.,0.]);self.forward/=np.linalg.norm(self.forward)
        self.right=np.cross(self.forward,[0,0,1]);self.focal=HEIGHT/(2*math.tan(math.radians(50)/2))
        self.model.vis.global_.fovy=50
    def image(self,t,events):
        eye=np.array([t/6,0,self.eye_height+.006*math.sin(t*2.3)])
        self.model.cam_pos[0]=eye
        self.mj.mj_forward(self.model,self.data)
        self.renderer.update_scene(self.data,camera='right')
        rgb=self.renderer.render();boxes={}
        for i,event in enumerate(events):
            center=np.array(event['world_center']);pts=[]
            w=event['width_m']/2;h=event['height_m']/2
            for dx,dz in [(-w,-h),(w,-h),(w,h),(-w,h)]:
                rel=center+[dx,0,dz]-eye;depth=rel@self.forward
                if depth<=0:break
                pts.append([WIDTH/2+self.focal*(rel@self.right)/depth,HEIGHT/2-self.focal*rel[2]/depth])
            if len(pts)!=4:continue
            pts=np.array(pts);lo=pts.min(0);hi=pts.max(0)
            if lo[0]<3 or hi[0]>WIDTH-3 or lo[1]<3 or hi[1]>HEIGHT-3 or hi[0]-lo[0]<20:continue
            boxes[i]=[lo[0]/WIDTH,lo[1]/HEIGHT,hi[0]/WIDTH,hi[1]/HEIGHT]
        frame=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
        for i,box in boxes.items():
            x0,y0,x1,y1=[int(v*s) for v,s in zip(box,[WIDTH,HEIGHT,WIDTH,HEIGHT])]
            patch=frame[y0:y1,x0:x1]
            condition=events[i]['condition']
            if condition=='blur':patch=cv2.GaussianBlur(patch,(0,0),1.3)
            elif condition=='motion':patch=cv2.filter2D(patch,-1,np.ones((1,9),np.float32)/9)
            elif condition in ['partial','unreadable']:patch=cv2.GaussianBlur(patch,(0,0),.7)
            frame[y0:y1,x0:x1]=patch
        return frame,boxes
    def close(self):self.renderer.close()


def build_one(args):
    output,video_id,seed,seconds,private_root,custom=args
    cv2.setNumThreads(1)
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    textures=Path(private_root)/video_id;textures.mkdir(parents=True,exist_ok=True)
    events=content(seed,custom);camera=Camera(events,textures);path=folder/f'{video_id}.mp4'
    if path.exists():raise ValueError('Choose a new output directory')
    process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24',
        '-s',f'{WIDTH}x{HEIGHT}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','25',
        '-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],stdin=subprocess.PIPE)
    labels=[]
    for e in events:
        labels.append({key:value for key,value in e.items() if key not in {'image','world_center'}})
        labels[-1].update(id=video_id+'/'+e['id'],video_id=video_id,boxes=[])
        if not e['readable']:labels[-1]['answer']=None
    for index in range(int(seconds*FPS)):
        t=index/FPS;frame,boxes=camera.image(t,events)
        for i,box in boxes.items():labels[i]['boxes'].append({'time_s':t,'box_xyxy':box})
        process.stdin.write(frame.tobytes())
        if index and index%(FPS*120)==0:print(video_id,index/FPS,'seconds rendered',flush=True)
    process.stdin.close();camera.close()
    if process.wait()!=0:raise RuntimeError('Video encoding failed')
    for event in labels:
        if not event['boxes']:raise RuntimeError('A sign is missing from video')
        event['start_s']=event['boxes'][0]['time_s'];event['end_s']=event['boxes'][-1]['time_s']+1/FPS
    h=hashlib.sha256(path.read_bytes()).hexdigest()
    print(video_id,seconds,'seconds',path.stat().st_size,'bytes',flush=True)
    return {'id':video_id,'file':path.name,'duration_s':seconds,'fps':FPS,'width':WIDTH,'height':HEIGHT,'sha256':h,'events':labels}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--private',type=Path,required=True)
    p.add_argument('--test-seed-file',type=Path,help='使用组织方保存的视频随机种子');p.add_argument('--content',type=Path,help='自定义12个训练标牌的数值 JSON');p.add_argument('--workers',type=int,default=2);p.add_argument('--preview-only',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);a.private.mkdir(parents=True,exist_ok=True)
    custom=None
    if a.content:
        import re
        custom=json.loads(a.content.read_text())['items']
        if len(custom)!=12 or any(e.get('kind') not in {'digits','temperature_display'} or not isinstance(e.get('value'),str) or len(e['value'])>8 or not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',e['value']) for e in custom):
            raise ValueError('内容文件需要12条数字或温度字符串')
    if a.preview_only:
        events=content(20261125,custom);folder=a.output/'textures';folder.mkdir(exist_ok=True)
        camera=Camera(events,folder)
        for i,event in enumerate(events):
            t=(event['world_center'][0]-.955*event['camera_lookahead'])*6
            frame,_=camera.image(t,events)
            cv2.imwrite(str(a.output/f'preview_{i+1:02d}_{event["condition"]}.jpg'),frame)
        camera.close()
        return
    if (a.output/'manifest.json').exists() or any(a.output.rglob('*.mp4')) or (a.private/'generation.json').exists():
        raise ValueError('请换一个新的输出目录和答案目录，保留已有视频及答案')
    private_seed=json.loads(a.test_seed_file.read_text())['private_test_seed'] if a.test_seed_file else secrets.randbits(63)
    if type(private_seed) is not int or private_seed<0:raise ValueError('视频种子需要是非负整数')
    (a.private/'generation.json').write_text(json.dumps({'private_test_seed':private_seed})+'\n')
    jobs=[(str(a.output/'train'),f'train{i+1:02d}',20261125+i,600,str(a.private/'textures'),custom) for i in range(8)]
    jobs += [(str(a.output/'test'),f'test{i+1:02d}',private_seed+i,600,str(a.private/'textures'),None) for i in range(2)]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:results=list(pool.map(build_one,jobs))
    train=[e for result in results if result['id'].startswith('train') for e in result['events']]
    test=[e for result in results if result['id'].startswith('test') for e in result['events']]
    common={'schema_version':'2.0','temperature_tolerance_C':'.1','minimum_iou':.2,'box_time_tolerance_s':.15}
    (a.output/'train'/'reference.json').write_text(json.dumps(dict(common,events=train),ensure_ascii=False)+'\n')
    (a.private/'video_test_reference.json').write_text(json.dumps(dict(common,events=test),ensure_ascii=False)+'\n')
    for result in results:result.pop('events')
    manifest={'schema_version':'2.0','source':'mujoco_right_camera_rendering','training_videos':8,'test_videos':2,
              'seconds_per_video':600,'signs_per_video':12,'video_reading_maximum':20,'videos':results}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Generated 8 training videos and 2 test videos.',flush=True)


if __name__=='__main__':main()
