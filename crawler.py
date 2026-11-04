import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from google import genai

# 환경변수 로드
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

def fetch_reddit_aivideo_content():
    """Jina Reader를 경유하여 레딧의 클라우드 IP 차단을 우회하고 실시간 인기 AI 영상 데이터 수집"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "X-No-Cache": "true"
    }
    
    # 1차 시도: 오늘(Day) 기준 최고 인기 AI 영상
    url_day = "https://r.jina.ai/https://www.reddit.com/r/aivideo/top/?t=day"
    try:
        res = requests.get(url_day, headers=headers, timeout=25)
        if res.status_code == 200 and len(res.text) > 600:
            print(f"[성공] r/aivideo 일간 데이터 수집 완료 ({len(res.text)} bytes)")
            return res.text
    except Exception as e:
        print(f"[안내] 일간 데이터 요청 예외: {e}")

    # 2차 시도: 게시물이 적을 경우 주간(Week) 기준 보충
    url_week = "https://r.jina.ai/https://www.reddit.com/r/aivideo/top/?t=week"
    try:
        res = requests.get(url_week, headers=headers, timeout=25)
        if res.status_code == 200 and len(res.text) > 600:
            print(f"[성공] r/aivideo 주간 데이터 수집 완료 ({len(res.text)} bytes)")
            return res.text
    except Exception as e:
        print(f"[오류] 주간 데이터 요청 예외: {e}")

    return None

def parse_and_summarize_with_gemini(raw_text):
    """Gemini를 통해 원문에서 TOP 10 순수 AI 영상 및 실제 링크 추출"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    today = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    
    prompt = f"""
오늘은 {today}이다.
아래 텍스트는 전 세계 1위 순수 AI 영상 커뮤니티인 Reddit r/aivideo에서 방금 실시간 수집한 최신 데이터 원문이다.
텍스트에 포함된 실제 게시물 데이터만을 기반으로 추천수(Upvotes)가 높은 순수 AI 영상 TOP 10을 추출해라.

[원문 데이터]
{raw_text[:12000]}

[작성 및 출력 양식 - 엄격한 HTML 준수]
- 텔레그램 전송용이므로 마크다운 볼드(**)나 샵(##)은 절대 쓰지 말고, 오직 <b>, <code>, <a> 태그와 이모지만 사용할 것.
- 제목: 🤖 <b>[글로벌 검증 순수 AI 숏폼 TOP 10]</b> - {today}

- 1위부터 10위까지 아래 형식으로 작성:
<b>1. 영상 제목 (필요시 핵심 한국어 요약 병기)</b>
   • 추천: 👍 숫자개 | 툴/태그: <code>원문에 표기된 AI 툴(Kling, Luma, Runway, Midjourney 등)</code>
   👉 <a href="원문의 실제 reddit.com 영상 게시물 링크"><b>[영상 바로보기]</b></a>

- 마지막 항목:
💡 <b>오늘의 AI 연출 분석 & 기획 제안</b>
(오늘 상위권 AI 영상들의 비주얼 특징과 숏폼 제작에 바로 적용할 수 있는 기획 팁 2줄)
"""
    for model_name in ["gemini-3.8-flash", "gemini-3.5-flash-lite"]:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text.strip()
        except Exception as e:
            print(f"[경고] {model_name} 호출 실패, 대체 모델 시도: {e}")
            
    print("[오류] Gemini 분석 실패")
    sys.exit(1)

def send_telegram(html_text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 텔레그램 4,000자 제한 안전 분할
    chunks = []
    text_to_split = html_text
    while len(text_to_split) > 3800:
        split_idx = text_to_split.rfind("\n\n", 0, 3800)
        if split_idx == -1: split_idx = 3800
        chunks.append(text_to_split[:split_idx])
        text_to_split = text_to_split[split_idx:].lstrip("\n")
    if text_to_split:
        chunks.append(text_to_split)

    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        res = requests.post(url, json=payload)
        if res.status_code != 200:
            print(f"[전송 에러 (HTTP {res.status_code})]: {res.text}")
            sys.exit(1)
            
    print("[성공] 텔레그램 발송 완료!")

if __name__ == "__main__":
    check_env()
    print("1. r/aivideo 우회 데이터 수집 중...")
    content = fetch_reddit_aivideo_content()
    
    if not content:
        print("[오류] 레딧 데이터 수집 실패")
        sys.exit(1)

    print("2. Gemini TOP 10 추출 및 분석 중...")
    report = parse_and_summarize_with_gemini(content)

    print("3. 텔레그램 메시지 발송 중...")
    send_telegram(report)
