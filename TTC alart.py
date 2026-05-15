import requests
import time
import os
import re
from google.transit import gtfs_realtime_pb2
from bs4 import BeautifulSoup

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
DB_FILE = "seen_ids.txt"

# GO Transit 官网警报页面
GO_URL = "https://www.gotransit.com/en/service-updates/service-alerts"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}
# ============================================

def get_embed_color(agency, text):
    text = text.lower()
    if agency == "TTC":
        if "line 1" in text: return 16766720  # Yellow
        if "line 2" in text: return 3066993   # Green
        return 14297372  # Red
    if agency == "GO Transit":
        if "lakeshore" in text: return 18791   # Dark Green
        if "kitchener" in text: return 3447003 # Light Blue
        return 5763719  # GO Green
    return 3447003

def send_to_discord(agency, route_info, desc_text, status):
    if not WEBHOOK_URL: return
    color = get_embed_color(agency, route_info + desc_text)
    
    # 限制描述长度，防止 Discord 报错
    clean_desc = (desc_text[:1800] + '...') if len(desc_text) > 1800 else desc_text
    
    payload = {
        "username": f"{agency} Tracker",
        "embeds": [{
            "title": f"{'🚨' if status == 'alert' else '✅'} {agency} | {route_info}",
            "description": clean_desc if status == "alert" else "Service on this route has returned to normal.",
            "color": color if status == "alert" else 5763719,
            "footer": {"text": f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}"},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }]
    }
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=15)
    except Exception as e:
        print(f"Discord POST Error: {e}")

def check_ttc():
    alerts = {}
    try:
        r = requests.get("https://bustime.ttc.ca/gtfsrt/alerts", timeout=20)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(r.content)
        
        count = 0
        for entity in feed.entity:
            if entity.HasField('alert'):
                # 提取线路编号 (Route ID)
                route_id = ""
                if entity.alert.informed_entity:
                    # 某些警报关联多个线路，我们取第一个
                    route_id = entity.alert.informed_entity[0].route_id
                
                # 获取标题和描述
                h = entity.alert.header_text.translation[0].text if entity.alert.header_text.translation else "Service Alert"
                d = entity.alert.description_text.translation[0].text if entity.alert.description_text.translation else ""
                
                # 构造显示标题：[编号] 名称
                route_display = f"{route_id} {h}".strip()
                alerts[f"TTC:{route_display}"] = d.strip()
                count += 1
        print(f"TTC: Found {count} active alerts.")
    except Exception as e:
        print(f"TTC Error: {e}")
    return alerts

def check_go_web():
    alerts = {}
    try:
        r = requests.get(GO_URL, headers=HEADERS, timeout=30)
        # 如果被拦截，打印状态码
        if r.status_code != 200:
            print(f"GO Transit Web Access Denied (HTTP {r.status_code})")
            return alerts

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 优化选择器：GO 官网现在的警报包装在特定的 section 或 div 中
        # 我们寻找包含 "alert" 关键字的所有卡片
        alert_cards = soup.find_all(["div", "section"], class_=re.compile(r"alert|update-item", re.I))
        
        for card in alert_cards:
            # 尝试抓取标题文本
            title_elem = card.find(["h3", "h4", "strong"])
            if not title_elem: continue
            
            title_text = title_elem.get_text().strip()
            # 获取完整文本作为描述
            full_text = card.get_text(separator=" ").strip()
            
            if title_text and len(title_text) > 3:
                # 过滤掉一些无关的导航文本
                if "view all" in title_text.lower(): continue
                alerts[f"GO Transit:{title_text[:100]}"] = full_text
        
        print(f"GO Transit: Found {len(alerts)} alerts via Web Scraping.")
    except Exception as e:
        print(f"GO Transit Web Error: {e}")
    return alerts

def main():
    # 1. 加载历史数据
    old_alerts = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "|||" in line:
                    parts = line.strip().split("|||", 1)
                    if len(parts) == 2: old_alerts[parts[0]] = parts[1]

    # 2. 获取实时数据
    current_alerts = {}
    ttc_data = check_ttc()
    go_data = check_go_web()
    current_alerts.update(ttc_data)
    current_alerts.update(go_data)

    # 3. 处理逻辑：对比并发送
    # A. 发送新发现的警报
    for k, v in current_alerts.items():
        if k not in old_alerts:
            agency, route = k.split(":", 1)
            send_to_discord(agency, route, v, "alert")
            print(f"New Alert Sent: {k}")

    # B. 处理恢复的警报
    # 注意：只有当该 Agency 成功获取到数据（非空）时，才对比删除的警报，防止接口挂掉导致误报全线恢复
    if ttc_data:
        for k, v in old_alerts.items():
            if k.startswith("TTC:") and k not in current_alerts:
                agency, route = k.split(":", 1)
                send_to_discord(agency, route, v, "recovery")
                print(f"Resolved: {k}")
                
    if go_data:
        for k, v in old_alerts.items():
            if k.startswith("GO Transit:") and k not in current_alerts:
                agency, route = k.split(":", 1)
                send_to_discord(agency, route, v, "recovery")
                print(f"Resolved: {k}")

    # 4. 保存当前状态为新的数据库
    with open(DB_FILE, "w", encoding="utf-8") as f:
        for k, v in current_alerts.items():
            # 合并：保留那些无法获取数据的机构的旧警报，更新已成功获取的
            f.write(f"{k}|||{v}\n")
        
        # 补丁：如果某个机构这次抓取失败了，保留它的旧警报在数据库里，不删除
        if not ttc_data:
            for k, v in old_alerts.items():
                if k.startswith("TTC:"): f.write(f"{k}|||{v}\n")
        if not go_data:
            for k, v in old_alerts.items():
                if k.startswith("GO Transit:"): f.write(f"{k}|||{v}\n")

if __name__ == "__main__":
    main()
