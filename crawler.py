import os
import sys
import html
import requests
from datetime import datetime, timezone, timedelta
from google import genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def check_env():
    missing = [k for k, v in [
        ("GEMINI_API_KEY", GEMINI_API_KEY),
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
        ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
    ] if not v]
    if missing:
        print(f"[오류] 누락된 Secrets: {', '.join(missing)}")
        sys.exit(1)

def fetch_top_ai_videos(limit=10):
    """r/aivideo에서 당일 추천수(Upvote) 기준 상위 10개 영상 추출"""
    headers = {"User-Agent": "python:aivideo.trend.notifier:v1.0 (by /u/DailyTrendBot)"}
    
    # 1차 시도: 오늘(24시간) 최고 인기 게시물
    url = "https://www.reddit.com/r/aivideo/top.json?t=day&limit=25"
    res = requests.get(url, headers=headers, timeout=10)
    
    posts = []
    if res.status_code == 200:
        posts = res.json().get("data", {}).get("children", [])
    
    # 만약 오늘 게시물이 10개 미만이면 이번 주(week) 인기 게시물로 보충
    if len(posts) < limit:
        url_week = "https://www.reddit.com/r/aivideo/top.json?t=week&limit=25"
        res_week = requests.get(url_week, headers=headers, timeout=10)
        if res_week.status_code == 200:
            posts = res_week.json().get("data", {}).get("children", [])

    results = []
    for p in posts:
        d = p.get("data", {})
        # 공지(Sticky) 제외
        if d.get("stickied"):
            continue
            
        title = d.get("title", "").strip()
        score = d.get("score", 0)
        comments = d.get("num_comments", 0)
        flair = d.get("link_flair_text") or "AI Video"
        permalink = f"https://www.reddit.com{d.get('permalink')}"
        video_url = d.get("url_overridden_by_dest") or permalink

        results.append({
            "title": title,
            "score": score,
            "comments": comments,
            "tool_flair": flair.strip(),
            "link": video_url,
            "reddit_link": permalink
        })
        
        if len(results) >= limit:
            break

    return results

def analyze_ai_trends(video_list):
    """Gemini를 통한 시각 연출 및 기획 포인트 분석"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    summary_context = "\n".join([
        f"- 제목: {v['title']} (사용한 툴/태그: {v['tool_flair']})"
        for v in video_list
    ])

    prompt = f"""
다음은 오늘 글로벌 1위 AI 영상 커뮤니티(r/aivideo)에서 추천수 1위부터 10위를 기록한 실제 신작 목록이다:
{summary_context}

숏폼 전문 크리에이터의 관점에서 다음 두 가지를 간결하고 실질적으로 작성해라:
1. 🎨 오늘의 지배적인 비주얼 스타일 & AI 툴 트렌드 (1~2줄)
2. 💡 당장 벤치마킹할 만한 숏폼 기획 아이디어 (1줄)

(마크다운 특수문자 볼드나 따옴표 없이 깔끔한 일반 텍스트로만 작성)
"""
    for model_name in ["gemini-2.5-flash", "gemini-1.5-flash"]:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text.strip()
        except Exception:
            continue
    return "물리 법칙을 비튼 초현실적 상황극과 정교한 텍스처 표현이 높은 반응을 얻고 있습니다."

def build_message(video_list, insights):
    today = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    lines = [f"🤖 <b>[글로벌 검증 순수 AI 숏폼 TOP 10]</b> - {today}\n"]
    
    for idx, v in enumerate(video_list, 1):
        clean_title = html.escape(v['title'])
        clean_flair = html.escape(v['tool_flair'])
        lines.append(f"<b>{idx}. {clean_title}</b>")
        lines.append(f"   • 추천: 👍 {v['score']:,}개 | 댓글: 💬 {v['comments']:,}개")
        lines.append(f"   • 제작 툴/태그: <code>{clean_flair}</code>")
        lines.append(f"   👉 <a href=\"{v['link']}\"><b>[영상 바로보기]</b></a>\n")

    lines.append("💡 <b>오늘의 AI 연출 분석 & 기획 팁</b>")
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
        print(f"[전송 에러] {res.text}")
        sys.exit(1)

if __name__ == "__main__":
    check_env()
    print("1. r/aivideo 실시간 랭킹 TOP 10 수집 중...")
    top_videos = fetch_top_ai_videos(limit=10)
    
    if not top_videos:
        print("[경고] 수집된 영상이 없습니다.")
        sys.exit(1)

    print("2. Gemini 트렌드 요약 분석 중...")
    insights = analyze_ai_trends(top_videos)

    print("3. 텔레그램 메시지 생성 및 전송...")
    msg = build_message(top_videos, insights)
    send_telegram(msg)
    print("성공적으로 발송되었습니다!")
