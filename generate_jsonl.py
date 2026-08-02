import json
import os
import random
import string


def generate_random_string(length=50):
    """랜덤한 문자열 생성"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def create_jsonl_file_fast(output_filename, target_size_mb, batch_size=10000):
    """
    배치 방식을 사용하여 빠른 속도로 지정 용량(MB)의 JSONL 파일을 생성하는 함수
    :param output_filename: 생성할 파일 이름 (예: 'large_test_100mb.jsonl')
    :param target_size_mb: 목표 파일 크기 (MB)
    :param batch_size: 한 번에 디스크에 작성할 레코드 수 (기본값: 10,000)
    """
    target_bytes = target_size_mb * 1024 * 1024
    current_bytes = 0
    record_id = 1

    print(f"[{output_filename}] 파일 생성 시작 (목표: {target_size_mb} MB)...")

    cities = ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon"]

    with open(output_filename, "w", encoding="utf-8") as f:
        buffer = []

        while current_bytes < target_bytes:
            # 테스트용 레코드 생성
            data = {
                "id": record_id,
                "name": f"user_{record_id}",
                "email": f"user_{record_id}@example.com",
                "age": random.randint(18, 65),
                "city": random.choice(cities),
                "description": generate_random_string(80),
                "is_active": random.choice([True, False]),
                "score": round(random.uniform(0, 100), 2),
            }

            # JSON 라인 생성 (\n 포함)
            json_line = json.dumps(data, ensure_ascii=False) + "\n"
            line_bytes = len(json_line.encode("utf-8"))

            buffer.append(json_line)
            current_bytes += line_bytes
            record_id += 1

            # 설정한 배치 크기에 도달하거나 목표 용량을 채웠을 때 일괄 쓰기
            if len(buffer) >= batch_size or current_bytes >= target_bytes:
                f.writelines(buffer)
                buffer.clear()

    # 실제 생성 완료 파일 크기 측정
    actual_size_mb = os.path.getsize(output_filename) / (1024 * 1024)
    print(f"[{output_filename}] 생성 완료! (실제 크기: {actual_size_mb:.2f} MB, 총 {record_id - 1:,}개 레코드)\n")


if __name__ == "__main__":
    # 테스트용 파일 생성 목록 설정 (파일명, 용량(MB))
    targets = [
        ("test_1000mb.jsonl", 1000),  # 1GB 대용량 파일 생성 예시
    ]

    for filename, size in targets:
        create_jsonl_file_fast(filename, size)
