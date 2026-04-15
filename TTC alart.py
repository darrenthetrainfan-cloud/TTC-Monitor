import requests
import time
import os
import re
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
# 从 GitHub Secrets 中安全地读取 Webhook 链接
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"
DB_FILE = "seen_ids.txt"
# ============================================

def check_alerts():
    # 如果没设置环境变量，直接报错提醒，防止脚本白跑
    if not WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK environment variable is not set!")
        return False

    seen_alerts = set()
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                seen_alerts = set(f.read().splitlines())
        except:
            pass

    new_alerts_found = False
    
    try:
        response = requests.get(TTC_ALERTS_URL, timeout=15)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        for entity in feed.entity:
            if entity.HasField('alert'):
                alert = entity.alert
                header = alert.header_text.translation[0].text if alert.header_text.translation else "TTC Alert"
                desc = alert.description_text.translation[0].text if alert.description_text.translation else "No details."
                
                fingerprint = f"{header}|{desc}"
                
                if fingerprint not in seen_alerts:
                    seen_alerts.add(fingerprint)
                    new_alerts_found = True
                    
                    # --- 增强型自动化配色逻辑 ---
                    content = (header + desc).lower()
                    
                    # 默认颜色：TTC 红色
                    embed_color = 14297372 

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
                    elif re.search(r'\b5\d{2}\b', content) or "streetcar" in content:
                        embed_color = 14297372
                    elif "bus" in content:
                        embed_color = 14297372

                    payload = {
                        "username": "TTC Tracker",
                        "avatar_url": "https://upload.wikimedia.org/wikipedia/en/thumb/8/8e/TTC.svg/1200px-TTC.svg.png",
                        "embeds": [{
                            "title": f"🚨 {header[:250]}",
                            "description": f"**Full Details:**\n{desc}",
                            "color": embed_color,
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    }
                    requests.post(WEBHOOK_URL, json=payload)
                    print(f"Sent: {header[:50]}")

        if new_alerts_found:
            # 只保留最近的 200 条记录，防止文件无限增大
            to_save = list(seen_alerts)[-200:]
            with open(DB_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(to_save))
            return True
            
    except Exception as e:
        print(f"Error: {e}")
    
    return False

if __name__ == "__main__":
    check_alerts()
