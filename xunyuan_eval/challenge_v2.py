"""Score five routes, four disturbance levels, and video readings."""

import math
from pathlib import Path

from .io import FormatError, contained, digest, read_json
from .validation import load_trace


def distance_to_segment(point, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length2 = dx*dx+dy*dy
    u = max(0., min(1., ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length2)) if length2 else 0.
    return math.hypot(point[0]-a[0]-u*dx, point[1]-a[1]-u*dy)


def coefficient(error, bands):
    for band in bands:
        if error <= band['distance_m'] + 1e-9:
            return band['credit']
    return 0.


def score_route(rows, route, rules, termination):
    """Follow ordered checkpoints, measuring the greatest path error per section."""
    points = route['path_xy']
    section_for_edge = route['section_for_edge']
    edge = 0
    errors = [0.]*6
    reached = [False]*6
    stop = None
    last = None
    valid_until = 0.
    for row in rows:
        t = row['time_s']
        if t > rules['timeout_s']:
            stop = 'timeout'; break
        if last is not None:
            dt = t-last['time_s']
            if dt > rules['max_gap_s']+1e-9:
                stop = 'telemetry_gap'; break
            displacement = math.dist(row['position_m'][:2], last['position_m'][:2])
            if displacement > rules['maximum_speed_mps']*dt+rules['step_position_slack_m']:
                stop = 'position_jump'; break
        stop = ('collision' if row['forbidden_contacts'] else
                'out_of_bounds' if row['out_of_bounds'] else
                'illegal_action' if not row['action_valid'] else
                'manual_intervention' if row['intervention'] else
                'fall' if max(abs(row['roll_rad']),abs(row['pitch_rad'])) > rules['fall_angle_rad'] else None)
        if stop:
            break
        point = row['position_m'][:2]
        if edge == 0 and last is None and math.dist(point, points[0]) > rules['start_radius_m']:
            stop = 'wrong_start'; break
        if edge < len(points)-1:
            section = section_for_edge[edge]
            error = distance_to_segment(point, points[edge], points[edge+1])
            if edge and math.dist(point,points[edge]) <= rules['checkpoint_radius_m']+.02:
                error=min(error,distance_to_segment(point,points[edge-1],points[edge]))
            errors[section] = max(errors[section], error)
            if math.dist(point, points[edge+1]) <= rules['checkpoint_radius_m']:
                edge += 1
                if edge == len(points)-1 or section_for_edge[edge] != section:
                    reached[section] = True
        valid_until = t
        last = row
    completed = edge == len(points)-1
    # Collisions and safety violations fail this whole attempt; other routes keep their scores.
    safety_failed = stop in {'collision','out_of_bounds','illegal_action','manual_intervention','fall','position_jump','wrong_start','telemetry_gap'}
    if termination not in {'completed','timeout','crashed','safety_stop'}:
        raise FormatError('Unknown termination')
    if termination in {'crashed','safety_stop'}:
        safety_failed = True
        stop = stop or termination
    parts = []
    for i in range(6):
        credit = coefficient(errors[i],rules['deviation_bands']) if reached[i] else 0.
        if safety_failed:
            credit = 0.
        parts.append({'id':f'J{i+1:02d}' if i<5 else 'return','reached':reached[i],
                      'maximum_deviation_m':errors[i],'score':credit,'maximum':1})
    return {'route_id':route['id'],'score':sum(p['score'] for p in parts),'maximum':6,
            'completed':completed and not safety_failed and stop is None and termination=='completed','passed':completed and not safety_failed and stop is None and termination=='completed' and max(errors)<=rules['disturbance_path_limit_m'],
            'reason':stop or ('completed' if completed and termination=='completed' else termination if termination!='completed' else 'route_incomplete'),
            'last_checkpoint':edge,'scored_until_s':valid_until,'parts':parts}


def intersection_over_union(a,b):
    w=max(0.,min(a[2],b[2])-max(a[0],b[0]));h=max(0.,min(a[3],b[3])-max(a[1],b[1]))
    intersection=w*h
    return intersection/max((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection,1e-12)


def validate_video_reference(reference):
    from decimal import Decimal, InvalidOperation
    from .io import number, text
    if not isinstance(reference, dict) or not isinstance(reference.get('events'), list) or not reference['events']:
        raise FormatError('Video reference needs events')
    try:
        tolerance = Decimal(str(reference.get('temperature_tolerance_C', '.1')))
    except InvalidOperation as exc:
        raise FormatError('Invalid temperature tolerance') from exc
    if not tolerance.is_finite() or tolerance < 0:
        raise FormatError('Invalid temperature tolerance')
    iou = number(reference.get('minimum_iou', .2), 'minimum_iou', 0)
    if not 0 < iou <= 1:
        raise FormatError('minimum_iou must be between zero and one')
    if number(reference.get('box_time_tolerance_s', .15), 'box time tolerance', 0) == 0:
        raise FormatError('Box time tolerance must be positive')
    seen = set()
    for event in reference['events']:
        if not isinstance(event, dict):
            raise FormatError('Invalid video event')
        identity = text(event.get('id'), 'event id')
        if identity in seen:
            raise FormatError('Duplicate video event ID')
        seen.add(identity)
        text(event.get('video_id'), 'video id')
        start = number(event.get('start_s'), 'event start', 0)
        if number(event.get('end_s'), 'event end', 0) <= start:
            raise FormatError('Invalid event interval')
        if type(event.get('readable')) is not bool or event.get('kind') not in {'digits', 'temperature_display'}:
            raise FormatError('Invalid video event label')
        if event['readable']:
            answer = text(event.get('answer'), 'event answer')
            if event['kind'] == 'temperature_display':
                try:
                    if not Decimal(answer).is_finite():
                        raise InvalidOperation
                except InvalidOperation as exc:
                    raise FormatError('Invalid temperature answer') from exc
        frames = event.get('boxes')
        if not isinstance(frames, list) or not frames:
            raise FormatError('Video event needs observed boxes')
        previous = -1.
        for frame in frames:
            t = number(frame.get('time_s'), 'box time', 0)
            if t <= previous or not start <= t < event['end_s']:
                raise FormatError('Invalid box timestamps')
            previous = t
            box = frame.get('box_xyxy')
            if not isinstance(box, list) or len(box) != 4:
                raise FormatError('Invalid reference box')
            for value in box:
                number(value, 'box coordinate')
            if not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1:
                raise FormatError('Invalid reference box bounds')
    return reference


def score_video(predictions, reference, include_answers=False):
    """Use the most confident single prediction per sign, then compare its value."""
    from decimal import Decimal, InvalidOperation
    if not isinstance(predictions,dict) or not isinstance(predictions.get('detections'),list):
        raise FormatError('Video predictions need a detections list')
    validate_video_reference(reference)
    detections=predictions['detections']
    by_video={}
    video_ids={e['video_id'] for e in reference['events']}
    for row in detections:
        if not isinstance(row,dict):raise FormatError('Detection must be an object')
        if row.get('video_id') not in video_ids:
            raise FormatError('Unknown video ID')
        for key in ['time_s','confidence']:
            if isinstance(row.get(key),bool) or not isinstance(row.get(key),(int,float)) or not math.isfinite(row[key]):
                raise FormatError('Invalid video prediction number')
        if row['time_s']<0 or not 0<=row['confidence']<=1:
            raise FormatError('Invalid video prediction range')
        box=row.get('box_xyxy')
        if not isinstance(box,list) or len(box)!=4 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in box):
            raise FormatError('Invalid detection box')
        if not (0<=box[0]<box[2]<=1 and 0<=box[1]<box[3]<=1):
            raise FormatError('Detection box must be normalized xyxy')
        if row.get('status') not in {'ok','abstain'}:
            raise FormatError('Invalid recognition status')
        by_video.setdefault(row['video_id'],[]).append(row)
    outcomes=[]
    for event in reference['events']:
        candidates=[]
        for row in by_video.get(event['video_id'],[]):
            if not event['start_s']<=row['time_s']<event['end_s']:
                continue
            frames=event['boxes']
            frame=min(frames,key=lambda item:abs(item['time_s']-row['time_s']))
            if abs(frame['time_s']-row['time_s'])>reference.get('box_time_tolerance_s',.15):
                continue
            if intersection_over_union(row['box_xyxy'],frame['box_xyxy'])>=reference.get('minimum_iou',.2):
                candidates.append(row)
        chosen=max(candidates,key=lambda row:row['confidence']) if candidates else None
        passed=False
        if chosen:
            if not event['readable']:
                passed=chosen['status']=='abstain' and isinstance(chosen.get('reason'),str) and bool(chosen['reason'].strip())
            elif chosen['status']=='ok' and isinstance(chosen.get('value'),str):
                if event['kind']=='digits':
                    passed=chosen['value']==event['answer'] and chosen.get('unit') is None
                elif chosen.get('unit')=='C':
                    try:
                        value=Decimal(chosen['value']);answer=Decimal(event['answer'])
                        passed=value.is_finite() and abs(value-answer)<=Decimal(str(reference.get('temperature_tolerance_C','.1')))
                    except InvalidOperation:
                        passed=False
        outcome={'id':event['id'],'video_id':event['video_id'],'passed':passed,
                 'reason':'correct' if passed else 'missing' if chosen is None else 'incorrect',
                 'prediction':chosen}
        if include_answers:
            outcome['expected_status']='ok' if event['readable'] else 'abstain'
            outcome['expected_value']=event.get('answer') if event['readable'] else None
        outcomes.append(outcome)
    if not outcomes:
        raise FormatError('Video reference has no events')
    passed=sum(row['passed'] for row in outcomes)
    return {'score':20*passed/len(outcomes),'maximum':20,'correct':passed,'total':len(outcomes),'events':outcomes}


def validate_reference(reference):
    from .io import number, text, vector
    if not isinstance(reference, dict) or reference.get('schema_version') != '2.0':
        raise FormatError('Expected challenge schema 2.0')
    text(reference.get('reference_id'), 'reference_id')
    routes = reference.get('routes')
    if not isinstance(routes, list) or len(routes) != 5 or any(not isinstance(r, dict) for r in routes):
        raise FormatError('Expected five routes')
    ids = [text(r.get('id'), 'route id') for r in routes]
    if len(set(ids)) != 5:
        raise FormatError('Expected five unique route IDs')
    if reference.get('weights') != {'route': 30, 'disturbance': 20, 'recognition': 20, 'report': 30}:
        raise FormatError('Expected 30 route + 20 disturbance + 20 recognition + 30 report')
    tiers = reference.get('force_levels_N')
    if not isinstance(tiers, list) or len(tiers) != 4:
        raise FormatError('Expected four increasing force levels')
    for value in tiers:
        if number(value, 'force_N', 0) == 0:
            raise FormatError('Force must be positive')
    if sorted(set(tiers)) != tiers:
        raise FormatError('Expected four increasing force levels')
    rules = reference.get('rules')
    if not isinstance(rules, dict):
        raise FormatError('Missing route rules')
    for key in ['timeout_s', 'sample_dt_s', 'max_gap_s', 'start_radius_m', 'checkpoint_radius_m',
                'maximum_speed_mps', 'step_position_slack_m', 'fall_angle_rad', 'disturbance_path_limit_m']:
        if number(rules.get(key), key, 0) == 0:
            raise FormatError(key + ' must be positive')
    if rules['max_gap_s'] < rules['sample_dt_s']:
        raise FormatError('max_gap_s must cover a physics step')
    bands = rules.get('deviation_bands')
    if not isinstance(bands, list) or not bands:
        raise FormatError('Missing deviation bands')
    distances = []
    credits = []
    for band in bands:
        if not isinstance(band,dict):raise FormatError('Invalid deviation band')
        distances.append(number(band.get('distance_m'), 'deviation distance', 0))
        credit = number(band.get('credit'), 'deviation credit', 0)
        if credit > 1:
            raise FormatError('Deviation credit cannot exceed one')
        credits.append(credit)
    if distances != sorted(set(distances)) or credits != sorted(credits, reverse=True):
        raise FormatError('Deviation bands must increase in distance and decrease in credit')
    disturbance = reference.get('disturbance', {})
    if not isinstance(disturbance,dict):raise FormatError('Invalid disturbance configuration')
    if disturbance.get('pulses_per_attempt') != 3:
        raise FormatError('Expected three disturbance pulses')
    if number(disturbance.get('pulse_duration_s'), 'pulse duration', 0) == 0:
        raise FormatError('Pulse duration must be positive')
    fractions = disturbance.get('progress_fractions')
    if not isinstance(fractions, list) or len(fractions) != 3:
        raise FormatError('Expected three pulse positions')
    for fraction in fractions:
        if not 0 < number(fraction, 'pulse progress') < 1:
            raise FormatError('Pulse positions must lie inside the route')
    if fractions != sorted(set(fractions)):
        raise FormatError('Pulse positions must be ordered')
    jitter=number(disturbance.get('progress_jitter_fraction',.04),'pulse jitter',0)
    if fractions[0]-jitter<=0 or fractions[-1]+jitter>=1 or any(b-a<=2*jitter for a,b in zip(fractions,fractions[1:])):
        raise FormatError('Pulse jitter must keep positions ordered inside the route')
    for route in routes:
        points = route.get('path_xy')
        sections = route.get('section_for_edge')
        if not isinstance(points, list) or len(points) < 7 or not isinstance(sections, list):
            raise FormatError('Missing route geometry')
        for point in points:
            vector(point, 2, 'route point')
        if any(type(section) is not int for section in sections):
            raise FormatError('Invalid route section')
        if len(sections) != len(points)-1 or sorted(set(sections)) != list(range(6)) or sections != sorted(sections):
            raise FormatError('Route needs five outbound sections and one return section')
        if math.dist(points[0], points[-1]) > 1e-8:
            raise FormatError('Reference route must return to its start')
        if any(math.dist(a, b) < 1e-8 for a, b in zip(points, points[1:])):
            raise FormatError('Route contains a zero-length edge')
    return reference


def evaluate(run, reference, root, video_reference=None):
    validate_reference(reference)
    if not isinstance(run,dict) or run.get('schema_version')!='2.0' or run.get('reference_id')!=reference['reference_id']:
        raise FormatError('Run and reference versions do not match')
    root=Path(root)
    expected={route['id'] for route in reference['routes']}
    def index(rows, disturbance=False):
        result={}
        if not isinstance(rows,list):raise FormatError('Attempts must be a list')
        for row in rows:
            if not isinstance(row,dict):raise FormatError('Attempt must be an object')
            if row.get('route_id') not in expected:
                raise FormatError('Unknown route ID')
            if disturbance and (isinstance(row.get('force_N'),bool) or row.get('force_N') not in reference['force_levels_N']):
                raise FormatError('Unknown force level')
            key=(row['route_id'],row['force_N']) if disturbance else row['route_id']
            if key in result:
                raise FormatError('Duplicate route attempt')
            result[key]=row
        return result
    normal=index(run.get('routes',[])); disturbed=index(run.get('disturbance',[]),True)
    used=set(); hashes={}
    def judge(item,route):
        path=contained(root,item['trace'])
        if path in used:
            raise FormatError('Each attempt needs its own state record')
        used.add(path);hashes[item['trace']]=digest(path)
        rows=load_trace(root,item['trace'])
        result=score_route(rows,route,reference['rules'],item['termination'])
        if item.get('force_N'):
            force_record=read_json(contained(root,item.get('force_record')))
            if not isinstance(force_record,dict):raise FormatError('Invalid force record')
            pulses=force_record.get('pulses',[]);force=float(item['force_N'])
            duration=reference['disturbance']['pulse_duration_s']
            good=isinstance(pulses,list) and len(pulses)==reference['disturbance']['pulses_per_attempt'] and force_record.get('force_N')==force
            previous_end=-1.
            if good:
                for pulse in pulses:
                    if not isinstance(pulse,dict):good=False;break
                    vector=pulse.get('force_world_N',[]);start=pulse.get('start_s')
                    good=(isinstance(start,(int,float)) and not isinstance(start,bool) and math.isfinite(start)
                          and start>=0 and start>=previous_end-1e-8 and isinstance(vector,list) and len(vector)==3
                          and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in vector))
                    if not good:break
                    good=(abs(math.sqrt(sum(v*v for v in vector))-force)<1e-5 and abs(vector[2])<1e-8
                          and isinstance(pulse.get('duration_s'),(int,float)) and abs(pulse['duration_s']-duration)<1e-8)
                    if not good:break
                    previous_end=start+duration
            impulse=0.
            for previous,row in zip(rows,rows[1:]):
                vector=row.get('force_world_N')
                if not isinstance(vector,list) or len(vector)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in vector):
                    good=False;break
                if good:
                    active=[p for p in pulses if p['start_s']-1e-9<=previous['time_s']<p['start_s']+duration-1e-9]
                    expected_vector=active[0]['force_world_N'] if active else [0,0,0]
                    if math.dist(vector,expected_vector)>1e-5:good=False
                impulse+=math.sqrt(sum(v*v for v in vector))*(row['time_s']-previous['time_s'])
            expected=force*reference['disturbance']['pulses_per_attempt']*duration
            good=good and abs(impulse-expected)<force*reference['rules']['sample_dt_s']*.1
            result['force_record_verified']=good
            result['passed']=result['passed'] and good
            if not good and result['reason']=='completed':result['reason']='incomplete_disturbance'
        return result
    route_results=[]; perturbation=[]
    for route in reference['routes']:
        item=normal.get(route['id'])
        route_results.append(judge(item,route) if item else {'route_id':route['id'],'score':0,'maximum':6,'reason':'missing'})
        lower_passed=True
        for level in reference['force_levels_N']:
            item=disturbed.get((route['id'],level))
            outcome=judge(item,route) if item else None
            passed=bool(lower_passed and outcome and outcome['passed'])
            perturbation.append({'route_id':route['id'],'force_N':level,'score':1 if passed else 0,'maximum':1,
                                 'reason':outcome['reason'] if lower_passed and outcome else 'lower_level_failed' if not lower_passed else 'missing',
                                 'attempt':outcome})
            lower_passed=passed
    video=score_video(read_json(contained(root,run['video_predictions'])),video_reference) if video_reference is not None and run.get('video_predictions') else {'score':0,'maximum':20,'reason':'missing_video_predictions'}
    route_score=sum(row['score'] for row in route_results)
    disturbance_score=sum(row['score'] for row in perturbation)
    return {'schema_version':'2.0','reference_id':reference['reference_id'],'team':run.get('team',''),
            'scores':{'route':{'score':route_score,'maximum':30},'disturbance':{'score':disturbance_score,'maximum':20},'recognition':video},
            'navigation_control_score':route_score+disturbance_score,'navigation_control_maximum':50,
            'automated_score':route_score+disturbance_score+video['score'],'automated_maximum':70,'maximum_score':100,
            'pending_manual':{'report':30},'final_score':None,'details':{'routes':route_results,'disturbance':perturbation},
            'trace_sha256':hashes}


def add_report_score(report,score):
    import copy
    from .io import number
    if not isinstance(report,dict) or report.get('schema_version') not in {'2.0','3.0'}:
        raise FormatError('需要测评成绩文件')
    score=number(score,'报告分',0)
    if score>30:raise FormatError('报告分应在 0 到 30 之间')
    automated=number(report.get('automated_score'),'自动评分',0)
    if automated>70:raise FormatError('自动评分超出 70 分')
    result=copy.deepcopy(report)
    result.setdefault('scores',{})['report']={'score':score,'maximum':30}
    result['pending_manual']={}
    result['final_score']=automated+score
    result['maximum_score']=100
    return result
