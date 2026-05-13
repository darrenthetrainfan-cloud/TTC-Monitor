import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
# 这里的 API Key 会从 GitHub Secrets 自动读取
API_KEY = os.environ.get("TRANSIT_API_KEY") 
DB_FILE = "seen_ids.txt"

MONITOR_CONFIGS = {
    "TTC": {
        "url": "https://bustime.ttc.ca/gtfsrt/alerts",
        "headers": {}
    },
    "YRT": {
        # Transitland 提供的 YRT 实时警报接口
        "url": "https://data.transit.land/api/v2/feeds/f-yrt~rt/realtime/alerts",
        "headers": {"x-api-key": API_KEY}
    }
}
# ============================================

def get_color(agency):
    # YRT 蓝色，TTC 默认红色
    return 3066993 if agency == "YRT" else 14297372

def send_to_discord(agency, raw_header, desc, status_type):
    if not WEBHOOK_URL: return
    short_header = raw_header.split(':')[0].strip() if ':' in raw_header else raw_header
    
    if status_type == "alert":
        title = f"🚨 {agency} | {short_header}"
        color = get_color(agency)
        description = f"**New Alert Details:**\n{desc}"
    else:
        title = f"✅ {agency} Resolved | {short_header}"
        color = 5763719 # 绿色表示恢复
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
    if not WEBHOOK_URL: 
        print("Error: DISCORD_WEBHOOK not found.")
        return

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
            # 安全检查：如果 YRT 没拿到 API Key 就跳过，防止解析错误
            if agency == "YRT" and not API_KEY:
                print("Skip YRT: TRANSIT_API_KEY environment variable is missing.")
                continue

            response = requests.get(config["url"], headers=config["headers"], timeout=20)
            
            # 解决 image_387c5f.png 的解析报错：检查是否为有效的 Protobuf 数据
            if "text/html" in response.headers.get("Content-Type", ""):
                print(f"Error: {agency} API returned HTML (likely invalid API Key or Auth error).")
                continue
            
            if response.status_code != 200:
                print(f"Error: {agency} HTTP {response.status_code}")
                continue

            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            for entity in feed.entity:
                if entity.HasField('alert'):
                    # 彻底修复 image_38ed35.png 的语法错误
                    h_raw = entity.alert.header_text.translation[0].text if entity.alert.header_text.translation else ""
                    d_raw = entity.alert.description_text.translation[0].text if entity.alert.description_text.translation else ""
                    
                    # 在大括号外清洗文本
                    h_clean = h_raw.replace('\n', ' ').replace('\r', '').strip()
                    d_clean = d_raw.replace('\n', ' ').replace('\r', '').strip()
                    
                    if h_clean:
                        current_alerts[f"{agency}:{h_clean}"] = d_clean
            
            fetch_success_agencies.append(agency)
            print(f"Successfully synced {agency}")
        except Exception as e:
            print(f"Exception during {agency} process: {e}")

    # 1. 发现新警报
    for k, v in current_alerts.items():
        if k not in old_alerts:
            ag, hd = k.split(':', 1)
            send_to_discord(ag, hd, v, "alert")

    # 2. 发现已解决的警报 (仅对比成功抓取的机构)
    for k, v in old_alerts.items():
        ag = k.split(':')[0]
        if ag in fetch_success_agencies and k not in current_alerts:
            hd = k.split(':', 1)[1]
            send_to_discord(ag, hd, v, "recovery")

    # 3. 汇总并写入数据库
    final_db = current_alerts.copy()
    for k, v in old_alerts.items():
        if k.split(':')[0] not in fetch_success_agencies:
            final_db[k] = v # 保留失败机构的旧警报，避免误报“恢复”

    with open(DB_FILE, "w", encoding="utf-8") as f:
        for k, v in final_db.items():
            f.write(f"{k}|||{v}\n")

if __name__ == "__main__":
    check_all_agencies()
