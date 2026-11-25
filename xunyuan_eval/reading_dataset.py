"""Convert public temperature-image annotations into reading references."""

from decimal import Decimal, InvalidOperation
from pathlib import Path

from .io import FormatError, contained, digest, loads, read_json, text


def reading_reference(dataset, split):
    dataset = Path(dataset)
    if split not in {"train", "val", "test"}:
        raise FormatError("Unknown dataset split")
    manifest = read_json(dataset / "manifest.json")
    if not isinstance(manifest, dict):
        raise FormatError("Dataset manifest must be an object")
    annotation = contained(dataset, split + ".jsonl")
    hashes = manifest.get("manifests_sha256", {})
    if not isinstance(hashes, dict):
        raise FormatError("Dataset annotation checksums must be an object")
    expected_hash = hashes.get(split)
    if expected_hash is not None and digest(annotation) != expected_hash:
        raise FormatError("Dataset annotation checksum mismatch")
    events = []
    seen = set()
    with annotation.open(encoding="utf-8") as stream:
        for line in stream:
            row = loads(line)
            if not isinstance(row, dict):
                raise FormatError("Dataset annotation must be an object")
            identity = text(row.get("id"), "sample id")
            if identity in seen:
                raise FormatError("Duplicate dataset sample ID")
            seen.add(identity)
            if row.get("split") != split:
                raise FormatError("Dataset sample belongs to a different split")
            readable = row.get("readable")
            if type(readable) is not bool or row.get("unit") != "C":
                raise FormatError("Invalid temperature sample label")
            if row.get("status") != ("ok" if readable else "abstain"):
                raise FormatError("Sample status disagrees with readability")
            for key in ["image_path", "crop_path"]:
                contained(dataset, row.get(key))
            event = {"id": identity, "target_id": identity, "kind": "temperature_display",
                     "readable": readable, "image_path": row["image_path"],
                     "crop_path": row["crop_path"], "unit": "C"}
            if readable:
                value = text(row.get("value"), "sample value")
                try:
                    if not Decimal(value).is_finite():
                        raise InvalidOperation
                except InvalidOperation as exc:
                    raise FormatError("Invalid temperature value") from exc
                event["answer"] = value
            elif row.get("value") is not None or row.get("text") is not None:
                raise FormatError("Unreadable samples must have null OCR targets")
            events.append(event)
    if not events:
        raise FormatError("Dataset split cannot be empty")
    return {"dataset_id": manifest.get("version", "temperature-v3"), "split": split,
            "source": "public_synthetic_temperature_images", "temperature_tolerance_C": "0.1",
            "image_paths_relative_to": "dataset directory passed to reading-reference",
            "events": events}
