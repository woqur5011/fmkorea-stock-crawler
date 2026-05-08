"""
FMKorea 특정 유저 게시글 크롤러
Usage:
    python fmkorea_crawler.py --user ha2mandx
    python fmkorea_crawler.py --user seosaengwon
"""
import requests, re, json, time, base64, httpx, os, argparse
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from openai import AzureOpenAI

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# ── 유저 설정 ─────────────────────────────────────────────────────────────────
USERS = {
    'ha2mandx': {
        'search_url': 'https://www.fmkorea.com/search.php?mid=stock&category=&search_keyword=3158413881&search_target=member_srl',
        'nickname': 'HA2MANDX',
    },
    'seosaengwon': {
        'search_url': 'https://www.fmkorea.com/search.php?mid=stock&category=&search_keyword=%EC%84%9C%EC%83%9D%EC%9B%90&search_target=nick_name',
        'nickname': '서생원',
    },
    'son': {
        'search_url': 'https://www.fmkorea.com/search.php?mid=stock&search_target=member_srl&search_keyword=224241',
        'nickname': '손흥민',
    },
}

# ── 공통 설정 ─────────────────────────────────────────────────────────────────
TARGET_YEAR      = 2026
DELAY_LIST       = 3.0
DELAY_POST       = 2.5
MAX_RETRY        = 3
MAX_IMAGES       = 4
CONSECUTIVE_STOP = 10

# ── Azure OpenAI ──────────────────────────────────────────────────────────────
client = AzureOpenAI(
    azure_endpoint="https://biz-insight-common-api.cognitiveservices.azure.com/",
    api_key="41quwWproISHED6BdaKPmarnJmWHdwNKuKrs61VuO7S6UX5VCyemJQQJ99CAACHYHv6XJ3w3AAAAACOGsnOn",
    api_version="2025-04-01-preview",
    http_client=httpx.Client(verify=False)
)

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
})

# ── 유틸 ─────────────────────────────────────────────────────────────────────
def strip_tags(html):
    return re.sub(r'<[^>]+>', '', html).strip()

def clean(text):
    for old, new in [('&nbsp;',' '),('&amp;','&'),('&lt;','<'),('&gt;','>'),('&quot;','"'),('&#39;',"'")]:
        text = text.replace(old, new)
    return re.sub(r'\s+', ' ', text).strip()

def fetch_with_retry(url, referer=None, retries=MAX_RETRY):
    headers = {'Referer': referer} if referer else {}
    for attempt in range(retries):
        try:
            r = SESSION.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 430:
                wait = 10 * (attempt + 1)
                print(f'  [430 차단] {wait}초 대기 후 재시도 ({attempt+1}/{retries})...')
                time.sleep(wait)
            else:
                print(f'  [HTTP {r.status_code}] {url}')
                return None
        except Exception as e:
            print(f'  [오류] {e}')
            time.sleep(5)
    return None

def get_post_ids(page, search_url):
    url = search_url + f'&page={page}'
    html = fetch_with_retry(url, referer=search_url)
    if not html:
        return []
    srls = re.findall(r'document_srl=(\d+)', html)
    seen = set(); ids = []
    for s in srls:
        if s not in seen:
            seen.add(s); ids.append(s)
    return ids

def download_image_b64(url):
    if url.startswith('//'): url = 'https:' + url
    try:
        r = SESSION.get(url, timeout=10)
        if r.status_code == 200:
            mime = r.headers.get('Content-Type', 'image/jpeg').split(';')[0]
            return base64.b64encode(r.content).decode(), mime
    except:
        pass
    return None, None

def vision_parse(images_b64):
    content = [{"type": "text", "text": "이 이미지(들)의 핵심 내용을 한국어로 간결하게 요약해줘. 차트/그래프면 수치와 트렌드 위주로, 텍스트/기사면 주요 내용 위주로."}]
    for b64, mime in images_b64:
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    resp = client.chat.completions.create(
        model="gpt-5.4",
        messages=[{"role": "user", "content": content}],
        max_completion_tokens=800
    )
    return resp.choices[0].message.content.strip(), resp.usage.prompt_tokens, resp.usage.completion_tokens

