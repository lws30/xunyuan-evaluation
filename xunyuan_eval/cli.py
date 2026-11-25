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
    parser = argparse.ArgumentParser(description="巡渊 S10 评分工具：读取运行记录，计算成绩并打包")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="生成一组样例运行记录")
    demo.add_argument("--output", type=Path, required=True, help="保存样例的目录")
    descriptions = {"validate": "检查运行记录", "evaluate": "计算成绩并生成报告",
                    "prepare-submission": "打包运行记录和成绩"}
    for name in ["validate", "evaluate", "prepare-submission"]:
        p = sub.add_parser(name, help=descriptions[name])
        p.add_argument("--run", type=Path, required=True, help="运行清单 run.json")
        p.add_argument("--reference", type=Path, required=True, help="本次赛道的规则文件")
        if name != "validate":
            p.add_argument("--output", type=Path, required=True, help="结果文件的保存位置")
            p.add_argument("--stage", choices=["preliminary", "final"], default="preliminary",
                           help="preliminary 为初赛，final 为决赛")
    readings = sub.add_parser("readings", help="比较图片识别结果和正确答案")
    readings.add_argument("--predictions", type=Path, required=True, help="OCR 识别结果文件")
    readings.add_argument("--reference", type=Path, required=True, help="正确答案文件")
    readings.add_argument("--output", type=Path, required=True, help="比较结果的保存位置")
    images = sub.add_parser("reading-reference", help="根据温度图片标注生成答案文件")
    images.add_argument("--dataset", type=Path, required=True, help="图片和标注所在目录")
    images.add_argument("--split", choices=["train", "val", "test"], required=True,
                        help="train 为训练，val 为验证，test 为测试")
    images.add_argument("--output", type=Path, required=True, help="答案文件的保存位置")
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
                          "note": "未完成的测试按 0 分计算，总次数保持不变。"}
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
