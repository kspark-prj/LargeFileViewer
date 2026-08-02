import random
import time
from datetime import datetime

# 로그를 기록할 파일명
LOG_FILE = "test_app.log"

LEVELS = ["INFO", "INFO", "INFO", "WARN", "ERROR"]
MESSAGES = [
    "User login successful",
    "Database query executed in 12ms",
    "API request received: GET /api/v1/users",
    "Cache miss for key: user_session_9482",
    "Connection timeout with payment gateway",
    "High memory usage detected (85%)",
]
print(f"[{LOG_FILE}] 파일에 실시간 로그를 생성을 시작합니다... (Ctrl+C 로 종료)")

try:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            level = random.choice(LEVELS)
            msg = random.choice(MESSAGES)

            log_line = f"[{timestamp}] [{level}] {msg}\n"

            # 파일에 쓰기 및 즉시 저장(flush)
            f.write(log_line)
            f.flush()

            # 갱신 간격 테스트 (0.5초 설정)
            time.sleep(0.5)

except KeyboardInterrupt:
    print("\n로그 생성을 종료합니다.")
