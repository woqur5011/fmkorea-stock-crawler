@echo off
:: Windows Task Scheduler에 일일 업데이트 작업 등록
:: 관리자 권한으로 실행 필요

set TASK_NAME=FMKorea Update
set BAT_FILE=C:\Users\bsjang\NEXON_Copilot\fmkorea\scripts\daily_update.bat

echo [Task Scheduler 등록 중... 6시간마다 (하루 4회)]
schtasks /create /tn "%TASK_NAME%" /tr "%BAT_FILE%" /sc hourly /mo 6 /st 03:00 /f

if %errorlevel% equ 0 (
    echo ✅ 등록 완료: 03:00 / 09:00 / 15:00 / 21:00 자동 실행
    echo 확인: schtasks /query /tn "%TASK_NAME%"
) else (
    echo ❌ 등록 실패. 관리자 권한으로 다시 실행해주세요.
)
pause
