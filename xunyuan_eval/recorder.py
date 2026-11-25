"""Save simulation states as JSONL records."""

import json
from pathlib import Path

from .io import FormatError
from .validation import validate_sample


class TraceRecorder:
    """Save one state per physics step, using a fresh file for each trial."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("x", encoding="utf-8")
        self.last = None

    def append(self, sample):
        validate_sample(sample)
        if self.last is None and abs(sample["time_s"]) > 1e-9:
            raise FormatError("Recorder must start at time zero")
        if self.last is not None and sample["time_s"] <= self.last:
            raise FormatError("Recorder timestamps must increase")
        self.stream.write(json.dumps(sample, allow_nan=False, separators=(",", ":")) + "\n")
        self.stream.flush()
        self.last = sample["time_s"]

    def close(self):
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
