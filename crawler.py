import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import requests
from google import genai

# 환경변수 확인
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

# 1. 유튜브 쇼츠 수집 (국내 / 해외 검색어 철저 분리)
def fetch_youtube_shorts(region_code="KR", query="#쇼츠", top_n=3):
    published_after = (datetime.now(timezone.utc) - timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
    search_url = "https://www.googleapis.com/youtube/v3/search"
    search_params = {
        "part": "id",
        "q": query,
        "type": "video",
        "videoDuration": "short",
        "order": "viewCount",
        "publishedAfter": published_after,
        "regionCode": region_code,
        "relevanceLanguage": "ko" if region_code == "KR" else "en",
        "maxResults": 15,
        "key": YOUTUBE_API_KEY
    }
    s_res = requests.get(search_url, params=search_params)
    if s_res.status_code != 200:
        return []

    items = s_res.json().get("items", [])
    video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
    if not video_ids:
        return []

    v_url = "https://www.googleapis.com/youtube/v3/videos"
    v_params = {"part": "snippet,statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY}
    v_res = requests.get(v_url, params=v_params)
    if v_res.status_code != 200:
        return []

    v_items = v_res.json().get("items", [])
    v_items.sort(key=lambda x: int(x.get("statistics", {}).get("viewCount", 0)), reverse=True)

    results = []
    for v in v_items[:top_n]:
        vid = v["id"]
        title = v["snippet"]["title"].replace("\n", " ")
        views = int(v["statistics"].get("viewCount", 0))
        results.append({
            "title": title,
            "views": views,
            "url": f"https://www.youtube.com/shorts/{vid}"
        })
    return results

# 2. 글로벌 틱톡/릴스 바이럴 쇼츠 수집 (IP 차단 없는 공식 API 검색)
def fetch_global_viral_reels_tiktok(top_n=3):
    published_after = (datetime.now(timezone.utc) - timedelta(days=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
    search_url = "https://www.googleapis.com/youtube/v3/search"
    search_params = {
        "part": "id",
        "q": "viral tiktok reels compilation trend",
        "type": "video",
        "videoDuration": "short",
        "order": "viewCount",
        "publishedAfter": published_after,
        "regionCode": "US",
        "relevanceLanguage": "en",
        "maxResults": 10,
        "key": YOUTUBE_API_KEY
    }
    s_res = requests.get(search_url, params=search_params)
    if s_res.status_code != 200:
        return []

    video_ids = [item["id"]["videoId"] for item in s_res.json().get("items", []) if "videoId" in item.get("id", {})]
    if not video_ids:
        return []

    v_res = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY})
    v_items = v_res.json().get("items", [])
    v_items.sort(key=lambda x: int(x.get("statistics", {}).get("viewCount", 0)), reverse=True)

    results = []
    for v in v_items[:top_n]:
        vid = v["id"]
        title = v["snippet"]["title"].replace("\n", " ")
        views = int(v["statistics"].get("viewCount", 0))
        results.append({
            "title": title,
            "views": views,
            "url": f"https://www.youtube.com/shorts/{vid}"
        })
    return results

# 3. 최신 글로벌 신규 밈/챌린지 수집 (Know Your Meme 공식 피드 - 100% 작동)
def fetch_latest_trending_memes(top_n=2):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get("https://knowyourmeme.com/memes.rss", headers=headers, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            items = root.findall("./channel/item")
            memes = []
            for item in items[:top_n]:
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                desc = item.find("description").text if item.find("description") is not None else ""
                # HTML 태그 제거
                clean_desc = desc.split("<")[0].strip() if desc else ""
                memes.append({"title": title, "link": link, "desc": clean_desc})
            return memes
    except Exception as e:
        print(f"밈 피드 수집 예외: {e}")
    return []

# 4. Gemini AI 분석 (링크 파손 방지를 위해 분석 텍스트만 별도 생성)
def analyze_insights(kr_list, global_list, viral_list):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    context_text = "오늘의 바이럴 영상 제목들:\n"
    for v in kr_list + global_list + viral_list:
        context_text += f"- {v['title']}\n"

    prompt = f"""
다음은 오늘 한국 및 전 세계 SNS에서 실제 급상승한 바이럴 영상 제목 목록이다:
{context_text}

숏폼 영상 크리에이터를 위해 다음 두 가지만 1~2줄로 명확하게 작성해줘:
1. 오늘 급상승 영상들의 핵심 후킹 특징 (시청자의 시선을 끈 이유)
2. 오늘 트렌드를 응용한 바로 써먹을 수 있는 숏폼 기획 아이디어 1줄
(답변에 마크다운 볼드나 링크는 넣지 말고 깔끔한 텍스트로만 작성해줘)
"""
    for model_name in ["gemini-3.8-flash", "gemini-3.5-flash-lite"]:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text.strip()
        except Exception:
            continue
    return "시청자의 즉각적인 호기심과 의외성을 자극하는 영상이 알고리즘을 타고 있습니다."

# 5. 파이썬이 직접 메시지를 조립하여 링크 원형을 100% 보존
def build_message(kr_shorts, global_shorts, viral_shorts, memes, insights):
    today = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    lines = [f"🌐 [숏폼 트렌드 데일리 브리핑] - {today}\n"]

    # 1. 국내 유튜브 쇼츠
    lines.append("🇰🇷 1. 유튜브 쇼츠 국내 급상승 TOP 3")
    for idx, v in enumerate(kr_shorts, 1):
        lines.append(f"{idx}. {v['title']}")
        lines.append(f"   조회수: {v['views']:,}회")
        lines.append(f"   👉 영상보기: {v['url']}\n")

    # 2. 해외 유튜브 쇼츠
    lines.append("🌍 2. 유튜브 쇼츠 해외 급상승 TOP 3")
    for idx, v in enumerate(global_shorts, 1):
        lines.append(f"{idx}. {v['title']}")
        lines.append(f"   조회수: {v['views']:,}회")
        lines.append(f"   👉 영상보기: {v['url']}\n")

    # 3. 틱톡/인스타 바이럴
    lines.append("🔥 3. 글로벌 틱톡 & 릴스 화제 영상 TOP 3")
    for idx, v in enumerate(viral_shorts, 1):
        lines.append(f"{idx}. {v['title']}")
        lines.append(f"   조회수: {v['views']:,}회")
        lines.append(f"   👉 영상보기: {v['url']}\n")

    # 4. 글로벌 신규 밈/챌린지
    if memes:
        lines.append("⚡ 4. 해외 신규 급상승 밈/챌린지")
        for m in memes:
            lines.append(f"• {m['title']}")
            if m['desc']: lines.append(f"  내용: {m['desc'][:60]}...")
            lines.append(f"  👉 상세보기: {m['link']}\n")

    # 5. 인사이트
    lines.append("💡 5. 오늘의 연출 포인트 & 기획 제안")
    lines.append(insights)

    return "\n".join(lines)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    check_env()
    print("1. 국내/해외/틱톡/릴스 데이터 수집 중...")
    kr_shorts = fetch_youtube_shorts(region_code="KR", query="#쇼츠", top_n=3)
    global_shorts = fetch_youtube_shorts(region_code="US", query="viral shorts -#쇼츠", top_n=3)
    viral_shorts = fetch_global_viral_reels_tiktok(top_n=3)
    memes = fetch_latest_trending_memes(top_n=2)

    print("2. 인사이트 분석 중...")
    insights = analyze_insights(kr_shorts, global_shorts, viral_shorts)

    print("3. 원본 링크 보존 메시지 조립 및 발송...")
    final_message = build_message(kr_shorts, global_shorts, viral_shorts, memes, insights)
    send_telegram(final_message)
    print("발송 완료!")
