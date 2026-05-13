import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "seen_ids.txt"

# 最终筛选出的最稳接口
MONITOR_CONFIGS = {
    "TTC": {
        "url": "https://bustime.ttc.ca/gtfsrt/alerts"
    },
    "YRT": {
        # 换回这个由社区维护的、无防火墙限制的标准源
        "url": "https://api.transitfeeds.com/v1/getGtfsRealtime?key=NON_PROFIT_KEY&feed_id=yrt/560&type=alerts"
    }
}
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
        color = 5763719 # 绿色
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
    fetch_success_agencies = [] # 记录哪些机构抓取成功了

    for agency, config in MONITOR_CONFIGS.items():
        try:
            response = requests.get(config["url"], timeout=15)
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            
            for entity in feed.entity:
                if entity.HasField('alert'):
                    h = entity.alert.header_text.translation[0].text
                    d = entity.alert.description_text.translation[0].text
                    h_clean = h.replace('\n', ' ').strip()
                    d_clean = d.replace('\n', ' ').strip()
                    current_alerts[f"{agency}:{h_clean}"] = d_clean
            fetch_success_agencies.append(agency)
        except Exception as e:
            print(f"Error fetching {agency}: {e}")

    # 3. 核心改进：只对抓取成功的机构进行对比
    # 找新出现的
    for h_key, d in current_alerts.items():
        if h_key not in old_alerts:
            agency_name, actual_header = h_key.split(':', 1)
            send_to_discord(agency_name, actual_header, d, "alert")

    # 找消失的（已解决）
    for h_key, d in old_alerts.items():
        agency_name = h_key.split(':')[0]
        # 关键：只有当该机构这次抓取成功，但警报消失了，才发 Resolved
        if agency_name in fetch_success_agencies and h_key not in current_alerts:
            actual_header = h_key.split(':', 1)[1]
            send_to_discord(agency_name, actual_header, d, "recovery")

    # 4. 增量更新记忆文件
    # 我们不能简单覆盖，要把抓取失败的机构的旧记忆保留下来，防止误报 Resolved
    new_db_content = current_alerts.copy()
    for h_key, d in old_alerts.items():
        agency_name = h_key.split(':')[0]
        if agency_name not in fetch_success_agencies:
            new_db_content[h_key] = d

    if new_db_content != old_alerts:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            for h, d in new_db_content.items():
                f.write(f"{h}|||{d}\n")

if __name__ == "__main__":
    check_all_agencies()
