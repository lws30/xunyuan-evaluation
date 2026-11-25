import copy
import json
import math
import tempfile
import unittest
import zipfile
from pathlib import Path

from xunyuan_eval.cli import main
from xunyuan_eval.demo import create_demo, sample
from xunyuan_eval.evaluator import evaluate, round_result, trial_result
from xunyuan_eval.geometry import HoldWindow, angle_error, crossing
from xunyuan_eval.io import FormatError, contained, loads, read_json
from xunyuan_eval.readings import evaluate_readings
from xunyuan_eval.submission import prepare_submission
from xunyuan_eval.validation import load_trace, validate_reference, validate_run


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / "demo"
        create_demo(cls.root)
        cls.ref = read_json(cls.root / "reference.json")
        cls.source_run = read_json(cls.root / "run.json")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.run = copy.deepcopy(self.source_run)
        self.ref = copy.deepcopy(type(self).ref)

    def score(self):
        return evaluate(self.run, self.ref, self.root)

    def test_complete_demo_is_seventy_not_a_hundred(self):
        report = self.score()
        self.assertEqual(report["automated_score"], 70)
        self.assertIsNone(report["final_score"])
        self.assertFalse(report["official_result"])
        self.assertEqual(report["pending_manual"], {"report": 30})
        self.assertTrue(all(r["route_completed"] for r in report["details"]["rounds"]))

    def test_final_stage_still_has_manual_items(self):
        report = evaluate(self.run, self.ref, self.root, stage="final")
        self.assertEqual(report["pending_manual"], {"record_review": 25, "deployment": 5})

    def test_missing_trial_keeps_original_denominator(self):
        self.run["locomotion"].pop(0)
        report = self.score()
        self.assertEqual(report["scores"]["locomotion"]["denominator"], 21)
        self.assertEqual(report["scores"]["locomotion"]["passed"], 20)
        self.assertAlmostEqual(report["automated_score"], 70 - 5 / 6)

    def test_missing_round_keeps_fifteen_and_twelve(self):
        self.run["rounds"].pop()
        report = self.score()
        self.assertEqual(report["scores"]["navigation"]["passed"], 10)
        self.assertEqual(report["scores"]["docking"]["passed"], 8)
        self.assertEqual(report["scores"]["navigation"]["denominator"], 15)
        self.assertEqual(report["scores"]["docking"]["denominator"], 12)

    def test_all_missing_is_zero(self):
        self.run["rounds"] = []
        self.run["locomotion"] = []
        self.assertEqual(self.score()["automated_score"], 0)

    def test_duplicate_or_unknown_trial_rejected(self):
        self.run["locomotion"].append(copy.deepcopy(self.run["locomotion"][0]))
        with self.assertRaises(FormatError):
            self.score()
        self.run["locomotion"][-1]["id"] = "made-up"
        with self.assertRaises(FormatError):
            self.score()

    def test_different_policy_rejected(self):
        self.run["rounds"][0]["policy_sha256"] = "f" * 64
        with self.assertRaises(FormatError):
            self.score()

    def test_reusing_one_trace_rejected(self):
        self.run["rounds"][0]["trace"] = self.run["locomotion"][0]["trace"]
        with self.assertRaises(FormatError):
            self.score()

    def test_wrong_reference_version_rejected(self):
        self.run["reference_id"] = "different"
        with self.assertRaises(FormatError):
            self.score()

    def test_changed_reference_denominator_rejected(self):
        self.ref["locomotion"].pop()
        with self.assertRaises(FormatError):
            self.score()

    def test_evaluator_ignores_participant_passed_flags(self):
        self.run["locomotion"][0]["passed"] = True
        self.run["locomotion"][0]["termination"] = "crashed"
        self.assertEqual(self.score()["scores"]["locomotion"]["passed"], 20)

    def test_bundle_is_reproducible_and_recomputes_report(self):
        a, b = self.root / "a.zip", self.root / "b.zip"
        first = prepare_submission(self.root / "run.json", self.root / "reference.json", a)
        second = prepare_submission(self.root / "run.json", self.root / "reference.json", b)
        self.assertEqual(first["sha256"], second["sha256"])
        with zipfile.ZipFile(a) as z:
            self.assertEqual(len(z.namelist()), 28)
            report = json.loads(z.read("report.json"))
            self.assertEqual(report["automated_score"], 70)
            self.assertFalse(json.loads(z.read("submission.json"))["official_result"])
        with self.assertRaises(FormatError):
            prepare_submission(self.root / "run.json", self.root / "reference.json", a)

    def test_cli_refuses_overwriting_run(self):
        self.assertEqual(main(["evaluate", "--run", str(self.root / "run.json"), "--reference",
                               str(self.root / "reference.json"), "--output", str(self.root / "run.json")]), 2)


