import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = "https://discord.com/api/webhooks/1493694754821505126/74HdOARTigkDHORW2psEDUzYp89IX25Hq0jqn6KZPu1sV1t2-G2n5R1E3rxCP91WDRuC"
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"
DB_FILE = "seen_ids.txt" # 用于存储已发送警报的文件
# ============================================

def load_seen_alerts():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return set(f.read().splitlines())
    return set()

def save_seen_alerts(seen_set):
    with open(DB_FILE, "w") as f:
        f.write("\n".join(seen_set))

def check_alerts():
    seen_alerts = load_seen_alerts()
    new_alerts_found = False
    
    try:
        response = requests.get(TTC_ALERTS_URL, timeout=10)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        for entity in feed.entity:
            if entity.HasField('alert'):
                alert = entity.alert
                header = alert.header_text.translation[0].text if alert.header_text.translation else ""
                desc = alert.description_text.translation[0].text if alert.description_text.translation else ""
                
                # 使用内容指纹
                fingerprint = f"{header}|{desc}"
                
                if fingerprint not in seen_alerts:
                    seen_alerts.add(fingerprint)
                    new_alerts_found = True
                    
                    # 发送 Discord
                    payload = {
                        "username": "TTC Service Alert",
                        "avatar_url": "https://upload.wikimedia.org/wikipedia/en/thumb/8/8e/TTC.svg/1200px-TTC.svg.png",
                        "embeds": [{
                            "title": f"🚨 {header}",
                            "description": desc,
                            "color": 14297372
                        }]
                    }
                    requests.post(WEBHOOK_URL, json=payload)
                    print(f"Sent: {header}")

        if new_alerts_found:
            save_seen_alerts(seen_alerts)
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

if __name__ == "__main__":
    check_alerts()
