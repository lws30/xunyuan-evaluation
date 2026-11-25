"""Strict JSON and contained file access for evaluation bundles."""

import hashlib
import json
import math
from pathlib import Path


class FormatError(ValueError):
    pass


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FormatError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(text):
    def invalid(value):
        raise FormatError(f"Non-finite JSON number: {value}")
    try:
        return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=invalid)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise FormatError(str(exc)) from exc


def read_json(path):
    return loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def contained(root, name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise FormatError("Expected a nonempty POSIX relative file path")
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise FormatError(f"Unsafe relative path: {name}")
    root = Path(root).resolve()
    resolved = (root / rel).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise FormatError(f"File missing or outside bundle: {name}")
    return resolved


def number(value, label, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise FormatError(f"{label}: expected finite number")
    if minimum is not None and value < minimum:
        raise FormatError(f"{label}: expected value >= {minimum}")
    return float(value)


def vector(value, count, label):
    if not isinstance(value, list) or len(value) != count:
        raise FormatError(f"{label}: expected {count}-element array")
    return [number(v, label) for v in value]


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise FormatError(f"{label}: expected nonempty string")
    return value


def boolean(value, label):
    if type(value) is not bool:
        raise FormatError(f"{label}: expected boolean")
    return value


def indexed(rows, key, label):
    if not isinstance(rows, list):
        raise FormatError(f"{label}: expected array")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise FormatError(f"{label}: expected object")
        identity = text(row.get(key), f"{label}.{key}")
        if identity in result:
            raise FormatError(f"{label}: duplicate ID {identity}")
        result[identity] = row
    return result