class PhysicalCriteriaTests(unittest.TestCase):
    def setUp(self):
        from xunyuan_eval.demo import example_reference
        self.ref = example_reference()
        self.rules = self.ref["rules"]
        self.spec = self.ref["locomotion"][0]
        self.item = {"termination": "completed"}
        self.rows = [sample(i * .02, i * .02, speed=1) for i in range(81)]

    def trial(self):
        return trial_result(self.spec, self.item, self.rows, self.rules)

    def test_base_crossed_but_tail_not_crossed(self):
        self.rows = self.rows[:56]
        self.assertEqual(self.trial()["reason"], "whole_envelope_did_not_exit")

    def test_spawn_beyond_exit_not_a_pass(self):
        for row in self.rows:
            row["envelope_points_m"] = [[2, y, z] for _, y, z in row["envelope_points_m"]]
        self.assertEqual(self.trial()["reason"], "no_pre_exit_envelope")

    def test_passing_outside_finite_gate_fails(self):
        for row in self.rows:
            row["envelope_points_m"] = [[x, y + 4, z] for x, y, z in row["envelope_points_m"]]
        self.assertEqual(self.trial()["reason"], "envelope_outside_exit_gate")

    def test_collision_and_safety_conditions_fail(self):
        for key, value, expected in [("forbidden_contacts", 1, "forbidden_contact"),
                                     ("out_of_bounds", True, "out_of_bounds"),
                                     ("action_valid", False, "illegal_action"),
                                     ("intervention", True, "manual_intervention"),
                                     ("roll_rad", 1.1, "fall")]:
            with self.subTest(key=key):
                prior = self.rows[1][key]
                self.rows[1][key] = value
                self.assertEqual(self.trial()["reason"], expected)
                self.rows[1][key] = prior

    def test_gap_is_failure(self):
        del self.rows[30]
        self.assertEqual(self.trial()["reason"], "telemetry_gap")

    def test_timeout_is_failure(self):
        self.spec["timeout_s"] = .5
        self.assertEqual(self.trial()["reason"], "timeout")

    def test_wrong_first_gate_stays_failed_after_recovery(self):
        spec = copy.deepcopy(self.ref["rounds"][0])
        spec["gates"]["wrong"] = {"center_m": [.5, 0, 0], "normal": [1, 0, 0], "width_m": 1}
        spec["navigation"][0]["candidates"].append("wrong")
        rows = [sample(i * .02, i * .02, speed=1) for i in range(301)]
        result = round_result(spec, self.item, rows, self.rules)
        self.assertFalse(result["navigation"][0]["passed"])
        self.assertEqual(result["navigation"][0]["reason"], "wrong_first_exit")
        self.assertEqual(sum(x["passed"] for x in result["navigation"]), 4)

    def test_trace_safety_failure_preserves_prior_valid_events(self):
        spec = self.ref["rounds"][0]
        rows = [sample(i * .02, i * .02, speed=1) for i in range(301)]
        rows[80]["forbidden_contacts"] = 1
        result = round_result(spec, self.item, rows, self.rules)
        self.assertTrue(result["navigation"][0]["passed"])
        self.assertEqual(sum(x["passed"] for x in result["navigation"]), 1)

    def test_gate_outside_width_does_not_count(self):
        self.assertIsNone(crossing(sample(0, 0, y=4), sample(.02, 2, y=4), self.spec["exit"]))

    def test_reverse_gate_crossing_does_not_count(self):
        self.assertIsNone(crossing(sample(0, 2), sample(.02, 0), self.spec["exit"]))

    def test_angle_wrap_and_continuous_hold(self):
        self.assertAlmostEqual(angle_error(-math.pi + .01, math.pi - .01), .02)
        window = HoldWindow(2, .03)
        self.assertFalse(window.update(0, True))
        self.assertFalse(window.update(2, True))  # a gap cannot stand for two seconds
        for i in range(1, 101):
            passed = window.update(2 + i * .02, True)
        self.assertTrue(passed)

    def test_moving_at_dock_does_not_count(self):
        spec = copy.deepcopy(self.ref["rounds"][0])
        rows = [sample(i * .02, min(i * .02, 1.5), speed=.04) for i in range(201)]
        result = round_result(spec, self.item, rows, self.rules)
        self.assertFalse(result["docking"][0]["passed"])


class InputAndReadingTests(unittest.TestCase):
    def test_bad_json_and_bool_number_rejected(self):
        for value in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
            with self.assertRaises(FormatError):
                loads(value)
        from xunyuan_eval.validation import validate_sample
        row = sample(0)
        row["speed_mps"] = True
        with self.assertRaises(FormatError):
            validate_sample(row)

    def test_file_escape_and_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            outside = Path(tmp) / "secret"
            outside.write_text("private")
            (root / "link").symlink_to(outside)
            for name in ["../secret", str(outside), "link"]:
                with self.assertRaises(FormatError):
                    contained(root, name)

    def test_duplicate_or_missing_start_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "trace.jsonl"
            for rows in [[sample(.02)], [sample(0), sample(0)]]:
                p.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
                with self.assertRaises(FormatError):
                    load_trace(tmp, "trace.jsonl")

    def test_reading_exact_string_and_decimal_tolerance(self):
        reference = {"events": [{"id": "a", "kind": "digits", "target_id": "A", "readable": True, "answer": "00127"},
                                 {"id": "b", "kind": "temperature_display", "target_id": "B", "readable": True, "answer": "31.4"},
                                 {"id": "c", "kind": "digits", "target_id": "A", "readable": False}]}
        predictions = {"results": [{"id": "a", "target_id": "A", "status": "ok", "value": "127", "unit": None},
                                    {"id": "b", "target_id": "B", "status": "ok", "value": "31.5", "unit": "C"},
                                    {"id": "c", "target_id": "A", "status": "abstain", "reason": "occluded"}]}
        result = evaluate_readings(predictions, reference)
        self.assertEqual(result["passed"], 2)
        self.assertIsNone(result["competition_score"])
        predictions["results"][1]["value"] = "NaN"
        self.assertEqual(evaluate_readings(predictions, reference)["passed"], 1)

    def test_missing_rejection_not_counted_as_correct(self):
        ref = {"events": [{"id": "a", "kind": "digits", "target_id": "A", "readable": False}]}
        self.assertEqual(evaluate_readings({"results": []}, ref)["passed"], 0)


if __name__ == "__main__":
    unittest.main()
