"""Compute development scores from evaluator-recorded telemetry."""

import math

from . import __version__
from .geometry import HoldWindow, angle_error, crossing, signed_distance
from .io import contained, digest
from .validation import GROUPS, validate_reference, validate_run


def usable_prefix(rows, rules, timeout_s):
    accepted = []
    for row in rows:
        if row["time_s"] > timeout_s + 1e-9:
            return accepted, "timeout"
        if accepted and row["time_s"] - accepted[-1]["time_s"] > rules["max_gap_s"] + 1e-9:
            return accepted, "telemetry_gap"
        reason = (
            "forbidden_contact" if row["forbidden_contacts"] else
            "out_of_bounds" if row["out_of_bounds"] else
            "illegal_action" if not row["action_valid"] else
            "manual_intervention" if row["intervention"] else
            "fall" if max(abs(row["roll_rad"]), abs(row["pitch_rad"])) > rules["fall_angle_rad"] else None
        )
        if reason:
            return accepted, reason
        accepted.append(row)
    return accepted, None


def trial_result(spec, item, rows, rules):
    result = {"id": spec["id"], "group": spec["group"], "passed": False}
    if item is None:
        return {**result, "reason": "missing_trial"}
    usable, stop = usable_prefix(rows, rules, spec["timeout_s"])
    if stop:
        return {**result, "reason": stop}
    if item["termination"] != "completed":
        return {**result, "reason": item["termination"]}
    distances = [min(signed_distance(p, spec["exit"]) for p in r["envelope_points_m"]) for r in usable]
    if not distances or distances[0] > 0:
        return {**result, "reason": "no_pre_exit_envelope"}
    finish = None
    for index in range(1, len(usable)):
        if distances[index - 1] <= 1e-9 < distances[index]:
            row = usable[index]
            nx, ny, _ = spec["exit"]["normal"]
            cx, cy, _ = spec["exit"]["center_m"]
            lateral = [abs(-(p[0] - cx) * ny + (p[1] - cy) * nx) for p in row["envelope_points_m"]]
            if max(lateral) > spec["exit"]["width_m"] / 2 + 1e-9:
                return {**result, "reason": "envelope_outside_exit_gate"}
            finish = row["time_s"]
            break
    # Crossing only the base centre never satisfies the full-envelope test.
    if finish is None:
        return {**result, "reason": "whole_envelope_did_not_exit"}
    return {**result, "passed": True, "reason": "completed", "completion_time_s": finish}


def round_result(spec, item, rows, rules):
    nav = [{"id": e["id"], "passed": False, "reason": "not_reached"} for e in spec["navigation"]]
    docks = [{"id": e["id"], "target_id": e["target_id"], "passed": False, "reason": "not_reached"}
             for e in spec["docking"]]
    result = {"id": spec["id"], "navigation": nav, "docking": docks}
    if item is None:
        return {**result, "stop_reason": "missing_round", "route_completed": False}
    usable, stop = usable_prefix(rows, rules, spec["timeout_s"])
    crossings = []
    for a, b in zip(usable, usable[1:]):
        for name, gate in spec["gates"].items():
            t = crossing(a, b, gate)
            if t is not None:
                crossings.append((t, name))
    crossings.sort()
    active = 0
    reached = {}
    first_choice = None
    for time_s, gate_id in crossings:
        if active == len(nav):
            break
        event = spec["navigation"][active]
        if gate_id not in event["candidates"]:
            continue
        if first_choice is None:
            first_choice = gate_id
            nav[active].update(first_gate=gate_id, time_s=time_s,
                               passed=gate_id == event["correct_gate"],
                               reason="correct_exit" if gate_id == event["correct_gate"] else "wrong_first_exit")
        if gate_id == event["correct_gate"]:
            reached[event["id"]] = time_s
            active += 1
            first_choice = None
    for event, outcome in zip(spec["docking"], docks):
        start = reached.get(event["after_nav"])
        if start is None:
            continue
        end = reached.get(event["before_nav"], spec["timeout_s"])
        window = HoldWindow(rules["dock_hold_s"], rules["max_gap_s"])
        outcome["reason"] = "no_continuous_stable_window"
        for row in usable:
            if not start <= row["time_s"] < end:
                continue
            distance = math.dist(row["position_m"][:2], event["position_m"][:2])
            good = (distance <= rules["dock_position_m"] + 1e-9
                    and abs(angle_error(row["yaw_rad"], event["yaw_rad"])) <= rules["dock_yaw_rad"] + 1e-9
                    and row["speed_mps"] <= rules["dock_speed_mps"] + 1e-9
                    and abs(row["yaw_rate_rps"]) <= rules["dock_yaw_rate_rps"] + 1e-9)
            if window.update(row["time_s"], good):
                outcome.update(passed=True, reason="stable_window", start_s=window.since, end_s=row["time_s"])
                break
    # A missing return gate cannot be replaced by a claimed task-complete flag.
    complete = (active == len(nav) and all(x["passed"] for x in docks)
                and stop is None and item["termination"] == "completed")
    return {**result, "stop_reason": stop or item["termination"], "route_completed": complete,
            "ordered_route_reached": active == len(nav),
            "scored_until_s": usable[-1]["time_s"] if usable else 0}


