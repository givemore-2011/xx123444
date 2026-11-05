"""
DIY 装机价格监控 - 统一入口

用法：
    python app.py              采集 + 生成 + 打开看板（默认）
    python app.py collect      只采集硬件价格
    python app.py news         只采集行情资讯
    python app.py build        只重新生成看板数据
    python app.py serve        起本地服务，可在手机上看（需 --lan）
    python app.py all          全流程但不自动打开浏览器
"""
import sys, os, argparse, threading, webbrowser, http.server, socketserver, time

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg):
    print(f"\n>>> {msg}", flush=True)


def cmd_collect():
    import collector
    collector.main()


def cmd_news():
    import news
    news.main()


def cmd_build():
    import build_board
    build_board.build()


def cmd_serve(port=8765, lan=False):
    host = "0.0.0.0" if lan else "127.0.0.1"
    url = f"http://127.0.0.1:{port}/index.html"

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    threading.Timer(0.9, lambda: webbrowser.open(url)).start()
    with socketserver.TCPServer((host, port), Handler) as httpd:
        print(f"看板地址：{url}")
        if lan:
            print("已开放局域网访问（同网段手机可用本机内网 IP 打开）")
        print("按 Ctrl+C 退出")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")


def cmd_publish():
    """生成可上传的纯静态目录 docs/，不含任何密钥（GitHub Pages 用 main 分支 /docs）"""
    import shutil
    pub = os.path.join(BASE, "docs")
    if os.path.isdir(pub):
        shutil.rmtree(pub)
    os.makedirs(os.path.join(pub, "data"), exist_ok=True)
    shutil.copy2(os.path.join(BASE, "index.html"), os.path.join(pub, "index.html"))
    for f in ("board.js", "news.js"):
        src = os.path.join(BASE, "data", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(pub, "data", f))

    # 硬性检查：绝不能把密钥带出去
    for root, _, files in os.walk(pub):
        for f in files:
            if f.endswith(".json") and "config" in f:
                raise SystemExit(f"中止：docs 目录里出现密钥文件 {root}/{f}")

    size = sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(pub) for f in fs) / 1024
    print(f"docs/ 已生成（{size:.0f} KB），不含密钥")


def cmd_push():
    """重新生成 docs 并推送到 GitHub Pages"""
    import subprocess
    from datetime import datetime
    cmd_publish()

    # 本机全局 git 配了 GitHub 加速规则（ghfast.top），它不支持 push，
    # 所以推送时用一个空的全局配置，让它直连 github.com
    empty_cfg = os.path.join(BASE, ".gitconfig-empty")
    if not os.path.exists(empty_cfg):
        open(empty_cfg, "w").close()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": empty_cfg}

    def run(*args, use_env=False):
        r = subprocess.run(args, cwd=BASE, capture_output=True, text=True,
                           encoding="utf-8", errors="ignore",
                           env=env if use_env else None)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if out:
            print("  " + out.splitlines()[-1][:200])
        return r.returncode

    run("git", "add", "-A")
    if run("git", "commit", "-m", f"更新行情数据 {datetime.now():%Y-%m-%d %H:%M}") != 0:
        print("  数据没有变化，跳过提交")
    if run("git", "push", use_env=True) != 0:
        print("推送失败：检查网络或 GitHub 凭据")
        return
    print("已推送，Pages 约 1 分钟后生效")


def cmd_all(open_after=False):
    t0 = time.time()
    log("1/3 采集硬件价格")
    cmd_collect()
    log("2/3 采集行情资讯")
    try:
        cmd_news()
    except Exception as e:
        print(f"资讯采集失败（不影响看板）：{e}")
    log("3/3 生成看板数据")
    cmd_build()
    print(f"\n全部完成，耗时 {time.time() - t0:.0f} 秒")
    if open_after:
        webbrowser.open(f"file:///{os.path.join(BASE, 'index.html').replace(os.sep, '/')}")


def main():
    ap = argparse.ArgumentParser(add_help=True, description="DIY 装机价格监控")
    ap.add_argument("cmd", nargs="?", default="run",
                    choices=["run", "collect", "news", "build", "serve", "all",
                             "publish", "push"])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true", help="允许局域网访问（手机看）")
    a = ap.parse_args()

    if a.cmd == "collect":
        cmd_collect()
    elif a.cmd == "news":
        cmd_news()
    elif a.cmd == "build":
        cmd_build()
    elif a.cmd == "serve":
        cmd_serve(a.port, a.lan)
    elif a.cmd == "publish":
        cmd_publish()
    elif a.cmd == "push":
        cmd_push()
    elif a.cmd == "all":
        cmd_all(False)
    else:
        cmd_all(True)


if __name__ == "__main__":
    main()
