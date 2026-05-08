@echo off
:: FMKorea 업데이트 스크립트 (하루 4회 자동 실행)

set REPO_DIR=C:\Users\bsjang\NEXON_Copilot\fmkorea
set PYTHON=C:\Users\bsjang\AppData\Local\Programs\Python\Python311\python.exe
set GIT=C:\Program Files\Git\cmd\git.exe
set LOG=%REPO_DIR%\data\update.log

echo ===== 업데이트 시작: %date% %time% ===== >> "%LOG%"

:: 1. 증분 크롤링
echo [1/3] 증분 크롤링 중... >> "%LOG%"
cd /d "%REPO_DIR%"
"%PYTHON%" scripts\incremental_crawl.py >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo [오류] 크롤링 실패 >> "%LOG%"
    goto :end
)

:: 2. 분석 캐시 업데이트 (이번 달만)
echo [2/3] 분석 업데이트 중... >> "%LOG%"
"%PYTHON%" scripts\pre_analyze.py --incremental >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo [오류] 분석 실패 >> "%LOG%"
    goto :end
)

:: 3. GitHub Push
echo [3/3] GitHub Push 중... >> "%LOG%"
"%GIT%" -C "%REPO_DIR%" add data\ >> "%LOG%" 2>&1
"%GIT%" -C "%REPO_DIR%" diff --staged --quiet
if %errorlevel% neq 0 (
    "%GIT%" -C "%REPO_DIR%" commit -m "data: update %date% %time%" >> "%LOG%" 2>&1
    "%GIT%" -C "%REPO_DIR%" push origin main >> "%LOG%" 2>&1
    echo [완료] Push 성공 >> "%LOG%"
) else (
    echo [스킵] 변경사항 없음 >> "%LOG%"
)

:end
echo ===== 완료: %time% ===== >> "%LOG%"
echo. >> "%LOG%"
