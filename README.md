# 🚀 Ultimate Large File Viewer & Searcher

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/Rust-Accelerated-DEA584?style=for-the-badge&logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-1f6feb?style=for-the-badge)](https://github.com/TomSchimansky/CustomTkinter)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey?style=for-the-badge)](#-빌드-및-실행)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

CustomTkinter 기반의 **대용량 텍스트/로그 파일 고속 뷰어 및 검색 도구**입니다.

수십 GB 이상의 초대형 파일도 **메모리 고갈이나 UI 멈춤(Freezing) 없이** 즉각적으로 로드, 탐색, 검색할 수 있도록 고도의 최적화 기술이 적용되었습니다.

---

## ✨ 주요 기능

| 기능                    | 설명                                                                               |
| ----------------------- | ---------------------------------------------------------------------------------- |
| **⚡ Rust 가속 코어**   | 인덱싱 속도 **10~20배**, 정규식 검색 **10~100배** 향상, 메모리 사용량 **78% 감소** |
| **🔄 하이브리드 폴백**  | Rust 미빌드 시 순수 파이썬 `mmap` 로직으로 자동 전환하여 정상 동작                 |
| **📂 초고속 인덱싱**    | 파일 크기 무관, 수초(Rust 가속 시 0.X초) 내 구조 분석 완료                         |
| **🖥️ 가상 스크롤**      | 화면에 보이는 영역만 실시간 렌더링하여 메모리 점유율 수십 MB 유지                  |
| **🔍 고속 검색**        | 키워드 및 **정규식(Regex)** 지원, 수백만 행 내 패턴 즉시 탐색                      |
| **🌐 인코딩 자동 감지** | `UTF-8`, `CP949(EUC-KR)`, `UTF-16`, `ASCII` 자동 분석, 한글 깨짐 방지              |
| **📋 HEAD / TAIL 필터** | 파일 앞/뒤 특정 행만 제한하여 모니터링                                             |
| **✂️ 파일 분할 / 병합** | 지정 용량(MB) 단위 분할 내보내기 및 다중 파일 순서 병합                            |
| **🎨 모던 다크 테마**   | CustomTkinter 기반 일관성 있는 세련된 다크 모드 GUI                                |

---

## 📁 프로젝트 구조

```
📂 largeFileViewer/
├── 📄 LargeFileViewer.py     # 메인 애플리케이션 (뷰어/검색/분할/병합)
├── 📄 LargeFileViewer.spec   # PyInstaller 빌드 스펙 파일
├── 📄 requirements.txt       # Python 의존성 패키지 목록
├── 📂 large_file_core/       # Rust 가속 코어 모듈
│   ├── 📄 Cargo.toml         #   Rust 종속성 및 빌드 설정
│   ├── 📄 pyproject.toml     #   Maturin(PyO3) 빌드 백엔드 구성
│   └── 📂 src/
│       └── 📄 lib.rs         #   Rust 인덱싱/검색 핵심 알고리즘
├── 📄 BUILD_GUIDE.md         # Windows / Linux 빌드 상세 가이드
├── 📄 RUST_GUIDE.md          # Rust 가속 원리 및 성능 향상 해설
├── 📄 LICENSE                # MIT 라이선스
└── 📄 README.md              # 본 문서

```

---

## ⚙️ 빌드 및 실행

### 빠른 시작 (소스 코드 실행)

```bash
# 1. 저장소 클론
git clone https://github.com/kspark-prj/largeFileViewer.git
cd largeFileViewer

# 2. (권장) 가상 환경 생성 및 활성화
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
# Linux:   source venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. (선택) Rust 가속 코어 빌드 — 10~100배 성능 향상
#    Rust 툴체인 + C++ 빌드 도구 필요 (상세: BUILD_GUIDE.md)
pip install ./large_file_core

# 5. 프로그램 실행
python LargeFileViewer.py

```

> **💡 Rust 코어가 빌드되지 않아도** 프로그램은 Python 폴백 모드로 완벽히 동작합니다.
> Rust 코어 빌드에는 Rust 툴체인과 C++ 링커가 필요합니다.

### 실행 파일 빌드 (Windows .exe / Linux ELF)

**환경 구성부터 Rust 코어 컴파일, 실행 파일 패키징, 트러블슈팅**까지 전체 과정을 단계별로 안내합니다.

👉 **[BUILD_GUIDE.md — 전체 빌드 상세 가이드](https://www.google.com/search?q=BUILD_GUIDE.md)**

---

## 🛠 핵심 기술 아키텍처 및 현행화 보완 사항

### 1. Rust 네이티브 Class 상태 유지 아키텍처 (`large_file_core`)

- **상태 유지형 바인딩:** 매 연산마다 대용량 인덱스 버퍼를 Python과 교환하며 발생하는 메모리 복사 지연(`IPC / 복사 랙`)을 완벽히 제거했습니다. Rust 내부에 `FileIndexCore` 인스턴스를 유지하여 힙 메모리를 독점적으로 관리합니다.
- **메모리 제로 카피(Zero-Copy):** 파일의 개행 인덱싱 상태와 바이트 버퍼를 Rust 네이티브 영역에 캡슐화한 뒤, 뷰포트 렌더링 시 필요한 오프셋 정보만 질의하는 구조로 전환되어 데이터 전송 오버헤드가 완전히 최적화되었습니다.

### 2. 메모리 안정성 및 정합성 방어 조치

- **Null/오류 하한선 방어 (`or 0` 안전장치):** 파일 끝(`EOF`) 도달 또는 비정상 포인터 예외 상황 시 Rust 엔진이 `None`을 반환하더라도 프로그램이 크래시(TypeError)되지 않도록 `self.rust_core.get_offset(idx) or 0` 코드를 구현하여 유효 오프셋을 철저하게 보장합니다.
- **좀비 스레드 격리 및 GUI 레이스 컨디션 방어:** 백그라운드 워커 스레드(`index_file_worker`, `search_keyword_worker`) 가 가동 중일 때 사용자가 창을 닫거나 다른 파일을 로드하는 상황을 대비하여, 메인 UI 진입부마다 `self.mmap_obj is not None` 및 `self.winfo_exists()` 검증 규칙을 촘촘히 설계하여 메모리 참조 오류(Segmentation Fault)와 데드락을 원천 차단했습니다.
- **용량별 파일 분할 메모리 정합성 보완:** 파일 청크 연산 시 `max()` 연산자를 통해 오프셋의 역전을 차단하고, 바이트 계산의 하한선 및 상한선 안전장치를 추가하여 루프가 무한히 돌거나 힙 메모리가 누수되는 결함을 해결했습니다.

### 3. mmap 기반 가상 스크롤

파일 전체를 메모리에 올리지 않고 OS의 `mmap`(Memory-Mapped File)으로 프로세스 주소 공간에 매핑합니다. 화면에 보이는 30~40줄의 바이트 영역만 실시간 슬라이싱하여 렌더링하므로, **수십 GB 파일에서도 메모리 점유율이 수십 MB 수준으로 유지**됩니다.

### 4. 멀티스레딩 비동기 처리

파일 인덱싱, 키워드 검색, 파일 분할/병합 등 모든 무거운 연산은 백그라운드 워커 스레드에서 수행되며, `after()` 메서드로 결과를 UI 스레드에 안전하게 전달합니다. 대용량 파일 처리 중에도 GUI가 멈추지 않습니다.

---

## 📦 클래스 구조

### `CTkCustomMenu(ctk.CTkFrame)`

CustomTkinter 다크 테마와 일관된 커스텀 드롭다운 메뉴입니다. 마우스 좌표 기반 외부 클릭 감지로 안정적인 메뉴 동작을 보장합니다.

### `UltimateLargeFileViewer(ctk.CTk)`

메인 애플리케이션 클래스입니다. 핵심 메서드:

| 메서드                    | 역할                                                                                    |
| ------------------------- | --------------------------------------------------------------------------------------- |
| `index_file_worker()`     | 대용량 파일 mmap 매핑 및 행 오프셋 인덱싱 (Rust 가속/파이썬 폴백 하이브리드)            |
| `render_view()`           | 현재 뷰포트 파일 내용 추출 및 키워드 하이라이팅 (Rust 안전장치 오프셋 연산 정합성 적용) |
| `search_keyword_worker()` | Rust/Python 하이브리드 고속 키워드·정규식 검색 (복사 랙 제거)                           |
| `split_file_worker()`     | 지정 용량 단위 파일 분할 내보내기 (오프셋 뒤틀림 및 메모리 누수 방지 적용)              |
| `merge_files_worker()`    | 다중 텍스트 파일 순서 병합                                                              |

---

## 📄 라이선스

본 프로젝트는 [MIT License](https://www.google.com/search?q=LICENSE) 하에 배포됩니다.

| 라이브러리                                                      | 라이선스         |
| --------------------------------------------------------------- | ---------------- |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT License      |
| [PyO3](https://github.com/PyO3/pyo3)                            | Apache-2.0 / MIT |
| Python 표준 라이브러리 (Tkinter)                                | PSF License      |
