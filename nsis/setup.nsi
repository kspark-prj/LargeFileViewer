Unicode true

!define PRODUCT_NAME "Hawkeye"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "Hawkeye Studio"

; =========================================================
; 소스 폴더 경로 및 실행 파일명 정의
; =========================================================
!define SRC_DIR "dist\Hawkeye"   ; PyInstaller -D 빌드 결과물 폴더 경로
!define EXE_NAME "Hawkeye.exe"   ; 폴더 내의 메인 실행 파일명
!define ICON_FILE "main.ico"     ; 아이콘 파일명

; Modern UI 적용
!include "MUI2.nsh"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "HawkeyeSetup.exe"

; AppData\Local 경로로 설치
InstallDir "$LOCALAPPDATA\${PRODUCT_NAME}"

; 관리자 권한 요청 없이 일반 사용자(user) 수준으로 실행
RequestExecutionLevel user

; 설치/언인설러 아이콘 지정
!define MUI_ICON "${ICON_FILE}"
!define MUI_UNICON "${ICON_FILE}"

; 페이지 설정
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; 언어 설정
!insertmacro MUI_LANGUAGE "Korean"

; =========================================================
; 설치 섹션
; =========================================================
Section "MainSection" SEC01
    ; 0. [추가] 설치/덮어쓰기 전 기존 실행 중인 프로세스 자동 종료
    nsExec::Exec 'taskkill /F /IM "${EXE_NAME}" /T'
    Sleep 1000 ; 파일 핸들 해제 대기 (1초)

    SetOutPath "$INSTDIR"

    ; PyInstaller 빌드 폴더 내 모든 파일 및 서브폴더 재귀 복사
    File /r "${SRC_DIR}\*.*"

    ; 1. 바탕화면 바로가기 생성
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0

    ; 2. 시작 메뉴 바로가기 생성
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; 3. 일반 사용자 전용 컨텍스트 메뉴 레지스트리 등록 (HKCU)
    WriteRegStr HKCU "Software\Classes\*\shell\HawkeyeViewer" "" "Hawkeye로 열기"
    WriteRegStr HKCU "Software\Classes\*\shell\HawkeyeViewer" "Icon" "$INSTDIR\${EXE_NAME}"
    WriteRegStr HKCU "Software\Classes\*\shell\HawkeyeViewer\command" "" '"$INSTDIR\${EXE_NAME}" "%1"'

    ; 4. 제어판 프로그램 추가/제거 등록 (HKCU)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayName" "${PRODUCT_NAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayIcon" "$INSTDIR\${EXE_NAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayVersion" "${PRODUCT_VERSION}"

    ; 언인설러 생성
    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

; =========================================================
; 삭제 섹션 (프로세스 자동 종료 및 완벽 제거)
; =========================================================
Section "Uninstall"
    ; 0. [핵심 추가] 실행 중인 Hawkeye 및 하위 프로세스 강제 종료 (콘솔 창 숨김)
    nsExec::Exec 'taskkill /F /IM "${EXE_NAME}" /T'
    Sleep 1000 ; 윈도우 OS가 프로세스 및 파일 잠금을 해제할 시간을 보장 (1초)

    ; 작업 경로를 임시 폴더($TEMP)로 이동하여 설치 폴더 핸들 잠금 해제
    SetOutPath $TEMP

    ; 1. 바탕화면 및 시작 메뉴 바로가기 삭제
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

    ; 2. 레지스트리 삭제
    DeleteRegKey HKCU "Software\Classes\*\shell\HawkeyeViewer"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

    ; 3. 실행 중인 언인스톨러 파일 자체 삭제 예약
    Delete /REBOOTOK "$INSTDIR\Uninstall.exe"

    ; 4. 설치 폴더 전체(하위 모든 파일/서브폴더 포함) 강제 제거
    RMDir /r /REBOOTOK "$INSTDIR"

    ; 5. 상위 디렉토리가 비어있는 경우 제거
    RMDir "$LOCALAPPDATA\${PRODUCT_NAME}"
SectionEnd
