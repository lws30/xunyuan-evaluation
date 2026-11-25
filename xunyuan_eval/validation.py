"""Validate the versioned public protocol before assigning any points."""

import re

from .io import FormatError, boolean, contained, indexed, loads, number, text, vector

SCHEMA = "1.0"
TERMINATIONS = {"completed", "timeout", "crashed", "safety_stop"}
GROUPS = {"straight_turn": 6, "slopes": 6, "stairs_up": 3, "stairs_down": 3, "friction": 3}


def gate(value, label):
    if not isinstance(value, dict):
        raise FormatError(f"{label}: expected gate object")
    vector(value.get("center_m"), 3, label)
    normal = vector(value.get("normal"), 3, label)
    if abs(sum(n * n for n in normal) - 1) > 1e-6 or abs(normal[2]) > 1e-9:
        raise FormatError(f"{label}: normal must be a horizontal unit vector")
    if number(value.get("width_m"), label, 0) == 0:
        raise FormatError(f"{label}: gate width must be positive")


def validate_reference(ref):
    if not isinstance(ref, dict) or ref.get("schema_version") != SCHEMA:
        raise FormatError("Unsupported reference schema_version")
    text(ref.get("reference_id"), "reference_id")
    text(ref.get("status"), "status")
    rules = ref.get("rules")
    if not isinstance(rules, dict):
        raise FormatError("Missing rules")
    for key in ["sample_dt_s", "max_gap_s", "dock_position_m", "dock_yaw_rad", "dock_speed_mps",
                "dock_yaw_rate_rps", "dock_hold_s", "fall_angle_rad"]:
        if number(rules.get(key), key, 0) == 0:
            raise FormatError(f"{key} must be positive")
    if rules["max_gap_s"] < rules["sample_dt_s"]:
        raise FormatError("max_gap_s is smaller than sample_dt_s")
    trials = indexed(ref.get("locomotion"), "id", "reference locomotion")
    counts = dict.fromkeys(GROUPS, 0)
    for trial in trials.values():
        if trial.get("group") not in counts:
            raise FormatError("Unknown locomotion group")
        counts[trial["group"]] += 1
        gate(trial.get("exit"), trial["id"])
        number(trial.get("timeout_s"), "trial timeout", 0.001)
    if counts != GROUPS:
        raise FormatError(f"Expected fixed 21-trial denominator: {GROUPS}")
    rounds = indexed(ref.get("rounds"), "id", "reference rounds")
    if len(rounds) != 3:
        raise FormatError("Expected exactly three rounds")
    for rnd in rounds.values():
        number(rnd.get("timeout_s"), "round timeout", 0.001)
        gates = rnd.get("gates")
        if not isinstance(gates, dict):
            raise FormatError("Missing gates")
        for name, value in gates.items():
            gate(value, name)
        nav = indexed(rnd.get("navigation"), "id", "reference navigation")
        docks = indexed(rnd.get("docking"), "id", "reference docking")
        if len(nav) != 5 or len(docks) != 4:
            raise FormatError("Each round needs five navigation events and four docking events")
        for event in nav.values():
            candidates = event.get("candidates")
            if (not isinstance(candidates, list) or not candidates
                    or any(not isinstance(c, str) or c not in gates for c in candidates)
                    or len(set(candidates)) != len(candidates)
                    or event.get("correct_gate") not in candidates):
                raise FormatError("Invalid navigation gate references")
        order = list(nav)
        for dock in docks.values():
            vector(dock.get("position_m"), 3, "dock position")
            number(dock.get("yaw_rad"), "dock yaw")
            text(dock.get("target_id"), "dock target")
            if dock.get("after_nav") not in nav:
                raise FormatError("Unknown docking prerequisite")
            before = dock.get("before_nav")
            if before is not None and (before not in nav or order.index(before) <= order.index(dock["after_nav"])):
                raise FormatError("Invalid docking event window")
    return ref


def validate_sample(row):
    if not isinstance(row, dict):
        raise FormatError("Telemetry row must be an object")
    number(row.get("time_s"), "time_s", 0)
    vector(row.get("position_m"), 3, "position_m")
    for key in ["yaw_rad", "roll_rad", "pitch_rad", "yaw_rate_rps"]:
        number(row.get(key), key)
    number(row.get("speed_mps"), "speed_mps", 0)
    points = row.get("envelope_points_m")
    if not isinstance(points, list) or len(points) < 4:
        raise FormatError("envelope_points_m needs at least four full-envelope support points")
    for point in points:
        vector(point, 3, "envelope point")
    count = row.get("forbidden_contacts")
    if type(count) is not int or count < 0:
        raise FormatError("forbidden_contacts must be a nonnegative integer")
    for key in ["out_of_bounds", "action_valid", "intervention"]:
        boolean(row.get(key), key)


def load_trace(root, name):
    path = contained(root, name)
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise FormatError(f"{name}:{line_number}: blank telemetry row")
            row = loads(line)
            validate_sample(row)
            if rows and row["time_s"] <= rows[-1]["time_s"]:
                raise FormatError(f"{name}:{line_number}: timestamps must increase")
            if rows and len(row["envelope_points_m"]) != len(rows[0]["envelope_points_m"]):
                raise FormatError(f"{name}:{line_number}: collision envelope point count changed")
            rows.append(row)
    if not rows or abs(rows[0]["time_s"]) > 1e-9:
        raise FormatError(f"{name}: trace must start at time 0 with at least one row")
    return rows


def validate_run(run, ref, root):
    if not isinstance(run, dict) or run.get("schema_version") != SCHEMA:
        raise FormatError("Unsupported run schema_version")
    if run.get("reference_id") != ref["reference_id"]:
        raise FormatError("Reference ID mismatch")
    for key in ["team", "method"]:
        text(run.get(key), key)
    if not isinstance(run.get("policy_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", run["policy_sha256"]):
        raise FormatError("policy_sha256 must be 64 lowercase hexadecimal characters")
    loaded = {}
    used_paths = set()
    for kind in ["locomotion", "rounds"]:
        actual = indexed(run.get(kind), "id", kind)
        expected = {item["id"] for item in ref[kind]}
        if actual.keys() - expected:
            raise FormatError(f"Unknown {kind} IDs: {sorted(actual.keys() - expected)}")
        for identity, item in actual.items():
            if item.get("termination") not in TERMINATIONS:
                raise FormatError(f"{identity}: invalid termination")
            if item.get("policy_sha256") != run["policy_sha256"]:
                raise FormatError(f"{identity}: policy differs from frozen run policy")
            path = contained(root, item.get("trace"))
            if path in used_paths:
                raise FormatError("A telemetry file cannot represent multiple trials/rounds")
            used_paths.add(path)
            loaded[(kind, identity)] = load_trace(root, item["trace"])
    return loaded
