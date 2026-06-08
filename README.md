# 로그 성능 분석기

JSON 라인 형식의 애플리케이션 로그를 읽어서 응답 시간, 로그 공백 구간, 에러/예외를 분석하고 `result/` 폴더에 리포트를 생성하는 도구입니다.

## 준비

Python 3.10 이상이 필요합니다. 외부 패키지는 사용하지 않고 표준 라이브러리만 사용합니다.

Windows에서 Python 명령이 잡히는지 확인합니다.

```powershell
py -3 --version
```

또는:

```powershell
python --version
```

명령을 찾지 못하면 Python을 설치하고 `Add python.exe to PATH` 옵션을 켜세요.

## 빠른 실행

분석할 로그 파일은 `logs/` 폴더에 둔 뒤 실행합니다.

```powershell
.\run_analysis.bat
```

특정 파일만 분석하려면 파일명을 넘깁니다.

```powershell
.\run_analysis.bat .\logs\sample-json.log
```

여러 파일을 한 번에 분석할 수도 있습니다.

```powershell
.\run_analysis.bat .\logs\was1.log .\logs\was2.log .\logs\api-json.log.1
```

폴더 안의 로그를 분석하려면 폴더 경로를 넘깁니다.

```powershell
.\run_analysis.bat .\logs
```

하위 폴더까지 포함하려면 `-r` 옵션을 사용합니다.

```powershell
.\run_analysis.bat -r .\logs
```

Python으로 직접 실행해도 됩니다.

```powershell
py -3 .\run_analysis.py .\logs\sample-json.log
```

## 입력 로그 형식

기본 입력은 한 줄에 JSON 객체 하나가 있는 JSONL 형식입니다.

```json
{"time":"2025-11-24T08:42:02.015Z","log":"[INFO] Controller REQUEST : ..."}
{"time":"2025-11-24T08:42:02.120Z","log":"[INFO] Controller RESPONSE : ..."}
```

각 줄에는 최소한 아래 필드가 필요합니다.

```text
time: ISO 날짜/시간
log : 실제 로그 메시지
```

지원하는 파일 패턴은 다음과 같습니다.

```text
*.log
*.log.*
*-json.log
*-json.log.*
```

## 분석 항목

- `Controller REQUEST/RESPONSE` 로그를 매칭해서 응답 시간을 계산합니다.
- `took 123ms`, `took 1.2s` 패턴을 찾아 외부 호출/HTTP 요청 시간을 수집합니다.
- 로그 간 시간 간격을 계산해서 긴 무응답 구간을 찾습니다.
- `ERROR`, `Exception`, `timeout`, HTTP 4xx/5xx, SQL 오류, 연결 오류, 스택트레이스를 탐지합니다.

## 결과 확인

실행이 끝나면 콘솔에 요약이 출력되고, 리포트 파일이 생성됩니다.

```text
result/analysis_report_YYYYMMDD_HHMMSS.txt
```

결과 폴더를 바꾸려면 `-o` 옵션을 사용합니다.

```powershell
.\run_analysis.bat -o .\reports .\logs\sample-json.log
```

## 테스트/디버그 스크립트

`tests/` 폴더의 파일들은 평소 로그 분석 실행에는 사용되지 않습니다. 분석 로직을 수정할 때 빠르게 확인하는 보조 스크립트입니다.

응답시간 추출만 빠르게 확인하려면:

```powershell
py -3 .\tests\test_analyzer.py .\logs\sample-json.log
```

파일을 넘기지 않으면 기본으로 `logs/test_took.log`를 찾습니다.

```powershell
py -3 .\tests\test_analyzer.py
```

에러 탐지 정규식이 정상 응답 로그를 오탐하지 않는지 확인하려면:

```powershell
py -3 .\tests\test_regex.py
```

정리하면 일반 사용자는 `run_analysis.bat`만 사용하면 되고, `tests/`는 분석 로직을 수정할 때 확인용으로 사용합니다.

## Git 주의사항

실제 로그 파일은 용량이 크고 개인정보가 포함될 수 있으므로 Git에 올리지 않는 것을 권장합니다. 이 저장소의 `.gitignore`에는 로그와 분석 결과가 제외되도록 설정되어 있습니다.

```text
*.log
*.log.*
*-json.log
*-json.log.*
logs/*
result/
```

새로 커밋하기 전에 아래 명령으로 대용량 로그가 포함되지 않는지 확인하세요.

```powershell
git status --short
```

## 기존 스크립트

- `log_performance_analyzer.py`: 메인 분석 로직입니다.
- `run_analysis.py`: 실행 편의를 위해 추가한 래퍼입니다. 파일, 폴더, glob, 재귀 검색을 지원합니다.
- `run_analysis.bat`: Windows에서 Python 실행 명령을 자동으로 찾아주는 배치 파일입니다.
- `tests/test_analyzer.py`: 응답시간 추출 로직을 빠르게 확인하는 테스트 스크립트입니다.
- `tests/test_regex.py`: 에러 탐지 정규식 오탐 여부를 확인하는 디버그 스크립트입니다.
