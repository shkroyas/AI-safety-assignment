import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "stop_tests.py"
spec = importlib.util.spec_from_file_location("stop_tests", HOOK)
stop_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stop_tests)


def test_failure_lines_keeps_only_failures_and_summary():
    output = "\n".join(
        [
            "....F..",
            "tests/test_a.py:12: AssertionError: boom",
            "FAILED tests/test_a.py::test_x - AssertionError: boom",
            "ERROR tests/test_b.py - ImportError",
            "1 failed, 6 passed in 0.5s",
        ]
    )
    lines = stop_tests.failure_lines(output)
    assert lines == [
        "FAILED tests/test_a.py::test_x - AssertionError: boom",
        "ERROR tests/test_b.py - ImportError",
        "1 failed, 6 passed in 0.5s",
    ]


def test_failure_lines_caps_length():
    output = "\n".join(f"FAILED tests/t.py::test_{i} - x" for i in range(50))
    assert len(stop_tests.failure_lines(output, limit=10)) == 11  # 10 + "... N more"
