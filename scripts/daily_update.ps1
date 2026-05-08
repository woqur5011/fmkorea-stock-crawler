# FMKorea 업데이트 스크립트 (PowerShell)
# Task Scheduler에서 실행: powershell -ExecutionPolicy Bypass -File "...\daily_update.ps1"

$REPO_DIR = "C:\Users\bsjang\NEXON_Copilot\fmkorea"
$PYTHON   = "C:\Users\bsjang\AppData\Local\Programs\Python\Python311\python.exe"
$GIT      = "C:\Program Files\Git\cmd\git.exe"
$LOG      = "$REPO_DIR\data\update.log"

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LOG -Value "$ts $msg" -Encoding UTF8
}

Set-Location $REPO_DIR
Log "===== 업데이트 시작 ====="

# 1. 증분 크롤링 (출력 실시간 로그)
Log "[1/3] 증분 크롤링 중..."
& $PYTHON scripts\incremental_crawl.py *>> $LOG
if ($LASTEXITCODE -ne 0) { Log "[오류] 크롤링 실패"; exit 1 }

# 2. 분석 업데이트 (현재 달만)
Log "[2/3] 분석 업데이트 중..."
& $PYTHON scripts\pre_analyze.py --incremental *>> $LOG
if ($LASTEXITCODE -ne 0) { Log "[오류] 분석 실패"; exit 1 }

# 3. GitHub Push
Log "[3/3] GitHub Push 중..."
& $GIT -C $REPO_DIR add data\
$diff = & $GIT -C $REPO_DIR diff --staged --name-only
if ($diff) {
    $date = Get-Date -Format "yyyy-MM-dd HH:mm"
    & $GIT -C $REPO_DIR commit -m "data: update $date" *>> $LOG
    & $GIT -C $REPO_DIR push origin main *>> $LOG
    Log "[완료] Push 성공"
} else {
    Log "[스킵] 변경사항 없음"
}

Log "===== 완료 ====="
Add-Content -Path $LOG -Value "" -Encoding UTF8