def parse_post(html, doc_id):
    title_m = re.search(r'<title>([^<]+)</title>', html)
    title = clean(strip_tags(title_m.group(1))) if title_m else ''
    title = re.sub(r'\s*[-|]\s*(주식|에펨코리아).*$', '', title).strip()

    date_m = re.search(r'class="date(?:\s[^"]*)?"\s*>([^<]+)<', html)
    date = clean(date_m.group(1)) if date_m else ''

    body = ''
    body_m = re.search(r'class="document_' + doc_id + r'[^"]*xe_content"[^>]*>(.*?)</div>', html, re.DOTALL)
    if body_m:
        body = clean(strip_tags(body_m.group(1)))

    comments = []
    for cmt_id, block in re.findall(r'<li[^>]*class="fdb_itm[^"]*comment-(\d+)"[^>]*>(.*?)</li>', html, re.DOTALL):
        nick_m = re.search(r'class="(?:nickname|nick)[^"]*"[^>]*>([^<]+)<', block)
        nick = clean(nick_m.group(1)) if nick_m else ''
        cmt_date_m = re.search(r'class="date[^"]*"\s*>([^<]+)<', block)
        cmt_date = clean(cmt_date_m.group(1)) if cmt_date_m else ''
        content_m = re.search(r'class="comment-content[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        content = clean(strip_tags(content_m.group(1))) if content_m else ''
        if content:
            comments.append({'author': nick, 'date': cmt_date, 'content': content})

    return {'id': doc_id, 'title': title, 'date': date, 'body': body, 'comments': comments}

def extract_year(date_str):
    m = re.search(r'(\d{4})', date_str)
    return int(m.group(1)) if m else None

def save_progress(results, page, total_prompt, total_completion, phase, progress_file, output_file):
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump({
            'results': results, 'next_page': page,
            'total_prompt_tokens': total_prompt,
            'total_completion_tokens': total_completion,
            'phase': phase,
        }, f, ensure_ascii=False)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def crawl_posts(page, results, collected_ids, total_prompt, total_completion, phase, search_url, progress_file, output_file):
    stop = False
    blocked = False
    consecutive_collected = 0

    while not stop:
        print(f'\n[Phase {phase} / 페이지 {page}] 목록 수집 중...')
        post_ids = get_post_ids(page, search_url)

        if not post_ids:
            print(f'  게시글 없음 (차단 또는 마지막 페이지) → 중단')
            blocked = True
            break

        print(f'  {len(post_ids)}개 발견')
        time.sleep(DELAY_LIST)

        for pid in post_ids:
            if pid in collected_ids:
                if phase == 2:
                    consecutive_collected += 1
                    if consecutive_collected >= CONSECUTIVE_STOP:
                        print(f'  연속 {CONSECUTIVE_STOP}개 기수집 → Phase 2 완료')
                        stop = True
                        break
                continue

            consecutive_collected = 0

            html = fetch_with_retry(f'https://www.fmkorea.com/{pid}', referer=search_url + f'&page={page}')
            if not html:
                continue

            post = parse_post(html, pid)
            year = extract_year(post['date'])

            if year is not None and year < TARGET_YEAR:
                if phase == 1:
                    print(f'  → {post["date"]} | {TARGET_YEAR}년 이전 글 발견 → Phase 1 완료')
                    stop = True
                    break
                else:
                    time.sleep(DELAY_POST)
                    continue
            elif year is not None and year > TARGET_YEAR:
                print(f'  → {post["date"]} | {TARGET_YEAR}년 이후 글 스킵')
                time.sleep(DELAY_POST)
                continue

            # 이미지 Vision 파싱
            body_m = re.search(r'class="document_' + pid + r'[^"]*xe_content"[^>]*>(.*?)</div>', html, re.DOTALL)
            imgs = []
            if body_m:
                imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', body_m.group(1))
                imgs = [img for img in imgs if 'fmkorea.com' in img or img.startswith('//image')]

            img_label = ''
            if imgs:
                images_b64 = []
                for img_url in imgs[:MAX_IMAGES]:
                    b64, mime = download_image_b64(img_url)
                    if b64:
                        images_b64.append((b64, mime))
                if images_b64:
                    try:
                        summary, pt, ct = vision_parse(images_b64)
                        total_prompt += pt
                        total_completion += ct
                        if summary:
                            existing = post['body'].strip()
                            post['body'] = (existing + f'\n\n[이미지 파싱] {summary}') if existing else f'[이미지 파싱] {summary}'
                            img_label = f'[이미지 {len(images_b64)}장 파싱]'
                    except Exception as e:
                        print(f'    Vision 오류: {e}')

            results.append(post)
            collected_ids.add(pid)
            print(f'  [{len(results):03d}] {post["date"]} | {post["title"][:40]} | 댓글 {len(post["comments"])}개 {img_label}')
            time.sleep(DELAY_POST)

        if stop:
            break

        save_progress(results, page + 1, total_prompt, total_completion, phase, progress_file, output_file)
        page += 1
        time.sleep(DELAY_LIST)

    return results, collected_ids, total_prompt, total_completion, page, stop, blocked

# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', required=True, choices=list(USERS.keys()), help='크롤링할 유저')
    args = parser.parse_args()

    user_key = args.user
    cfg = USERS[user_key]
    search_url = cfg['search_url']
    nickname = cfg['nickname']

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    os.makedirs(data_dir, exist_ok=True)
    output_file   = os.path.join(data_dir, f'{user_key}_{TARGET_YEAR}.json')
    progress_file = os.path.join(data_dir, f'{user_key}_progress.json')

    print(f'{"="*60}')
    print(f'FMKorea 크롤러 - {nickname} ({user_key})')
    print(f'출력: {output_file}')
    print(f'{"="*60}')

    if os.path.exists(progress_file):
        with open(progress_file, encoding='utf-8') as f:
            progress = json.load(f)
        results = progress['results']
        start_page = progress['next_page']
        total_prompt = progress['total_prompt_tokens']
        total_completion = progress['total_completion_tokens']
        phase = progress.get('phase', 1)
        collected_ids = set(p['id'] for p in results)
        print(f'[재개] Phase {phase}, 페이지 {start_page}부터, 기수집 {len(results)}개\n')
    else:
        results = []
        start_page = 1
        total_prompt = 0
        total_completion = 0
        phase = 1
        collected_ids = set()

    SESSION.get('https://www.fmkorea.com/', timeout=10)
    time.sleep(2)

    # Phase 1: 역방향
    if phase == 1:
        print(f'\n[Phase 1] 역방향 수집 (page {start_page}~ → {TARGET_YEAR}.01.01까지)')
        results, collected_ids, total_prompt, total_completion, last_page, done, blocked = \
            crawl_posts(start_page, results, collected_ids, total_prompt, total_completion,
                        1, search_url, progress_file, output_file)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        if blocked:
            save_progress(results, last_page, total_prompt, total_completion, 1, progress_file, output_file)
            print(f'\n차단됨. progress 보존 → 나중에 재개 가능')
            _print_summary(results, total_prompt, total_completion)
            return

        print(f'\n[Phase 1 완료] 총 {len(results)}개. Phase 2 시작...')
        start_page = 1
        phase = 2
        time.sleep(DELAY_LIST)

    # Phase 2: 순방향 (신규 글)
    print(f'\n[Phase 2] 순방향 수집 (page 1~ → 기수집 {CONSECUTIVE_STOP}개 연속 시 종료)')
    results, collected_ids, total_prompt, total_completion, last_page, done, blocked = \
        crawl_posts(start_page, results, collected_ids, total_prompt, total_completion,
                    2, search_url, progress_file, output_file)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if blocked:
        save_progress(results, last_page, total_prompt, total_completion, 2, progress_file, output_file)
        print(f'\n차단됨. progress 보존 → 나중에 재개 가능')
    else:
        if os.path.exists(progress_file):
            os.remove(progress_file)

    _print_summary(results, total_prompt, total_completion)

def _print_summary(results, total_prompt, total_completion):
    cost = total_prompt * 2.50/1e6 + total_completion * 10.0/1e6
    print(f'\n{"="*60}')
    print(f'총 {len(results)}개 수집 ({TARGET_YEAR}년)')
    print(f'Vision 토큰: 입력 {total_prompt:,} / 출력 {total_completion:,}')
    print(f'Vision 비용: ${cost:.4f} (약 {cost*1400:.0f}원)')

if __name__ == '__main__':
    main()
