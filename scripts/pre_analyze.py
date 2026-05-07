"""
사전 분석 스크립트 - GPT로 두 유저 게시글 분석 후 캐시 저장
실행:
  python scripts/pre_analyze.py             # 전체 분석
  python scripts/pre_analyze.py --incremental  # 현재 달만 재분석
"""
import json, re, httpx, os, sys
from datetime import datetime
from openai import AzureOpenAI

client = AzureOpenAI(
    azure_endpoint=os.environ.get("AZURE_ENDPOINT", "https://biz-insight-common-api.cognitiveservices.azure.com/"),
    api_key=os.environ.get("AZURE_API_KEY", "41quwWproISHED6BdaKPmarnJmWHdwNKuKrs61VuO7S6UX5VCyemJQQJ99CAACHYHv6XJ3w3AAAAACOGsnOn"),
    api_version=os.environ.get("AZURE_API_VERSION", "2025-04-01-preview"),
    http_client=httpx.Client(verify=False),
)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "analysis_cache.json")

USERS = {
    "ha2mandx": {
        "file": os.path.join(DATA_DIR, "ha2mandx_2026.json"),
        "name": "HA2MANDX",
    },
    "seosaengwon": {
        "file": os.path.join(DATA_DIR, "seosaengwon_2026.json"),
        "name": "서생원",
    },
}

total_prompt = 0
total_completion = 0


def gpt(prompt, max_tokens=1500):
    global total_prompt, total_completion
    resp = client.chat.completions.create(
        model="gpt-5.4",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=max_tokens,
    )
    total_prompt += resp.usage.prompt_tokens
    total_completion += resp.usage.completion_tokens
    return resp.choices[0].message.content.strip()


def extract_month(date_str):
    m = re.search(r'2026\.(\d{2})', date_str)
    return int(m.group(1)) if m else None


def posts_to_text(posts, max_body=120):
    lines = []
    for p in posts:
        body = p.get("body", "")
        if "[이미지 파싱]" in body:
            body = body[: body.index("[이미지 파싱]")]
        body = body[:max_body].strip().replace("\n", " ")
        comments_preview = " / ".join(
            c["content"][:40] for c in p.get("comments", [])[:3]
        )
        line = f"[{p['date']}] {p['title']}"
        if body:
            line += f" | {body}"
        if comments_preview:
            line += f" | 댓글: {comments_preview}"
        lines.append(line)
    return "\n".join(lines)


def analyze_philosophy(user_name, posts):
    print(f"  전체 철학 분석 중 ({len(posts)}개 게시글)...")
    text = posts_to_text(posts)
    prompt = f"""아래는 주식 커뮤니티(FMKorea)에서 '{user_name}'이(가) 2026년에 작성한 게시글 전체 목록입니다.
이 사람의 투자 관점을 심층 분석해주세요.

**결과 형식 (마크다운):**

## 핵심 투자 철학
(3~5줄, 이 사람의 시장 세계관과 투자 원칙)

## 반복 주장 Top 7
각 주장을 한 줄로 요약하고, 대표 발언을 인용해주세요.
1. **주장명**: 요약 / > "대표 발언 인용"
...

## 현재 시장 전망 (2026년 5월 기준)
(이 사람이 지금 시장을 어떻게 보는지, 포지션 추정)

---
{text}
"""
    return gpt(prompt, max_tokens=2000)


def analyze_monthly(user_name, posts, month):
    month_posts = [p for p in posts if extract_month(p.get("date", "")) == month]
    if not month_posts:
        return None
    print(f"  {month}월 분석 중 ({len(month_posts)}개 게시글)...")
    text = posts_to_text(month_posts)
    prompt = f"""아래는 '{user_name}'이(가) 2026년 {month}월에 작성한 게시글입니다.
이 달의 시장 상황 맥락에서 이 사람이 무엇을 주장했는지 분석해주세요.

**결과 형식 (마크다운):**

## 이달의 핵심 주장
(3~4가지, 각 주장 한 줄 + 배경 설명)

## 주목할 발언
> "발언 인용 1" (날짜)
> "발언 인용 2" (날짜)

## 댓글 반응
(동의/반박/질문 패턴, 어떤 글에 반응이 많았는지)

## 시장 관점 요약
(이 달에 이 사람이 전반적으로 강세/약세 어떤 포지션이었는지)

---
{text}
"""
    return gpt(prompt, max_tokens=1200)


def analyze_comparison(ha2_philosophy, seo_philosophy):
    print("  두 사람 비교 분석 중...")
    prompt = f"""아래는 두 주식 투자자의 핵심 투자 철학 분석입니다.

=== HA2MANDX ===
{ha2_philosophy}

=== 서생원 ===
{seo_philosophy}

두 사람의 투자 관점을 비교 분석해주세요.

**결과 형식 (마크다운):**

## 공통 주장
(두 사람이 공통적으로 믿는 것들)

## 시각 차이
(의견이 다른 부분, 접근 방식 차이)

## 상호 보완 포인트
(두 관점을 합치면 얻을 수 있는 인사이트)
"""
    return gpt(prompt, max_tokens=1000)


def main(incremental=False):
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"기존 캐시 로드됨")

    data = {}
    for key, cfg in USERS.items():
        with open(cfg["file"], encoding="utf-8") as f:
            data[key] = json.load(f)
        print(f"{cfg['name']}: {len(data[key])}개 게시글 로드")

    if not incremental:
        # 전체 분석: 철학 + 비교 + 모든 월
        for key, cfg in USERS.items():
            cache_key = f"{key}_philosophy"
            if cache_key not in cache:
                print(f"\n[{cfg['name']}] 전체 철학 분석")
                cache[cache_key] = analyze_philosophy(cfg["name"], data[key])
                _save(cache)
            else:
                print(f"[{cfg['name']}] 전체 철학 캐시 있음 - 스킵")

        if "comparison" not in cache:
            print("\n[비교 분석]")
            cache["comparison"] = analyze_comparison(
                cache["ha2mandx_philosophy"], cache["seosaengwon_philosophy"]
            )
            _save(cache)
        else:
            print("[비교 분석] 캐시 있음 - 스킵")

        months = range(1, 13)
    else:
        # 증분 분석: 현재 달만 재분석
        current_month = datetime.now().month
        print(f"\n[증분 모드] {current_month}월만 재분석")
        months = [current_month]

    if "monthly" not in cache:
        cache["monthly"] = {"ha2mandx": {}, "seosaengwon": {}}

    for month in months:
        for key, cfg in USERS.items():
            if key not in cache["monthly"]:
                cache["monthly"][key] = {}
            # 증분 모드에서는 현재 달 강제 재분석
            if incremental or str(month) not in cache["monthly"].get(key, {}):
                print(f"\n[{cfg['name']}] {month}월 분석")
                result = analyze_monthly(cfg["name"], data[key], month)
                if result:
                    cache["monthly"][key][str(month)] = result
                    _save(cache)
            else:
                print(f"[{cfg['name']}] {month}월 캐시 있음 - 스킵")

    cost = total_prompt * 2.50 / 1e6 + total_completion * 10.0 / 1e6
    print(f"\n{'='*50}")
    print(f"분석 완료!")
    print(f"토큰: 입력 {total_prompt:,} / 출력 {total_completion:,}")
    print(f"비용: ${cost:.4f} (약 {cost*1400:.0f}원)")


def _save(cache):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    incremental = "--incremental" in sys.argv
    main(incremental=incremental)
