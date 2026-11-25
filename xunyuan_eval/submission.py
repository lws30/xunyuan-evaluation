"""Build a reproducible submission archive from run records."""

import json
import zipfile
from pathlib import Path

from .io import FormatError, contained, digest, read_json, text


def prepare_submission(run_path, reference_path, output, stage="preliminary"):
    # Compute the report from the input records before packing the archive.
    from .evaluator import evaluate
    run_path, reference_path, output = map(Path, (run_path, reference_path, output))
    if output.exists():
        raise FormatError("Submission output already exists; choose a new path")
    root = run_path.resolve().parent
    run, reference = read_json(run_path), read_json(reference_path)
    report = evaluate(run, reference, root, run_path=run_path, reference_path=reference_path, stage=stage)
    files = {}
    archived = {}
    # Use fixed archive names for manifest/reference; traces are relative to run.json.
    for archive_name, path in [("run.json", run_path), ("reference.json", reference_path)]:
        archived[archive_name] = path.resolve()
    for kind in ["locomotion", "rounds"]:
        for row in run[kind]:
            name = row["trace"]
            path = contained(root, name)
            if name in archived and archived[name] != path:
                raise FormatError(f"Conflicting archive path: {name}")
            if Path(name).parts[0] in {"submission.json", "report.json", "reference.json", "run.json"}:
                raise FormatError("Trace path conflicts with reserved archive entry")
            archived[name] = path
    for name, path in archived.items():
        files[name] = {"sha256": digest(path), "bytes": path.stat().st_size}
    index = {"schema_version": "1.0", "team": text(run["team"], "team"), "method": text(run["method"], "method"),
             "reference_id": reference["reference_id"], "policy_sha256": run["policy_sha256"],
             "submission_type": "public_self_evaluation_evidence", "official_result": False,
             "files": files, "report": "report.json"}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(archived.items()):
            _write(archive, name, path.read_bytes())
        _write(archive, "report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode())
        _write(archive, "submission.json", json.dumps(index, ensure_ascii=False, indent=2).encode())
    return {"path": str(output), "sha256": digest(output), "automated_score": report["automated_score"],
            "automated_maximum": 70, "official_result": False}


def _write(archive, name, data):
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)
