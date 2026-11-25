"""Record a hinged body's gravity-driven tipping and check the fall result.

Run from the repository: python -m examples.mujoco_fall_check --output artifacts/fall
"""

import argparse
import math
from pathlib import Path

from xunyuan_eval.evaluator import trial_result, usable_prefix
from xunyuan_eval.io import read_json, write_json
from xunyuan_eval.mujoco_recorder import MuJoCoSampler
from xunyuan_eval.recorder import TraceRecorder
from xunyuan_eval.validation import load_trace


MODEL = """
<mujoco>
  <option timestep="0.005" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="3 3 .1"/>
    <body name="base_link" pos="0 0 .1">
      <joint name="tip" type="hinge" axis="1 0 0" damping=".02"/>
      <geom name="body" type="box" pos="0 0 .4" size=".1 .1 .4" mass="1"/>
    </body>
  </worldbody>
</mujoco>
"""


def run_check(output):
    import mujoco

    output = Path(output)
    if output.exists():
        raise ValueError("Choose a new output directory to preserve previous traces")
    output.mkdir(parents=True)
    root = Path(__file__).resolve().parents[1]
    rules = read_json(root / "references/public_dev_v3_candidate.json")["rules"]
    spec = {"id": "gravity_tip", "group": "straight_turn", "timeout_s": 2,
            "exit": {"center_m": [2, 0, 0], "normal": [1, 0, 0], "width_m": 2}}
    results = {}
    for name, initial_angle in [("upright", 0.0), ("tipping", 0.05)]:
        model = mujoco.MjModel.from_xml_string(MODEL)
        data = mujoco.MjData(model)
        data.qpos[0] = initial_angle
        mujoco.mj_forward(model, data)
        sampler = MuJoCoSampler(model, root_body="base_link", terrain_geom_names=["floor"],
                                allowed_terrain_body_names=["base_link"],
                                boundary_check=lambda points: any(abs(p[0]) > 2 or abs(p[1]) > 2 for p in points))
        filename = name + ".jsonl"
        with TraceRecorder(output / filename) as recorder:
            recorder.append(sampler.sample(data, action_valid=True))
            for _ in range(240):
                mujoco.mj_step(model, data)
                mujoco.mj_forward(model, data)
                recorder.append(sampler.sample(data, action_valid=True))
        rows = load_trace(output, filename)
        accepted, stop = usable_prefix(rows, rules, 2)
        judged = trial_result(spec, {"termination": "completed"}, rows, rules)
        results[name] = {"samples": len(rows), "stop_reason": stop,
                         "maximum_tilt_deg": math.degrees(max(max(abs(r["roll_rad"]), abs(r["pitch_rad"])) for r in rows)),
                         "valid_until_s": accepted[-1]["time_s"] if accepted else 0,
                         "trial_result": judged}
    if results["upright"]["stop_reason"] is not None:
        raise RuntimeError("Upright fixture unexpectedly failed")
    if results["tipping"]["stop_reason"] != "fall" or results["tipping"]["trial_result"]["reason"] != "fall":
        raise RuntimeError("Gravity-driven tipping was not identified as fall")
    result = {"fixture": "gravity_driven_hinged_body", "mujoco_version": mujoco.__version__,
              "timestep_s": 0.005, "fall_threshold_deg": math.degrees(rules["fall_angle_rad"]),
              "checks_passed": True, "cases": results}
    write_json(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="让方块在重力下倾倒，检查姿态记录和摔倒判定")
    parser.add_argument("--output", type=Path, required=True, help="保存两份运行记录和检查结果的目录")
    args = parser.parse_args()
    print(run_check(args.output))