def evaluate(run, ref, root, *, reference_path=None, run_path=None, stage="preliminary"):
    validate_reference(ref)
    loaded = validate_run(run, ref, root)
    trials = {item["id"]: item for item in run["locomotion"]}
    actual_rounds = {item["id"]: item for item in run["rounds"]}
    locomotion = [trial_result(spec, trials.get(spec["id"]), loaded.get(("locomotion", spec["id"]), []),
                               ref["rules"]) for spec in ref["locomotion"]]
    rounds = [round_result(spec, actual_rounds.get(spec["id"]), loaded.get(("rounds", spec["id"]), []),
                          ref["rules"]) for spec in ref["rounds"]]
    groups = {}
    for group, denominator in GROUPS.items():
        passed = sum(row["passed"] for row in locomotion if row["group"] == group)
        groups[group] = {"passed": passed, "denominator": denominator, "score": 5 * passed / denominator,
                         "maximum": 5}
    navigation_passed = sum(item["passed"] for row in rounds for item in row["navigation"])
    docking_passed = sum(item["passed"] for row in rounds for item in row["docking"])
    loc_score = sum(row["score"] for row in groups.values())
    nav_score = 25 * navigation_passed / 15
    dock_score = 20 * docking_passed / 12
    manual = ({"report": 30} if stage == "preliminary" else {"record_review": 25, "deployment": 5})
    trace_hashes = {item["trace"]: digest(contained(root, item["trace"]))
                    for kind in ["locomotion", "rounds"] for item in run[kind]}
    return {
        "schema_version": "1.0", "evaluator_version": __version__, "reference_id": ref["reference_id"],
        "rules_status": ref["status"], "evaluation_kind": "public_development_self_evaluation",
        "official_result": False, "stage": stage, "team": run["team"], "method": run["method"],
        "policy_sha256": run["policy_sha256"],
        "provenance": {"reference_sha256": digest(reference_path) if reference_path else None,
                       "run_sha256": digest(run_path) if run_path else None,
                       "trace_sha256": trace_hashes},
        "scores": {
            "locomotion": {"score": loc_score, "maximum": 25, "passed": sum(x["passed"] for x in locomotion),
                           "denominator": 21, "groups": groups},
            "navigation": {"score": nav_score, "maximum": 25, "passed": navigation_passed, "denominator": 15},
            "docking": {"score": dock_score, "maximum": 20, "passed": docking_passed, "denominator": 12}},
        "automated_score": loc_score + nav_score + dock_score, "automated_maximum": 70,
        "pending_manual": manual, "final_score": None,
        "details": {"locomotion": locomotion, "rounds": rounds},
        "trust_boundary": "Scores assume complete evaluator-recorded telemetry. Participant-edited logs are not official evidence.",
    }
