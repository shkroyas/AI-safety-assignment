import json

from guardbank.audit import AuditLog, verify
from guardbank.types import GuardResult


def _write_three(path):
    log = AuditLog(path)
    for stage in ("input.pii", "input.injection", "output.schema"):
        log.append("req-1", GuardResult.allow(stage, latency_ms=1.0))
    return log


def test_chain_verifies(tmp_path):
    path = tmp_path / "audit.jsonl"
    _write_three(path)
    assert verify(path) is None
    assert len(path.read_text().splitlines()) == 3


def test_tampering_detected_at_edited_line(tmp_path):
    path = tmp_path / "audit.jsonl"
    _write_three(path)
    lines = path.read_text().splitlines()
    entry = json.loads(lines[1])
    entry["verdict"] = "block"
    lines[1] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n")
    assert verify(path) == 2


def test_deleted_line_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    _write_three(path)
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n")
    assert verify(path) == 2


def test_chain_continues_across_instances(tmp_path):
    path = tmp_path / "audit.jsonl"
    _write_three(path)
    AuditLog(path).append("req-2", GuardResult.allow("input.pii", latency_ms=1.0))
    assert verify(path) is None


def test_raw_text_not_stored(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    secret = "my phone is 9841234567"
    log.append("req-1", GuardResult.allow("input.pii", latency_ms=1.0), input_text=secret)
    content = path.read_text()
    assert "9841234567" not in content
    entry = json.loads(content.splitlines()[0])
    assert entry["input_len"] == len(secret)
    assert len(entry["input_sha256"]) == 64
