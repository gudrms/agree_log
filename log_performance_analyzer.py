#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application log performance analyzer.

The analyzer expects JSON lines where each line contains at least:

    {"time": "2025-11-24T08:42:02.015Z", "log": "..."}

It extracts slow responses, log gaps, and common error signals.
"""

from __future__ import annotations

import io
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from typing import Any


class LogPerformanceAnalyzer:
    def __init__(self) -> None:
        self.response_time_thresholds = {
            "normal": 500,
            "warning": 2000,
            "danger": 5000,
        }
        self.gap_thresholds = {
            "normal": 3,
            "warning": 10,
            "danger": 30,
        }

        self.logs: list[dict[str, Any]] = []
        self.response_times: list[dict[str, Any]] = []
        self.log_gaps: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

        self.error_patterns = {
            "timeout": re.compile(r"(?i)(timeout|timed out|time out)"),
            "http_error": re.compile(r"(?i)(?:status|http|response|error)[\s:]*(?:code)?[\s:=]+([45]\d{2})\b"),
            "sql_error": re.compile(r"(?i)(\bsql\s*error|deadlock|constraint|duplicate key)"),
            "connection_error": re.compile(r"(?i)(connection\s+(?:refused|reset|timeout|failed)|unable\s+to\s+connect)"),
            "null_pointer": re.compile(r"(?i)\b(null\s*pointer|npe|nullpointerexception)\b"),
        }

    def parse_log_file(self, file_path: str) -> bool:
        """Parse one JSONL log file and append valid entries to self.logs."""
        print(f"로그 파일 분석 중: {file_path}")

        if not os.path.exists(file_path):
            print(f"파일을 찾을 수 없습니다: {file_path}")
            return False

        parsed_count = 0
        skipped_count = 0

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as file:
                for line_num, line in enumerate(file, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        log_entry = json.loads(line)
                    except json.JSONDecodeError:
                        skipped_count += 1
                        continue

                    if "time" not in log_entry or "log" not in log_entry:
                        skipped_count += 1
                        continue

                    try:
                        timestamp = datetime.fromisoformat(str(log_entry["time"]).replace("Z", "+00:00"))
                    except ValueError as exc:
                        skipped_count += 1
                        print(f"라인 {line_num} 시간 파싱 오류: {exc}")
                        continue

                    self.logs.append(
                        {
                            "timestamp": timestamp,
                            "log": str(log_entry["log"]).strip(),
                            "line_num": line_num,
                            "file_path": file_path,
                        }
                    )
                    parsed_count += 1

            print(f"파싱 완료: {parsed_count}건, 건너뜀: {skipped_count}건")
            return parsed_count > 0
        except OSError as exc:
            print(f"파일 읽기 오류: {exc}")
            return False

    def sort_logs(self) -> None:
        """Sort all parsed logs by timestamp before cross-file analysis."""
        self.logs.sort(key=lambda entry: entry["timestamp"])

    def extract_response_times(self) -> None:
        """Extract response-time records from common log patterns."""
        print("\n응답시간 분석 중...")
        self.response_times.clear()

        paren_time_pattern = re.compile(r"\((\d+(?:\.\d+)?)\s*(ms|s)\)")
        took_pattern = re.compile(r"\btook\s+(\d+(?:\.\d+)?)\s*(ms|s)\b", re.IGNORECASE)

        for entry in self.logs:
            log_text = entry["log"]

            for match in paren_time_pattern.finditer(log_text):
                self.response_times.append(
                    {
                        "timestamp": entry["timestamp"],
                        "method": self._extract_method(log_text),
                        "time_ms": self._to_millis(match.group(1), match.group(2)),
                        "log": self._truncate(log_text, 500),
                        "line_num": entry["line_num"],
                        "file_path": entry["file_path"],
                    }
                )

            for match in took_pattern.finditer(log_text):
                self.response_times.append(
                    {
                        "timestamp": entry["timestamp"],
                        "method": self._extract_method(log_text),
                        "time_ms": self._to_millis(match.group(1), match.group(2)),
                        "log": self._truncate(log_text, 500),
                        "line_num": entry["line_num"],
                        "file_path": entry["file_path"],
                    }
                )

        print(f"응답시간 데이터 {len(self.response_times)}건 추출 완료")

    def analyze_log_gaps(self) -> None:
        """Analyze time gaps between adjacent logs."""
        print("\n로그 간격 분석 중...")
        self.log_gaps.clear()

        if len(self.logs) < 2:
            print("로그가 2건 미만이라 간격 분석을 건너뜁니다.")
            return

        self.sort_logs()
        for previous, current in zip(self.logs, self.logs[1:]):
            gap_seconds = (current["timestamp"] - previous["timestamp"]).total_seconds()
            self.log_gaps.append(
                {
                    "start_time": previous["timestamp"],
                    "end_time": current["timestamp"],
                    "gap_seconds": gap_seconds,
                    "prev_log": self._truncate(previous["log"], 250),
                    "next_log": self._truncate(current["log"], 250),
                    "prev_file": previous["file_path"],
                    "next_file": current["file_path"],
                }
            )

        print(f"로그 간격 {len(self.log_gaps)}건 분석 완료")

    def extract_errors(self) -> None:
        """Extract error and exception records."""
        print("\n에러/예외 분석 중...")
        self.errors.clear()

        processed_indices: set[int] = set()
        for index, entry in enumerate(self.logs):
            if index in processed_indices:
                continue

            log_text = entry["log"]
            is_info_log = bool(re.search(r"\[(INFO|DEBUG|TRACE)\]", log_text))
            exception_match = self._exception_match(log_text)
            if exception_match and is_info_log:
                exception_match = None

            log_level_error = bool(re.search(r"\[(ERROR|FATAL|SEVERE)\]", log_text))
            explicit_error = (
                bool(re.search(r"(?i)\b(failed|failure|error occurred|exception occurred)\b", log_text))
                and not re.search(r"\bat\s+[\w.$]+\(", log_text)
                and not is_info_log
            )

            if not (exception_match or log_level_error or explicit_error):
                continue

            error_types: set[str] = set()
            http_codes: set[str] = set()
            stack_trace_lines: list[str] = []

            if exception_match:
                error_types.add("exception")
            if log_level_error:
                error_types.add("error")

            for error_type, pattern in self.error_patterns.items():
                matches = pattern.findall(log_text)
                if matches:
                    error_types.add(error_type)
                    if error_type == "http_error":
                        http_codes.update(matches)

            next_index = index + 1
            while next_index < len(self.logs):
                next_log = self.logs[next_index]["log"]
                if re.search(r"^\s*at\s+[\w.$<>]+\(|^\s*Caused by:", next_log):
                    stack_trace_lines.append(self._truncate(next_log, 200))
                    processed_indices.add(next_index)
                    next_index += 1
                    continue
                break

            if stack_trace_lines:
                error_types.add("stack_trace")

            if error_types:
                self.errors.append(
                    {
                        "timestamp": entry["timestamp"],
                        "error_types": sorted(error_types),
                        "http_codes": sorted(http_codes),
                        "has_stack_trace": bool(stack_trace_lines),
                        "stack_trace_lines": stack_trace_lines[:10],
                        "log": self._truncate(log_text, 1000),
                        "line_num": entry["line_num"],
                        "file_path": entry["file_path"],
                    }
                )

        print(f"에러/예외 {len(self.errors)}건 발견")

    def generate_report(self) -> str:
        output = io.StringIO()

        print("\n" + "=" * 80, file=output)
        print("로그 성능 분석 리포트", file=output)
        print("=" * 80, file=output)

        self._report_summary(output)
        self._report_errors(output)
        self._report_response_times(output)
        self._report_log_gaps(output)
        self._report_recommendations(output)

        return output.getvalue()

    def categorize_performance(self, value: float, thresholds: dict[str, int]) -> tuple[str, str]:
        if value <= thresholds["normal"]:
            return "normal", "정상"
        if value <= thresholds["warning"]:
            return "warning", "주의"
        if value <= thresholds["danger"]:
            return "danger", "경고"
        return "critical", "위험"

    def _report_summary(self, output: io.StringIO) -> None:
        print("\n종합 통계", file=output)
        print("-" * 50, file=output)

        if not self.logs:
            print("분석된 로그가 없습니다.", file=output)
            return

        start_time = min(log["timestamp"] for log in self.logs)
        end_time = max(log["timestamp"] for log in self.logs)
        duration_seconds = max((end_time - start_time).total_seconds(), 0)
        file_count = len({log["file_path"] for log in self.logs})

        print(f"분석 기간: {start_time:%Y-%m-%d %H:%M:%S} ~ {end_time:%Y-%m-%d %H:%M:%S}", file=output)
        print(f"총 시간: {duration_seconds:.1f}초", file=output)
        print(f"분석 파일: {file_count}개", file=output)
        print(f"총 로그: {len(self.logs)}건", file=output)
        if duration_seconds > 0:
            print(f"로그 빈도: {len(self.logs) / duration_seconds:.1f}건/초", file=output)

        print(f"응답시간 데이터: {len(self.response_times)}건", file=output)
        print(f"로그 간격 데이터: {len(self.log_gaps)}건", file=output)
        print(f"에러/예외: {len(self.errors)}건", file=output)

    def _report_response_times(self, output: io.StringIO) -> None:
        print("\n응답시간 분석", file=output)
        print("-" * 50, file=output)

        if not self.response_times:
            print("응답시간 데이터가 없습니다.", file=output)
            return

        times = [record["time_ms"] for record in self.response_times]
        sorted_times = sorted(times)
        p95_index = min(int(len(sorted_times) * 0.95), len(sorted_times) - 1)
        category_counts = Counter(
            self.categorize_performance(record["time_ms"], self.response_time_thresholds)[0]
            for record in self.response_times
        )

        print(f"평균: {mean(times):.1f}ms", file=output)
        print(f"최대: {max(times):.1f}ms", file=output)
        print(f"P95: {sorted_times[p95_index]:.1f}ms", file=output)
        print(f"정상(0~0.5초): {category_counts['normal']}건", file=output)
        print(f"주의(0.5~2초): {category_counts['warning']}건", file=output)
        print(f"경고(2~5초): {category_counts['danger']}건", file=output)
        print(f"위험(5초 초과): {category_counts['critical']}건", file=output)

        print("\n가장 느린 응답 TOP 10", file=output)
        for index, record in enumerate(sorted(self.response_times, key=lambda item: item["time_ms"], reverse=True)[:10], 1):
            print(
                f"{index:2d}. {self._format_ms(record['time_ms'])} | "
                f"{record['timestamp']:%H:%M:%S} | {record['method']} "
                f"({os.path.basename(record['file_path'])}:{record['line_num']})",
                file=output,
            )

    def _report_log_gaps(self, output: io.StringIO) -> None:
        print("\n로그 간격 분석", file=output)
        print("-" * 50, file=output)

        if not self.log_gaps:
            print("로그 간격 데이터가 없습니다.", file=output)
            return

        category_counts = Counter(
            self.categorize_performance(record["gap_seconds"], self.gap_thresholds)[0]
            for record in self.log_gaps
        )

        print(f"정상(0~3초): {category_counts['normal']}건", file=output)
        print(f"주의(3~10초): {category_counts['warning']}건", file=output)
        print(f"경고(10~30초): {category_counts['danger']}건", file=output)
        print(f"위험(30초 초과): {category_counts['critical']}건", file=output)

        print("\n가장 긴 로그 공백 TOP 10", file=output)
        for index, gap in enumerate(sorted(self.log_gaps, key=lambda item: item["gap_seconds"], reverse=True)[:10], 1):
            print(
                f"{index:2d}. {gap['gap_seconds']:.1f}초 | "
                f"{gap['start_time']:%H:%M:%S} ~ {gap['end_time']:%H:%M:%S}",
                file=output,
            )
            print(f"    이전: {gap['prev_log']}", file=output)
            print(f"    다음: {gap['next_log']}", file=output)

    def _report_errors(self, output: io.StringIO) -> None:
        print("\n에러/예외 분석", file=output)
        print("-" * 50, file=output)

        if not self.errors:
            print("에러/예외가 발견되지 않았습니다.", file=output)
            return

        type_counts: Counter[str] = Counter()
        for error in self.errors:
            type_counts.update(error["error_types"])

        print(f"총 에러/예외: {len(self.errors)}건", file=output)
        for error_type, count in type_counts.most_common():
            print(f"{error_type}: {count}건", file=output)

        hourly_counts: defaultdict[int, int] = defaultdict(int)
        for error in self.errors:
            hourly_counts[error["timestamp"].hour] += 1

        if hourly_counts:
            print("\n시간대별 에러 분포", file=output)
            for hour in sorted(hourly_counts):
                print(f"{hour:02d}시: {hourly_counts[hour]}건", file=output)

        print("\n최근 에러 TOP 10", file=output)
        for index, error in enumerate(sorted(self.errors, key=lambda item: item["timestamp"], reverse=True)[:10], 1):
            print(
                f"{index:2d}. {error['timestamp']:%H:%M:%S} | "
                f"{', '.join(error['error_types'])} "
                f"({os.path.basename(error['file_path'])}:{error['line_num']})",
                file=output,
            )
            print(f"    {error['log'][:180]}", file=output)
            for stack_line in error["stack_trace_lines"][:3]:
                print(f"    {stack_line}", file=output)

    def _report_recommendations(self, output: io.StringIO) -> None:
        print("\n권장 조치", file=output)
        print("-" * 50, file=output)

        recommendations: list[str] = []

        timeout_count = sum(1 for error in self.errors if "timeout" in error["error_types"])
        if timeout_count:
            recommendations.append(f"타임아웃 {timeout_count}건이 발견되었습니다. 외부 API, DB, 네트워크 응답시간을 확인하세요.")

        server_error_count = sum(
            1 for error in self.errors for code in error["http_codes"] if str(code).startswith("5")
        )
        if server_error_count:
            recommendations.append(f"HTTP 5xx 오류 {server_error_count}건이 발견되었습니다. 서버 측 예외 로그를 우선 확인하세요.")

        critical_gaps = [
            gap for gap in self.log_gaps if self.categorize_performance(gap["gap_seconds"], self.gap_thresholds)[0] == "critical"
        ]
        if critical_gaps:
            max_gap = max(critical_gaps, key=lambda item: item["gap_seconds"])
            recommendations.append(f"30초 초과 로그 공백이 있습니다. 최대 공백은 {max_gap['gap_seconds']:.1f}초입니다.")

        critical_responses = [
            record
            for record in self.response_times
            if self.categorize_performance(record["time_ms"], self.response_time_thresholds)[0] == "critical"
        ]
        if critical_responses:
            slowest = max(critical_responses, key=lambda item: item["time_ms"])
            recommendations.append(
                f"5초 초과 응답이 있습니다. 가장 느린 대상은 {slowest['method']} ({self._format_ms(slowest['time_ms'])})입니다."
            )

        if not recommendations:
            recommendations.append("현재 기준에서 즉시 조치가 필요한 성능/오류 신호는 발견되지 않았습니다.")

        for index, recommendation in enumerate(recommendations, 1):
            print(f"{index}. {recommendation}", file=output)

    def _extract_method(self, log_text: str) -> str:
        url_match = re.search(r"\bto\s+(https?://[^\s]+)", log_text)
        if url_match:
            return url_match.group(1)

        controller_match = re.search(r"(Controller|Service|ServiceImpl)\s*(REQUEST|RESPONSE)\s*:\s*([^=]+)", log_text)
        if controller_match:
            return controller_match.group(3).strip()

        request_match = re.search(r"(HTTP Request[^t]*to\s+[^\s]+)", log_text)
        if request_match:
            return request_match.group(1).replace(" took", "").strip()

        first_line = log_text.splitlines()[0] if log_text.splitlines() else log_text
        return self._truncate(first_line, 100)

    def _exception_match(self, log_text: str) -> re.Match[str] | None:
        return re.search(r"^(java\.[\w.]+(?:Exception|Error))\s*:?\s*(.*)?$", log_text) or re.search(
            r"^([\w.]+(?:Exception|Error))\s*:?\s*(.+)?$", log_text
        )

    def _to_millis(self, value: str, unit: str) -> float:
        number = float(value)
        return number * 1000 if unit.lower() == "s" else number

    def _format_ms(self, value: float) -> str:
        return f"{value:.0f}ms" if value < 1000 else f"{value / 1000:.1f}s"

    def _truncate(self, value: str, limit: int) -> str:
        return value[:limit] + "..." if len(value) > limit else value
