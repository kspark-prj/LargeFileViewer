from typing import List, Tuple

def index_file(file_path: str) -> List[int]:
    """대용량 파일을 열어 바이트 단위의 개행 문자(\\n) 오프셋 리스트를 초고속으로 생성합니다."""
    ...

def search_keyword(
    file_path: str,
    pattern: bytes,
    is_regex: bool,
    line_offsets: List[int],
    case_insensitive: bool,
) -> Tuple[List[str], List[int], int]:
    """대용량 파일에서 지정된 키워드 또는 정규식 패턴을 검색하여 라인 번호 레이블, 라인 인덱스 및 매칭 개수를 반환합니다."""
    ...
