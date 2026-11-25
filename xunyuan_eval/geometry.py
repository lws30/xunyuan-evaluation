"""Geometry and continuous holding windows, independent of simulation engine."""

import math


def angle_error(a, b):
    return math.atan2(math.sin(a - b), math.cos(a - b))


def signed_distance(point, gate):
    return sum((a - b) * n for a, b, n in zip(point, gate["center_m"], gate["normal"]))


def crossing(a, b, gate):
    """Forward crossing of a finite gate; return interpolated time or None."""
    da = signed_distance(a["position_m"], gate)
    db = signed_distance(b["position_m"], gate)
    if not da < 0 <= db:
        return None
    fraction = -da / (db - da)
    point = [x + fraction * (y - x) for x, y in zip(a["position_m"], b["position_m"])]
    nx, ny, _ = gate["normal"]
    lateral = -(point[0] - gate["center_m"][0]) * ny + (point[1] - gate["center_m"][1]) * nx
    if abs(lateral) > gate["width_m"] / 2 + 1e-9:
        return None
    return a["time_s"] + fraction * (b["time_s"] - a["time_s"])


class HoldWindow:
    def __init__(self, duration_s, max_gap_s):
        self.duration = duration_s
        self.max_gap = max_gap_s
        self.since = None
        self.last = None

    def update(self, time_s, good):
        if self.last is not None and (time_s <= self.last or time_s - self.last > self.max_gap + 1e-9):
            self.since = None
        self.last = time_s
        if not good:
            self.since = None
            return False
        if self.since is None:
            self.since = time_s
        return time_s - self.since >= self.duration - 1e-9
