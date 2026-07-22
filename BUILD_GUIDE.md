# 🛠️ 빌드 및 설치 가이드 (BUILD_GUIDE.md)

이 가이드는 GitHub에서 소스를 클론한 후 **프로그램을 실행하거나 배포용 실행 파일을 만드는 전체 과정**을 단계별로 안내합니다.

> **💡 Rust 코어 없이도 동작합니다**
> 본 프로그램은 **자동 폴백(Fallback) 구조**로 설계되어 있어, Rust 코어를 빌드하지 않아도 순수 파이썬 모드로 정상 작동합니다.
> 다만 대용량 파일 인덱싱과 정규식 검색 속도를 **10~100배 가속**하려면 Rust 코어 빌드를 적극 권장합니다.

---

## 📋 전체 빌드 흐름 한눈에 보기

```
① Git 클론 → ② Python 환경 구성 → ③ Python 의존성 설치
                                          ↓
                    ┌─────────────────────────────────────────┐
                    │  ④ (선택) Rust 코어 빌드 — 고속 모드    │
                    │    C++ 빌드 도구 설치                    │
                    │    Rust 툴체인 설치                      │
                    │    maturin으로 코어 컴파일               │
                    └─────────────────────────────────────────┘
                                          ↓
              ⑤ 프로그램 실행 (python LargeFileViewer.py)
                                          ↓
                    ┌─────────────────────────────────────────┐
                    │  ⑥ (선택) 실행 파일 패키징 (.exe / ELF) │
                    └─────────────────────────────────────────┘
```

---

## 🪟 Windows 환경

### ① 소스 코드 클론

```powershell
git clone https://github.com/kspark-prj/largeFileViewer.git
cd largeFileViewer
```

### ② Python 환경 구성

Python **3.8 이상**이 필요합니다. 가상 환경 사용을 권장합니다.

```powershell
# Python 버전 확인
python --version

# (권장) 가상 환경 생성 및 활성화
python -m venv venv
.\venv\Scripts\Activate.ps1
```

> **⚠️ PowerShell 실행 정책 오류 시**
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` 실행 후 다시 시도하세요.

### ③ Python 의존성 설치

```powershell
pip install -r requirements.txt
```

이 단계에서 설치되는 패키지:
| 패키지 | 용도 |
|--------|------|
| `customtkinter` | 모던 다크 테마 GUI 프레임워크 |
| `pyinstaller` | 실행 파일(.exe) 패키징 도구 |

### ④ (선택) Rust 가속 코어 빌드

> **이 단계를 건너뛰면** 프로그램은 순수 파이썬 모드로 동작합니다.
> 대용량 파일(1GB+)을 자주 다루신다면 빌드를 권장합니다.

#### 4-1. Visual Studio C++ 빌드 도구 설치

Rust 코드를 컴파일하려면 C++ 링커(`link.exe`)가 필요합니다.

1. [MS C++ 빌드 도구 다운로드](https://visualstudio.microsoft.com/ko/visual-cpp-build-tools/)로 이동하여 설치 파일을 다운로드합니다.
2. 설치 관리자에서 **"C++를 사용한 데스크톱 개발"** 워크로드를 선택합니다.
3. 우측 상세 정보에서 아래 컴포넌트가 체크되어 있는지 확인합니다:
    - **MSVC v143 - VS 2022 C++ x64/x86 빌드 도구**
    - **Windows 10 SDK** 또는 **Windows 11 SDK**
4. 설치 완료 후 **시스템을 재부팅**합니다.

#### 4-2. Rust 툴체인 설치

1. [Rust 공식 사이트](https://www.rust-lang.org/tools/install)에서 `rustup-init.exe`를 다운로드하여 실행합니다.
2. 설치 프롬프트에서 기본 옵션(1번)을 선택합니다.
3. 설치 완료 후 **새 터미널**을 열어 설치를 확인합니다:

```powershell
rustc --version    # 예: rustc 1.xx.x
cargo --version    # 예: cargo 1.xx.x
```

> **⚠️ `cargo`를 찾을 수 없다는 오류가 나올 경우**
> 터미널에서 아래 명령으로 PATH를 임시 등록하세요:
>
> ```powershell
> $env:PATH += ";$env:USERPROFILE\.cargo\bin"
> ```

#### 4-3. Rust 코어 컴파일 및 설치

```powershell
# maturin(Rust↔Python 빌드 도구)이 자동으로 설치되며 컴파일을 수행합니다
pip install ./large_file_core
```

이 명령이 수행하는 작업:

1. `pyproject.toml`을 읽고 빌드 백엔드로 **maturin**을 자동 설치
2. `Cargo.toml`의 Rust 의존성(`memmap2`, `rayon`, `regex`, `pyo3`)을 다운로드
3. `src/lib.rs` Rust 소스를 네이티브 코드로 컴파일
4. 컴파일된 `.pyd` 확장 모듈을 현재 Python 환경에 설치

> **💡 Python 3.13+ 호환성**
> 본 프로젝트는 최신 `pyo3 (v0.23.3+)` 및 `Bound` API로 설계되어 있어 Python 3.13 이상에서도 별도 환경 변수 없이 정상 빌드됩니다.

#### 4-4. Rust 가속 활성화 확인

프로그램 실행 후 파일을 열면 상단에 다음과 같이 표시됩니다:

- ✅ **`인덱싱 중... (Rust 가속 사용)`** → 정상 활성화
- ⚠️ `인덱싱 중... (Python 모드)` → 코어 미설치, 순수 파이썬으로 동작

### ⑤ 프로그램 실행

```powershell
python LargeFileViewer.py
```

### ⑥ (선택) 실행 파일(.exe) 패키징

Rust 코어 포함 여부와 관계없이 독립 실행형 `.exe`를 생성할 수 있습니다.

```powershell
# Spec 파일을 이용한 빌드 (Rust 코어가 설치된 상태라면 자동으로 포함됨)
pyinstaller --clean --noconfirm LargeFileViewer.spec
```

빌드 완료 후 **`dist/LargeFileViewer.exe`** 가 생성됩니다.

> **💡 Rust 코어를 exe에 포함시키려면**
> 반드시 ④단계에서 Rust 코어를 먼저 빌드한 뒤 PyInstaller를 실행하세요.
> `.spec` 파일이 설치된 패키지를 자동으로 감지하여 포함시킵니다.

---

## 🐧 Linux 환경

### ① 소스 코드 클론

```bash
git clone https://github.com/kspark-prj/largeFileViewer.git
cd largeFileViewer
```

### ② 시스템 의존성 설치

GUI 프레임워크(Tkinter)와 컴파일 도구를 설치합니다.

#### Debian / Ubuntu 계열

```bash
sudo apt-get update
sudo apt-get install -y build-essential python3-tk python3-dev python3-venv curl
```

#### RedHat / Fedora 계열

```bash
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y python3-tkinter python3-devel gcc curl
```

### ③ Python 환경 구성 및 의존성 설치

```bash
# (권장) 가상 환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# Python 의존성 설치
pip install -r requirements.txt
```

### ④ (선택) Rust 가속 코어 빌드

#### 4-1. Rust 툴체인 설치

```bash
# Rust 설치 스크립트 다운로드 및 실행
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 환경 변수 반영 (새 터미널을 열어도 됩니다)
source $HOME/.cargo/env

