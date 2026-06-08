#!/usr/bin/env python3
# -*- coding: utf-8 -*-"""
KMI 로그 성능 분석기 (개선 버전)
- 트랜잭션 기반 응답시간 분석 (스레드 ID 매칭, 미완료 요청 탐지)
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
        self.incomplete_requests = [] # New: To store requests that never got a response

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
                        
            # 시간순으로 로그 정렬 (필수: 트랜잭션 매칭 및 갭 분석 위함)
            self.logs.sort(key=lambda x: x['timestamp'])
            print(f"총 {len(self.logs)}개 로그 엔트리 파싱 및 정렬 완료")
            return True
            
        except Exception as e:
            print(f"파일 읽기 오류: {e}")
            return False

    def analyze_transactions(self):
        """REQUEST/RESPONSE 로그를 스레드 ID로 묶어 분석하고, 완료되지 않은 요청을 찾습니다."""
        print("\n🔍 트랜잭션 분석 (REQUEST/RESPONSE 매칭) 중...")
        pending_requests = {} # Key: thread_id, Value: {'timestamp', 'method', 'log', 'line_num', 'instance_id'}

        # 새로운 로그 형식에 맞게 정규식 수정
        # 예시: [HOMEPAGE_LOGGER:46] - [http-nio-8080-exec-6] DESKTOP-J1LV9C8 | Controller REQUEST : ...
        # \[(.*?)\] - \[(.+?)\]\s+([^\|]+?)\s*\|\s*Controller\s+(REQUEST|RESPONSE)\s*:\s*([^=]+)
        # Group 1: thread_id
        # Group 2: instance_id
        # Group 3: log_type (REQUEST/RESPONSE)
        # Group 4: method_info
        tx_pattern = re.compile(r'\[.*?\] - \[(.+?)\]\s+([^\|]+?)\s*\|\s*Controller\s+(REQUEST|RESPONSE)\s*:\s*([^=]+)')

        for entry in self.logs:
            log_text = entry['log']
            match = tx_pattern.search(log_text)

            if match:
                thread_id, instance_id_raw, log_type, method_info = match.groups()
                thread_id = thread_id.strip()
                instance_id = instance_id_raw.strip() # 인스턴스 ID도 추출
                method_info = method_info.strip()

                # 트랜잭션 ID로 스레드 ID 사용
                current_tx_id = thread_id

                if log_type == 'REQUEST':
                    # 동일 스레드에서 이전 요청이 응답 없이 새 요청으로 대체된 경우 경고
                    if current_tx_id in pending_requests:
                        prev_request = pending_requests[current_tx_id]
                        print(f"⚠️ 경고: 스레드 '{current_tx_id}'의 이전 요청이 응답 없이 새 요청으로 대체되었습니다. "
                              f"이전 요청 시작: {prev_request['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}, "
                              f"메서드: {prev_request['method']} (Line: {prev_request['line_num']})")
                        self.incomplete_requests.append(prev_request)
                        
                    pending_requests[current_tx_id] = {
                        'timestamp': entry['timestamp'],
                        'method': method_info,
                        'log': log_text,
                        'line_num': entry['line_num'],
                        'instance_id': instance_id 
                    }
                elif log_type == 'RESPONSE':
                    if current_tx_id in pending_requests:
                        request_entry = pending_requests.pop(current_tx_id)
                        duration_ms = (entry['timestamp'] - request_entry['timestamp']).total_seconds() * 1000
                        
                        self.response_times.append({
                            'timestamp': request_entry['timestamp'], # 시작 시간 기준
                            'method': method_info,
                            'time_ms': duration_ms,
                            'log': f"REQUEST: {request_entry['log']}\nRESPONSE: {log_text}",
                            'line_num': request_entry['line_num'],
                            'instance_id': instance_id
                        })
                    else:
                        # 짝이 없는 응답 - 분석 시작 전 요청이거나, 로그 누락 등의 경우
                        pass
        
        # 분석 종료 후에도 남은 요청들은 모두 미완료 요청으로 처리
        # 오래된 순서대로 정렬하여 먼저 멈춘 요청을 파악하기 쉽게 함
        self.incomplete_requests.extend(sorted(pending_requests.values(), key=lambda x: x['timestamp']))
        print(f"✅ {len(self.response_times)}개 완료된 트랜잭션 및 {len(self.incomplete_requests)}개 미완료 트랜잭션 발견")

        # 기존 'took' 패턴 분석은 계속 유지 (Redis, HTTP 클라이언트 등 외부 호출)
        print("\n🔍 'took' 키워드 기반 응답시간 분석 중...")
        took_pattern = r'took\s+(\d+(?:\.\d+)?)\s*(ms|s)'
        original_response_time_count = len(self.response_times)

        for entry in self.logs:
            log_text = entry['log']
            
            # Controller REQUEST/RESPONSE 로그가 아닌 경우에만 'took' 패턴 분석
            if not tx_pattern.search(log_text):
                took_matches = re.finditer(took_pattern, log_text)
                for match in took_matches:
                    time_value, unit = match.groups()
                    time_ms = float(time_value) * 1000 if unit == 's' else float(time_value)
                    
                    # URL 정보 추출 (http:// 또는 https://)
                    url_match = re.search(r'to\s+(https?://[^\s]+)', log_text)
                    if url_match:
                        method_info = url_match.group(1)
                    else:
                        request_match = re.search(r'(HTTP Request[^t]*to\s+[^\s]+)', log_text)
                        if request_match:
                            method_info = request_match.group(1).replace(' took', '').strip()
                        else:
                            method_info = log_text.splitlines()[0][:100] # 첫 줄 100자 정도
                            if len(log_text.splitlines()[0]) > 100:
                                method_info += "..."

                    self.response_times.append({
                        'timestamp': entry['timestamp'],
                        'method': method_info,
                        'time_ms': time_ms,
                        'log': log_text,
                        'line_num': entry['line_num'],
                        'instance_id': "N/A" # 이 로그에는 인스턴스 ID가 없을 수 있음
                    })
        
        print(f"✅ 'took' 패턴으로 {len(self.response_times) - original_response_time_count}개 응답시간 추가 추출 완료")
    
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

        self._report_incomplete_requests(output) # New report section
        self._report_errors(output)
        self._report_response_times(output)
        self._report_log_gaps(output)
        self._report_summary(output)
        self._report_recommendations(output)
        
        return output.getvalue()
    
    def _report_incomplete_requests(self, output):
        """미완료 요청 리포트"""
        print("\n❓ 미완료(Incomplete) 요청 분석", file=output)
        print("-