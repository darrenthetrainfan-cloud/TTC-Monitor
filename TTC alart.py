import requests
import time
import os
import re
from google.transit import gtfs_realtime_pb2
from bs4 import BeautifulSoup

# ... (配置区域保持不变) ...

def get_embed_color(agency, text):
    text = text.lower()
    if agency == "TTC":
        if "line 1" in text or "yous" in text: return 16766720
        if "line 2" in text or "bloor" in text: return 3066993
        return 14297372
    if agency == "GO Transit":
        if "lakeshore" in text: return 18791
        if "kitchener" in text: return 3447003
        return 5763719
    return 3447003

def send_to_discord(agency, route_info, desc_text, status):
    if not WEBHOOK_URL: return
    color = get_embed_color(agency, route_info + desc_text)
    
    # 构造标题：[线路编号/名称]
    display_title = f"{'🚨' if status == 'alert' else '✅'} {agency} | {route_info}"
    
    payload = {
        "username": f"{agency} Tracker",
        "embeds": [{
            "title": display_title,
            "description": desc_text if status == "alert" else "此线路运行已恢复正常。",
            "color": color if status == "alert" else 5763719,
            "footer": {"text": f"数据来源: {agency} Real-time Feed"},
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
                # 尝试获取线路编号
                route_id = ""
                if entity.alert.informed_entity:
                    route_id = entity.alert.informed_entity[0].route_id
                
                h_raw = entity.alert.header_text.translation[0].text
                d_raw = entity.alert.description_text.translation[0].text
                
                # 组合标题：例如 "504 King" 或 "Line 1 (YUS)"
                route_display = f"{route_id} {h_raw}".strip()
                alerts[f"TTC:{route_display}"] = d_raw.strip()
        print("Successfully synced TTC")
    except Exception as e: print(f"TTC Error: {e}")
    return alerts

def check_go_web():
    alerts = {}
    try:
        r = requests.get(GO_URL, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, 'html.parser')
        items = soup.find_all(class_=re.compile("service-alert", re.I))
        
        for item in items:
            raw_text = item.get_text(separator=" ").strip()
            # 使用正则提取线路名，例如 "Lakeshore West", "Kitchener" 等
            # GO 的网页结构较杂，这里取前 50 个字符作为线路标识
            clean_title = raw_text.split('\n')[0].strip()[:60]
            if clean_title:
                alerts[f"GO Transit:{clean_title}"] = raw_text
        
        print(f"Successfully synced GO Transit (Web)")
    except Exception as e: print(f"GO Transit Web Error: {e}")
    return alerts

# ... (main 函数与之前保持一致) ...
