#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convenience runner for the log performance analyzer."""

from __future__ import annotations

import argparse
import glob
import io
import os
import sys
from datetime import datetime
from pathlib import Path

from log_performance_analyzer import LogPerformanceAnalyzer


PROJECT_DIR = Path(__file__).resolve().parent
LOG_PATTERNS = ("*.log", "*.log.*", "*-json.log", "*-json.log.*")


def configure_console() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def collect_log_files(paths: list[str], recursive: bool) -> list[Path]:
    targets = [str(PROJECT_DIR / "logs")] if not paths else paths
    files: list[Path] = []

    for target in targets:
        path = Path(target)
        if path.is_file():
            files.append(path)
            continue

        if path.is_dir():
            for pattern in LOG_PATTERNS:
                iterator = path.rglob(pattern) if recursive else path.glob(pattern)
                files.extend(p for p in iterator if p.is_file())
            continue

        matched = [Path(p) for p in glob.glob(target, recursive=recursive)]
        files.extend(p for p in matched if p.is_file())

    unique_files = sorted({p.resolve() for p in files})
    return unique_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze JSON-line application logs and generate a performance report."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Log file, directory, or glob pattern. Defaults to the logs directory.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search directories recursively.",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        default=str(PROJECT_DIR / "result"),
        help="Directory to write the report. Default: result",
    )
    return parser.parse_args()


def main() -> int:
    configure_console()
    args = parse_args()

    log_files = collect_log_files(args.paths, args.recursive)
    if not log_files:
        print("No log files found.")
        print("Put log files in the logs directory or pass a file path explicitly.")
        print("Example: python run_analysis.py logs/app.log")
        return 1

    print(f"Found {len(log_files)} log file(s).")
    analyzer = LogPerformanceAnalyzer()
    analyzed_files: list[Path] = []

    for log_file in log_files:
        if analyzer.parse_log_file(str(log_file)):
            analyzed_files.append(log_file)

    if not analyzed_files:
        print("No readable log files were analyzed.")
        return 1

    analyzer.sort_logs()
    analyzer.extract_errors()
    analyzer.extract_response_times()
    analyzer.analyze_log_gaps()

    report = analyzer.generate_report()
    print(report)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.write_text(report, encoding="utf-8")

    print(f"Report saved: {report_path.resolve()}")
    print("Analyzed files:")
    for log_file in analyzed_files:
        print(f"- {log_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
