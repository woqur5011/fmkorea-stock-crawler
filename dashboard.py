"""
FMKorea 투자자 분석 대시보드
실행: streamlit run fmkorea/dashboard.py
"""
import json, re, os
import streamlit as st
import pandas as pd

st.set_page_config(page_title="FMKorea 투자자 분석", layout="wide", page_icon="📈")

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

# ── 데이터 로드 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)  # 1시간마다 자동 갱신
def load_data():
    ha2 = json.load(open(os.path.join(DATA_DIR, "ha2mandx_2026.json"), encoding="utf-8"))
    seo = json.load(open(os.path.join(DATA_DIR, "seosaengwon_2026.json"), encoding="utf-8"))
    cache_path = os.path.join(DATA_DIR, "analysis_cache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    for p in ha2:
        p["user"] = "HA2MANDX"
    for p in seo:
        p["user"] = "서생원"
    return ha2, seo, cache


def extract_date(date_str):
    m = re.search(r'2026\.(\d{2})\.(\d{2})', date_str)
    if m:
        return pd.to_datetime(f"2026-{m.group(1)}-{m.group(2)}")
    return None


def filter_posts(posts, keyword="", date_from=None, date_to=None):
    result = []
    for p in posts:
        dt = extract_date(p.get("date", ""))
        if date_from and dt and dt.date() < date_from:
            continue
        if date_to and dt and dt.date() > date_to:
            continue
        if keyword:
            text = (p.get("title", "") + p.get("body", "")).lower()
            if keyword.lower() not in text:
                continue
        result.append(p)
    return result


def render_post(p):
    """게시글 상세 렌더링"""
    body = p.get("body", "")
    img_summary = ""
    if "[이미지 파싱]" in body:
        idx = body.index("[이미지 파싱]")
        img_summary = body[idx:]
        body = body[:idx].strip()

    if body:
        st.markdown(body)
    if img_summary:
        with st.expander("🖼️ 이미지 파싱 내용"):
            st.markdown(img_summary.replace("[이미지 파싱]", "").strip())

    st.markdown(f"🔗 [원본 글 보기](https://www.fmkorea.com/{p['id']})")

    comments = p.get("comments", [])
    if comments:
        with st.expander(f"💬 댓글 {len(comments)}개"):
            for c in comments:
                st.markdown(f"- {c['content']}")


# ── 메인 ─────────────────────────────────────────────────────────────────────
ha2, seo, cache = load_data()
all_posts = ha2 + seo

# 최근 수집일 계산
all_dates = [extract_date(p.get("date", "")) for p in all_posts]
all_dates = [d for d in all_dates if d is not None]
latest_date = max(all_dates).date() if all_dates else None

col_title, col_refresh = st.columns([8, 1])
with col_title:
    st.title("📈 FMKorea 투자자 분석 대시보드")
    if latest_date:
        st.caption(f"HA2MANDX · 서생원 | 2026년 게시글 기반 | 최근 수집일: **{latest_date.strftime('%Y.%m.%d')}**")
with col_refresh:
    st.write("")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()

tab1, tab2, tab3 = st.tabs(["🧠 핵심 투자 철학", "📋 게시글 탐색", "📅 월별 인사이트"])

# ── Tab 1: 핵심 투자 철학 ─────────────────────────────────────────────────────
with tab1:
    if not cache:
        st.warning("분석 캐시가 없습니다. 먼저 `python pre_analyze.py`를 실행해주세요.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("HA2MANDX")
            content = cache.get("ha2mandx_philosophy", "분석 결과 없음")
            st.markdown(content)

        with col2:
            st.subheader("서생원")
            content = cache.get("seosaengwon_philosophy", "분석 결과 없음")
            st.markdown(content)

        if "comparison" in cache:
            st.divider()
            st.subheader("🔍 두 사람 비교")
            st.markdown(cache["comparison"])

# ── Tab 2: 게시글 탐색 ───────────────────────────────────────────────────────
with tab2:
    # 필터 영역
    with st.container():
        col1, col2, col3 = st.columns([1, 2, 2])
        with col1:
            user_sel = st.selectbox("유저", ["전체", "HA2MANDX", "서생원"])
        with col2:
            date_from = st.date_input("시작일", value=pd.to_datetime("2026-01-01").date())
        with col3:
            date_to = st.date_input("종료일", value=latest_date if latest_date else pd.to_datetime("2026-05-07").date())

    keyword = st.text_input("🔍 키워드 검색 (제목 + 본문)", placeholder="예: 반도체, 코스피, 삼성")

    # 필터 적용
    if user_sel == "HA2MANDX":
        pool = ha2
    elif user_sel == "서생원":
        pool = seo
    else:
        pool = all_posts

    filtered = filter_posts(pool, keyword=keyword, date_from=date_from, date_to=date_to)
    filtered.sort(key=lambda x: x.get("date", ""), reverse=True)

    st.caption(f"총 **{len(filtered)}**개 게시글")

    if not filtered:
        st.info("검색 결과가 없습니다.")
    else:
        # 목록 표시 (최대 100개)
        for p in filtered[:100]:
            user_badge = "🔵" if p["user"] == "HA2MANDX" else "🟢"
            comment_cnt = len(p.get("comments", []))
            has_img = "🖼️" if "[이미지 파싱]" in p.get("body", "") else ""
            label = f"{user_badge} {p['user']} | {p['date']} | {p['title']} {has_img} | 💬{comment_cnt}"
            with st.expander(label):
                render_post(p)

        if len(filtered) > 100:
            st.caption(f"상위 100개만 표시 중. 키워드나 날짜를 좁혀주세요.")

# ── Tab 3: 월별 인사이트 ──────────────────────────────────────────────────────
with tab3:
    if not cache or "monthly" not in cache:
        st.warning("분석 캐시가 없습니다. 먼저 `python pre_analyze.py`를 실행해주세요.")
    else:
        month_labels = {1: "1월", 2: "2월", 3: "3월", 4: "4월", 5: "5월"}
        month_sel = st.select_slider(
            "월 선택",
            options=[1, 2, 3, 4, 5],
            format_func=lambda x: f"2026년 {month_labels[x]}",
        )

        col1, col2 = st.columns(2)

        with col1:
            st.subheader(f"HA2MANDX - {month_labels[month_sel]}")
            content = cache["monthly"].get("ha2mandx", {}).get(str(month_sel))
            if content:
                st.markdown(content)
            else:
                st.info("해당 월 분석 없음")

            # 해당 월 게시글 링크
            month_posts_ha2 = [
                p for p in ha2
                if re.search(rf'2026\.{month_sel:02d}\.', p.get("date", ""))
            ]
            if month_posts_ha2:
                with st.expander(f"📋 {month_labels[month_sel]} 게시글 목록 ({len(month_posts_ha2)}개)"):
                    for p in sorted(month_posts_ha2, key=lambda x: x.get("date",""), reverse=True):
                        st.markdown(f"- [{p['title']}](https://www.fmkorea.com/{p['id']}) `{p['date']}`")

        with col2:
            st.subheader(f"서생원 - {month_labels[month_sel]}")
            content = cache["monthly"].get("seosaengwon", {}).get(str(month_sel))
            if content:
                st.markdown(content)
            else:
                st.info("해당 월 분석 없음")

            month_posts_seo = [
                p for p in seo
                if re.search(rf'2026\.{month_sel:02d}\.', p.get("date", ""))
            ]
            if month_posts_seo:
                with st.expander(f"📋 {month_labels[month_sel]} 게시글 목록 ({len(month_posts_seo)}개)"):
                    for p in sorted(month_posts_seo, key=lambda x: x.get("date",""), reverse=True):
                        st.markdown(f"- [{p['title']}](https://www.fmkorea.com/{p['id']}) `{p['date']}`")
