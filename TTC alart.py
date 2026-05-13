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
        # GO Transit 公共 GTFS-R 接口，通常无需 API Key
        "url": "https://api.metrolinx.com/gtfs/v1/realtime/alerts",
        "headers": {
            "Accept": "application/x-protobuf",
            "User-Agent": "Mozilla/5.0" 
        }
    }
}
# ============================================

def get_embed_color(agency, content):
    content = content.lower()
    if agency == "TTC":
        if "line 1" in content: return 16766720  # Yellow
        if "line 2" in content: return 3066993   # Green
        if "line 4" in content: return 10181046  # Purple
        return 14297372  # Red
    
    if agency == "GO Transit":
        # 根据路线关键词分配 GO 官方颜色
        if "lakeshore" in content: return 18791   # Lakeshore West/East (Dark Green)
        if "kitchener" in content: return 3447003 # Kitchener (Light Blue)
        if "milton" in content: return 16738657   # Milton (Orange)
        if "barrie" in content: return 2123412    # Barrie (Navy)
        if "stouffville" in content: return 10181046 # Stouffville (Purple)
        return 5763719  # GO Green (Default)
    
    return 3447003

def send_to_discord(agency, raw_header, desc, status_type):
    if not WEBHOOK_URL: return
    # 提取短标题，避免 Discord 标题过长
    short_header = raw_header.split(':')[0].strip() if ':' in raw_header else raw_header
    
    if status_type == "alert":
        title = f"🚨 {agency} | {short_header}"
        color = get_embed_color(agency, raw_header + desc)
        description = f"**New Alert Details:**\n{desc}"
    else:
        title = f"✅ {agency} Resolved | {short_header}"
        color = 5763719 # 绿色
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
                    parts = line.strip().split("|||", 1)
                    if len(parts) == 2:
                        old_alerts[parts[0]] = parts[1]

    current_alerts = {}
    fetch_success_agencies = []

    for agency, config in MONITOR_CONFIGS.items():
        try:
            response = requests.get(config["url"], headers=config["headers"], timeout=20)
            
            # 安全检查：防止返回 HTML 导致解析崩溃
            if "text/html" in response.headers.get("Content-Type", ""):
                print(f"Error: {agency} returned HTML. Check URL.")
                continue

            if response.status_code == 200:
                feed = gtfs_realtime_pb2.FeedMessage()
                feed.ParseFromString(response.content)
                
                for entity in feed.entity:
                    if entity.HasField('alert'):
                        # 提取多语言文本（默认为第一条）
                        h_t = entity.alert.header_text.translation[0].text if entity.alert.header_text.translation else ""
                        d_t = entity.alert.description_text.translation[0].text if entity.alert.description_text.translation else ""
                        
                        # 清洗掉换行符，防止破坏 TXT 数据库
                        h_clean = h_t.replace('\n', ' ').replace('\r', '').strip()
                        d_clean = d_t.replace('\n', ' ').replace('\r', '').strip()
                        
                        if h_clean:
                            current_alerts[f"{agency}:{h_clean}"] = d_clean
                
                fetch_success_agencies.append(agency)
                print(f"Successfully synced {agency}")
            else:
                print(f"Error: {agency} HTTP {response.status_code}")
        except Exception as e:
            print(f"Exception during {agency}: {e}")

    # 发送通知逻辑
    for k, v in current_alerts.items():
        if k not in old_alerts:
            ag, hd = k.split(':', 1)
            send_to_discord(ag, hd, v, "alert")

    for k, v in old_alerts.items():
        ag = k.split(':')[0]
        if ag in fetch_success_agencies and k not in current_alerts:
            hd = k.split(':', 1)[1]
            send_to_discord(ag, hd, v, "recovery")

    # 汇总写入数据库
    final_db = current_alerts.copy()
    for k, v in old_alerts.items():
        if k.split(':')[0] not in fetch_success_agencies:
            final_db[k] = v

    with open(DB_FILE, "w", encoding="utf-8") as f:
        for k, v in final_db.items():
            f.write(f"{k}|||{v}\n")

if __name__ == "__main__":
    check_all_agencies()
