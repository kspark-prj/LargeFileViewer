@echo off
chcp 65001 > nul
echo =========================================
echo  Hawkeye Installer 빌드를 시작합니다...
echo =========================================

:: NSIS 실행 파일 경로 설정
set MAKENSIS="C:\Program Files (x86)\NSIS\makensis.exe"

:: NSIS 설치 여부 확인 (경로 변수 전체를 따옴표로 감쌉니다)
if not exist %MAKENSIS% (
    echo [ERROR] NSIS가 설치되어 있지 않거나 경로를 찾을 수 없습니다.
    echo %MAKENSIS% 경로를 확인해 주세요.
    pause
    exit /b
)

:: NSI 스크립트 컴파일 실행
%MAKENSIS% /V3 "setup.nsi"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =========================================
    echo  빌드가 성공적으로 완료되었습니다!
    echo  결과물: HawkeyeSetup.exe
    echo =========================================
) else (
    echo.
    echo [ERROR] 빌드 중 오류가 발생했습니다.
)

pause
