import requests
import time
import os
import re
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"
DB_FILE = "seen_ids.txt"
# ============================================

def get_color_for_alert(content):
    """根据内容判断新警报的颜色"""
    embed_color = 14297372 # 默认 TTC 红色
    if any(x in content for x in ["elevator", "escalator", "wheel-trans", "accessibility"]):
        embed_color = 3447003 
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

def send_to_discord(header, desc, status_type):
    """专门负责发送消息到 Discord 的函数"""
    if not WEBHOOK_URL:
        return
        
    content = (header + desc).lower()
    
    # 状态分流：警报 vs 恢复
    if status_type == "alert":
        title = f"🚨 {header[:200]}"
        color = get_color_for_alert(content)
        description = f"**New Alert Details:**\n{desc}"
    else:
        title = f"✅ TTC Resolved: {header[:200]}"
        color = 5763719  # 恢复通知专属绿色
        # 在恢复通知中，给描述加上删除线，表示已失效
        description = f"**This issue has been cleared.**\n~~{desc}~~"

    payload = {
        "username": "TTC Tracker",
               "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    }
    
    try:
        requests.post(WEBHOOK_URL, json=payload)
        print(f"Sent {status_type}: {header[:50]}")
    except Exception as e:
        print(f"Failed to send Discord message: {e}")

def check_alerts():
    if not WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK is not set!")
        return False

    # 1. 翻开“记事本”，看看上一分钟有哪些没解决的警报
    old_alerts = {}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if "|||" in line:
                        h, d = line.strip().split("|||", 1)
                        old_alerts[h] = d
        except Exception as e:
            print(f"DB Read Error: {e}")

    current_alerts = {}
    has_changes = False
    
    try:
        # 伪装成浏览器，防止被 TTC 封锁
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(TTC_ALERTS_URL, timeout=15, headers=headers)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        # 2. 收集现在正活跃的所有警报
        for entity in feed.entity:
            if entity.HasField('alert'):
                alert = entity.alert
                header = alert.header_text.translation[0].text if alert.header_text.translation else "TTC Alert"
                desc = alert.description_text.translation[0].text if alert.description_text.translation else "No details."
                
                # 清洗文本，防止换行符把我们的记事本弄乱
                header_clean = header.replace("\n", " ").replace("|||", " ")
                desc_clean = desc.replace("\n", " ")
                current_alerts[header_clean] = desc_clean

        # 3. 找“新警报”（在现在的列表里，但不在旧列表里）
        for h, d in current_alerts.items():
            if h not in old_alerts:
                send_to_discord(h, d, "alert")
                has_changes = True

        # 4. 找“已恢复”（在旧列表里，但不在现在的列表里）
        for h, d in old_alerts.items():
            if h not in current_alerts:
                send_to_discord(h, d, "recovery")
                has_changes = True

        # 5. 如果有任何变化（或者第一次运行），把最新状态存起来
        if has_changes or len(old_alerts) == 0:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                for h, d in current_alerts.items():
                    f.write(f"{h}|||{d}\n")
            return True
            
    except Exception as e:
        print(f"Error during execution: {e}")
    
    return False

if __name__ == "__main__":
    check_alerts()
