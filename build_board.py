"""
把 SQLite 快照汇总成面板用的 board.json
"""
import sqlite3, os, json, statistics
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data", "prices.db")
OUT = os.path.join(BASE, "data", "board.json")

CAT_ORDER = ["CPU", "显卡", "主板", "内存", "固态硬盘", "机械硬盘", "电源", "显示器"]


def build():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT snap_date FROM price_snapshot ORDER BY snap_date")]
    if not dates:
        print("数据库为空")
        return None
    latest = dates[-1]

    board = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
             "latest_date": latest, "dates": dates, "categories": {}}

    for cat in CAT_ORDER:
        rows = con.execute(
            "SELECT model, brand, price, url FROM price_snapshot "
            "WHERE category=? AND snap_date=? ORDER BY price",
            (cat, latest)).fetchall()
        if not rows:
            continue

        # 每个型号的上一期价格
        prev_map = {}
        if len(dates) > 1:
            for r in con.execute(
                    "SELECT model, price FROM price_snapshot "
                    "WHERE category=? AND snap_date=?", (cat, dates[-2])):
                prev_map[r["model"]] = r["price"]

        models = []
        for r in rows:
            p = r["price"]
            prev = prev_map.get(r["model"])
            chg = round((p - prev) / prev * 100, 1) if prev else None
            models.append({"model": r["model"], "brand": r["brand"], "price": p,
                           "prev": prev, "chg": chg, "url": r["url"]})

        prices = [m["price"] for m in models]
        # 分类均价时间序列
        series = []
        for d in dates:
            vals = [x[0] for x in con.execute(
                "SELECT price FROM price_snapshot WHERE category=? AND snap_date=?",
                (cat, d))]
            series.append({"date": d, "avg": round(sum(vals) / len(vals), 0) if vals else None,
                           "min": min(vals) if vals else None,
                           "max": max(vals) if vals else None,
                           "count": len(vals)})

        movers = [m for m in models if m["chg"] is not None]
        board["categories"][cat] = {
            "count": len(models),
            "min": min(prices), "max": max(prices),
            "avg": round(sum(prices) / len(prices)),
            "median": round(statistics.median(prices)),
            "models": models,
            "series": series,
            "drops": sorted(movers, key=lambda x: x["chg"])[:5],
            "rises": sorted(movers, key=lambda x: -x["chg"])[:5],
            "changed": len(movers),
        }

    con.close()

    # 整机参考水位：各类中位价相加，看市场整体量级，不是具体配置单
    CORE = ["CPU", "显卡", "主板", "内存", "固态硬盘", "电源"]
    med = {c: v["median"] for c, v in board["categories"].items()}
    board["overview"] = {
        "core": sum(med.get(c, 0) for c in CORE),
        "core_complete": all(c in med for c in CORE),
        "with_monitor": sum(med.get(c, 0) for c in CORE) + med.get("显示器", 0),
        "medians": med,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=1)
    # 同时输出 board.js，让 index.html 双击即可打开（file:// 下 fetch 会被拦）
    with open(os.path.join(BASE, "data", "board.js"), "w", encoding="utf-8") as f:
        f.write("window.BOARD = ")
        json.dump(board, f, ensure_ascii=False)
        f.write(";")
    total = sum(c["count"] for c in board["categories"].values())
    print(f"board.json 已生成: {len(board['categories'])} 个分类 / {total} 款 / {len(dates)} 天数据")
    return board


if __name__ == "__main__":
    build()
