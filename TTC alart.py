import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = "https://discord.com/api/webhooks/1493694754821505126/74HdOARTigkDHORW2psEDUzYp89IX25Hq0jqn6KZPu1sV1t2-G2n5R1E3rxCP91WDRuC"
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"
DB_FILE = "seen_ids.txt"
# ============================================

def load_seen_alerts():
    # 增加保护：如果文件不存在，返回空集合而不是报错
    if not os.path.exists(DB_FILE):
        return set()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return set(f.read().splitlines())
    except:
        return set()

def save_seen_alerts(seen_set):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(seen_set))

def check_alerts():
    seen_alerts = load_seen_alerts()
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
                    
                    # 颜色和分类
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
                    print(f"Sent: {header[:50]}")

        if new_alerts_found:
            save_seen_alerts(seen_alerts)
            return True
            
    except Exception as e:
        print(f"Error: {e}")
    return False

if __name__ == "__main__":
    # 第一次运行启动通知
    if not os.path.exists(DB_FILE):
        try:
            requests.post(WEBHOOK_URL, json={"content": "🚀 **TTC Tracker First-Time Setup Complete.**"})
        except: pass
        
    check_alerts()
