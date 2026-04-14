import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = "https://discord.com/api/webhooks/1493694754821505126/74HdOARTigkDHORW2psEDUzYp89IX25Hq0jqn6KZPu1sV1t2-G2n5R1E3rxCP91WDRuC"
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"
DB_FILE = "seen_ids.txt"
# ============================================

def check_alerts():
    # 1. 尝试读取已发送的历史，如果文件不存在就给个空的 set
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
                
                # 指纹去重
                fingerprint = f"{header}|{desc}"
                
                if fingerprint not in seen_alerts:
                    seen_alerts.add(fingerprint)
                    new_alerts_found = True
                    
                    # 地铁红色，其他蓝色
                    subway_keywords = ["Line 1", "Line 2", "Line 4", "Subway"]
                    embed_color = 14297372 if any(k in header or k in desc for k in subway_keywords) else 3447003
                    
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
                    print(f"Sent alert: {header[:50]}")

        # 2. 如果有新警报，保存并更新文件
        if new_alerts_found:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(seen_alerts))
            print("Database updated.")
            return True
            
    except Exception as e:
        print(f"Error: {e}")
    
    return False

if __name__ == "__main__":
    check_alerts()
