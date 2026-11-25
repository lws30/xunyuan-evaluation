import copy
import json
import tempfile
import unittest
from pathlib import Path

from xunyuan_eval.challenge_v3 import evaluate, validate_reference
from xunyuan_eval.demo_v2 import rows_for_route
from xunyuan_eval.io import FormatError, read_json, write_json


class ScoringV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.ref = validate_reference(read_json(Path(__file__).resolve().parents[1] / 'challenges/v3/reference.json'))
        route = cls.ref['routes'][0]
        cls.records = {'schema_version': '3.0', 'reference_id': cls.ref['reference_id'], 'routes': [], 'disturbance': [], 'friction': []}
        attempts = [('normal', 0, .8, 'routes')]
        attempts += [(f'push_{f}', f, .8, 'disturbance') for f in cls.ref['force_levels_N']]
        attempts += [(f'mu_{mu}', 0, mu, 'friction') for mu in cls.ref['friction_levels']]
        duration = cls.ref['disturbance']['pulse_duration_s']
        for name, force, mu, group in attempts:
            path = cls.root / (name + '.jsonl')
            with path.open('w') as stream:
                for original in rows_for_route(route):
                    row = copy.deepcopy(original)
                    active = any(t + 1e-9 < row['time_s'] <= t + duration + 1e-9 for t in [1, 3, 5])
                    row.update(force_world_N=[0, force if active else 0, 0], ground_contact_friction=[mu])
                    stream.write(json.dumps(row) + '\n')
            item = {'route_id': route['id'], 'trace': path.name, 'termination': 'completed'}
            if force:
                item.update(force_N=force, force_record=name + '.json')
                write_json(cls.root / item['force_record'], {'force_N': force, 'pulses': [
                    {'start_s': t, 'duration_s': duration, 'force_world_N': [0, force, 0]} for t in [1, 3, 5]]})
            if group == 'friction':
                item['friction'] = mu
            cls.records[group].append(item)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_one_perfect_map_scores_six_plus_two_plus_two(self):
        result = evaluate(self.records, self.ref, self.root)
        self.assertEqual(result['navigation_control_score'], 10)
        self.assertEqual(result['scores']['disturbance']['push']['score'], 2)
        self.assertEqual(result['scores']['disturbance']['friction']['score'], 2)

    def test_highest_force_failure_keeps_lower_force_credit(self):
        run = copy.deepcopy(self.records)
        run['disturbance'][0]['termination'] = 'safety_stop'
        result = evaluate(run, self.ref, self.root)
        self.assertEqual(result['scores']['disturbance']['push']['score'], 1.5)
        self.assertEqual([r['force_N'] for r in result['details']['disturbance'][:4]], self.ref['force_levels_N'])
        self.assertEqual([r['score'] for r in result['details']['disturbance'][:4]], [0, .5, .5, .5])

    def test_wrong_actual_friction_cannot_earn_friction_points(self):
        run = copy.deepcopy(self.records)
        # Claim the .1 run as .2 and remove the genuine .2 record.
        run['friction'] = [dict(run['friction'][0], friction=.2)]
        result = evaluate(run, self.ref, self.root)
        self.assertEqual(result['scores']['disturbance']['friction']['score'], 0)
        self.assertFalse(result['details']['friction'][1]['attempt']['friction_record_verified'])

    def test_force_and_friction_orders_are_validated(self):
        for field in ['force_levels_N', 'friction_levels']:
            ref = copy.deepcopy(self.ref); ref[field] = ref[field][::-1]
            with self.assertRaises(FormatError):
                validate_reference(ref)


if __name__ == '__main__':
    unittest.main()
