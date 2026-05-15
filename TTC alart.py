import requests
import time
import os
import re
from google.transit import gtfs_realtime_pb2
from bs4 import BeautifulSoup

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "seen_ids.txt"

# 备用的 GO Transit 警报聚合页面
GO_URL = "https://www.gotransit.com/en/service-updates/service-alerts"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.gotransit.com/"
}
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

def send_to_discord(agency, route_info, desc_text, status):
    if not WEBHOOK_URL: return
    color = get_embed_color(agency, route_info + desc_text)
    
    payload = {
        "username": f"{agency} Tracker",
        "embeds": [{
            "title": f"{'🚨' if status == 'alert' else '✅'} {agency} | {route_info}",
            "description": (desc_text[:1500] + '...') if len(desc_text) > 1500 else desc_text,
            "color": color if status == "alert" else 5763719,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    }
    requests.post(WEBHOOK_URL, json=payload, timeout=15)

def check_ttc():
    alerts = {}
    try:
        r = requests.get("https://bustime.ttc.ca/gtfsrt/alerts", timeout=20)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(r.content)
        for entity in feed.entity:
            if entity.HasField('alert'):
                # 优化标题：线路编号 + 标题
                rid = entity.alert.informed_entity[0].route_id if entity.alert.informed_entity else ""
                h = entity.alert.header_text.translation[0].text if entity.alert.header_text.translation else ""
                d = entity.alert.description_text.translation[0].text if entity.alert.description_text.translation else ""
                alerts[f"TTC:{rid} {h}".strip()] = d.strip()
        print(f"TTC: Found {len(alerts)} alerts.")
    except Exception as e: print(f"TTC Error: {e}")
    return alerts

def check_go_web():
    alerts = {}
    try:
        # 使用 Session 保持状态，增加通过率
        session = requests.Session()
        r = session.get(GO_URL, headers=HEADERS, timeout=30)
        
        if r.status_code != 200:
            print(f"GO Transit Web Access Failed: HTTP {r.status_code}")
            return alerts

        soup = BeautifulSoup(r.text, 'html.parser')
        # GO 页面结构经常变化，这里使用更通用的选择器：查找所有包含警报关键字的 div
        cards = soup.select('div[class*="alert"], div[class*="ServiceAlert"], section[class*="update"]')
        
        for card in cards:
            title_elem = card.find(['h3', 'h4', 'span'], class_=re.compile(r'title|name|header', re.I))
            if title_elem:
                title = title_elem.get_text().strip()
                desc = card.get_text(separator=" ").strip()
                if title and len(title) > 3:
                    alerts[f"GO Transit:{title[:80]}"] = desc
        
        # 如果还是抓不到，尝试匹配所有加粗文本作为标题 (兜底方案)
        if not alerts:
            for bold in soup.find_all('strong'):
                txt = bold.get_text().strip()
                if len(txt) > 5 and any(kw in txt.lower() for kw in ['line', 'bus', 'train', 'delay']):
                    alerts[f"GO Transit:{txt[:80]}"] = txt

        print(f"GO Transit: Found {len(alerts)} alerts.")
    except Exception as e: print(f"GO Transit Error: {e}")
    return alerts

def main():
    old_alerts = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "|||" in line:
                    k, v = line.strip().split("|||", 1)
                    old_alerts[k] = v

    curr_ttc = check_ttc()
    curr_go = check_go_web()
    curr_all = {**curr_ttc, **curr_go}

    # 发送新警报
    for k, v in curr_all.items():
        if k not in old_alerts:
            agency, info = k.split(":", 1)
            send_to_discord(agency, info, v, "alert")

    # 发送恢复 (仅当该机构当前有成功抓取到数据时才对比，防止误报)
    if curr_ttc:
        for k, v in old_alerts.items():
            if k.startswith("TTC:") and k not in curr_ttc:
                send_to_discord("TTC", k.split(":", 1)[1], v, "recovery")

    if curr_go:
        for k, v in old_alerts.items():
            if k.startswith("GO Transit:") and k not in curr_go:
                send_to_discord("GO Transit", k.split(":", 1)[1], v, "recovery")

    # 保存，同时保留抓取失败机构的旧数据
    final_save = curr_all.copy()
    if not curr_ttc:
        for k, v in old_alerts.items():
            if k.startswith("TTC:"): final_save[k] = v
    if not curr_go:
        for k, v in old_alerts.items():
            if k.startswith("GO Transit:"): final_save[k] = v

    with open(DB_FILE, "w", encoding="utf-8") as f:
        for k, v in final_save.items():
            f.write(f"{k}|||{v}\n")

if __name__ == "__main__":
    main()
