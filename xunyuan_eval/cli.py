"""Offline evaluation, image-reference export, and submission CLI."""

import argparse
import json
import sys
from pathlib import Path

from .demo import create_demo
from .evaluator import evaluate
from .io import FormatError, read_json, write_json
from .readings import evaluate_readings
from .reading_dataset import reading_reference
from .submission import prepare_submission
from .validation import validate_reference, validate_run


def main(argv=None):
    parser = argparse.ArgumentParser(description="巡渊公开开发自评工具（规则候选版，非正式裁判成绩）")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="生成合成协议样例，不运行机器人仿真")
    demo.add_argument("--output", type=Path, required=True)
    for name in ["validate", "evaluate", "prepare-submission"]:
        p = sub.add_parser(name)
        p.add_argument("--run", type=Path, required=True)
        p.add_argument("--reference", type=Path, required=True)
        if name != "validate":
            p.add_argument("--output", type=Path, required=True)
            p.add_argument("--stage", choices=["preliminary", "final"], default="preliminary")
    readings = sub.add_parser("readings", help="离线读数诊断，不计入赛事总分")
    readings.add_argument("--predictions", type=Path, required=True)
    readings.add_argument("--reference", type=Path, required=True)
    readings.add_argument("--output", type=Path, required=True)
    images = sub.add_parser("reading-reference", help="从温度图片数据集导出读数诊断参考")
    images.add_argument("--dataset", type=Path, required=True)
    images.add_argument("--split", choices=["train", "val", "test"], required=True)
    images.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            path = create_demo(args.output)
            print(json.dumps({"run": str(path), "kind": "synthetic_protocol_fixture_not_robot_simulation"}))
            return 0
        if args.command == "reading-reference":
            if args.output.resolve().is_relative_to(args.dataset.resolve()):
                raise FormatError("Output must be outside the source dataset")
            result = reading_reference(args.dataset, args.split)
            write_json(args.output, result)
            print(json.dumps({"reference": str(args.output), "events": len(result["events"]),
                              "split": args.split}, ensure_ascii=False))
            return 0
        if args.command == "readings":
            if args.output.resolve() in {args.predictions.resolve(), args.reference.resolve()}:
                raise FormatError("Output cannot overwrite input files")
            result = evaluate_readings(read_json(args.predictions), read_json(args.reference))
            write_json(args.output, result)
        elif args.command == "prepare-submission":
            result = prepare_submission(args.run, args.reference, args.output, args.stage)
        else:
            ref = validate_reference(read_json(args.reference))
            run = read_json(args.run)
            if args.command == "validate":
                validate_run(run, ref, args.run.resolve().parent)
                result = {"valid": True, "reference_id": ref["reference_id"],
                          "note": "Missing expected trials/events remain in the scoring denominator."}
            else:
                if args.output.resolve() in {args.run.resolve(), args.reference.resolve()}:
                    raise FormatError("Output cannot overwrite input files")
                result = evaluate(run, ref, args.run.resolve().parent, reference_path=args.reference,
                                  run_path=args.run, stage=args.stage)
                # Do not allow an output path to replace any input telemetry.
                for kind in ["locomotion", "rounds"]:
                    for row in run[kind]:
                        if args.output.resolve() == (args.run.resolve().parent / row["trace"]).resolve():
                            raise FormatError("Output cannot overwrite telemetry")
                write_json(args.output, result)
        if args.command == "evaluate":
            print(json.dumps({"automated_score": result["automated_score"], "automated_maximum": 70,
                              "pending_manual": result["pending_manual"], "official_result": False,
                              "report": str(args.output)}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (FormatError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"evaluation error: {exc}", file=sys.stderr)
        return 2
