import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "seen_ids.txt"

MONITOR_CONFIGS = {
    "TTC": {
        "url": "https://bustime.ttc.ca/gtfsrt/alerts",
        "headers": {}
    },
    "GO Transit": {
        # 换用 Transitland 的公共镜像，避开 Metrolinx 官网的 HTML 拦截
        "url": "https://data.transit.land/api/v2/feeds/f-dpz-gotransit/realtime/alerts",
        "headers": {"User-Agent": "Mozilla/5.0"}
    }
}
# ============================================

def get_embed_color(agency, content):
    content = content.lower()
    if agency == "TTC":
        if "line 1" in content: return 16766720  # Yellow
        if "line 2" in content: return 3066993   # Green
        return 14297372  # Red
    
    if agency == "GO Transit":
        if "lakeshore" in content: return 18791   # Dark Green
        if "kitchener" in content: return 3447003 # Light Blue
        if "milton" in content: return 16738657   # Orange
        return 5763719  # GO Green
    return 3447003

def send_to_discord(agency, raw_header, desc, status_type):
    if not WEBHOOK_URL: return
    short_header = raw_header.split(':')[0].strip() if ':' in raw_header else raw_header
    
    if status_type == "alert":
        title = f"🚨 {agency} | {short_header}"
        color = get_embed_color(agency, raw_header + desc)
        msg_desc = f"**New Alert Details:**\n{desc}"
    else:
        title = f"✅ {agency} Resolved | {short_header}"
        color = 5763719
        msg_desc = f"**This issue has been cleared.**\n~~{desc}~~"

    payload = {
        "username": f"{agency} Tracker",
        "embeds": [{
            "title": title, "description": msg_desc, "color": color,
            "footer": {"text": "Real-time Updates"},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    }
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except: pass

def check_all_agencies():
    old_alerts = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "|||" in line:
                    parts = line.strip().split("|||", 1)
                    if len(parts) == 2: old_alerts[parts[0]] = parts[1]

    current_alerts = {}
    fetch_success_agencies = []

    for agency, config in MONITOR_CONFIGS.items():
        try:
            response = requests.get(config["url"], headers=config["headers"], timeout=25)
            
            # 解决 image_2c35c0.png 的核心逻辑：判断是否为有效的 Protobuf
            if response.status_code == 200 and "text/html" not in response.headers.get("Content-Type", ""):
                feed = gtfs_realtime_pb2.FeedMessage()
                feed.ParseFromString(response.content)
                
                for entity in feed.entity:
                    if entity.HasField('alert'):
                        h = entity.alert.header_text.translation[0].text if entity.alert.header_text.translation else "No Title"
                        d = entity.alert.description_text.translation[0].text if entity.alert.description_text.translation else ""
                        
                        h_clean = h.replace('\n', ' ').replace('\r', '').strip()
                        d_clean = d.replace('\n', ' ').replace('\r', '').strip()
                        
                        if h_clean:
                            current_alerts[f"{agency}:{h_clean}"] = d_clean
                
                fetch_success_agencies.append(agency)
                print(f"Successfully synced {agency}")
            else:
                print(f"Error: {agency} returned non-GTFS data (HTTP {response.status_code})")
        except Exception as e:
            print(f"Exception during {agency}: {e}")

    # 发送逻辑
    for k, v in current_alerts.items():
        if k not in old_alerts:
            ag, hd = k.split(':', 1)
            send_to_discord(ag, hd, v, "alert")

    for k, v in old_alerts.items():
        ag = k.split(':')[0]
        if ag in fetch_success_agencies and k not in current_alerts:
            hd = k.split(':', 1)[1]
            send_to_discord(ag, hd, v, "recovery")

    # 写入 DB
    final_db = current_alerts.copy()
    for k, v in old_alerts.items():
        if k.split(':')[0] not in fetch_success_agencies:
            final_db[k] = v

    with open(DB_FILE, "w", encoding="utf-8") as f:
        for k, v in final_db.items():
            f.write(f"{k}|||{v}\n")

if __name__ == "__main__":
    check_all_agencies()
