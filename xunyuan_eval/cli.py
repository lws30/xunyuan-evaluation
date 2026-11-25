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
    parser = argparse.ArgumentParser(description="巡渊 S10 测评：运行选手项目，计算路线、扰动和视频识别成绩")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="v1：生成旧版样例记录")
    demo.add_argument("--output", type=Path, required=True, help="保存样例的目录")
    descriptions = {"validate": "v1：检查运行记录", "evaluate": "v1：计算旧版成绩",
                    "prepare-submission": "v1：打包旧版运行记录"}
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
    check = sub.add_parser("check-submission", help="检查两个项目、权重、AGENT.md 和报告")
    check.add_argument("--submission", type=Path, required=True)
    check.add_argument("--smoke", action="store_true", help="实际启动两个项目并各调用一次")
    pack = sub.add_parser("package-models", help="把选手的模型和报告打成提交包")
    pack.add_argument("--submission", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    run_model = sub.add_parser("run-submission", help="在五张赛道和测试视频中运行选手模型")
    run_model.add_argument("--submission", type=Path, required=True)
    run_model.add_argument("--challenge", type=Path, default=Path("challenges/v3"))
    run_model.add_argument("--output", type=Path, required=True)
    run_model.add_argument("--videos", type=Path)
    run_model.add_argument("--video-reference", type=Path)
    run_model.add_argument("--split", choices=["train", "test"], default="train", help="train 本地练习；test 组织方测试")
    run_model.add_argument("--route", help="只试跑一张地图，例如 map01")
    run_model.add_argument("--max-seconds", type=float, help="缩短试跑时间")
    run_model.add_argument("--seed", type=int, default=20261126, help="扰动随机种子；同一批测试使用相同的值")
    score2 = sub.add_parser("score-challenge", help="按路线30、扰动20、识别20分计算成绩")
    score2.add_argument("--run", type=Path, required=True)
    score2.add_argument("--reference", type=Path, required=True)
    score2.add_argument("--video-reference", type=Path)
    score2.add_argument("--output", type=Path, required=True)
    video2 = sub.add_parser("score-video", help="给一组视频识别结果算分")
    video2.add_argument("--predictions", type=Path, required=True)
    video2.add_argument("--reference", type=Path, required=True)
    video2.add_argument("--output", type=Path, required=True)
    video2.add_argument("--video", help="只查看一段视频的成绩，例如 train01")
    reader2 = sub.add_parser("read-videos", help="用识别项目读取训练或测试视频")
    reader_source = reader2.add_mutually_exclusive_group(required=True)
    reader_source.add_argument("--model", type=Path, help="旧版 ONNX 文件")
    reader_source.add_argument("--submission", type=Path, help="项目 submission.json")
    reader2.add_argument("--videos", type=Path, required=True)
    reader2.add_argument("--split", choices=["train", "test"], required=True)
    reader2.add_argument("--video", help="只读取一段视频，例如 train01")
    reader2.add_argument("--output", type=Path, required=True)
    demo2 = sub.add_parser("demo-v2", help="生成新版评分的样例记录")
    demo2.add_argument("--output", type=Path, required=True)
    demo3 = sub.add_parser("demo-v3", help="生成路线、推力、摩擦和识别评分样例")
    demo3.add_argument("--output", type=Path, required=True)
    manual = sub.add_parser("add-report-score", help="评委填写报告分，生成100分制总成绩")
    manual.add_argument("--report", type=Path, required=True)
    manual.add_argument("--score", type=float, required=True)
    manual.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "add-report-score":
            from .challenge_v2 import add_report_score
            if args.output.resolve()==args.report.resolve():
                raise FormatError("请另选一个文件保存总成绩")
            result=add_report_score(read_json(args.report),args.score)
            write_json(args.output,result)
            print(json.dumps({"final_score":result["final_score"],"output":str(args.output)},ensure_ascii=False))
            return 0
        if args.command in {"check-submission", "package-models", "run-submission"}:
            submission_data = read_json(args.submission)
            if not isinstance(submission_data, dict):
                raise FormatError('提交清单需要是 JSON 对象')
            if submission_data.get('schema_version') == '3.0':
                from .projects import check_projects, package_projects, smoke_projects
                if args.command == 'run-submission':
                    from .project_runtime import run_projects
                    result = run_projects(args.submission, args.challenge, args.output, args.videos,
                        args.video_reference, args.route, args.max_seconds, args.seed, args.split)
                    print(json.dumps({'navigation_control_score': result['navigation_control_score'],
                        'automated_score': result['automated_score'], 'report': str(args.output / 'report.json')}, ensure_ascii=False))
                elif args.command == 'package-models':
                    print(json.dumps(package_projects(args.submission, args.output), ensure_ascii=False))
                elif args.smoke:
                    print(json.dumps(smoke_projects(args.submission), ensure_ascii=False))
                else:
                    data, _ = check_projects(args.submission)
                    print(json.dumps({'valid': True, 'sensors': data['navigation']['sensors']}, ensure_ascii=False))
                return 0
            from .onnx_runtime_v2 import check_submission, run_submission, package_models
            if args.command == "run-submission":
                result = run_submission(args.submission, args.challenge, args.output, args.videos,
                                        args.video_reference, args.route, args.max_seconds, args.seed)
                print(json.dumps({"automated_score": result["automated_score"], "report": str(args.output / "report.json")}, ensure_ascii=False))
            elif args.command == "package-models":
                result=package_models(args.submission,args.output)
                print(json.dumps(result,ensure_ascii=False))
            else:
                _, files, _, _=check_submission(args.submission)
                print(json.dumps({"valid":True,"files":{k:str(v) for k,v in files.items()}},ensure_ascii=False))
            return 0
        if args.command == "read-videos":
            from .onnx_runtime_v2 import model_session, recognize_videos, READER_INPUTS, READER_OUTPUTS
            if args.output.resolve().is_relative_to(args.videos.resolve()) or (args.model and args.output.resolve()==args.model.resolve()):
                raise FormatError("结果文件请放在视频和模型目录以外")
            if args.submission:
                from .projects import check_projects, ProjectSession
                data, files = check_projects(args.submission)
                if args.output.resolve().is_relative_to(args.submission.resolve().parent):
                    raise FormatError('识别结果请放在提交文件夹之外')
                with ProjectSession(files['recognition'], data['recognition'], 'recognition') as reader:
                    recognize_videos(reader,args.videos,read_json(args.videos/'manifest.json'),args.output,args.split,args.video)
                print(json.dumps({'predictions':str(args.output)},ensure_ascii=False))
                return 0
            session=model_session(args.model,READER_INPUTS,READER_OUTPUTS)
            recognize_videos(session,args.videos,read_json(args.videos / "manifest.json"),args.output,args.split,args.video)
            print(json.dumps({"predictions":str(args.output)},ensure_ascii=False))
            return 0
        if args.command == "demo-v2":
            from .demo_v2 import create_demo as create_demo_v2
            print(json.dumps({"run":str(create_demo_v2(args.output))}))
            return 0
        if args.command == 'demo-v3':
            from .demo_v3 import create_demo as create_demo_v3
            print(json.dumps({'run': str(create_demo_v3(args.output))}))
            return 0
        if args.command in {"score-challenge", "score-video"}:
            from .challenge_v2 import evaluate as evaluate_v2, score_video
            reference=read_json(args.reference)
            source=read_json(args.run if args.command=="score-challenge" else args.predictions)
            if not isinstance(source,dict) or not isinstance(reference,dict):
                raise FormatError('输入文件需要是 JSON 对象')
            protected=[args.reference,args.run if args.command=="score-challenge" else args.predictions]
            if args.command=="score-challenge":
                if args.video_reference:protected.append(args.video_reference)
                for group in ["routes","disturbance","friction"]:
                    for item in source.get(group,[]):
                        for key in ["trace","force_record"]:
                            if key in item:protected.append(args.run.resolve().parent / item[key])
                if source.get("video_predictions"):protected.append(args.run.resolve().parent / source["video_predictions"])
            if any(path.resolve()==args.output.resolve() for path in protected):
                raise FormatError("结果文件不能覆盖输入文件")
            if args.command=="score-video":
                if args.video:
                    reference=dict(reference,events=[e for e in reference["events"] if e["video_id"]==args.video])
                    source=dict(source,detections=[d for d in source["detections"] if d["video_id"]==args.video])
                result=score_video(source,reference,include_answers=True)
            else:
                if reference.get('schema_version') == '3.0':
                    from .challenge_v3 import evaluate as evaluate_v2
                result=evaluate_v2(source,reference,args.run.resolve().parent,
                                   read_json(args.video_reference) if args.video_reference else None)
            write_json(args.output,result)
            print(json.dumps({"score":result.get("automated_score",result.get("score")),"output":str(args.output)},ensure_ascii=False))
            return 0
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
    except ImportError as exc:
        print("需要安装运行依赖：python -m pip install -e \".[runtime]\"；"+str(exc),file=sys.stderr)
        return 2
    except (FormatError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"evaluation error: {exc}", file=sys.stderr)
        return 2
