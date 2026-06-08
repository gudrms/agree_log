#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual regex check for false-positive error detection.

This script is not part of the normal analyzer flow. Run it when changing
error patterns and you want to confirm that known normal logs are not
classified as errors.
"""

from __future__ import annotations

import re


NORMAL_RESPONSE_LOG = """
[2025-11-24 07:19:21] [INFO] [LogAspect:107] -
sampleServiceImpl RESPONSE : SampleServiceImpl(searchReservation) =
{"data":{"message":[{"msg":"success","code":"info"}],"item":[
{"name":"MASKED_NAME","phone":"010-0000-0000","email":"masked@example.com",
"address":"MASKED_ADDRESS","rrn":"000000-0******","status":"OK"}]}} (99ms)
"""

ERROR_PATTERNS = {
    "error": r"(?i)\b(error|exception|failed|failure)\b",
    "timeout": r"(?i)(timeout|timed out|time out)",
    "http_error": r"(?i)(status_code|status|code|error_code)[\s:=]*\b([45]\d{2})\b",
    "stack_trace": r"at\s+[\w.$]+\(",
    "sql_error": r"(?i)(\bsql\s*error|deadlock|constraint)",
    "connection_error": r"(?i)(connection\s+(?:refused|reset|timeout)|unable\s+to\s+connect)",
    "null_pointer": r"(?i)(null\s*pointer|npe|nullpointerexception)",
}


def main() -> int:
    print("Checking normal response log against error patterns...")
    found = False

    for error_type, pattern in ERROR_PATTERNS.items():
        match = re.search(pattern, NORMAL_RESPONSE_LOG)
        if match:
            print(f"MATCH FOUND: {error_type}")
            print(f"Pattern: {pattern}")
            print(f"Match: {match.group(0)}")
            found = True

    if not found:
        print("No false-positive match found.")

    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
