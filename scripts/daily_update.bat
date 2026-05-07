@echo off
:: FMKorea 일일 업데이트 스크립트
:: Windows Task Scheduler에 등록: 매일 새벽 3시 실행

set REPO_DIR=C:\Users\bsjang\NEXON_Copilot\fmkorea
set PYTHON=C:\Users\bsjang\AppData\Local\Programs\Python\Python311\python.exe
set LOG=%REPO_DIR%\data\update.log

echo ===== 일일 업데이트 시작: %date% %time% ===== >> %LOG%

:: 1. 증분 크롤링
echo [1/3] 증분 크롤링 중... >> %LOG%
cd /d %REPO_DIR%
%PYTHON% scripts\incremental_crawl.py >> %LOG% 2>&1
if %errorlevel% neq 0 (
    echo [오류] 크롤링 실패 >> %LOG%
    goto :end
)

:: 2. 분석 캐시 업데이트 (이번 달만)
echo [2/3] 분석 업데이트 중... >> %LOG%
%PYTHON% scripts\pre_analyze.py --incremental >> %LOG% 2>&1
if %errorlevel% neq 0 (
    echo [오류] 분석 실패 >> %LOG%
    goto :end
)

:: 3. GitHub Push
echo [3/3] GitHub Push 중... >> %LOG%
git add data\ >> %LOG% 2>&1
git diff --staged --quiet
if %errorlevel% neq 0 (
    git commit -m "data: daily update %date%" >> %LOG% 2>&1
    git push origin main >> %LOG% 2>&1
    echo [완료] Push 성공 >> %LOG%
) else (
    echo [스킵] 변경사항 없음 >> %LOG%
)

:end
echo ===== 업데이트 완료: %time% ===== >> %LOG%
echo. >> %LOG%
