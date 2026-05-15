import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"
DB_FILE = "seen_ids.txt"
# ============================================

def get_color_for_alert(content):
    """根据线路名称判断警报颜色，让 Discord 侧边条符合 TTC 标准"""
    embed_color = 14297372 # 默认 TTC 红色
    if any(x in content for x in ["elevator", "escalator", "wheel-trans", "accessibility"]):
        embed_color = 3447003  # 蓝色
    elif any(x in content for x in ["line 1", "yonge-university"]):
        embed_color = 16766720  # 黄色
    elif any(x in content for x in ["line 2", "bloor-danforth"]):
        embed_color = 3066993   # 绿色
    elif any(x in content for x in ["line 4", "sheppard"]):
        embed_color = 10181046  # 紫色
    elif any(x in content for x in ["line 5", "eglinton"]):
        embed_color = 16750848  # 橙色
    elif any(x in content for x in ["line 6", "finch west"]):
        embed_color = 8421504   # 灰色
    return embed_color

def send_to_discord(raw_header, desc, status_type):
    """发送格式化后的消息到 Discord"""
    if not WEBHOOK_URL:
        return
        
    content = (raw_header + desc).lower()
    
    # 标题精简逻辑：只保留冒号前面的文字 (例如: Line 1 Yonge-University)
    short_header = raw_header.split(':')[0].strip() if ':' in raw_header else raw_header

    # 状态分流：警报 vs 恢复
    if status_type == "alert":
        title = f"🚨 {short_header}"
        color = get_color_for_alert(content)
        # 这里移除了重复且显示不全的 raw_header，直接显示详细内容
        description = f"**New Alert Details:**\n{desc}"
    else:
        title = f"✅ Resolved: {short_header}"
        color = 5763719  # 恢复通知固定使用绿色
        description = f"**This issue has been cleared.**\n~~{desc}~~"

    payload = {
        "username": "TTC Tracker",
        # 不传 avatar_url，强制使用你在 Discord Webhook 设置里手动上传的头像
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "footer": {"text": "TTC Real-time Alerts"},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    }
    
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
        print(f"Successfully sent {status_type}: {short_header}")
    except Exception as e:
        print(f"Failed to send Discord message: {e}")

def check_alerts():
    if not WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK is not set!")
        return False

    # 1. 加载旧警报（用于对比，判断谁恢复了）
    old_alerts = {}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if "|||" in line:
                        h, d = line.strip().split("|||", 1)
                        old_alerts[h] = d
        except Exception as e:
            print(f"Database Read Error: {e}")

    current_alerts = {}
    has_changes = False
    
    try:
        # 伪装 Header 降低被封风险
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
        response = requests.get(TTC_ALERTS_URL, timeout=15, headers=headers)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        # 2. 解析当前所有活跃警报，清洗掉换行符防止数据库格式崩坏
        for entity in feed.entity:
            if entity.HasField('alert'):
                alert = entity.alert
                header = alert.header_text.translation[0].text if alert.header_text.translation else "TTC Alert"
                description = alert.description_text.translation[0].text if alert.description_text.translation else "No details."
                
                h_clean = header.replace("\n", " ").replace("\r", "").replace("|||", " ").strip()
                d_clean = description.replace("\n", " ").replace("\r", "").strip()
                current_alerts[h_clean] = d_clean

        # 3. 核心对比逻辑
        # 找出新出现的警报
        for h, d in current_alerts.items():
            if h not in old_alerts:
                send_to_discord(h, d, "alert")
                has_changes = True

        # 找出刚刚消失（恢复）的警报
        for h, d in old_alerts.items():
            if h not in current_alerts:
                send_to_discord(h, d, "recovery")
                has_changes = True

        # 4. 如果有变动，存回仓库
        if has_changes:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                for h, d in current_alerts.items():
                    f.write(f"{h}|||{d}\n")
            print("Memory updated.")
        else:
            print("No changes detected.")
        return True
            
    except Exception as e:
        print(f"Critical Error: {e}")
    return False

if __name__ == "__main__":
    check_alerts()
