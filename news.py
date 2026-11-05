"""
行情资讯采集：抓科技媒体 RSS，按 DIY 硬件关键词筛选
输出 data/news.json / data/news.js
"""
import urllib.request, gzip, re, os, json, html
from datetime import datetime
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

FEEDS = [
    {"name": "IT之家", "url": "https://www.ithome.com/rss/"},
]

# 命中任意一个即视为相关
KEYS = ["显卡", "CPU", "处理器", "内存", "DDR5", "DDR4", "固态", "SSD", "硬盘",
        "主板", "电源", "显示器", "机箱", "散热", "存储", "显存", "GPU", "锐龙",
        "酷睿", "英伟达", "AMD", "英特尔", "三星电子", "海力士", "长江存储",
        "涨价", "降价", "缺货", "产能", "停产", "出货", "装机", "DIY"]


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        "Accept-Encoding": "gzip, deflate"})
    r = urllib.request.urlopen(req, timeout=25)
    raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="ignore")


def clean(s, n=110):
    s = re.sub(r"<[^>]+>", "", html.unescape(s or "")).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:n] + ("…" if len(s) > n else "")


def main():
    out = []
    for f in FEEDS:
        try:
            xml = fetch(f["url"])
        except Exception as e:
            print(f"  x {f['name']}: {type(e).__name__}")
            continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            print(f"  x {f['name']}: RSS 解析失败")
            continue
        n = 0
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = item.findtext("description") or ""
            pub = (item.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            if not any(k.lower() in (title + desc).lower() for k in KEYS):
                continue
            out.append({"source": f["name"], "title": title, "url": link,
                        "summary": clean(desc), "time": pub})
            n += 1
        print(f"  {f['name']}: {n} 条相关")

    # 去重 + 按时间倒序（RSS 通常已倒序，这里只去重保序）
    seen, uniq = set(), []
    for a in out:
        if a["title"] in seen:
            continue
        seen.add(a["title"])
        uniq.append(a)

    data = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"), "items": uniq[:40]}
    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)
    with open(os.path.join(BASE, "data", "news.json"), "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
    with open(os.path.join(BASE, "data", "news.js"), "w", encoding="utf-8") as fp:
        fp.write("window.NEWS = ")
        json.dump(data, fp, ensure_ascii=False)
        fp.write(";")
    print(f"news.js 已生成：{len(uniq)} 条")


if __name__ == "__main__":
    main()
