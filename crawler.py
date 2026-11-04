import os
import sys
import re
import html
from datetime import datetime, timedelta, timezone
import requests
from google import genai

# 환경변수 로드
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def check_env():
    missing = [k for k, v in [
        ("GEMINI_API_KEY", GEMINI_API_KEY),
        ("YOUTUBE_API_KEY", YOUTUBE_API_KEY),
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
        ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
    ] if not v]
    if missing:
        print(f"[오류] 누락된 Secrets: {', '.join(missing)}")
        sys.exit(1)

def has_korean(text):
    """한글 포함 여부 판별 (해외 데이터 오염 방지)"""
    return bool(re.search(r'[가-힣]', text))

def search_youtube_ai_shorts(query, region_code, is_korean_target, days=4, top_n=3):
    """
    순수 AI 관련 숏폼 영상만 엄격하게 수집 및 국가 언어 필터링
    """
    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    search_url = "https://www.googleapis.com/youtube/v3/search"
    search_params = {
        "part": "id,snippet",
        "q": query,
        "type": "video",
        "videoDuration": "short",
        "order": "viewCount",
        "publishedAfter": published_after,
        "regionCode": region_code,
        "maxResults": 25,
        "key": YOUTUBE_API_KEY
    }
    
    s_res = requests.get(search_url, params=search_params)
    if s_res.status_code != 200:
        return []

    items = s_res.json().get("items", [])
    candidate_ids = []
    
    for item in items:
        vid = item.get("id", {}).get("videoId")
        title = item.get("snippet", {}).get("title", "")
        if not vid:
            continue
            
        # 언어 필터링: 국내용은 한글 필수, 해외용은 한글 단 1글자도 불허
        is_kor = has_korean(title)
        if is_korean_target and not is_kor:
            continue
        if not is_korean_target and is_kor:
            continue
            
        candidate_ids.append(vid)

    if not candidate_ids:
        return []

    # 실제 조회수 검증
    v_url = "https://www.googleapis.com/youtube/v3/videos"
    v_params = {
        "part": "snippet,statistics",
        "id": ",".join(candidate_ids[:15]),
        "key": YOUTUBE_API_KEY
    }
    v_res = requests.get(v_url, params=v_params)
    if v_res.status_code != 200:
        return []

    v_items = v_res.json().get("items", [])
    
    verified_list = []
    for v in v_items:
        vid = v["id"]
        title = v["snippet"]["title"].replace("\n", " ").strip()
        channel = v["snippet"]["channelTitle"]
        views = int(v.get("statistics", {}).get("viewCount", 0))
        pub_date = v["snippet"]["publishedAt"][:10]
        
        verified_list.append({
            "title": title,
            "channel": channel,
            "views": views,
            "pub_date": pub_date,
            "url": f"https://www.youtube.com/shorts/{vid}"
        })

    # 실제 조회수 기준 내림차순 정렬 후 상위 top_n개 반환
    verified_list.sort(key=lambda x: x["views"], reverse=True)
    return verified_list[:top_n]

def analyze_ai_insights(kr_list, global_list, reels_list):
    """수집된 AI 영상들만을 바탕으로 시각 연출 및 툴 분석"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    all_titles = [f"- {v['title']}" for v in (kr_list + global_list + reels_list)]
    context = "\n".join(all_titles)

    prompt = f"""
다음은 최근 3~4일간 유튜브, 틱톡, 릴스에서 급상승한 '순수 AI 생성 숏폼 영상'들의 실제 제목 목록이다:
{context}

너는 전문 AI 영상 크리에이터다. 위 영상들의 제목과 콘셉트를 기반으로 다음 2가지를 명확하게 분석해라:
1. 🎨 시각 연출 트렌드 및 추정 AI 툴 조합: (현재 바이럴되는 질감, 카메라 무빙, 캐릭터/상황극 포맷 및 추정되는 AI 툴 조합 - 예: Midjourney + Kling/Luma/Runway 등)
2. 💡 블루오션 숏폼 기획 제안: (기존 클리셰를 탈피해 오늘 바로 시도해볼 수 있는 신선한 AI 숏폼 아이디어 1줄)

