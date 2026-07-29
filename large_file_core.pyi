from collections.abc import Callable
from typing import Any

class FileIndexCore:
    def __init__(self) -> None: ...
    def index_file(
        self, file_path: str, progress_callback: Callable[[int, int], Any] | None = None
    ) -> int: ...
    def get_offsets_range(self, start_idx: int, count: int) -> list[int]: ...
    def search_keyword(
        self,
        pattern: bytes,
        use_regex: bool = False,
    ) -> tuple[list[str], list[int], int]:
        """이미 인덱싱된 데이터를 바탕으로 키워드 또는 정규식(use_regex) 패턴을 검색합니다.

        Args:
            pattern (bytes): 검색할 바이트 패턴
            use_regex (bool): 정규식 검색 사용 여부 (기본값: False)

        Returns:
            tuple[list[str], list[int], int]: (라인 표기 목록, 라인 인덱스 목록, 총 검색 수)
        """

    def get_offset(self, index: int) -> int | None: ...
