import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.transit import gtfs_realtime_pb2

# ================= 配置区域 =================
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
TTC_ALERTS_URL = "https://bustime.ttc.ca/gtfsrt/alerts"
DB_FILE = "seen_ids.txt"  # 内容改为 JSON，文件名保持不变，兼容现有的 workflow
# 首次运行（没有数据库或旧格式）时是否把当前所有警报都发出去。默认只建立基线，避免刷屏
SEND_ON_FIRST_RUN = os.environ.get("SEND_ON_FIRST_RUN", "0") == "1"
# ============================================

# Discord 限制
MAX_TITLE = 256
MAX_DESC = 4000          # 官方 4096，留余量
MAX_EMBEDS_PER_MSG = 10
MAX_CHARS_PER_MSG = 5500  # 官方每条消息所有 embed 合计 6000

# 颜色
RED, BLUE, YELLOW, GREEN, PURPLE, ORANGE, GREY = (
    14297372, 3447003, 16766720, 3066993, 10181046, 16750848, 8421504
)
RESOLVED_GREEN = 5763719
UPDATE_BLUE = 5793266

# 按顺序匹配，用 \b 避免 "line 1" 误匹配 "line 10"
COLOR_RULES = [
    (BLUE,   r"elevator|escalator|wheel-trans|accessib"),
    (YELLOW, r"\bline 1\b|yonge-university"),
    (GREEN,  r"\bline 2\b|bloor-danforth"),
    (PURPLE, r"\bline 4\b|sheppard"),
    (ORANGE, r"\bline 5\b|eglinton"),
    (GREY,   r"\bline 6\b|finch west"),
]

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"})
session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=1, status_forcelist=(500, 502, 503, 504)
)))


# ---------- 工具函数 ----------
def truncate(text, limit):
    return text if len(text) <= limit else text[: limit - 1] + "…"


def get_color(header, desc):
    """先看标题，再看全文，防止描述里顺带提到别的线路导致颜色错误"""
    for text in (header.lower(), f"{header} {desc}".lower()):
        for color, pattern in COLOR_RULES:
            if re.search(pattern, text):
                return color
    return RED


def pick_text(translated):
    """优先取英文，否则取第一条"""
    if not translated.translation:
        return ""
    for t in translated.translation:
        if t.language.lower().startswith("en"):
            return t.text
    return translated.translation[0].text


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def is_active(alert, now):
    """没有 active_period 视为一直有效；有的话必须当前处于某个时间段内"""
    if not alert.active_period:
        return True
    for p in alert.active_period:
        start = p.start or 0
        end = p.end or float("inf")
        if start <= now <= end:
            return True
    return False


def short_header(raw):
    return raw.split(":")[0].strip() if ":" in raw else raw


# ---------- 数据库 ----------
def load_db():
    """返回 dict；文件不存在或是旧格式时返回 None（视为首次运行）"""
    if not os.path.exists(DB_FILE):
        return None
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError) as e:
        print(f"Database unreadable or legacy format, treating as first run: {e}")
        return None


def save_db(db):
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, DB_FILE)  # 原子替换，避免写到一半崩溃损坏数据库


# ---------- 抓取 ----------
def fetch_alerts():
    """返回 {key: {"header", "desc", "url"}}；失败抛异常，空 feed 返回 None 表示可疑"""
    r = session.get(TTC_ALERTS_URL, timeout=15)
    r.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(r.content)

    if not feed.entity:
        return None

    now = int(time.time())
    alerts = {}
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        a = entity.alert
        if not is_active(a, now):
            continue

        header = clean(pick_text(a.header_text).replace("|||", " ")) or "TTC Alert"
        desc = clean(pick_text(a.description_text)) or "No details."
        url = pick_text(a.url) if a.HasField("url") else ""

        # 标题重复时不要互相覆盖
        key, n = header, 2
        while key in alerts:
            key = f"{header} #{n}"
            n += 1
        alerts[key] = {"header": header, "desc": desc, "url": url}
    return alerts


