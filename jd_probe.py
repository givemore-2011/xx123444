"""
京东联盟 API 连通性自检
读 config.local.json，验证密钥是否可用、哪些接口有权限。
不打印密钥本身，只打印结果。
"""
import json, os, sys, hashlib, urllib.request, urllib.parse
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "config.local.json")
GATEWAY = "https://api.jd.com/routerjson"

ERRORS = {
    "1000": "系统错误",
    "1001": "签名错误（app_secret 不对，或签名算法不匹配）",
    "1002": "缺少必要参数",
    "1003": "app_key 不存在或已停用",
    "1004": "接口不存在",
    "1005": "无接口权限（该 method 未申请或未审核通过）",
    "1006": "调用超限（QPS 或日额度用完）",
    "1007": "IP 不在白名单（后台需配置调用来源 IP，或设为不限）",
    "1008": "access_token 无效",
    "1009": "参数格式错误",
}


def load_cfg():
    if not os.path.exists(CFG):
        print("x 找不到 config.local.json")
        return None
    cfg = json.load(open(CFG, encoding="utf-8"))
    key = (cfg.get("jd_app_key") or "").strip()
    sec = (cfg.get("jd_app_secret") or "").strip()
    if not key:
        print("x 配置还没填：jd_app_key 为空")
        return None
    if not sec:
        print("! jd_app_secret 为空，本次用空密钥签名——只能验证网关认不认这个 key，不能验证签名")
    print(f"key 长度 {len(key)}，secret 长度 {len(sec)}（只报长度，不打印内容）")
    return key, sec


def sign(params, secret):
    raw = "".join(k + str(params[k]) for k in sorted(params))
    return hashlib.md5((secret + raw + secret).encode("utf-8")).hexdigest().upper()


def call(method, biz, key, secret, timeout=20):
    p = {
        "method": method,
        "app_key": key,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "1.0",
        "sign_method": "md5",
        "360buy_param_json": json.dumps(biz, ensure_ascii=False, separators=(",", ":")),
    }
    p["sign"] = sign(p, secret)
    data = urllib.parse.urlencode(p).encode("utf-8")
    req = urllib.request.Request(GATEWAY, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": "diy-monitor/1.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def explain(resp):
    """把响应翻译成一句人话"""
    try:
        d = json.loads(resp)
    except Exception:
        return "返回不是 JSON，可能是网关层拦截"
    if "error_response" in d:
        e = d["error_response"]
        code = str(e.get("code", ""))
        desc = e.get("zh_desc") or e.get("en_desc") or ""
        return f"失败 [{code}] {ERRORS.get(code, '')} | 原文: {desc[:120]}"
    for k, v in d.items():
        if k.endswith("_responce") or k.endswith("_response"):
            if isinstance(v, dict) and v.get("code") == "0":
                return "成功 code=0"
            return f"响应 code={v.get('code') if isinstance(v,dict) else '?'} 原文: {resp[:200]}"
    return f"未知结构: {resp[:200]}"


TESTS = [
    ("jd.union.open.goods.query",
     {"goodsReqDTO": {"keyword": "RTX5060", "pageIndex": 1, "pageSize": 5}}),
    ("jd.union.open.goods.promotiongoodsinfo.query",
     {"skuIds": "100012043978"}),
    ("jd.union.open.category.goods.get",
     {"req": {"parentId": 0, "grade": 0}}),
]


def main():
    c = load_cfg()
    if not c:
        return 1
    key, sec = c
    print("-" * 56)
    for method, biz in TESTS:
        print(f"\n[{method}]")
        try:
            resp = call(method, biz, key, sec)
            print("  " + explain(resp))
            if len(resp) < 600:
                print("  原始: " + resp.replace("\n", " ")[:400])
            else:
                print("  原始前400字: " + resp[:400].replace("\n", " "))
        except Exception as e:
            print(f"  请求异常: {type(e).__name__}: {e}")
    print("\n" + "-" * 56)
    print("把这里的输出发我就行（不含密钥）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
