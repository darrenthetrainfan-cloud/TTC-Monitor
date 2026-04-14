import requests
import time
import os
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
# 你的 Discord Webhook 链接
WEBHOOK_URL = "https://discord.com/api/webhooks/1493694754821505126/74HdOARTigkDHORW2psEDUzYp89IX25Hq0jqn6KZPu1sV1t2-G2n5R1E3rxCP91WDRuC"
# TTC 数据源
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"
# 记忆文件命名
DB_FILE = "seen_ids.txt"
# ============================================

def load_seen_alerts():
    """从文件读取已发送过的警报指纹"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return set(f.read().splitlines())
    return set()

def save_seen_alerts(seen_set):
    """将新的警报指纹保存到文件"""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(seen_set))

def check_alerts():
    seen_alerts = load_seen_alerts()
    new_alerts_found = False
    
    try:
        response = requests.get(TTC_ALERTS_URL, timeout=15)
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        # 按时间倒序处理，确保新消息逻辑正确
        for entity in feed.entity:
            if entity.HasField('alert'):
                alert = entity.alert
                
                # 提取原始数据
                header = alert.header_text.translation[0].text if alert.header_text.translation else "TTC Alert"
                desc = alert.description_text.translation[0].text if alert.description_text.translation else "No details provided."
                
                # 生成指纹（用于去重）
                fingerprint = f"{header}|{desc}"
                
                if fingerprint not in seen_alerts:
                    seen_alerts.add(fingerprint)
                    new_alerts_found = True
                    
                    # --- 优化显示逻辑 ---
                    # 1. 颜色分类：地铁线路用红色，其他（巴士/电车）用蓝色
                    subway_keywords = ["Line 1", "Line 2", "Line 4", "Subway", "Yonge-University", "Bloor-Danforth"]
                    embed_color = 14297372 if any(k in header or k in desc for k in subway_keywords) else 3447003
                    
                    # 2. 处理标题截断：如果标题太长或不全，我们在标题加个提示，重点看描述
                    short_header = (header[:97] + '...') if len(header) > 100 else header

                    payload = {
                        "username": "TTC Tracker",
                        "avatar_url": "https://upload.wikimedia.org/wikipedia/en/thumb/8/8e/TTC.svg/1200px-TTC.svg.png",
                        "embeds": [{
                            "title": f"🚨 {short_header}",
                            "description": f"**Detailed Information:**\n{desc}",
                            "color
