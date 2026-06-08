import re

log_entry = """[2025-11-24 07:19:21] [INFO ] [LogAspect:107] - kicsServiceImpl RESPONSE : kr.or.kmi.service.impl.KicsServiceImpl(searchReservation) = {"data":{"message":[{"msg":"정상적으로 처리되었습니다.","code":"info","description":"","type":"info"}],"item":[{"clntempid":"302864","addrgstno":null,"selexamlist":"LUNG CT(폐),※위내시경(수면),갑상선초음파","dikey":"MC0GCCqGSIb3DQIJAyEA5DQaZgFLgkBW3rSAQ/ObqGh4JWzzGhqdFufadh1OpOk=","mpphontel":"01053823431","pid":"005053138","hngnm":"허찬욱","capaflag":"00","addexamlist":"","statflag":"C","rsrvtmflag":"A","escope":"위내시경,위수면","cmpynm":"한국미쓰비시엘리베이터","instcd":"111","healexamdetlnm":"종합건강검진/일반건강검진","rsrvflag":"5","addr":"11456 경기 양주시 고암길 305-40 청담마을 409동1103호","famyflag":"직원","shppaddr":"11456 경기 양주시 고암길 305-40 청담마을 409동1103호","sex":"M","ownamt":"130000","clamflag":"","deptnm":"설치사업부","statflagnm":"접수","orddd":"20251124","cmpycd":"B003523","instnm":"광화문","rsrvflagnm":"HOPS예약","rsrvstat":"1","capaflagnm":"예약확정","rrgstno":"990616-1","examnm":"종합검진[A형]","rsrvstatnm":"정상","rgstno":"2507398107","shpcyn":"Y","upperrgstno":"","linkrgstno":"","rsrvsndbsflag":"1","bogjamt":"","famyrelacd":"05","histremcnts":"","examlist":"일반건강검진,종합검진[A형],LUNG CT(폐),※위내시경(수면),갑상선초음파,기본검사,선택검사1,선택검사2,선택검사3,정신건강검사(우울증)(PHQ-9),정신건강검사(조기정신증)(CAPE-15),","selpkgcd":"ZZ991-XP012,ZZ992-XC029,ZZ993-KMI012","addpkgcd":"","cmpyseqno":"8","examseqno":"8","famynm":"허찬욱","cikey":"FLlHfU5JdKMRLPK/rqlXwezMD8YTsQlBo7WaFr3n22C4vi/yX+EXjLWUsglnyS3GocqXj51DaKKq/7/1k5qacg==","email":"cksdnr5382@naver.com","zipcd":"11456","zipcdaddr":"경기 양주시 고암길 305-40","detladdr":"청담마을 409동1103호","shppzipcd":"11456","shppzipcdaddr":"경기 양주시 고암길 305-40","shppdetladdr":"청담마을 409동1103호","status":null,"rdrncnt":"1","userid":null,"homepgchgrsrv":"Y","errormsg":"","altslist":"","mobilevgyn":"N","healexamdetlflag":"C01/G01","utm_source":null,"cmpycdlist":"B003523","brthdd":"19990616"}],"itemList":[{"clntempid":"302864","addrgstno":null,"selexamlist":"LUNG CT(폐),※위내시경(수면),갑상선초음파","dikey":"MC0GCCqGSIb3DQIJAyEA5DQaZgFLgkBW3rSAQ/ObqGh4JWzzGhqdFufadh1OpOk=","mpphontel":"01053823431","pid":"005053138","hngnm":"허찬욱","capaflag":"00","addexamlist":"","statflag":"C","rsrvtmflag":"A","escope":"위내시경,위수면","cmpynm":"한국미쓰비시엘리베이터","instcd":"111","healexamdetlnm":"종합건강검진/일반건강검진","rsrvflag":"5","addr":"11456 경기 양주시 고암길 305-40 청담마을 409동1103호","famyflag":"직원","shppaddr":"11456 경기 양주시 고암길 305-40 청담마을 409동1103호","sex":"M","ownamt":"130000","clamflag":"","deptnm":"설치사업부","statflagnm":"접수","orddd":"20251124","cmpycd":"B003523","instnm":"광화문","rsrvflagnm":"HOPS예약","rsrvstat":"1","capaflagnm":"예약확정","rrgstno":"990616-1","examnm":"종합검진[A형]","rsrvstatnm":"정상","rgstno":"2507398107","shpcyn":"Y","upperrgstno":"","linkrgstno":"","rsrvsndbsflag":"1","bogjamt":"","famyrelacd":"05","histremcnts":"","examlist":"일반건강검진,종합검진[A형],LUNG CT(폐),※위내시경(수면),갑상선초음파,기본검사,선택검사1,선택검사2,선택검사3,정신건강검사(우울증)(PHQ-9),정신건강검사(조기정신증)(CAPE-15),","selpkgcd":"ZZ991-XP012,ZZ992-XC029,ZZ993-KMI012","addpkgcd":"","cmpyseqno":"8","examseqno":"8","famynm":"허찬욱","cikey":"FLlHfU5JdKMRLPK/rqlXwezMD8YTsQlBo7WaFr3n22C4vi/yX+EXjLWUsglnyS3GocqXj51DaKKq/7/1k5qacg==","email":"cksdnr5382@naver.com","zipcd":"11456","zipcdaddr":"경기 양주시 고암길 305-40","detladdr":"청담마을 409동1103호","shppzipcd":"11456","shppzipcdaddr":"경기 양주시 고암길 305-40","shppdetladdr":"청담마을 409동1103호","status":null,"rdrncnt":"1","userid":null,"homepgchgrsrv":"Y","errormsg":"","altslist":"","mobilevgyn":"N","healexamdetlflag":"C01/G01","utm_source":null,"cmpycdlist":"B003523","brthdd":"19990616"}]},\"kicsParams\":{\"data\":[{\"searchflag\":\"3\",\"rgstno\":\"2507398107\"}]}} (99ms)"""

error_patterns = {
    'error': r'(?i)\b(error|exception|failed|failure)\b',
    'timeout': r'(?i)(timeout|timed out|time out)',
    'http_error': r'(?i)(status_code|status|code|error_code)[\s:=]*\b([45]\d{2})\b',  # 4xx, 5xx
    'stack_trace': r'at\s+[\w.$]+\(',
    'sql_error': r'(?i)(\bsql\s*error|deadlock|constraint)',
    'connection_error': r'(?i)(connection\s+(?:refused|reset|timeout)|unable\s+to\s+connect)',
    'null_pointer': r'(?i)(null\s*pointer|npe|nullpointerexception)',
}

print("Checking log entry against error patterns...")
found = False
for error_type, pattern in error_patterns.items():
    match = re.search(pattern, log_entry)
    if match:
        print(f"MATCH FOUND! Type: {error_type}")
        print(f"Pattern: {pattern}")
        print(f"Match: {match.group(0)}")
        found = True

if not found:
    print("No match found.")
