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
                    
                    # --- 自动配色逻辑（6号线修正为灰色） ---
                    content = (header + desc).lower()
                    
                    # 默认颜色：TTC 红色 (Bus/Streetcar)
                    embed_color = 14297372 

                    # 优先级 1: 无障碍设施 -> 蓝色 (Blue)
                    if any(x in content for x in ["elevator", "escalator", "wheel-trans", "accessibility"]):
                        embed_color = 3447003 
                    # 优先级 2: 地铁/轻轨线路
                    elif any(x in content for x in ["line 1", "yonge-university"]):
                        embed_color = 16766720  # 黄色
                    elif any(x in content for x in ["line 2", "bloor-danforth"]):
                        embed_color = 3066993   # 绿色
                    elif any(x in content for x in ["line 4", "sheppard"]):
                        embed_color = 10181046  # 紫色
                    elif any(x in content for x in ["line 5", "eglinton"]):
                        embed_color = 16750848  # 橙色
                    elif any(x in content for x in ["line 6", "finch west"]):
                        embed_color = 8421504   # 灰色 (Official Line 6 Color)

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
                    print(f"Sent: {header[:50]} (Color: {embed_color})")

        if new_alerts_found:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(seen_alerts))
            return True
            
    except Exception as e:
        print(f"Error: {e}")
    
    return False

if __name__ == "__main__":
    check_alerts()