# ---------- Discord ----------
def build_embed(kind, item):
    header, desc, url = item["header"], item["desc"], item.get("url", "")
    name = short_header(header)

    if kind == "alert":
        title = f"🚨 {name}"
        color = get_color(header, desc)
        body = f"**New Alert Details:**\n{desc}"
    elif kind == "update":
        title = f"🔄 Updated: {name}"
        color = UPDATE_BLUE
        body = f"**Alert details changed:**\n{desc}"
    else:
        title = f"✅ Resolved: {name}"
        color = RESOLVED_GREEN
        body = f"**This issue has been cleared.**\n~~{truncate(desc, MAX_DESC - 80)}~~"

    embed = {
        "title": truncate(title, MAX_TITLE),
        "description": truncate(body, MAX_DESC),
        "color": color,
        "footer": {"text": "TTC Alerts"},
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if url and kind != "recovery":
        embed["url"] = url
    return embed


def post_discord(embeds):
    # 不传 avatar_url，使用 Webhook 设置里手动上传的头像
    payload = {"username": "TTC Tracker", "embeds": embeds}
    for _ in range(3):
        try:
            r = session.post(WEBHOOK_URL, json=payload, timeout=10)
        except requests.RequestException as e:
            print(f"Discord request failed: {e}")
            time.sleep(2)
            continue
        if r.status_code == 429:  # 被限流，按服务器要求等待
            try:
                wait = float(r.json().get("retry_after", 2))
            except Exception:
                wait = 2
            time.sleep(min(wait, 30))
            continue
        if r.ok:
            return True
        print(f"Discord HTTP {r.status_code}: {r.text[:200]}")
        return False
    return False


def chunk_items(items):
    """按 Discord 限制（条数 + 总字数）把 embed 分批，减少请求数"""
    batch, chars = [], 0
    for it in items:
        size = len(it["embed"]["title"]) + len(it["embed"]["description"])
        if batch and (len(batch) >= MAX_EMBEDS_PER_MSG or chars + size > MAX_CHARS_PER_MSG):
            yield batch
            batch, chars = [], 0
        batch.append(it)
        chars += size
    if batch:
        yield batch


# ---------- 主逻辑 ----------
def check_alerts():
    if not WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK is not set!")
        return False

    old_db = load_db()
    first_run = old_db is None
    old = old_db or {}

    try:
        current = fetch_alerts()
    except Exception as e:
        print(f"Fetch Error: {e}")
        return False

    if current is None:
        print("Feed returned no entities at all; skipping to avoid false 'resolved' spam.")
        return True

    # 把当前状态整理成数据库格式
    cur_db = {k: {"header": v["header"], "desc": v["desc"]} for k, v in current.items()}

    # 首次运行：只建立基线
    if first_run and not SEND_ON_FIRST_RUN:
        save_db(cur_db)
        print(f"First run: baseline saved ({len(cur_db)} alerts), nothing sent.")
        return True

    # 对比
    pending = []
    for key, item in current.items():
        if key not in old:
            pending.append({"kind": "alert", "key": key, "item": item})
        elif old[key].get("desc") != item["desc"]:
            pending.append({"kind": "update", "key": key, "item": item})
    for key, item in old.items():
        if key not in current:
            pending.append({"kind": "recovery", "key": key, "item": item})

    if not pending:
        print("No changes detected.")
        return True

    for p in pending:
        p["embed"] = build_embed(p["kind"], p["item"])

    # 只有发送成功的才写入数据库，失败的下次运行会自动重试
    new_db = dict(old)
    ok_count = 0
    for i, batch in enumerate(chunk_items(pending)):
        if i:
            time.sleep(1)
        if post_discord([p["embed"] for p in batch]):
            for p in batch:
                if p["kind"] == "recovery":
                    new_db.pop(p["key"], None)
                else:
                    new_db[p["key"]] = cur_db[p["key"]]
                print(f"Sent {p['kind']}: {short_header(p['item']['header'])}")
            ok_count += len(batch)
        else:
            print(f"Batch of {len(batch)} failed; will retry next run.")

    if ok_count:
        save_db(new_db)
        print("Memory updated.")
    return ok_count == len(pending)


if __name__ == "__main__":
    sys.exit(0 if check_alerts() else 1)
