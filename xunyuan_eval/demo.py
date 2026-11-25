"""Synthetic protocol fixtures: never simulation or robot capability evidence."""

import copy
import hashlib
import math
from pathlib import Path

from .io import write_json
from .recorder import TraceRecorder


def example_reference():
    rules = {"sample_dt_s": 0.02, "max_gap_s": 0.030, "dock_position_m": 0.15,
             "dock_yaw_rad": math.radians(10), "dock_speed_mps": 0.03,
             "dock_yaw_rate_rps": 0.05, "dock_hold_s": 2.0, "fall_angle_rad": math.radians(45)}
    categories = [("M01", "straight_turn"), ("M02", "straight_turn"), ("M03", "slopes"),
                  ("M04", "slopes"), ("M05", "stairs_up"), ("M06", "stairs_down"), ("M08", "friction")]
    trials = [{"id": f"{category}_T{i}", "group": group, "timeout_s": 60,
               "scene_id": "SYNTHETIC_PROTOCOL_FIXTURE",
               "exit": {"center_m": [1, 0, 0], "normal": [1, 0, 0], "width_m": 1}}
              for category, group in categories for i in range(1, 4)]
    gates = {f"G{i}": {"center_m": [i, 0, 0], "normal": [1, 0, 0], "width_m": 1}
             for i in range(1, 6)}
    navigation = [{"id": f"N{i:02d}", "candidates": [f"G{i}"], "correct_gate": f"G{i}"}
                  for i in range(1, 6)]
    docking = [{"id": f"D{i:02d}", "target_id": ["A", "B", "A", "G0"][i - 1],
                "position_m": [x, 0, 0.5], "yaw_rad": 0,
                "after_nav": f"N{n:02d}", "before_nav": f"N{n + 1:02d}" if i < 4 else None}
               for i, (x, n) in enumerate([(1.5, 1), (2.5, 2), (3.5, 3), (5.5, 5)], 1)]
    return {"schema_version": "1.0", "reference_id": "synthetic-protocol-fixture-v1",
            "status": "synthetic_protocol_fixture_not_a_robot_test", "rules": rules, "locomotion": trials,
            "rounds": [{"id": f"R{i}", "timeout_s": 60, "gates": copy.deepcopy(gates),
                        "navigation": copy.deepcopy(navigation), "docking": copy.deepcopy(docking)} for i in range(1, 4)]}


def sample(t, x=0, y=0, yaw=0, speed=0):
    # Four corners bound the entire synthetic rectangular footprint.
    points = [[x + dx, y + dy, 0.2] for dx in [-0.2, 0.2] for dy in [-0.1, 0.1]]
    return {"time_s": round(t, 8), "position_m": [x, y, 0.5], "yaw_rad": yaw,
            "roll_rad": 0, "pitch_rad": 0, "speed_mps": speed, "yaw_rate_rps": 0,
            "envelope_points_m": points, "forbidden_contacts": 0, "out_of_bounds": False,
            "action_valid": True, "intervention": False}


def create_demo(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    reference = example_reference()
    policy = hashlib.sha256(b"synthetic protocol fixture: no robot policy").hexdigest()
    run = {"schema_version": "1.0", "reference_id": reference["reference_id"], "team": "example-team",
           "method": "SYNTHETIC PROTOCOL FIXTURE ONLY", "policy_sha256": policy, "locomotion": [], "rounds": []}
    for spec in reference["locomotion"]:
        name = f"traces/{spec['id']}.jsonl"
        with TraceRecorder(output / name) as recorder:
            for i in range(81):
                recorder.append(sample(i * 0.02, x=i * 0.02, speed=1))
        run["locomotion"].append({"id": spec["id"], "termination": "completed", "trace": name, "policy_sha256": policy})
    for spec in reference["rounds"]:
        name = f"traces/{spec['id']}.jsonl"
        i, x = 0, 0
        with TraceRecorder(output / name) as recorder:
            recorder.append(sample(0))
            for destination in [1.5, 2.5, 3.5, 5.5]:
                while x < destination - 1e-9:
                    i += 1
                    x = min(destination, x + 0.02)
                    recorder.append(sample(i * 0.02, x=x, speed=1))
                for _ in range(108):
                    i += 1
                    recorder.append(sample(i * 0.02, x=x, speed=0))
        run["rounds"].append({"id": spec["id"], "termination": "completed", "trace": name, "policy_sha256": policy})
    write_json(output / "reference.json", reference)
    write_json(output / "run.json", run)
    return output / "run.json"
