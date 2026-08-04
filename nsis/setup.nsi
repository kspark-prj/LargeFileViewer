Unicode true

!define PRODUCT_NAME "Hawkeye"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "Hawkeye Studio"
!define EXE_NAME "Hawkeye.exe"
!define ICON_FILE "main.ico" ; 아이콘 파일명

; Modern UI 적용
!include "MUI2.nsh"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "HawkeyeSetup.exe"
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
RequestExecutionLevel admin ; 레지스트리 등록을 위한 관리자 권한 요청

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

; 설치 섹션
Section "MainSection" SEC01
    SetOutPath "$INSTDIR"

    ; 설치할 파일 복사 (스크립트 경로에 Hawkeye.exe가 존재해야 함)
    File "${EXE_NAME}"

    ; 1. 바탕화면 바로가기 생성
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0

    ; 2. 시작 메뉴 바로가기 생성
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; 3. 컨텍스트 메뉴 레지스트리 등록
    WriteRegStr HKCR "*\shell\HawkeyeViewer" "" "Hawkeye로 열기"
    WriteRegStr HKCR "*\shell\HawkeyeViewer" "Icon" "$INSTDIR\${EXE_NAME}"
    WriteRegStr HKCR "*\shell\HawkeyeViewer\command" "" '"$INSTDIR\${EXE_NAME}" "%1"'

    ; 4. 제어판 프로그램 추가/제거 등록
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayName" "${PRODUCT_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayIcon" "$INSTDIR\${EXE_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "DisplayVersion" "${PRODUCT_VERSION}"

    ; 언인설러 생성
    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

; 제거 섹션
Section "Uninstall"
    ; 1. 바탕화면 및 시작 메뉴 바로가기 삭제
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

    ; 2. 설치 파일 삭제
    Delete "$INSTDIR\${EXE_NAME}"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"

    ; 3. 컨텍스트 메뉴 레지스트리 삭제
    DeleteRegKey HKCR "*\shell\HawkeyeViewer"

    ; 4. 제어판 등록 정보 삭제
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
SectionEnd
