import json
from datetime import datetime

log_file = r'D:\기타\eae664ceb63ce5c8cbad0e667abc3ec86e41939d6ee18c38cb0e4bd16b91b922-json.log.2'

logs = []
with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            log_entry = json.loads(line.strip())
            if 'time' in log_entry:
                logs.append({
                    'time': log_entry['time'],
                    'log': log_entry.get('log', '').strip()
                })
        except:
            pass

start_time = datetime.fromisoformat("2025-10-27T22:15:21+00:00")
end_time = datetime.fromisoformat("2025-10-27T22:17:56+00:00")

print("=" * 120)
print("문제 구간 분석: 07:15:21 ~ 07:17:56 (154.75초)")
print("=" * 120)

last_before_gap = None
first_after_gap = None

for i, entry in enumerate(logs):
    t = datetime.fromisoformat(entry['time'].replace('Z', '+00:00'))
    
    if t <= start_time:
        last_before_gap = (i, entry)
    
    if t >= end_time and first_after_gap is None:
        first_after_gap = (i, entry)
        break

if last_before_gap:
    print(f"\n[마지막 정상 로그]")
    print(f"시간: {last_before_gap[1]['time']}")
    print(f"내용: {last_before_gap[1]['log']}")
    
    print(f"\n[이후 로그들]")
    for j in range(last_before_gap[0] + 1, min(len(logs), last_before_gap[0] + 6)):
        t1 = datetime.fromisoformat(last_before_gap[1]['time'].replace('Z', '+00:00'))
        t2 = datetime.fromisoformat(logs[j]['time'].replace('Z', '+00:00'))
        gap = (t2 - t1).total_seconds()
        print(f"\n+{gap:.1f}초 후: {logs[j]['time']}")
        print(f"  {logs[j]['log'][:200]}")

if first_after_gap:
    print(f"\n" + "=" * 120)
    print(f"[154초 후 첫 로그]")
    print(f"시간: {first_after_gap[1]['time']}")
    print(f"내용: {first_after_gap[1]['log']}")
