import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from xunyuan_eval.challenge_v2 import coefficient,evaluate,score_route,score_video,validate_reference,add_report_score
from xunyuan_eval.demo_v2 import rows_for_route
from xunyuan_eval.io import FormatError,write_json

ROOT=Path(__file__).resolve().parents[1]


class RouteV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref=validate_reference(json.loads((ROOT/'challenges/v2/reference.json').read_text()))
        cls.route=cls.ref['routes'][0]
        cls.rows=rows_for_route(cls.route)

    def test_five_routes_have_correct_outbound_and_reverse_instructions(self):
        for route in self.ref['routes']:
            task=json.loads((ROOT/'challenges/v2'/route['task']).read_text())
            reverse=[{'left':'right','right':'left','straight':'straight'}[t] for t in route['outbound_turns'][::-1]]
            self.assertEqual([t['turn'] for t in task['return']],reverse)
            self.assertEqual(len(task['outbound']),5)
            self.assertEqual(route['path_xy'][0],route['path_xy'][-1])

    def test_exact_path_and_return_scores_six(self):
        result=score_route(self.rows,self.route,self.ref['rules'],'completed')
        self.assertEqual(result['score'],6)
        self.assertTrue(result['passed'])

    def test_outbound_only_has_no_return_credit(self):
        goal=self.route['path_xy'][len(self.route['path_xy'])//2]
        end=next(i for i,row in enumerate(self.rows) if math.dist(row['position_m'][:2],goal)<1e-8)
        result=score_route(self.rows[:end+1],self.route,self.ref['rules'],'timeout')
        self.assertEqual(result['score'],5)
        self.assertEqual(result['parts'][-1]['score'],0)
        self.assertFalse(result['passed'])

    def test_fifth_turn_scores_before_final_approach(self):
        fifth_exit=self.route['path_xy'][10]
        end=next(i for i,row in enumerate(self.rows) if math.dist(row['position_m'][:2],fifth_exit)<1e-8)
        result=score_route(self.rows[:end+1],self.route,self.ref['rules'],'timeout')
        self.assertEqual(result['score'],5)
        self.assertEqual(result['parts'][-1]['score'],0)

    def test_deviation_deductions_have_distinct_bands(self):
        bands=self.ref['rules']['deviation_bands']
        self.assertEqual([coefficient(d,bands) for d in [.10,.20,.40,.60]],[1,.75,.5,0])
        self.assertEqual([coefficient(d,bands) for d in [.15,.30,.50]],[1,.75,.5])

    def test_collision_invalidates_current_route(self):
        rows=copy.deepcopy(self.rows)
        rows[-2]['forbidden_contacts']=1
        result=score_route(rows,self.route,self.ref['rules'],'completed')
        self.assertEqual(result['score'],0)
        self.assertEqual(result['reason'],'collision')

    def test_spawn_at_finish_and_teleport_do_not_complete_route(self):
        rows=copy.deepcopy(self.rows[:2]);rows[1]['position_m']=self.rows[-1]['position_m']
        result=score_route(rows,self.route,self.ref['rules'],'completed')
        self.assertEqual(result['score'],0)
        rows[1]['position_m']=[40,40,.5]
        result=score_route(rows,self.route,self.ref['rules'],'completed')
        self.assertEqual(result['reason'],'position_jump')

    def test_failed_low_tier_blocks_higher_tiers_and_preserves_earlier_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run={'schema_version':'2.0','reference_id':self.ref['reference_id'],'routes':[],'disturbance':[]}
            for force in [.5,1,3,5]:
                filename=f'{force}.jsonl'
                with (root/filename).open('w') as stream:
                    for i,original in enumerate(self.rows):
                        row=copy.deepcopy(original)
                        row['force_world_N']=[0,force if any(t+1e-9<row['time_s']<=t+.2+1e-9 for t in [1,3,5]) else 0,0]
                        if force==1 and i==len(self.rows)-2:row['forbidden_contacts']=1
                        stream.write(json.dumps(row)+'\n')
                write_json(root/f'{force}.json',{'force_N':force,'pulses':[{'start_s':t,'duration_s':.2,'force_world_N':[0,force,0]} for t in [1,3,5]]})
                run['disturbance'].append({'route_id':self.route['id'],'force_N':force,'trace':filename,'force_record':f'{force}.json','termination':'completed'})
            result=evaluate(run,self.ref,root)
            self.assertEqual(result['scores']['disturbance']['score'],1)
            self.assertEqual([r['score'] for r in result['details']['disturbance'][:4]],[1,0,0,0])
            self.assertEqual(result['pending_manual'],{'report':30})

    def test_old_weights_and_extra_routes_are_rejected(self):
        for key,value in [('weights',{'route':35,'disturbance':15,'recognition':20,'report':30}),('routes',self.ref['routes']*2)]:
            ref=copy.deepcopy(self.ref);ref[key]=value
            with self.assertRaises(FormatError):validate_reference(ref)


class VideoV2Tests(unittest.TestCase):
    def setUp(self):
        self.ref={'events':[{'id':'test01/E01','video_id':'test01','start_s':1,'end_s':2,'readable':True,'kind':'digits','answer':'00127',
                            'boxes':[{'time_s':1,'box_xyxy':[.4,.4,.6,.6]}]}]}
        self.pred={'detections':[{'video_id':'test01','time_s':1,'box_xyxy':[.4,.4,.6,.6],'status':'ok','value':'00127','unit':None,'confidence':.8}]}

    def test_correct_reading_gets_points_wrong_reading_gets_zero(self):
        self.assertEqual(score_video(self.pred,self.ref)['score'],20)
        self.pred['detections'][0]['value']='127'
        self.assertEqual(score_video(self.pred,self.ref)['score'],0)

    def test_many_guesses_use_highest_confidence_not_any_correct_answer(self):
        wrong=copy.deepcopy(self.pred['detections'][0]);wrong.update(value='00000',confidence=.9)
        self.pred['detections'].append(wrong)
        self.assertEqual(score_video(self.pred,self.ref)['score'],0)

    def test_detection_needs_correct_time_and_location(self):
        for update in [{'time_s':3},{'box_xyxy':[0,0,.1,.1]}]:
            pred=copy.deepcopy(self.pred);pred['detections'][0].update(update)
            self.assertEqual(score_video(pred,self.ref)['score'],0)

    def test_unreadable_needs_a_reason(self):
        self.ref['events'][0]['readable']=False
        self.pred['detections'][0].update(status='abstain')
        self.assertEqual(score_video(self.pred,self.ref)['score'],0)
        self.pred['detections'][0]['reason']='blurred'
        self.assertEqual(score_video(self.pred,self.ref)['score'],20)

    def test_training_feedback_can_show_answers_and_test_feedback_omits_them(self):
        self.assertNotIn('expected_value',score_video(self.pred,self.ref)['events'][0])
        feedback=score_video(self.pred,self.ref,include_answers=True)
        self.assertEqual(feedback['events'][0]['expected_value'],'00127')
        self.assertEqual(feedback['events'][0]['prediction']['value'],'00127')

    def test_temperature_tolerance_and_missing_events(self):
        self.ref['events'][0].update(kind='temperature_display',answer='31.4')
        self.pred['detections'][0].update(value='31.5',unit='C')
        self.assertEqual(score_video(self.pred,self.ref)['score'],20)
        self.pred['detections'][0]['value']='31.6'
        self.assertEqual(score_video(self.pred,self.ref)['score'],0)
        self.assertEqual(score_video({'detections':[]},self.ref)['score'],0)


class ManualReportTests(unittest.TestCase):
    def test_manual_points_are_added_to_seventy(self):
        report={'schema_version':'2.0','automated_score':70,'scores':{},'pending_manual':{'report':30}}
        result=add_report_score(report,27)
        self.assertEqual(result['final_score'],97)
        self.assertEqual(result['maximum_score'],100)
        self.assertEqual(result['pending_manual'],{})
        self.assertEqual(report['pending_manual'],{'report':30})

    def test_report_points_must_be_finite_and_within_thirty(self):
        report={'schema_version':'2.0','automated_score':70}
        for score in [-1,31,True,float('nan'),float('inf')]:
            with self.subTest(score=score):
                with self.assertRaises(FormatError):add_report_score(report,score)


if __name__=='__main__':unittest.main()
