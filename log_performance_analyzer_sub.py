#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KMI 로그 성능 분석기
- 응답시간 분석 (느린 API/Controller 탐지)
- 로그 갭 분석 (시스템 블로킹/무응답 구간 탐지)
- 종합 성능 리포트 생성
"""

import json
import re
from datetime import datetime, timedelta
from collections import defaultdict
import os
import sys
import glob
import io

class LogPerformanceAnalyzer:
    def __init__(self):
        # 응답시간 기준 (ms)
        self.response_time_thresholds = {
            'normal': 500,      # 정상: 0-500ms
            'warning': 2000,    # 주의: 500ms-2초
            'danger': 5000,     # 경고: 2-5초
            # 위험: 5초 이상
        }
        
        # 로그 갭 기준 (초)
        self.gap_thresholds = {
            'normal': 3,        # 정상: 0-3초
            'warning': 10,      # 주의: 3-10초
            'danger': 30,       # 경고: 10-30초
            # 위험: 30초 이상
        }
        
        self.logs = []
        self.response_times = []
        self.log_gaps = []
        self.errors = []

        # 에러 패턴
        self.error_patterns = {
            'error': r'(?i)\b(error|exception|failed|failure)\b',
            'timeout': r'(?i)(timeout|timed out|time out)',
            'http_error': r'(?i)(status_code|status|code|error_code)[\s:=]*\b([45]\d{2})\b',  # 4xx, 5xx
            'stack_trace': r'at\s+[\w.$]+\(',
            'sql_error': r'(?i)(\bsql\s*error|deadlock|constraint)',
            'connection_error': r'(?i)(connection\s+(?:refused|reset|timeout)|unable\s+to\s+connect)',
            'null_pointer': r'(?i)\b(null\s*pointer|npe|nullpointerexception)\b',
        }
        
    def parse_log_file(self, file_path):
        """로그 파일 파싱"""
        print(f"로그 파일 분석 중: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"파일을 찾을 수 없습니다: {file_path}")
            return False
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        log_entry = json.loads(line.strip())
                        if 'time' in log_entry and 'log' in log_entry:
                            timestamp = datetime.fromisoformat(log_entry['time'].replace('Z', '+00:00'))
                            self.logs.append({
                                'timestamp': timestamp,
                                'log': log_entry['log'].strip(),
                                'line_num': line_num
                            })
                    except json.JSONDecodeError:
                        # JSON이 아닌 라인은 건너뛰기
                        continue
                    except Exception as e:
                        print(f"라인 {line_num} 파싱 오류: {e}")
                        
            print(f"총 {len(self.logs)}개 로그 엔트리 파싱 완료")
            return True
            
        except Exception as e:
            print(f"파일 읽기 오류: {e}")
            return False
    
    def extract_response_times(self):
        """응답시간 추출 및 분석"""
        print("\n🔍 응답시간 분석 중...")

        # 응답시간 패턴: (XXXms) 또는 (X.Xs) 등
        time_pattern = r'\((\d+(?:\.\d+)?)\s*(ms|s)\)'
        # took 패턴: took XXXms 또는 took X.Xs
        took_pattern = r'took\s+(\d+(?:\.\d+)?)\s*(ms|s)'

        for entry in self.logs:
            log_text = entry['log']

            # 패턴 1: 괄호 안의 시간 (기존 방식)
            matches = re.findall(time_pattern, log_text)
            for match in matches:
                time_value, unit = match

                # 시간을 밀리초로 통일
                if unit == 's':
                    time_ms = float(time_value) * 1000
                else:
                    time_ms = float(time_value)

                # Controller나 Service 정보 추출
                controller_match = re.search(r'(Controller|Service|ServiceImpl)\s*(REQUEST|RESPONSE)\s*:\s*([^=]+)', log_text)
                method_info = "Unknown"
                if controller_match:
                    method_info = controller_match.group(3).strip()

                self.response_times.append({
                    'timestamp': entry['timestamp'],
                    'method': method_info,
                    'time_ms': time_ms,
                    'log': log_text[:500] + "..." if len(log_text) > 500 else log_text,
                    'line_num': entry['line_num']
                })

            # 패턴 2: took XXms 형식 (HTTP Request 등)
            took_matches = re.finditer(took_pattern, log_text)
            for match in took_matches:
                time_value, unit = match.groups()

                # 시간을 밀리초로 통일
                if unit == 's':
                    time_ms = float(time_value) * 1000
                else:
                    time_ms = float(time_value)

                # URL 정보 추출 (http:// 또는 https://)
                url_match = re.search(r'to\s+(https?://[^\s]+)', log_text)
                if url_match:
                    method_info = url_match.group(1)
                else:
                    # URL이 없으면 전체 메시지에서 정보 추출
                    # "HTTP Request (JSON Object) to ..." 형식
                    request_match = re.search(r'(HTTP Request[^t]*to\s+[^\s]+)', log_text)
                    if request_match:
                        method_info = request_match.group(1).replace(' took', '').strip()
                    else:
                        method_info = "Unknown HTTP Request"

                self.response_times.append({
                    'timestamp': entry['timestamp'],
                    'method': method_info,
                    'time_ms': time_ms,
                    'log': log_text[:500] + "..." if len(log_text) > 500 else log_text,
                    'line_num': entry['line_num']
                })

        print(f"✅ {len(self.response_times)}개 응답시간 데이터 추출 완료")
    
    def analyze_log_gaps(self):
        """로그 간격 분석"""
        print("\n🔍 로그 갭 분석 중...")
        
        if len(self.logs) < 2:
            print("⚠️ 로그가 너무 적어 갭 분석을 수행할 수 없습니다.")
            return
        
        for i in range(1, len(self.logs)):
            prev_time = self.logs[i-1]['timestamp']
            curr_time = self.logs[i]['timestamp']
            gap_seconds = (curr_time - prev_time).total_seconds()
            
            self.log_gaps.append({
                'start_time': prev_time,
                'end_time': curr_time,
                'gap_seconds': gap_seconds,
                'prev_log': self.logs[i-1]['log'][:250] + "..." if len(self.logs[i-1]['log']) > 250 else self.logs[i-1]['log'],
                'next_log': self.logs[i]['log'][:250] + "..." if len(self.logs[i]['log']) > 250 else self.logs[i]['log']
            })
        
        print(f"✅ {len(self.log_gaps)}개 로그 간격 분석 완료")

    def extract_errors(self):
        """에러 및 예외 추출 (개선된 버전)"""
        print("\n🔍 에러 분석 중...")

        i = 0
        processed_indices = set()  # 이미 처리된 인덱스 추적

        while i < len(self.logs):
            if i in processed_indices:
                i += 1
                continue

            entry = self.logs[i]
            log_text = entry['log']

            # 1. Exception/Error 시작 라인 확인 (실제 에러의 시작)
            # Exception/Error가 줄의 시작이나 독립적으로 나타나는 경우만 (클래스명 일부 제외)
            exception_match = re.search(r'^(java\.[\w.]+(?:Exception|Error))\s*:?\s*(.*)?$', log_text) or \
                            re.search(r'^([\w.]+(?:Exception|Error))\s*:?\s*(.+)?$', log_text)

            # INFO 레벨 로그에서 필터/클래스 이름에 Exception이 포함된 경우 제외
            is_info_log = re.search(r'\[(INFO|DEBUG|TRACE)\]', log_text)
            if exception_match and is_info_log:
                # INFO 로그에서 클래스/필터 이름만 나오는 경우 무시
                exception_match = None

            # 2. 로깅 프레임워크의 에러 레벨 확인
            log_level_error = re.search(r'\[(ERROR|FATAL|SEVERE)\]', log_text)

            # 3. 명시적 에러 메시지 확인 (스택트레이스 제외)
            explicit_error = re.search(r'(?i)\b(failed|failure|error occurred|exception occurred)\b', log_text) and \
                           not re.search(r'at\s+[\w.$]+\(', log_text) and \
                           not is_info_log

            if exception_match or log_level_error or explicit_error:
                error_types = []
                http_codes = []
                stack_trace_lines = []

                # 에러 유형 분류
                if exception_match:
                    error_types.append('exception')
                    # NullPointerException 등 특정 예외 확인
                    if re.search(r'(?i)null.*pointer', log_text):
                        error_types.append('null_pointer')

                if log_level_error:
                    error_types.append('error')

                # 타임아웃 확인
                if re.search(r'(?i)(timeout|timed out|time out)', log_text):
                    error_types.append('timeout')

                # HTTP 에러 코드 확인 (더 엄격한 패턴)
                http_pattern = r'(?i)(?:status|http|response|error)[\s:]*(?:code)?[\s:=]+([45]\d{2})\b'
                http_matches = re.findall(http_pattern, log_text)
                if http_matches:
                    error_types.append('http_error')
                    http_codes.extend(http_matches)

                # SQL 에러 확인
                if re.search(r'(?i)(\bsql\s*error|deadlock|constraint|duplicate key)', log_text):
                    error_types.append('sql_error')

                # 연결 에러 확인
                if re.search(r'(?i)(connection\s+(?:refused|reset|timeout|failed)|unable\s+to\s+connect)', log_text):
                    error_types.append('connection_error')

                # 스택트레이스 수집 (다음 라인들)
                has_stack_trace = False
                j = i + 1
                while j < len(self.logs):
                    next_log = self.logs[j]['log']
                    # 스택트레이스 라인 패턴: "at xxx" 또는 "Caused by:"
                    if re.search(r'^\s*at\s+[\w.$<>]+\(|^\s*Caused by:', next_log):
                        has_stack_trace = True
                        stack_trace_lines.append(next_log[:200])
                        processed_indices.add(j)  # 스택트레이스 라인은 별도 에러로 처리 안 함
                        j += 1
                    else:
                        break

                if has_stack_trace:
                    error_types.append('stack_trace')

                # 에러 정보 저장
                if error_types:  # 에러 타입이 하나라도 있으면 저장
                    self.errors.append({
                        'timestamp': entry['timestamp'],
                        'error_types': list(set(error_types)),  # 중복 제거
                        'http_codes': list(set(http_codes)),
                        'has_stack_trace': has_stack_trace,
                        'stack_trace_lines': stack_trace_lines[:10],  # 최대 10줄
                        'log': log_text[:1000] + "..." if len(log_text) > 1000 else log_text,
                        'line_num': entry['line_num']
                    })
                    processed_indices.add(i)

            i += 1

        print(f"✅ {len(self.errors)}개 에러/예외 발견")

    def categorize_performance(self, value, thresholds, is_gap=False):
        """성능 등급 분류"""
        if is_gap:
            if value <= thresholds['normal']:
                return 'normal', '정상'
            elif value <= thresholds['warning']:
                return 'warning', '주의'
            elif value <= thresholds['danger']:
                return 'danger', '경고'
            else:
                return 'critical', '위험'
        else:
            if value <= thresholds['normal']:
                return 'normal', '정상'
            elif value <= thresholds['warning']:
                return 'warning', '주의'
            elif value <= thresholds['danger']:
                return 'danger', '경고'
            else:
                return 'critical', '위험'
    
    def generate_report(self):
        """종합 성능 리포트 생성"""
        output = io.StringIO()
        
        print("\n" + "="*80, file=output)
        print("📊 KMI 로그 성능 분석 리포트", file=output)
        print("="*80, file=output)

        # 1. 에러 분석 리포트 (최우선)
        self._report_errors(output)

        # 2. 응답시간 분석 리포트
        self._report_response_times(output)

        # 3. 로그 갭 분석 리포트
        self._report_log_gaps(output)

        # 4. 종합 통계
        self._report_summary(output)

        # 5. 권장사항
        self._report_recommendations(output)
        
        return output.getvalue()
    
    def _report_response_times(self, output):
        """응답시간 분석 리포트"""
        print("\n🚀 응답시간 분석", file=output)
        print("-" * 50, file=output)
        
        if not self.response_times:
            print("응답시간 데이터가 없습니다.", file=output)
            return
        
        # 등급별 분류
        categories = {'critical': [], 'danger': [], 'warning': [], 'normal': []}
        
        for rt in self.response_times:
            category, label = self.categorize_performance(rt['time_ms'], self.response_time_thresholds)
            categories[category].append(rt)
        
        # 위험부터 출력
        for category in ['critical', 'danger', 'warning']:
            items = sorted(categories[category], key=lambda x: x['time_ms'], reverse=True)
            if items:
                labels = {'critical': '🔴 위험', 'danger': '🟠 경고', 'warning': '🟡 주의'}
                print(f"\n{labels[category]} ({len(items)}건):", file=output)
                
                for i, item in enumerate(items[:25]):  # 상위 25개까지 표시
                    time_str = f"{item['time_ms']:.0f}ms" if item['time_ms'] < 1000 else f"{item['time_ms']/1000:.1f}s"
                    print(f"  {i+1:2d}. {time_str:>8} | {item['timestamp'].strftime('%H:%M:%S')} | {item['method']}", file=output)
                    # 상세 로그 정보 추가 (상위 10개만)
                    if i < 10:
                        print(f"      📝 {item['log']}", file=output)
                
                if len(items) > 25:
                    print(f"     ... 외 {len(items)-25}건 더", file=output)
        
        # 통계
        times = [rt['time_ms'] for rt in self.response_times]
        if times:
            print(f"\n📈 응답시간 통계:", file=output)
            print(f"  평균: {sum(times)/len(times):.1f}ms", file=output)
            print(f"  최대: {max(times):.1f}ms", file=output)
            print(f"  최소: {min(times):.1f}ms", file=output)
            times_sorted = sorted(times)
            print(f"  중앙값: {times_sorted[len(times_sorted)//2]:.1f}ms", file=output)
            print(f"  90%: {times_sorted[int(len(times_sorted)*0.90)]:.1f}ms", file=output)
            print(f"  95%: {times_sorted[int(len(times_sorted)*0.95)]:.1f}ms", file=output)
            print(f"  99%: {times_sorted[int(len(times_sorted)*0.99)]:.1f}ms", file=output)
            
            # 시간대별 분포 추가
            print(f"\n📊 응답시간 분포:", file=output)
            under_500 = len([t for t in times if t <= 500])
            under_1000 = len([t for t in times if 500 < t <= 1000])
            under_2000 = len([t for t in times if 1000 < t <= 2000])
            under_5000 = len([t for t in times if 2000 < t <= 5000])
            over_5000 = len([t for t in times if t > 5000])
            
            print(f"  500ms 이하: {under_500}건 ({under_500/len(times)*100:.1f}%)", file=output)
            print(f"  500ms-1s: {under_1000}건 ({under_1000/len(times)*100:.1f}%)", file=output)
            print(f"  1-2초: {under_2000}건 ({under_2000/len(times)*100:.1f}%)", file=output)
            print(f"  2-5초: {under_5000}건 ({under_5000/len(times)*100:.1f}%)", file=output)
            print(f"  5초 이상: {over_5000}건 ({over_5000/len(times)*100:.1f}%)", file=output)
    
    def _report_log_gaps(self, output):
        """로그 갭 분석 리포트"""
        print("\n⏰ 로그 갭 분석", file=output)
        print("-" * 50, file=output)
        
        if not self.log_gaps:
            print("로그 갭 데이터가 없습니다.", file=output)
            return
        
        # 등급별 분류
        categories = {'critical': [], 'danger': [], 'warning': [], 'normal': []}
        
        for gap in self.log_gaps:
            category, label = self.categorize_performance(gap['gap_seconds'], self.gap_thresholds, is_gap=True)
            categories[category].append(gap)
        
        # 위험부터 출력
        for category in ['critical', 'danger', 'warning']:
            items = sorted(categories[category], key=lambda x: x['gap_seconds'], reverse=True)
            if items:
                labels = {'critical': '🔴 위험', 'danger': '🟠 경고', 'warning': '🟡 주의'}
                print(f"\n{labels[category]} 갭 ({len(items)}건):", file=output)
                
                for i, item in enumerate(items[:12]):  # 상위 12개까지 표시
                    gap_str = f"{item['gap_seconds']:.1f}s"
                    start_time = item['start_time'].strftime('%H:%M:%S')
                    end_time = item['end_time'].strftime('%H:%M:%S')
                    print(f"  {i+1}. {gap_str:>8} | {start_time} ~ {end_time}", file=output)
                    print(f"     이전: {item['prev_log']}", file=output)
                    print(f"     이후: {item['next_log']}", file=output)
                    print("", file=output)
                
                if len(items) > 12:
                    print(f"     ... 외 {len(items)-12}건 더", file=output)
        
        # 통계
        gaps = [gap['gap_seconds'] for gap in self.log_gaps]
        if gaps:
            print(f"\n📈 로그 갭 통계:", file=output)
            print(f"  평균: {sum(gaps)/len(gaps):.1f}초", file=output)
            print(f"  최대: {max(gaps):.1f}초", file=output)
            print(f"  최소: {min(gaps):.1f}초", file=output)
            gaps_sorted = sorted(gaps)
            print(f"  중앙값: {gaps_sorted[len(gaps_sorted)//2]:.1f}초", file=output)
            print(f"  90%: {gaps_sorted[int(len(gaps_sorted)*0.90)]:.1f}초", file=output)
            print(f"  95%: {gaps_sorted[int(len(gaps_sorted)*0.95)]:.1f}초", file=output)
            
            # 갭 분포 추가
            print(f"\n📊 로그 갭 분포:", file=output)
            under_1 = len([g for g in gaps if g <= 1])
            under_3 = len([g for g in gaps if 1 < g <= 3])
            under_10 = len([g for g in gaps if 3 < g <= 10])
            under_30 = len([g for g in gaps if 10 < g <= 30])
            over_30 = len([g for g in gaps if g > 30])
            
            print(f"  1초 이하: {under_1}건 ({under_1/len(gaps)*100:.1f}%)", file=output)
            print(f"  1-3초: {under_3}건 ({under_3/len(gaps)*100:.1f}%)", file=output)
            print(f"  3-10초: {under_10}건 ({under_10/len(gaps)*100:.1f}%)", file=output)
            print(f"  10-30초: {under_30}건 ({under_30/len(gaps)*100:.1f}%)", file=output)
            print(f"  30초 이상: {over_30}건 ({over_30/len(gaps)*100:.1f}%)", file=output)

    def _report_errors(self, output):
        """에러 분석 리포트"""
        print("\n❌ 에러 및 예외 분석", file=output)
        print("-" * 50, file=output)

        if not self.errors:
            print("✅ 에러가 발견되지 않았습니다!", file=output)
            return

        # 에러 유형별 분류
        error_type_counts = defaultdict(int)
        for error in self.errors:
            for error_type in error['error_types']:
                error_type_counts[error_type] += 1

        print(f"\n📊 에러 유형별 통계:", file=output)
        error_labels = {
            'error': '일반 에러/예외',
            'timeout': '타임아웃',
            'http_error': 'HTTP 에러 (4xx/5xx)',
            'stack_trace': '스택트레이스',
            'sql_error': 'SQL 에러',
            'connection_error': '연결 에러',
            'null_pointer': 'Null Pointer',
        }

        for error_type, count in sorted(error_type_counts.items(), key=lambda x: x[1], reverse=True):
            label = error_labels.get(error_type, error_type)
            print(f"  {label}: {count}건", file=output)

        # HTTP 에러 코드별 분류
        http_code_counts = defaultdict(int)
        for error in self.errors:
            for code in error['http_codes']:
                http_code_counts[code] += 1

        if http_code_counts:
            print(f"\n🌐 HTTP 에러 코드 분포:", file=output)
            for code, count in sorted(http_code_counts.items()):
                http_labels = {
                    '400': '400 Bad Request',
                    '401': '401 Unauthorized',
                    '403': '403 Forbidden',
                    '404': '404 Not Found',
                    '500': '500 Internal Server Error',
                    '502': '502 Bad Gateway',
                    '503': '503 Service Unavailable',
                    '504': '504 Gateway Timeout',
                }
                label = http_labels.get(code, f'{code} Error')
                print(f"  {label}: {count}건", file=output)

        # 타임아웃 에러 상세 분석
        timeout_errors = [e for e in self.errors if 'timeout' in e['error_types']]
        if timeout_errors:
            print(f"\n⏱️ 타임아웃 에러 ({len(timeout_errors)}건):", file=output)
            for i, error in enumerate(timeout_errors[:10], 1):
                time_str = error['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                print(f"  {i}. {time_str} | Line {error['line_num']}", file=output)
                print(f"     {error['log'][:200]}", file=output)
            if len(timeout_errors) > 10:
                print(f"     ... 외 {len(timeout_errors)-10}건 더", file=output)

        # 스택트레이스가 있는 에러 상세 분석
        stack_trace_errors = [e for e in self.errors if e['has_stack_trace']]
        if stack_trace_errors:
            print(f"\n📚 스택트레이스 포함 에러 ({len(stack_trace_errors)}건):", file=output)
            for i, error in enumerate(stack_trace_errors[:5], 1):
                time_str = error['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                print(f"\n  {i}. {time_str} | Line {error['line_num']}", file=output)
                print(f"     {error['log'][:300]}", file=output)
                if error['stack_trace_lines']:
                    print(f"     스택트레이스:", file=output)
                    for line in error['stack_trace_lines'][:3]:
                        print(f"       {line}", file=output)
            if len(stack_trace_errors) > 5:
                print(f"\n     ... 외 {len(stack_trace_errors)-5}건 더", file=output)

        # 시간대별 에러 분포
        if len(self.errors) > 10:
            hourly_error_counts = defaultdict(int)
            for error in self.errors:
                hour = error['timestamp'].hour
                hourly_error_counts[hour] += 1

            if hourly_error_counts:
                print(f"\n🕐 시간대별 에러 분포:", file=output)
                for hour in sorted(hourly_error_counts.keys()):
                    count = hourly_error_counts[hour]
                    bar = '█' * min(count, 50)
                    print(f"  {hour:02d}시: {bar} {count}건", file=output)

        # 최근 에러 목록
        print(f"\n🔴 최근 에러 TOP 10:", file=output)
        recent_errors = sorted(self.errors, key=lambda x: x['timestamp'], reverse=True)[:10]
        for i, error in enumerate(recent_errors, 1):
            time_str = error['timestamp'].strftime('%H:%M:%S')
            # Exception 타입 추출
            exception_match = re.search(r'([\w.]+(?:Exception|Error))', error['log'])
            if exception_match:
                error_name = exception_match.group(1)
            else:
                # exception 타입에서 제외된 에러 타입들 표시
                error_types_filtered = [t for t in error['error_types'] if t != 'exception' and t != 'stack_trace']
                error_name = ', '.join(error_types_filtered[:2]) if error_types_filtered else 'unknown'

            print(f"  {i:2d}. {time_str} | {error_name}", file=output)
            print(f"      {error['log'][:150]}", file=output)

    def _report_summary(self, output):
        """종합 통계"""
        print("\n📊 종합 통계", file=output)
        print("-" * 50, file=output)
        
        if self.logs:
            start_time = min(log['timestamp'] for log in self.logs)
            end_time = max(log['timestamp'] for log in self.logs)
            duration = end_time - start_time
            
            print(f"분석 기간: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_time.strftime('%H:%M:%S')}", file=output)
            print(f"총 시간: {duration.total_seconds():.1f}초", file=output)
            print(f"총 로그: {len(self.logs)}건", file=output)
            print(f"로그 빈도: {len(self.logs)/duration.total_seconds():.1f}건/초", file=output)
            
            # 시간대별 로그 분포 추가
            if duration.total_seconds() > 3600:  # 1시간 이상인 경우
                print(f"\n📅 시간대별 로그 분포:", file=output)
                hourly_counts = defaultdict(int)
                for log in self.logs:
                    hour = log['timestamp'].hour
                    hourly_counts[hour] += 1
                
                for hour in sorted(hourly_counts.keys()):
                    print(f"  {hour:02d}시: {hourly_counts[hour]}건", file=output)
        
        print(f"\n📋 파일별 상세 정보:", file=output)
        # 파일별 통계는 메인에서 추가됨
        
        # 응답시간 분포
        if self.response_times:
            rt_categories = {'critical': 0, 'danger': 0, 'warning': 0, 'normal': 0}
            for rt in self.response_times:
                category, _ = self.categorize_performance(rt['time_ms'], self.response_time_thresholds)
                rt_categories[category] += 1
            
            print(f"\n응답시간 분포:", file=output)
            print(f"  🔴 위험 (5초+): {rt_categories['critical']}건", file=output)
            print(f"  🟠 경고 (2-5초): {rt_categories['danger']}건", file=output)
            print(f"  🟡 주의 (0.5-2초): {rt_categories['warning']}건", file=output)
            print(f"  🟢 정상 (0-0.5초): {rt_categories['normal']}건", file=output)
            
            # 상위 느린 메서드 요약
            if self.response_times:
                print(f"\n🐌 가장 느린 메서드 TOP 5:", file=output)
                sorted_rt = sorted(self.response_times, key=lambda x: x['time_ms'], reverse=True)
                for i, rt in enumerate(sorted_rt[:5], 1):
                    time_str = f"{rt['time_ms']:.0f}ms" if rt['time_ms'] < 1000 else f"{rt['time_ms']/1000:.1f}s"
                    print(f"  {i}. {time_str} - {rt['method']}", file=output)
        
        # 로그 갭 분포
        if self.log_gaps:
            gap_categories = {'critical': 0, 'danger': 0, 'warning': 0, 'normal': 0}
            for gap in self.log_gaps:
                category, _ = self.categorize_performance(gap['gap_seconds'], self.gap_thresholds, is_gap=True)
                gap_categories[category] += 1
            
            print(f"\n로그 갭 분포:", file=output)
            print(f"  🔴 위험 (30초+): {gap_categories['critical']}건", file=output)
            print(f"  🟠 경고 (10-30초): {gap_categories['danger']}건", file=output)
            print(f"  🟡 주의 (3-10초): {gap_categories['warning']}건", file=output)
            print(f"  🟢 정상 (0-3초): {gap_categories['normal']}건", file=output)
            
            # 가장 긴 갭 요약
            if self.log_gaps:
                print(f"\n⏱️ 가장 긴 로그 갭 TOP 5:", file=output)
                sorted_gaps = sorted(self.log_gaps, key=lambda x: x['gap_seconds'], reverse=True)
                for i, gap in enumerate(sorted_gaps[:5], 1):
                    time_str = f"{gap['gap_seconds']:.1f}초"
                    start_time = gap['start_time'].strftime('%H:%M:%S')
                    print(f"  {i}. {time_str} - {start_time}부터", file=output)

        # 에러 통계
        if self.errors:
            print(f"\n❌ 에러 통계:", file=output)
            print(f"  총 에러 수: {len(self.errors)}건", file=output)

            # 에러 유형별
            error_type_counts = defaultdict(int)
            for error in self.errors:
                for error_type in error['error_types']:
                    error_type_counts[error_type] += 1

            print(f"  타임아웃 에러: {error_type_counts.get('timeout', 0)}건", file=output)
            print(f"  HTTP 에러: {error_type_counts.get('http_error', 0)}건", file=output)
            print(f"  SQL 에러: {error_type_counts.get('sql_error', 0)}건", file=output)
            print(f"  연결 에러: {error_type_counts.get('connection_error', 0)}건", file=output)
            print(f"  스택트레이스 포함: {len([e for e in self.errors if e['has_stack_trace']])}건", file=output)

            # 에러율 계산
            if self.logs:
                error_rate = (len(self.errors) / len(self.logs)) * 100
                print(f"  에러율: {error_rate:.2f}%", file=output)

    def _report_recommendations(self, output):
        """권장사항"""
        print("\n💡 권장사항", file=output)
        print("-" * 50, file=output)

        recommendations = []

        # 에러 분석
        if self.errors:
            # 타임아웃 에러
            timeout_errors = [e for e in self.errors if 'timeout' in e['error_types']]
            if timeout_errors:
                recommendations.append(f"🔥 긴급: {len(timeout_errors)}건의 타임아웃 에러 발생 - 서비스/네트워크 응답시간 개선 필요")

            # HTTP 5xx 에러
            server_errors = [e for e in self.errors if any(c.startswith('5') for c in e['http_codes'])]
            if server_errors:
                recommendations.append(f"⚠️ 서버 에러: {len(server_errors)}건의 5xx 에러 발생 - 서버 안정성 점검 필요")

            # 연결 에러
            connection_errors = [e for e in self.errors if 'connection_error' in e['error_types']]
            if connection_errors:
                recommendations.append(f"🔌 연결 문제: {len(connection_errors)}건의 연결 에러 - 네트워크/DB 연결 상태 확인 필요")

            # SQL 에러
            sql_errors = [e for e in self.errors if 'sql_error' in e['error_types']]
            if sql_errors:
                recommendations.append(f"💾 데이터베이스: {len(sql_errors)}건의 SQL 에러 - 쿼리 최적화 및 DB 상태 점검 필요")

            # 전체 에러율
            if self.logs:
                error_rate = (len(self.errors) / len(self.logs)) * 100
                if error_rate > 5:
                    recommendations.append(f"📊 높은 에러율: {error_rate:.1f}% - 전반적인 시스템 안정성 개선 필요")

        # 위험한 로그 갭 확인
        critical_gaps = [gap for gap in self.log_gaps
                        if self.categorize_performance(gap['gap_seconds'], self.gap_thresholds, is_gap=True)[0] == 'critical']
        if critical_gaps:
            max_gap = max(critical_gaps, key=lambda x: x['gap_seconds'])
            recommendations.append(f"⏸️ 시스템 중단: {max_gap['gap_seconds']:.1f}초 무응답 구간 원인 분석 필요")

        # 느린 응답시간 확인
        critical_responses = [rt for rt in self.response_times
                            if self.categorize_performance(rt['time_ms'], self.response_time_thresholds)[0] == 'critical']
        if critical_responses:
            slowest = max(critical_responses, key=lambda x: x['time_ms'])
            time_str = f"{slowest['time_ms']:.0f}ms" if slowest['time_ms'] < 1000 else f"{slowest['time_ms']/1000:.1f}s"
            recommendations.append(f"⚡ 성능 개선: {slowest['method']} ({time_str}) 최적화 필요")

        # 패턴 분석
        if len(self.response_times) > 10:
            avg_time = sum(rt['time_ms'] for rt in self.response_times) / len(self.response_times)
            if avg_time > self.response_time_thresholds['warning']:
                recommendations.append(f"📈 전반적 성능 개선 필요 (평균 응답시간: {avg_time:.1f}ms)")

        if not recommendations:
            recommendations.append("✅ 현재 성능 상태가 양호합니다.")

        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}", file=output)

def main():
    """메인 함수"""
    print("KMI 로그 성능 분석기 시작")

    # 현재 스크립트가 위치한 디렉토리
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 결과 디렉토리 생성
    result_dir = os.path.join(script_dir, 'result')
    os.makedirs(result_dir, exist_ok=True)

    # 사용자가 특정 파일을 지정했는지 확인
    if len(sys.argv) > 1:
        log_files = [sys.argv[1]]
    else:
        # 루트 디렉토리에서 모든 .log 및 .log.* 파일 찾기
        log_files = []
        log_files.extend(glob.glob(os.path.join(script_dir, '*.log')))      # .log 파일
        log_files.extend(glob.glob(os.path.join(script_dir, '*.log.*')))    # .log.1, .log.2 등
        log_files = sorted(set(log_files))  # 중복 제거 및 정렬
        print(f"📂 {script_dir} 디렉토리에서 {len(log_files)}개의 로그 파일을 발견했습니다.")

    analyzer = LogPerformanceAnalyzer()
    
    # 존재하는 파일만 분석
    analyzed_files = []
    for log_file in log_files:
        if os.path.exists(log_file):
            if analyzer.parse_log_file(log_file):
                analyzed_files.append(log_file)
        else:
            print(f"⚠️ 파일 없음: {log_file}")
    
    if not analyzed_files:
        print("❌ 분석할 로그 파일이 없습니다.")
        return
    
    print(f"\n✅ {len(analyzed_files)}개 파일 분석 완료")

    # 분석 수행
    analyzer.extract_errors()          # 에러 분석 (최우선)
    analyzer.extract_response_times()  # 응답시간 분석
    analyzer.analyze_log_gaps()        # 로그 갭 분석

    # 리포트 생성
    report = analyzer.generate_report()
    
    # 리포트 화면에 출력
    print(report)
    
    # 리포트 파일로 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"analysis_report_{timestamp}.txt"
    report_filepath = os.path.join(result_dir, report_filename)
    
    try:
        with open(report_filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n🎉 분석 완료! 리포트가 다음 파일에 저장되었습니다: {report_filepath}")
    except Exception as e:
        print(f"\n🚨 리포트 파일 저장 실패: {e}")

    print(f"구분된 파일: {', '.join(os.path.basename(f) for f in analyzed_files)}")

if __name__ == "__main__":
    main()
