import requests
import time
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
# 填入你的 Discord Webhook 链接
WEBHOOK_URL = "https://discord.com/api/webhooks/1493694754821505126/74HdOARTigkDHORW2psEDUzYp89IX25Hq0jqn6KZPu1sV1t2-G2n5R1E3rxCP91WDRuC"

# TTC 官方 GTFS-RT 警报数据源
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"

# 检查间隔（秒），建议 60 秒
CHECK_INTERVAL = 60
# ============================================

# 使用内容指纹来记录已发送的警报
seen_alerts = set()

def check_alerts(initial=False):
    try:
        # 请求数据
        response = requests.get(TTC_ALERTS_URL, timeout=10)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        for entity in feed.entity:
            if entity.HasField('alert'):
                alert = entity.alert
                
                # 提取标题和描述
                header = alert.header_text.translation[0].text if alert.header_text.translation else ""
                desc = alert.description_text.translation[0].text if alert.description_text.translation else ""
                
                # --- 核心改进：内容去重逻辑 ---
                # 创建一个基于文字内容的“指纹”，防止 TTC 更换 ID 导致的重报
                alert_fingerprint = f"{header}|{desc}"
                
                if alert_fingerprint not in seen_alerts:
                    seen_alerts.add(alert_fingerprint)
                    
                    # 初始扫描时不发送，只存入指纹
                    if initial:
                        continue

                    # 发送消息到 Discord
                    payload = {
                        "username": "TTC Service Alert",
                        "avatar_url": "https://upload.wikimedia.org/wikipedia/en/thumb/8/8e/TTC.svg/1200px-TTC.svg.png",
                        "embeds": [{
                            "title": f"🚨 {header}",
                            "description": desc,
                            "color": 14297372,  # TTC Red
                            "footer": {
                                "text": f"Sent at {time.strftime('%Y-%m-%d %H:%M:%S')}"
                            }
                        }]
                    }
                    
                    res = requests.post(WEBHOOK_URL, json=payload)
                    if res.status_code == 204:
                        print(f"[{time.strftime('%H:%M:%S')}] Success: {header}")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] Webhook Error: {res.status_code}")

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error: {e}")

# --- 主程序启动 ---
print("Connecting to TTC servers...")

# 1. 初始扫描：记录当前所有警报，但不推送
check_alerts(initial=True)

# 2. 发送启动通知
try:
    startup_msg = {
        "username": "TTC Tracker System",
        "content": "✅ **TTC Tracker is now ON and monitoring alerts.*"
    }
    requests.post(WEBHOOK_URL, json=startup_msg)
    print("TTC Tracker is ON. Startup notification sent.")
except:
    print("Failed to send startup notification.")

print("Monitoring for new alerts...")

# 3. 循环监听
while True:
    check_alerts(initial=False)
    time.sleep(CHECK_INTERVAL)