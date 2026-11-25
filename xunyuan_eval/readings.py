"""Compare number and temperature predictions with their reference answers."""

from decimal import Decimal, InvalidOperation

from .io import FormatError, indexed, text


def evaluate_readings(predictions, reference):
    if not isinstance(predictions, dict) or not isinstance(reference, dict):
        raise FormatError("Reading inputs must be JSON objects")
    expected = indexed(reference.get("events"), "id", "reading reference")
    actual = indexed(predictions.get("results"), "id", "reading results")
    if not expected:
        raise FormatError("Reading reference cannot be empty")
    if actual.keys() - expected.keys():
        raise FormatError("Unknown reading event IDs")
    outcomes = []
    try:
        tolerance = Decimal(str(reference.get("temperature_tolerance_C", "0.1")))
    except InvalidOperation as exc:
        raise FormatError("Invalid temperature tolerance") from exc
    if not tolerance.is_finite() or tolerance < 0:
        raise FormatError("Invalid temperature tolerance")
    for identity, truth in expected.items():
        if type(truth.get("readable")) is not bool or truth.get("kind") not in {"digits", "temperature_display"}:
            raise FormatError("Invalid reading reference")
        text(truth.get("target_id"), "reference target_id")
        if truth["readable"]:
            text(truth.get("answer"), "reference answer")
            if truth["kind"] == "temperature_display":
                try:
                    answer = Decimal(truth["answer"])
                    if not answer.is_finite():
                        raise InvalidOperation
                except InvalidOperation as exc:
                    raise FormatError("Invalid temperature reference answer") from exc
        item = actual.get(identity)
        reason = "missing_event"
        if item is not None:
            if item.get("status") not in {"ok", "abstain", "error"}:
                raise FormatError("Invalid reading status")
            passed = item.get("target_id") == truth["target_id"]
            if truth["readable"]:
                passed = passed and item["status"] == "ok"
                if truth["kind"] == "digits":
                    passed = passed and isinstance(item.get("value"), str) and item["value"] == truth["answer"] and item.get("unit") is None
                else:
                    try:
                        if not isinstance(item.get("value"), str):
                            raise InvalidOperation
                        value = Decimal(item["value"])
                        answer = Decimal(truth["answer"])
                        if not answer.is_finite():
                            raise FormatError("Non-finite reference answer")
                        passed = passed and value.is_finite() and item.get("unit") == "C" and abs(value - answer) <= tolerance
                    except InvalidOperation:
                        passed = False
            else:
                passed = passed and item["status"] == "abstain" and isinstance(item.get("reason"), str) and bool(item["reason"].strip())
            reason = "matched" if passed else "mismatch_or_invalid_rejection"
        outcomes.append({"id": identity, "passed": reason == "matched", "reason": reason})
    return {"kind": "public_reading_diagnostic", "competition_score": None,
            "denominator": len(expected), "passed": sum(x["passed"] for x in outcomes), "events": outcomes}
