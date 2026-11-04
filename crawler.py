import os
import sys
import requests
from datetime import datetime, timedelta, timezone
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

# ----------------------------------------------------
# 1. 유튜브 쇼츠 (공식 API: 최근 72시간 실시간 검증)
# ----------------------------------------------------
def fetch_youtube_shorts(region_code="KR", top_n=3):
    published_after = (datetime.now(timezone.utc) - timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
    search_url = "https://www.googleapis.com/youtube/v3/search"
    search_params = {
        "part": "id",
        "q": "#쇼츠 #shorts",
        "type": "video",
        "videoDuration": "short",
        "order": "viewCount",
        "publishedAfter": published_after,
        "regionCode": region_code,
        "maxResults": 15,
        "key": YOUTUBE_API_KEY
    }
    s_res = requests.get(search_url, params=search_params)
    if s_res.status_code != 200:
        return "유튜브 데이터 수집 실패"

    items = s_res.json().get("items", [])
    video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
    if not video_ids:
        return "최근 영상 없음"

    v_url = "https://www.googleapis.com/youtube/v3/videos"
    v_params = {"part": "snippet,statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY}
    v_res = requests.get(v_url, params=v_params)
    if v_res.status_code != 200:
        return "유튜브 상세 수집 실패"

    v_items = v_res.json().get("items", [])
    v_items.sort(key=lambda x: int(x.get("statistics", {}).get("viewCount", 0)), reverse=True)

    results = []
    for v in v_items[:top_n]:
        vid = v["id"]
        title = v["snippet"]["title"].replace("\n", " ")
        views = int(v["statistics"].get("viewCount", 0))
        results.append(f"- [유튜브 쇼츠] {title} (조회수 {views:,}회)\n  링크: https://www.youtube.com/shorts/{vid}")
    return "\n".join(results)

# ----------------------------------------------------
# 2. 틱톡 (TikTok Creative Center 실시간 급상승 해시태그/트렌드)
# ----------------------------------------------------
def fetch_tiktok_trends(top_n=3):
    """틱톡 크리에이티브 센터의 실시간 인기 해시태그 API 수집"""
    url = "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
    params = {"page": 1, "limit": top_n, "period": 7, "country_code": "KR"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"
    }
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json().get("data", {}).get("list", [])
            trends = []
            for item in data[:top_n]:
                tag_name = item.get("hashtag_name", "")
                views = item.get("video_views", 0)
                link = f"https://www.tiktok.com/tag/{tag_name}"
                trends.append(f"- [틱톡 급상승] #{tag_name} (조회수 약 {views:,}회)\n  링크: {link}")
            if trends:
                return "\n".join(trends)
    except Exception as e:
        print(f"틱톡 수집 예외: {e}")
    return "- [틱톡 트렌드] 실시간 인기 챌린지 직접 확인\n  링크: https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"

# ----------------------------------------------------
# 3. 글로벌 릴스 & 틱톡 화제 영상 (Reddit Viral 피드 실시간 수집)
# ----------------------------------------------------
def fetch_reddit_viral_shorts(top_n=3):
    """틱톡/인스타 릴스 등 해외 SNS에서 폭발한 실제 영상 모음 수집"""
    url = "https://www.reddit.com/r/TikTokCringe/hot.json?limit=15"
    headers = {"User-Agent": "DailyShortsBot/1.0 (by /u/TrendTracker)"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            posts = res.json().get("data", {}).get("children", [])
            results = []
            count = 0
            for p in posts:
                data = p.get("data", {})
                if data.get("is_video") or "tiktok" in data.get("url", "") or "v.redd.it" in data.get("url", ""):
                    title = data.get("title", "")
                    score = data.get("score", 0)
                    link = f"https://www.reddit.com{data.get('permalink')}"
                    results.append(f"- [글로벌 틱톡/릴스 화제작] {title} (추천수 {score:,}개)\n  영상 바로보기: {link}")
                    count += 1
                    if count >= top_n:
                        break
            if results:
                return "\n".join(results)
    except Exception as e:
        print(f"레딧 바이럴 수집 예외: {e}")
    return "글로벌 바이럴 영상 수집 일시 지연"

# ----------------------------------------------------
# 4. Gemini 멀티 플랫폼 데이터 종합 분석
# ----------------------------------------------------
def analyze_all_platforms(yt_kr, yt_global, tiktok, viral_shorts):
    client = genai.Client(api_key=GEMINI_API_KEY)
    today_str = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    
    prompt = f"""
오늘은 {today_str}이다.
아래는 유튜브, 틱톡, 글로벌 숏폼 커뮤니티에서 실시간 수집한 데이터 원본이다.
제공된 실제 링크와 수치만을 토대로 크리에이터를 위한 종합 아침 브리핑을 작성해라.

[1. 유튜브 쇼츠 급상승]
국내:
{yt_kr}

해외:
{yt_global}

[2. 틱톡 실시간 급상승 키워드/챌린지]
{tiktok}

[3. 글로벌(인스타/틱톡) 화제 영상]
{viral_shorts}

[작성 규칙]
- 마크다운 특수문자 없이 줄바꿈과 이모지만 사용해 가독성을 높일 것.
- 각 플랫폼별 핵심 영상/트렌드와 실제 링크를 누락 없이 표시할 것.
- 마지막에 "오늘 전 세계 숏폼을 관통하는 공통 연출 포인트 1줄"과 "제작 기획 아이디어 1줄"을 포함할 것.
"""
    for model_name in ["gemini-3.8-flash", "gemini-3.5-flash-lite"]:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text
        except Exception:
            continue
    sys.exit(1)

def send_telegram(text):
    header = "🌐 [전 플랫폼 종합: 오늘의 숏폼 트렌드 브리핑]\n\n"
    full_text = header + text
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 3800자 분할 전송
    while len(full_text) > 3800:
        idx = full_text.rfind("\n", 0, 3800)
        if idx == -1: idx = 3800
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": full_text[:idx], "disable_web_page_preview": True})
        full_text = full_text[idx:].lstrip("\n")
    if full_text:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": full_text, "disable_web_page_preview": True})

if __name__ == "__main__":
    check_env()
    print("1. 플랫폼별 실시간 데이터 수집 중...")
    yt_kr = fetch_youtube_shorts(region_code="KR", top_n=3)
    yt_global = fetch_youtube_shorts(region_code="US", top_n=3)
    tiktok_data = fetch_tiktok_trends(top_n=3)
    viral_data = fetch_reddit_viral_shorts(top_n=3)
    
    print("2. Gemini 종합 분석 중...")
    report = analyze_all_platforms(yt_kr, yt_global, tiktok_data, viral_data)
    
    print("3. 텔레그램 발송 중...")
    send_telegram(report)
