"""
DIY 装机价格监控 - 采集器
数据源：中关村在线报价库（公开页面，低频访问）
存储：SQLite（data/prices.db）

设计要点：
1. 只保留「当代主流」型号——ZOL 报价库混有大量停产老货，必须过滤
2. 清洗型号名——ZOL 的 title 属性把描述文字和型号粘在一起
3. 每次重跑先删当天该分类数据，保证幂等
"""
import urllib.request, http.cookiejar, gzip, re, os, sys, time, random, sqlite3, json
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data", "prices.db")
LOG = os.path.join(BASE, "data", "collect.log")
STATS = {"pages_ok": 0, "pages_fail": 0}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# ---------------------------------------------------------------- 品类规则
# require : 型号名必须匹配（正则），用于筛掉停产/非主流型号
# price   : 中端价位区间，筛掉顶配与入门
# brands  : 一线品牌白名单
CATEGORIES = {
    "CPU": {
        "path": "cpu", "pages": 4, "price": (700, 3200),
        "require": r"(酷睿\s*(?:Ultra\s*)?i[57][\s-]?(?:1[2-9]|2[0-9])\d{3}"
                   r"|Ultra\s*[579]\s*\d{3}"
                   r"|Ryzen\s*[57]\s*[5-9]\d{3}"
                   r"|锐龙\s*[57]\s*[5-9]\d{3})",
        "brands": ["Intel", "AMD"],
    },
    "显卡": {
        "path": "vga", "pages": 4, "price": (1500, 6500),
        "require": r"(RTX\s*(?:40[6-9]0|50[5-9]0)|RX\s*(?:7[6-9]\d{2}|9\d{3}))",
        "brands": ["华硕", "微星", "技嘉", "七彩虹", "影驰", "索泰", "蓝宝石",
                   "铭瑄", "耕升", "映众", "撼讯", "瀚铠", "盈通", "迪兰", "万丽"],
    },
    "主板": {
        "path": "motherboard", "pages": 4, "price": (600, 2800),
        "require": r"(?:^|[^0-9A-Z])(B[6-8]\d{2}|Z[6-9]\d{2}|X[6-8]\d{2}|A6[0-9]0)",
        "brands": ["华硕", "微星", "技嘉", "华擎", "七彩虹", "铭瑄", "映泰", "昂达"],
    },
    "内存": {
        "path": "memory", "pages": 3, "price": (250, 2500),
        "require": r"(DDR5|DDR4[^0-9]{0,6}(?:3[2-9]\d{2}|4\d{3}))",
        "brands": ["金士顿", "芝奇", "海盗船", "威刚", "光威", "金百达", "英睿达",
                   "科赋", "十铨", "阿斯加特", "宏想", "玖合", "美商海盗船"],
    },
    "固态硬盘": {
        "path": "solid_state_drive", "pages": 5, "price": (200, 2000),
        "require": r"(NVMe|M\.2|PCIe|PCle)",
        "brands": ["三星", "西部数据", "铠侠", "致态", "英睿达", "希捷", "闪迪",
                   "金士顿", "影驰", "威刚", "浦科特", "长江存储", "雷克沙", "梵想",
                   "光威", "金泰克", "惠普", "联想", "七彩虹", "台电", "美光"],
    },
    "机械硬盘": {
        "path": "hard_drives", "pages": 3, "price": (350, 2500),
        "require": r"[48]\s*TB",
        "brands": ["西部数据", "希捷", "东芝"],
    },
    "电源": {
        "path": "power", "pages": 4, "price": (300, 1500),
        "require": r"(\d{3,4}\s*[Ww]|金牌|铜牌|白牌|全模组|额定)",
        "min_watt": 550,
        "brands": ["海韵", "振华", "航嘉", "长城", "酷冷", "微星", "华硕", "安钛克",
                   "鑫谷", "爱国者", "美商海盗船", "全汉", "先马", "骨伽",
                   "九州风神", "利民", "追风者", "金河田"],
    },
    "显示器": {
        "path": "lcd", "pages": 3, "price": (700, 4500),
        "brands": ["戴尔", "AOC", "华硕", "微星", "LG", "三星", "HKC", "泰坦军团",
                   "飞利浦", "优派", "明基", "联想", "技嘉", "宏碁"],
    },
}

# 型号名里的描述起始词——从这里截断，得到干净型号
DESC_CUT = re.compile(
    r"(\d+相|\d+核心|\d+线程|支持|智能|全新|散热|高刷|电竞|游戏|办公|专业|"
    r"内置|配备|采用|搭载|认证|供电|频率|转速|静音|模组|额定|接口|"
    r"：|，|。|、|\s{2,})")

