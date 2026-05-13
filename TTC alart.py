import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
# 建议在 GitHub Secrets 中设置 TRANSLINK_API_KEY
TRANSLINK_KEY = os.environ.get("TRANSLINK_API_KEY") 
DB_FILE = "seen_ids.txt"

MONITOR_CONFIGS = {
    "TTC": {
        "url": "https://bustime.ttc.ca/gtfsrt/alerts",
        "headers": {}
    },
    "TransLink": {
        "url": f"https://gtfs.translink.ca/v2/gtfsrealtime/alerts?apikey={TRANSLINK_KEY}",
        "headers": {"Accept": "application/x-protobuf"}
    }
}
# ============================================

def get_embed_color(agency, content):
    content = content.lower()
    if agency == "TTC":
        if "line 1" in content: return 16766720  # Yonge-University (Yellow)
        if "line 2" in content: return 3066993   # Bloor-Danforth (Green)
        if "line 4" in content: return 10181046  # Sheppard (Purple)
        return 14297372  # Default Red
    
    if agency == "TransLink":
        if "expo line" in content: return 2123412  # Blue
        if "millennium line" in content: return 16766720  # Yellow
        if "canada line" in content: return 3447003  # Sky Blue
        if "west coast express" in content: return 10181046 # Purple
        return 5763719  # Green (Bus/Generic)
    
    return 3447003

def send_to_discord(agency, raw_header, desc, status_type):
    if not WEBHOOK_URL: return
    short_header = raw_header.split(':')[0].strip() if ':' in raw_header else raw_header
    
    if status_type == "alert":
        title = f"🚨 {agency} | {short_header}"
        color = get_embed_color(agency, raw_header + desc)
        description = f"**New Alert Details:**\n{desc}"
    else:
        title = f"✅ {agency} Resolved | {short_header}"
        color = 5763719
        description = f"**This issue has been cleared.**\n~~{desc}~~"

    payload = {
        "username": f"{agency} Tracker",
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
    old_alerts = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "|||" in line:
                    key, val = line.strip().split("|||", 1)
                    old_alerts[key] = val

    current_alerts = {}
    fetch_success_agencies = []

    for agency, config in MONITOR_CONFIGS.items():
        try:
            # 检查 TransLink Key
            if agency == "TransLink" and (not TRANSLINK_KEY or "None" in config["url"]):
                print("Skip TransLink: API Key missing.")
                continue

            response = requests.get(config["url"], headers=config["headers"], timeout=20)
            
            if response.status_code != 200:
                print(f"Error: {agency} HTTP {response.status_code}")
                continue

            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            for entity in feed.entity:
                if entity.HasField('alert'):
                    h_text = entity.alert.header_text.translation[0].text if entity.alert.header_text.translation else ""
                    d_text = entity.alert.description_text.translation[0].text if entity.alert.description_text.translation else ""
                    
                    h_clean = h_text.replace('\n', ' ').replace('\r', '').strip()
                    d_clean = d_text.replace('\n', ' ').replace('\r', '').strip()
                    
                    if h_clean:
                        current_alerts[f"{agency}:{h_clean}"] = d_clean
            
            fetch_success_agencies.append(agency)
            print(f"Successfully synced {agency}")
        except Exception as e:
            print(f"Exception during {agency} process: {e}")

    # 1. 发送新警报
    for k, v in current_alerts.items():
        if k not in old_alerts:
            ag, hd = k.split(':', 1)
            send_to_discord(ag, hd, v, "alert")

    # 2. 发送恢复通知
    for k, v in old_alerts.items():
        ag = k.split(':')[0]
        if ag in fetch_success_agencies and k not in current_alerts:
            hd = k.split(':', 1)[1]
            send_to_discord(ag, hd, v, "recovery")

    # 3. 写入文件
    final_db = current_alerts.copy()
    for k, v in old_alerts.items():
        if k.split(':')[0] not in fetch_success_agencies:
            final_db[k] = v

    with open(DB_FILE, "w", encoding="utf-8") as f:
        for k, v in final_db.items():
            f.write(f"{k}|||{v}\n")

if __name__ == "__main__":
    check_all_agencies()
