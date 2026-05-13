import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "seen_ids.txt"
# ============================================

def get_color_for_alert(agency, content):
    content = content.lower()
    if agency == "YRT": return 3066993
    embed_color = 14297372
    if any(x in content for x in ["elevator", "accessibility"]): embed_color = 3447003
    elif "line 1" in content: embed_color = 16766720
    elif "line 2" in content: embed_color = 3066993
    elif "line 4" in content: embed_color = 10181046
    elif "line 5" in content: embed_color = 16750848
    return embed_color

def send_to_discord(agency, raw_header, desc, status_type):
    if not WEBHOOK_URL: return
    short_header = raw_header.split(':')[0].strip() if ':' in raw_header else raw_header
    
    if status_type == "alert":
        title = f"🚨 {agency} | {short_header}"
        color = get_color_for_alert(agency, raw_header + desc)
        description = f"**New Alert Details:**\n{desc}"
    else:
        title = f"✅ {agency} Resolved | {short_header}"
        color = 5763719
        description = f"**This issue has been cleared.**\n~~{desc}~~"

    payload = {
        "username": "Transit Tracker",
        "embeds": [{
            "title": title, "description": description, "color": color,
            "footer": {"text": f"{agency} Real-time Updates"},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    }
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except: pass

def check_all_agencies():
    if not WEBHOOK_URL: return
    old_alerts = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "|||" in line:
                    key, d = line.strip().split("|||", 1)
                    old_alerts[key] = d

    current_alerts = {}
    fetch_success_agencies = []

    # 1. 抓取 TTC (Protobuf 格式)
    try:
        ttc_res = requests.get("https://bustime.ttc.ca/gtfsrt/alerts", timeout=15)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(ttc_res.content)
        for entity in feed.entity:
            if entity.HasField('alert'):
                h = entity.alert.header_text.translation[0].text
                d = entity.alert.description_text.translation[0].text
                current_alerts[f"TTC:{h.replace('\n', ' ').strip()}"] = d.replace('\n', ' ').strip()
        fetch_success_agencies.append("TTC")
    except Exception as e: print(f"TTC Error: {e}")

    # 2. 抓取 YRT (直接抓官网 JSON 接口，避开 Protobuf 解析错误)
    try:
        yrt_res = requests.get("https://opendata.york.ca/api/v2/feeds/f-dpz-yrt/realtime/alerts", timeout=15)
        # 即使官网 API 偶尔抽风返回 JSON，我们也通过通用逻辑处理
        if yrt_res.status_code == 200:
            data = yrt_res.json()
            # Transitland/OpenData 提供的标准 JSON 格式解析
            for item in data.get('entities', []):
                alert = item.get('alert', {})
                h = alert.get('header_text', {}).get('translation', [{}])[0].get('text', 'YRT Alert')
                d = alert.get('description_text', {}).get('translation', [{}])[0].get('text', '')
                current_alerts[f"YRT:{h.replace('\n', ' ').strip()}"] = d.replace('\n', ' ').strip()
            fetch_success_agencies.append("YRT")
    except:
        # 如果 JSON 接口也挂了，尝试最后的标准 REST 接口
        try:
            yrt_res = requests.get("https://api.transitfeeds.com/v1/getGtfsRealtime?key=NON_PROFIT_KEY&feed_id=yrt/560&type=alerts", timeout=15)
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(yrt_res.content)
            for entity in feed.entity:
                if entity.HasField('alert'):
                    h = entity.alert.header_text.translation[0].text
                    d = entity.alert.description_text.translation[0].text
                    current_alerts[f"YRT:{h.replace('\n', ' ').strip()}"] = d.replace('\n', ' ').strip()
            fetch_success_agencies.append("YRT")
        except Exception as e: print(f"YRT Error: {e}")

    # 3. 对比发出通知 (包括已解决通知)
    for h_key, d in current_alerts.items():
        if h_key not in old_alerts:
            agency, head = h_key.split(':', 1)
            send_to_discord(agency, head, d, "alert")

    for h_key, d in old_alerts.items():
        agency = h_key.split(':')[0]
        if agency in fetch_success_agencies and h_key not in current_alerts:
            head = h_key.split(':', 1)[1]
            send_to_discord(agency, head, d, "recovery")

    # 4. 保存记忆
    new_db = current_alerts.copy()
    for h_key, d in old_alerts.items():
        if h_key.split(':')[0] not in fetch_success_agencies:
            new_db[h_key] = d
    
    if new_db != old_alerts:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            for h, d in new_db.items(): f.write(f"{h}|||{d}\n")

if __name__ == "__main__":
    check_all_agencies()
