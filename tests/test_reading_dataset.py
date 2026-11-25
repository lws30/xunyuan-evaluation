import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from xunyuan_eval.cli import main
from xunyuan_eval.io import FormatError
from xunyuan_eval.reading_dataset import reading_reference
from xunyuan_eval.readings import evaluate_readings


class ReadingDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = Path(__file__).resolve().parents[1] / "datasets/readings_v3/images/network_T01.png"
        (self.root / "image.png").write_bytes(self.image.read_bytes())
        self.rows = [dict(id="test_0", split="test", readable=True, status="ok", value="-08.3",
                          text="-08.3C", unit="C", image_path="image.png", crop_path="image.png"),
                     dict(id="test_1", split="test", readable=False, status="abstain", value=None,
                          text=None, source_value="31.4", unit="C", image_path="image.png", crop_path="image.png")]
        (self.root / "manifest.json").write_text('{"version":"test-dataset"}')
        self.write_rows()

    def write_rows(self):
        (self.root / "test.jsonl").write_text(''.join(json.dumps(row) + '\n' for row in self.rows))

    def test_export_feeds_reading_diagnostic_without_exposing_hidden_targets(self):
        reference = reading_reference(self.root, "test")
        self.assertEqual(reference["events"][0]["answer"], "-08.3")
        self.assertNotIn("answer", reference["events"][1])
        self.assertNotIn("source_value", reference["events"][1])
        predictions = {"results": [dict(id="test_0", target_id="test_0", status="ok", value="-8.3", unit="C"),
                                   dict(id="test_1", target_id="test_1", status="abstain", reason="occluded")]}
        self.assertEqual(evaluate_readings(predictions, reference)["passed"], 2)

    def test_missing_and_escaping_images_are_rejected(self):
        for path in ["missing.png", "../outside.png"]:
            with self.subTest(path=path):
                self.rows[0]["image_path"] = path
                self.write_rows()
                with self.assertRaises(FormatError):
                    reading_reference(self.root, "test")

    def test_mixed_split_duplicate_ids_and_unreadable_answers_are_rejected(self):
        original = copy.deepcopy(self.rows)
        for key, value, index in [("split", "train", 0), ("id", "test_0", 1), ("value", "31.4", 1)]:
            with self.subTest(key=key):
                self.rows = copy.deepcopy(original)
                self.rows[index][key] = value
                self.write_rows()
                with self.assertRaises(FormatError):
                    reading_reference(self.root, "test")

    def test_modified_annotations_fail_checksum_validation(self):
        sha = hashlib.sha256((self.root / "test.jsonl").read_bytes()).hexdigest()
        (self.root / "manifest.json").write_text(json.dumps({"manifests_sha256": {"test": sha}}))
        self.rows[0]["value"] = "20.0"
        self.write_rows()
        with self.assertRaises(FormatError):
            reading_reference(self.root, "test")
        (self.root / "manifest.json").write_text('{"manifests_sha256":[]}')
        with self.assertRaises(FormatError):
            reading_reference(self.root, "test")

    def test_cli_cannot_replace_dataset_annotations(self):
        path = self.root / "test.jsonl"
        before = path.read_bytes()
        self.assertEqual(main(["reading-reference", "--dataset", str(self.root), "--split", "test",
                               "--output", str(path)]), 2)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
