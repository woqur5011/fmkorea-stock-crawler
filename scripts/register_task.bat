@echo off
:: Windows Task Scheduler에 일일 업데이트 작업 등록
:: 관리자 권한으로 실행 필요

set TASK_NAME=FMKorea Daily Update
set BAT_FILE=C:\Users\bsjang\NEXON_Copilot\fmkorea\scripts\daily_update.bat
set RUN_TIME=03:00

echo [Task Scheduler 등록 중...]
schtasks /create /tn "%TASK_NAME%" /tr "%BAT_FILE%" /sc daily /st %RUN_TIME% /ru "%USERNAME%" /f

if %errorlevel% equ 0 (
    echo ✅ 등록 완료: 매일 새벽 %RUN_TIME%에 자동 실행됩니다.
    echo 확인: schtasks /query /tn "%TASK_NAME%"
) else (
    echo ❌ 등록 실패. 관리자 권한으로 다시 실행해주세요.
)
pause
