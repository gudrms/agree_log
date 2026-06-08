#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

# 표준 출력을 UTF-8로 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 로그 분석기 임포트
from log_performance_analyzer import LogPerformanceAnalyzer

# 테스트 실행
analyzer = LogPerformanceAnalyzer()

if analyzer.parse_log_file('test_took.log'):
    print("✅ 파일 파싱 성공!")

    # 응답시간 추출
    analyzer.extract_response_times()

    print(f"\n추출된 응답시간 데이터: {len(analyzer.response_times)}개")
    print("\n상세 내용:")
    for i, rt in enumerate(analyzer.response_times, 1):
        print(f"\n{i}. 시간: {rt['time_ms']}ms")
        print(f"   메서드/URL: {rt['method']}")
        print(f"   로그: {rt['log'][:100]}")
else:
    print("❌ 파일 파싱 실패")