# 설치 확인
rustc --version
cargo --version
```

> **💡 Linux에서는 C++ 빌드 도구가 별도로 필요하지 않습니다.**
> ②단계에서 설치한 `build-essential`(Debian) 또는 `Development Tools`(Fedora)에 GCC 링커가 이미 포함되어 있습니다.

#### 4-2. Rust 코어 컴파일 및 설치

```bash
pip install ./large_file_core
```

### ⑤ 프로그램 실행

```bash
python3 LargeFileViewer.py
```

> **ℹ️ 참고:** GUI 환경(X11 / Wayland)이 활성화된 데스크톱 환경에서만 화면이 정상 로드됩니다.
> CLI 전용 서버 환경에서는 가상 디스플레이(Xvfb 등) 구성이 필요합니다.

### ⑥ (선택) 실행 파일 (ELF 바이너리) 패키징

```bash
# 단일 바이너리 빌드
pyinstaller -w -F --collect-all large_file_core LargeFileViewer.py
```

빌드 완료 후 **`dist/LargeFileViewer`** 경로에 실행 파일이 생성됩니다.

---

## ❓ 트러블슈팅

### 공통 문제

| 증상                                             | 원인                      | 해결 방법                                                                                 |
| ------------------------------------------------ | ------------------------- | ----------------------------------------------------------------------------------------- |
| `pip install ./large_file_core` 실패             | Rust 툴체인 미설치        | Rust 설치 후 **새 터미널**에서 재시도                                                     |
| `cargo` 명령을 찾을 수 없음                      | PATH 미등록               | Windows: `$env:PATH += ";$env:USERPROFILE\.cargo\bin"` / Linux: `source $HOME/.cargo/env` |
| `link.exe` 에러 (Windows)                        | C++ 빌드 도구 미설치      | Visual Studio C++ 빌드 도구 설치 후 재부팅                                                |
| `error: linker 'cc' not found` (Linux)           | GCC 미설치                | `sudo apt install build-essential`                                                        |
| PyInstaller exe에 Rust 코어가 빠짐               | 코어 미설치 상태에서 빌드 | `pip install ./large_file_core` 후 PyInstaller 재실행                                     |
| `ModuleNotFoundError: No module named 'tkinter'` | Tkinter 미설치 (Linux)    | `sudo apt install python3-tk`                                                             |

### 빌드 결과 확인

```powershell
# Python에서 Rust 코어 설치 여부 확인
python -c "import large_file_core; print('✅ Rust 코어 설치됨')"
```

정상이면 `✅ Rust 코어 설치됨`이 출력됩니다.
`ModuleNotFoundError`가 출력되면 ④단계를 다시 수행하세요.

---

## 📂 빌드 산출물 정리

빌드 과정에서 생성되는 폴더들은 `.gitignore`에 의해 Git 추적에서 제외됩니다.

| 폴더                      | 내용                   | 크기    | 재생성 방법                     |
| ------------------------- | ---------------------- | ------- | ------------------------------- |
| `large_file_core/target/` | Rust 컴파일 캐시       | ~470 MB | `pip install ./large_file_core` |
| `build/`                  | PyInstaller 중간 파일  | ~38 MB  | `pyinstaller` 재실행            |
| `dist/`                   | 최종 실행 파일         | ~30 MB  | `pyinstaller` 재실행            |
| `__pycache__/`            | Python 바이트코드 캐시 | ~0.1 MB | Python 실행 시 자동 생성        |
| `venv/`                   | Python 가상 환경       | 다양    | `python -m venv venv`           |
