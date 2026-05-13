import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "seen_ids.txt"

# 监控配置列表：可以轻松扩展更多来源
MONITOR_CONFIGS = {
    "TTC": {
        "url": "https://bustime.ttc.ca/gtfsrt/alerts",
        "icon": "https://upload.wikimedia.org/wikipedia/en/thumb/8/8e/TTC.svg/64px-TTC.svg.png"
    },
    "YRT": {
        "url": "https://opendata.yorton.ca/gtfs-rt/alerts",
        "icon": "https://www.yrt.ca/en/images/yrt-logo.png"
    }
}
# ============================================

def get_color_for_alert(agency, content):
    """根据机构和线路内容判断颜色"""
    content = content.lower()
    if agency == "YRT":
        return 3066993  # YRT 品牌绿色
    
    # TTC 的色系逻辑
    embed_color = 14297372 # 默认红色
    if any(x in content for x in ["elevator", "accessibility"]):
        embed_color = 3447003  # 蓝色
    elif "line 1" in content: embed_color = 16766720  # 黄色
    elif "line 2" in content: embed_color = 3066993   # 绿色
    elif "line 4" in content: embed_color = 10181046  # 紫色
    return embed_color

def send_to_discord(agency, raw_header, desc, status_type):
    """发送格式化后的消息"""
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
        "username": f"{agency} Tracker",
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "footer": {"text": f"{agency} Real-time Updates"},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    }
    
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send: {e}")

def check_all_agencies():
    if not WEBHOOK_URL: return

    # 1. 读取旧记忆
    old_alerts = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "|||" in line:
                    key, d = line.strip().split("|||", 1)
                    old_alerts[key] = d

    current_alerts = {}
    has_changes = False
    
    # 2. 轮询所有机构
    for agency, config in MONITOR_CONFIGS.items():
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(config["url"], timeout=15, headers=headers)
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            for entity in feed.entity:
                if entity.HasField('alert'):
                    h = entity.alert.header_text.translation[0].text
                    d = entity.alert.description_text.translation[0].text
                    
                    # 关键：Key 加上 agency 前缀，防止不同机构的 Header 撞车
                    h_clean = f"{agency}:{h.replace('\n', ' ').strip()}"
                    d_clean = d.replace('\n', ' ').strip()
                    current_alerts[h_clean] = d_clean
        except Exception as e:
            print(f"Error fetching {agency}: {e}")

    # 3. 对比逻辑
    for h, d in current_alerts.items():
        if h not in old_alerts:
            agency_prefix = h.split(':')[0]
            actual_header = h.split(':', 1)[1]
            send_to_discord(agency_prefix, actual_header, d, "alert")
            has_changes = True

    for h, d in old_alerts.items():
        if h not in current_alerts:
            agency_prefix = h.split(':')[0]
            actual_header = h.split(':', 1)[1]
            send_to_discord(agency_prefix, actual_header, d, "recovery")
            has_changes = True

    # 4. 存回记忆
    if has_changes:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            for h, d in current_alerts.items():
                f.write(f"{h}|||{d}\n")

if __name__ == "__main__":
    check_all_agencies()