CPU_MODEL = re.compile(
    r"(酷睿\s*(?:Ultra\s*)?[iI][3579][\s-]?\d{4,5}[A-Z]{0,3}"
    r"|Ultra\s*[579]\s*\d{3}"
    r"|(?:AMD\s*)?(?:Ryzen|锐龙)\s*[3579]\s*\d{4}[A-Z0-9]{0,3})")

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def fetch(url, referer="https://detail.zol.com.cn/", retry=3):
    for attempt in range(retry):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": referer,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            })
            r = opener.open(req, timeout=30)
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            txt = raw.decode("gbk", errors="ignore")
            if len(txt) < 5000:
                raise ValueError("response too short, likely rate-limited")
            STATS["pages_ok"] += 1
            return txt
        except Exception as e:
            if attempt == retry - 1:
                STATS["pages_fail"] += 1
                print(f"    x 放弃 {url} ({type(e).__name__})")
                return None
            time.sleep(8 + attempt * 6)
    return None


def parse_items(html):
    """提取 (原始标题, 价格, 详情链接)
    注意：固态硬盘等品类是「系列」维度，价格表现为区间 359-1799，取最低配价"""
    out = []
    hits = list(re.finditer(r'<h3><a href="([^"]+)"\s+title="([^"]+)"', html))
    for i, m in enumerate(hits):
        url, title = m.group(1).strip(), m.group(2).strip()
        if url.startswith("/"):
            url = "https://detail.zol.com.cn" + url
        end = hits[i + 1].start() if i + 1 < len(hits) else min(len(html), m.end() + 3000)
        seg = html[m.end():end]
        pm = re.search(r'price-type">([\d.]+)(?:-[\d.]+)?<', seg)
        if not pm:
            continue
        price = float(pm.group(1))
        if price <= 0:
            continue
        out.append((title, price, url))
    return out


def clean_model(name):
    """把「型号+描述」的粘连标题切成干净型号"""
    m = CPU_MODEL.search(name)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    cut = DESC_CUT.search(name)
    if cut and cut.start() >= 4:
        name = name[:cut.start()]
    name = re.sub(r"\s+", " ", name).strip()
    return name[:44]


def pick_brand(model, whitelist, cat=None):
    for b in whitelist:
        if b.lower() in model.lower():
            return b
    if cat == "CPU":
        if re.search(r"酷睿|Ultra|[iI][3579]", model):
            return "Intel"
        if re.search(r"Ryzen|锐龙", model):
            return "AMD"
    return None


def watt_ok(model, minw):
    ws = [int(x) for x in re.findall(r"(\d{3,4})\s*[Ww]", model)]
    return any(w >= minw for w in ws) if ws else True  # 型号里没写功率则不误杀


def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS price_snapshot (
            snap_date TEXT NOT NULL,
            category  TEXT NOT NULL,
            brand     TEXT,
            model     TEXT NOT NULL,
            price     REAL NOT NULL,
            url       TEXT,
            PRIMARY KEY (snap_date, category, model)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_cat ON price_snapshot(category, snap_date)")
    con.commit()
    return con


def main():
    today = date.today().isoformat()
    con = init_db()
    summary = {}

    for cat, cfg in CATEGORIES.items():
        lo, hi = cfg["price"]
        req = re.compile(cfg["require"]) if cfg.get("require") else None
        collected = {}
        print(f"[{cat}] 抓取中...")
        for page in range(1, cfg["pages"] + 1):
            url = f"https://detail.zol.com.cn/{cfg['path']}/" if page == 1 \
                else f"https://detail.zol.com.cn/{cfg['path']}/{page}.html"
            html = fetch(url, referer=f"https://detail.zol.com.cn/{cfg['path']}/")
            if not html:
                continue
            items = parse_items(html)
            kept = 0
            for raw, price, link in items:
                model = clean_model(raw)
                if not (lo <= price <= hi):
                    continue
                if req and not req.search(model):
                    continue
                if "min_watt" in cfg and not watt_ok(model, cfg["min_watt"]):
                    continue
                brand = pick_brand(model, cfg["brands"], cat)
                if not brand:
                    continue
                if model not in collected:
                    collected[model] = (brand, price, link)
                    kept += 1
            print(f"    第{page}页: 解析 {len(items)} 条, 入池 {kept} 条")
            time.sleep(random.uniform(3.5, 6.5))

        con.execute("DELETE FROM price_snapshot WHERE snap_date=? AND category=?", (today, cat))
        rows = [(today, cat, b, m, p, u) for m, (b, p, u) in collected.items()]
        con.executemany("INSERT OR REPLACE INTO price_snapshot VALUES (?,?,?,?,?,?)", rows)
        con.commit()
        summary[cat] = len(rows)
        print(f"  -> {cat}: 入库 {len(rows)} 款\n")

    con.close()
    print("完成：", json.dumps(summary, ensure_ascii=False))

    total = sum(summary.values())
    line = (f"{today} 入库{total}款 {summary} "
            f"页面成功{STATS['pages_ok']}/失败{STATS['pages_fail']}")
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {line}\n")
    except Exception:
        pass

    try:
        sys.path.insert(0, BASE)
        import build_board
        build_board.build()
    except Exception as e:
        print("生成面板数据失败:", e)


if __name__ == "__main__":
    main()
