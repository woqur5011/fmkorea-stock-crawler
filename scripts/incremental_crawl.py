"""
증분 크롤러 - 마지막 수집 이후 신규 글만 수집
실행: python scripts/incremental_crawl.py
"""
import requests, re, json, time, base64, httpx, os, sys
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from openai import AzureOpenAI

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# ── 설정 ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

USERS = {
    "ha2mandx": {
        "search_url": "https://www.fmkorea.com/search.php?mid=stock&category=&search_keyword=3158413881&search_target=member_srl",
        "nickname": "HA2MANDX",
        "file": os.path.join(DATA_DIR, "ha2mandx_2026.json"),
    },
    "seosaengwon": {
        "search_url": "https://www.fmkorea.com/search.php?mid=stock&category=&search_keyword=%EC%84%9C%EC%83%9D%EC%9B%90&search_target=nick_name",
        "nickname": "서생원",
        "file": os.path.join(DATA_DIR, "seosaengwon_2026.json"),
    },
}

TARGET_YEAR   = 2026
DELAY_LIST    = 3.0
DELAY_POST    = 2.5
MAX_RETRY     = 3
MAX_IMAGES    = 4
CONSECUTIVE_STOP = 10  # 연속 N개 기수집 글 → 종료

client = AzureOpenAI(
    azure_endpoint=os.environ.get("AZURE_ENDPOINT", "https://biz-insight-common-api.cognitiveservices.azure.com/"),
    api_key=os.environ.get("AZURE_API_KEY", "41quwWproISHED6BdaKPmarnJmWHdwNKuKrs61VuO7S6UX5VCyemJQQJ99CAACHYHv6XJ3w3AAAAACOGsnOn"),
    api_version=os.environ.get("AZURE_API_VERSION", "2025-04-01-preview"),
    http_client=httpx.Client(verify=False),
)

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
})

# ── 유틸 ─────────────────────────────────────────────────────────────────────
def strip_tags(html): return re.sub(r"<[^>]+>", "", html).strip()
def clean(text):
    for old, new in [("&nbsp;"," "),("&amp;","&"),("&lt;","<"),("&gt;",">"),("&quot;",'"'),("&#39;","'")]:
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()

def fetch(url, referer=None):
    headers = {"Referer": referer} if referer else {}
    for attempt in range(MAX_RETRY):
        try:
            r = SESSION.get(url, headers=headers, timeout=15)
            if r.status_code == 200: return r.text
            elif r.status_code == 430:
                wait = 10 * (attempt + 1)
                print(f"  [430] {wait}초 대기...")
                time.sleep(wait)
            else:
                print(f"  [HTTP {r.status_code}]")
                return None
        except Exception as e:
            print(f"  [오류] {e}")
            time.sleep(5)
    return None

def get_post_ids(page, search_url):
    html = fetch(search_url + f"&page={page}", referer=search_url)
    if not html: return []
    srls = re.findall(r"document_srl=(\d+)", html)
    seen = set(); ids = []
    for s in srls:
        if s not in seen: seen.add(s); ids.append(s)
    return ids

def download_image_b64(url):
    if url.startswith("//"): url = "https:" + url
    try:
        r = SESSION.get(url, timeout=10)
        if r.status_code == 200:
            mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
            return base64.b64encode(r.content).decode(), mime
    except: pass
    return None, None

def vision_parse(images_b64):
    content = [{"type": "text", "text": "이 이미지(들)의 핵심 내용을 한국어로 간결하게 요약해줘. 차트/그래프면 수치와 트렌드 위주로, 텍스트/기사면 주요 내용 위주로."}]
    for b64, mime in images_b64:
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    resp = client.chat.completions.create(
        model=os.environ.get("AZURE_MODEL", "gpt-5.4"),
        messages=[{"role": "user", "content": content}],
        max_completion_tokens=800,
    )
    return resp.choices[0].message.content.strip()