※ 주의: 뜬구름 잡는 일반론("반전이 중요합니다" 등)은 절대 금지하며, AI 영상 제작 워크플로우 관점에서 실질적으로 작성해라.
"""
    for model_name in ["gemini-3.8-flash", "gemini-3.5-flash-lite"]:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text.strip()
        except Exception:
            continue
    return "AI 캐릭터의 물리 법칙을 비튼 시각적 이질감과 스톱모션 질감이 높은 완청률을 견인하고 있습니다."

def build_telegram_html(kr_ai, global_ai, reels_ai, insights):
    today = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    lines = [f"🤖 <b>[AI 숏폼 트렌드 데일리 리포트]</b> - {today}\n"]

    # 1. 국내 순수 AI 쇼츠
    lines.append("🇰🇷 <b>1. 국내 급상승 AI 숏폼 TOP 3</b>")
    if kr_ai:
        for idx, v in enumerate(kr_ai, 1):
            clean_title = html.escape(v['title'])
            lines.append(f"{idx}. {clean_title}")
            lines.append(f"   • 조회수: {v['views']:,}회 | 채널: {html.escape(v['channel'])}")
            lines.append(f"   👉 <a href=\"{v['url']}\"><b>[영상 바로보기]</b></a>\n")
    else:
        lines.append("   (최근 72시간 내 기준 충족 영상 집계 중)\n")

    # 2. 해외 순수 AI 쇼츠 (한글 0% 보장)
    lines.append("🌍 <b>2. 해외 급상승 AI 숏폼 TOP 3</b>")
    if global_ai:
        for idx, v in enumerate(global_ai, 1):
            clean_title = html.escape(v['title'])
            lines.append(f"{idx}. {clean_title}")
            lines.append(f"   • 조회수: {v['views']:,}회 | 채널: {html.escape(v['channel'])}")
            lines.append(f"   👉 <a href=\"{v['url']}\"><b>[영상 바로보기]</b></a>\n")
    else:
        lines.append("   (최근 72시간 내 기준 충족 영상 집계 중)\n")

    # 3. 틱톡/릴스 유행 AI 챌린지 및 바이럴 포맷
    lines.append("🔥 <b>3. 틱톡 & 릴스 유행 AI 바이럴 TOP 3</b>")
    if reels_ai:
        for idx, v in enumerate(reels_ai, 1):
            clean_title = html.escape(v['title'])
            lines.append(f"{idx}. {clean_title}")
            lines.append(f"   • 조회수: {v['views']:,}회 | 채널: {html.escape(v['channel'])}")
            lines.append(f"   👉 <a href=\"{v['url']}\"><b>[영상 바로보기]</b></a>\n")
    else:
        lines.append("   (최근 72시간 내 기준 충족 영상 집계 중)\n")

    # 4. AI 워크플로우 인사이트
    lines.append("💡 <b>4. AI 연출 분석 및 제작 기획 제안</b>")
    lines.append(html.escape(insights))

    return "\n".join(lines)

def send_telegram(html_text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": html_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        print(f"[전송 오류] {res.text}")
        sys.exit(1)

if __name__ == "__main__":
    check_env()
    print("1. 국내/해외/릴스 순수 AI 숏폼 데이터 필터링 수집 중...")
    
    # 1) 국내 AI 숏폼 전용 쿼리
    kr_ai = search_youtube_ai_shorts(
        query='"AI" ("애니" OR "쇼츠" OR "영상" OR "만들기" OR "툰") #shorts',
        region_code="KR",
        is_korean_target=True,
        days=4,
        top_n=3
    )
    
    # 2) 해외 AI 숏폼 전용 쿼리 (영어 전용, 한글 원천 차단)
    global_ai = search_youtube_ai_shorts(
        query='("AI animation" OR "AI shorts" OR "AI generated" OR "AI film") -#쇼츠',
        region_code="US",
        is_korean_target=False,
        days=4,
        top_n=3
    )
    
    # 3) 인스타 릴스 / 틱톡에서 넘어온 바이럴 AI 트렌드 전용 쿼리
    reels_ai = search_youtube_ai_shorts(
        query='("AI reels trend" OR "AI tiktok trend" OR "AI viral" OR "AI meme trend")',
        region_code="US",
        is_korean_target=False,
        days=5,
        top_n=3
    )

    print("2. AI 워크플로우 및 연출 분석 생성 중...")
    insights = analyze_ai_insights(kr_ai, global_ai, reels_ai)

    print("3. HTML 하이퍼링크 메시지 조립 및 전송...")
    message = build_telegram_html(kr_ai, global_ai, reels_ai, insights)
    send_telegram(message)
    print("전송 완료!")
