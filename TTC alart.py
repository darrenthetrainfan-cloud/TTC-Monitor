import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "seen_ids.txt"

# 在这里填入你拿到的 API 信息
# 如果是通过 Github Secrets 传入，建议使用 os.environ.get("TRANSIT_API_KEY")
API_KEY = os.environ.get("TRANSIT_API_KEY") 

MONITOR_CONFIGS = {
    "TTC": {
        "url": "https://bustime.ttc.ca/gtfsrt/alerts",
        "headers": {}
    },
    "YRT": {
        # 使用你找到的 Transitland Onestop ID 对应的 API 路径
        "url": "https://data.transit.land/api/v2/feeds/f-yrt~rt/realtime/alerts",
        "headers": {"x-api-key": API_KEY} # Transitland 通常使用这个 Header
    }
}
# ============================================

def send_to_discord(agency, raw_header, desc, status_type):
    if not WEBHOOK_URL: return
    # 简单的标题处理
    short_header = raw_header.split(':')[0].strip() if ':' in raw_header else raw_header
    
    if status_type == "alert":
        title = f"🚨 {agency} | {short_header}"
        color = 3066993 if agency == "YRT" else 14297372
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
                    key, val = line.strip().split("|||", 1)
                    old_alerts[key] = val

    current_alerts = {}
    fetch_success_agencies = []

    for agency, config in MONITOR_CONFIGS.items():
        try:
            # 携带 API Key 进行请求
            response = requests.get(config["url"], headers=config["headers"], timeout=20)
            
            # 解决 image_38e4bd.png 提到的权限/内容问题
            if response.status_code != 200:
                print(f"Fetch {agency} failed: HTTP {response.status_code}")
                continue

            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            for entity in feed.entity:
                if entity.HasField('alert'):
                    # 彻底修复 image_38ed35.png 的 f-string 语法错误
                    # 先提取文本，并在大括号外部清洗掉换行符
                    h_text = entity.alert.header_text.translation[0].text if entity.alert.header_text.translation else ""
                    d_text = entity.alert.description_text.translation[0].text if entity.alert.description_text.translation else ""
                    
                    h_clean = h_text.replace('\n', ' ').replace('\r', '').strip()
                    d_clean = d_text.replace('\n', ' ').replace('\r', '').strip()
                    
                    if h_clean:
                        current_alerts[f"{agency}:{h_clean}"] = d_clean
            
            fetch_success_agencies.append(agency)
        except Exception as e:
            print(f"Error processing {agency}: {e}")

    # 1. 发送新通知
    for k, v in current_alerts.items():
        if k not in old_alerts:
            ag, hd = k.split(':', 1)
            send_to_discord(ag, hd, v, "alert")

    # 2. 发送恢复通知 (仅针对抓取成功的机构)
    for k, v in old_alerts.items():
        ag = k.split(':')[0]
        if ag in fetch_success_agencies and k not in current_alerts:
            hd = k.split(':', 1)[1]
            send_to_discord(ag, hd, v, "recovery")

    # 3. 更新记忆文件
    final_db = current_alerts.copy()
    for k, v in old_alerts.items():
        if k.split(':')[0] not in fetch_success_agencies:
            final_db[k] = v # 保留抓取失败机构的旧警报，防止误报已恢复

    with open(DB_FILE, "w", encoding="utf-8") as f:
        for k, v in final_db.items():
            f.write(f"{k}|||{v}\n")

if __name__ == "__main__":
    check_all_agencies()
