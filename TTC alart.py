import requests
import time
import os
import re
from google.transit import gtfs_realtime_pb2
from bs4 import BeautifulSoup

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "seen_ids.txt"

# 网页爬取配置 (GO Transit)
GO_URL = "https://www.gotransit.com/en/service-updates/service-alerts"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"}

# ============================================

def get_embed_color(agency, text):
    text = text.lower()
    if agency == "TTC":
        if "line 1" in text: return 16766720
        if "line 2" in text: return 3066993
        return 14297372
    if agency == "GO Transit":
        if "lakeshore" in text: return 18791
        if "kitchener" in text: return 3447003
        return 5763719
    return 3447003

def send_to_discord(agency, title_text, desc_text, status):
    if not WEBHOOK_URL: return
    color = get_embed_color(agency, title_text + desc_text)
    
    payload = {
        "username": f"{agency} Tracker",
        "embeds": [{
            "title": f"{'🚨' if status == 'alert' else '✅'} {agency} | {title_text[:200]}",
            "description": f"{desc_text[:2000]}" if status == "alert" else "This issue has been resolved.",
            "color": color if status == "alert" else 5763719,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    }
    requests.post(WEBHOOK_URL, json=payload, timeout=10)

def check_ttc():
    alerts = {}
    try:
        r = requests.get("https://bustime.ttc.ca/gtfsrt/alerts", timeout=20)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(r.content)
        for entity in feed.entity:
            if entity.HasField('alert'):
                h = entity.alert.header_text.translation[0].text
                d = entity.alert.description_text.translation[0].text
                alerts[f"TTC:{h.strip()}"] = d.strip()
        print("Successfully synced TTC")
    except Exception as e: print(f"TTC Error: {e}")
    return alerts

def check_go_web():
    alerts = {}
    try:
        # 直接爬取网页内容
        r = requests.get(GO_URL, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 根据 GO Transit 官网结构寻找警报卡片 (可能需要根据官网变动微调选择器)
        # 这里的选择器尝试抓取包含警报标题的元素
        items = soup.find_all(class_=re.compile("service-alert", re.I))
        
        for item in items:
            title = item.get_text(separator=" ").strip()
            if title:
                # 网页爬虫通常很难拿到详细描述，我们将标题作为 ID
                alerts[f"GO Transit:{title[:100]}"] = title
        
        print(f"Successfully synced GO Transit (Web) - Found {len(alerts)} alerts")
    except Exception as e:
        print(f"GO Transit Web Error: {e}")
    return alerts

def main():
    # 读取旧数据
    old_alerts = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "|||" in line:
                    k, v = line.strip().split("|||", 1)
                    old_alerts[k] = v

    # 获取新数据
    current_alerts = {}
    current_alerts.update(check_ttc())
    current_alerts.update(check_go_web())

    # 比较发送
    for k, v in current_alerts.items():
        if k not in old_alerts:
            agency, title = k.split(":", 1)
            send_to_discord(agency, title, v, "alert")

    for k, v in old_alerts.items():
        if k not in current_alerts and k.split(":")[0] in ["TTC", "GO Transit"]:
            agency, title = k.split(":", 1)
            send_to_discord(agency, title, v, "recovery")

    # 保存
    with open(DB_FILE, "w", encoding="utf-8") as f:
        for k, v in current_alerts.items():
            f.write(f"{k}|||{v}\n")

if __name__ == "__main__":
    main()
