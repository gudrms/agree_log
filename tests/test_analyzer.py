#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small smoke test for response-time extraction."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from log_performance_analyzer import LogPerformanceAnalyzer


def configure_console() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a quick analyzer smoke test with one log file.")
    parser.add_argument(
        "log_file",
        nargs="?",
        default=str(ROOT_DIR / "logs" / "test_took.log"),
        help="JSONL log file to analyze. Default: logs/test_took.log",
    )
    return parser.parse_args()


def main() -> int:
    configure_console()
    args = parse_args()

    analyzer = LogPerformanceAnalyzer()
    if not analyzer.parse_log_file(args.log_file):
        print(f"Failed to parse log file: {args.log_file}")
        return 1

    analyzer.extract_response_times()
    print(f"Extracted response-time records: {len(analyzer.response_times)}")

    for index, response_time in enumerate(analyzer.response_times[:20], 1):
        print(f"\n{index}. time: {response_time['time_ms']}ms")
        print(f"   method/url: {response_time['method']}")
        print(f"   line: {response_time['line_num']}")
        print(f"   log: {response_time['log'][:160]}")

    if len(analyzer.response_times) > 20:
        print(f"\n... {len(analyzer.response_times) - 20} more record(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
