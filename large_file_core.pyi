from typing import Any, Callable, List, Optional, Tuple

class FileIndexCore:
    """Rust 메모리 내부에 대용량 파일의 인덱싱 데이터와 mmap 매핑을 소유하고,
    데이터 복사 오버헤드와 GIL 병목 없이 초고속 연산을 수행하는 네이티브 가속 클래스입니다.
    """

    def __init__(self) -> None:
        """내부 상태(파일 경로, 라인 오프셋 벡터, 파일 크기 등)를 초기화합니다."""
        self.file_path: str = ""
        self.file_size: int = 0

    def index_file(
        self, file_path: str, progress_callback: Optional[Callable[[int, int], Any]] = None
    ) -> int:
        """대용량 파일을 열어 바이트 단위의 개행 문자(\n) 오프셋 벡터를 Rust 내부에 생성합니다.

        연산 전체가 GIL 해제 상태(allow_threads)에서 수행되며, 파이썬으로 거대한 리스트를
        리턴하지 않으므로 메모리 카피 비용이 발생하지 않습니다.

        Args:
            file_path (str): 분석할 파일 경로
            progress_callback (callable, optional): (진행률%, 현재까지 발견된 라인수)를 인자로 받는 콜백 함수

        Returns:
            int: 인덱싱이 완료된 파일의 총 라인 수 (Total Lines)
        """
        ...

    def search_keyword(
        self,
        pattern: bytes,
        is_regex: bool,
        case_insensitive: bool,
    ) -> Tuple[List[str], List[int], int]:
        """이미 인덱싱된 데이터를 바탕으로 지정된 키워드나 정규식 패턴을 초고속으로 검색합니다.

        파이썬에서 대량의 오프셋 리스트를 인자로 받지 않고 Rust 내부 메모리를 직접 참조하므로,
        수십 GB 파일에서도 복사 지연(Lag) 없이 즉시 검색 결과가 반환됩니다.

        Args:
            pattern (bytes): 검색할 바이트 패턴 (일반 문자열은 인코딩 처리 후 bytes로 전달)
            is_regex (bool): 정규식(Regex) 모드 활성화 여부
            case_insensitive (bool): 대소문자 구분 안 함 여부

        Returns:
            Tuple[List[str], List[int], int]:
                - List[str]: 매칭된 라인의 텍스트 리스트 (최대 2,000개 제한)
                - List[int]: 매칭된 라인의 제로 베이스(0-indexed) 인덱스 번호 리스트 (최대 2,000개 제한)
                - int: 파일 전체에서 발견된 매칭 항목의 총 개수 (전체 Count)
        """
        ...

    def get_offset(self, index: int) -> Optional[int]:
        """지정한 라인 번호(인덱스)의 바이트 오프셋 위치를 파일 뷰어 렌더링용으로 신속하게 조회합니다.

        Args:
            index (int): 조회하고자 하는 라인의 인덱스 (0-indexed)

        Returns:
            Optional[int]: 해당 라인의 바이트 시작 오프셋 값 (인덱스 범위를 벗어나면 None 반환)
        """
        ...