def parse_post(html, doc_id):
    title_m = re.search(r"<title>([^<]+)</title>", html)
    title = clean(strip_tags(title_m.group(1))) if title_m else ""
    title = re.sub(r"\s*[-|]\s*(주식|에펨코리아).*$", "", title).strip()
    date_m = re.search(r'class="date(?:\s[^"]*)?"\s*>([^<]+)<', html)
    date = clean(date_m.group(1)) if date_m else ""
    body = ""
    body_m = re.search(r'class="document_' + doc_id + r'[^"]*xe_content"[^>]*>(.*?)</div>', html, re.DOTALL)
    if body_m: body = clean(strip_tags(body_m.group(1)))
    comments = []
    for _, block in re.findall(r'<li[^>]*class="fdb_itm[^"]*comment-(\d+)"[^>]*>(.*?)</li>', html, re.DOTALL):
        content_m = re.search(r'class="comment-content[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        content = clean(strip_tags(content_m.group(1))) if content_m else ""
        if content: comments.append({"content": content})
    return {"id": doc_id, "title": title, "date": date, "body": body, "comments": comments}

def extract_year(date_str):
    m = re.search(r"(\d{4})", date_str)
    return int(m.group(1)) if m else None

# ── 증분 크롤링 ───────────────────────────────────────────────────────────────
def incremental_crawl(user_key):
    cfg = USERS[user_key]
    search_url = cfg["search_url"]
    data_file = cfg["file"]

    # 기존 데이터 로드
    if os.path.exists(data_file):
        with open(data_file, encoding="utf-8") as f:
            results = json.load(f)
    else:
        results = []

    collected_ids = set(p["id"] for p in results)
    print(f"\n[{cfg['nickname']}] 기수집: {len(results)}개")

    SESSION.get("https://www.fmkorea.com/", timeout=10)
    time.sleep(2)

    new_count = 0
    consecutive = 0
    page = 1

    while True:
        print(f"  page {page} 확인 중...", end=" ")
        post_ids = get_post_ids(page, search_url)
        if not post_ids:
            print("빈 결과 → 중단")
            break

        print(f"{len(post_ids)}개")
        time.sleep(DELAY_LIST)
        stop = False

        for pid in post_ids:
            if pid in collected_ids:
                consecutive += 1
                if consecutive >= CONSECUTIVE_STOP:
                    print(f"  연속 {CONSECUTIVE_STOP}개 기수집 → 완료")
                    stop = True
                    break
                continue
            consecutive = 0

            html = fetch(f"https://www.fmkorea.com/{pid}", referer=search_url + f"&page={page}")
            if not html: continue

            post = parse_post(html, pid)
            year = extract_year(post["date"])
            if year is not None and year < TARGET_YEAR:
                print(f"  {post['date']} → {TARGET_YEAR}년 이전 글 → 완료")
                stop = True
                break
            elif year is not None and year > TARGET_YEAR:
                time.sleep(DELAY_POST)
                continue

            # Vision 파싱
            body_m = re.search(r'class="document_' + pid + r'[^"]*xe_content"[^>]*>(.*?)</div>', html, re.DOTALL)
            if body_m:
                imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', body_m.group(1))
                imgs = [img for img in imgs if "fmkorea.com" in img or img.startswith("//image")]
                if imgs:
                    images_b64 = []
                    for img_url in imgs[:MAX_IMAGES]:
                        b64, mime = download_image_b64(img_url)
                        if b64: images_b64.append((b64, mime))
                    if images_b64:
                        try:
                            summary = vision_parse(images_b64)
                            if summary:
                                existing = post["body"].strip()
                                post["body"] = (existing + f"\n\n[이미지 파싱] {summary}") if existing else f"[이미지 파싱] {summary}"
                        except Exception as e:
                            print(f"    Vision 오류: {e}")

            results.append(post)
            collected_ids.add(pid)
            new_count += 1
            print(f"  [신규] {post['date']} | {post['title'][:40]}")
            time.sleep(DELAY_POST)

        if stop: break
        page += 1
        time.sleep(DELAY_LIST)

    # 날짜순 정렬 후 저장
    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"  → 신규 {new_count}개 추가, 총 {len(results)}개")
    return new_count


if __name__ == "__main__":
    total_new = 0
    for user_key in USERS:
        total_new += incremental_crawl(user_key)
    print(f"\n전체 신규: {total_new}개")
