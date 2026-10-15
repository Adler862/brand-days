#!/usr/bin/env python3
"""验证手机能否订阅线上 ics（需要 adb + 已开启 USB 调试）。

与 verify_on_phone.py 的区别：
  verify_on_phone.py  检查"本地文件导入后，手机上是否正确"
  verify_subscribe.py 检查"手机从 CDN 取回来的文件，是否还能被正确处理"

为什么必须单独验证：CDN 可能改写换行（实测 jsDelivr 分发的是 LF 版本，
而生成器本地产出 CRLF），客户端能否解析只有真机能答。
另外手机的网络环境与电脑不同，能否访问 CDN 本身就是个独立问题。

用法：
    python tools/verify_subscribe.py
    python tools/verify_subscribe.py --url https://cdn.jsdelivr.net/gh/用户/仓库@main/deals.ics
    python tools/verify_subscribe.py --open      # 顺带让手机日历打开它，触发真实导入
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_URL = "https://cdn.jsdelivr.net/gh/Adler862/brand-days@main/deals.ics"
REMOTE_PATH = "/sdcard/Download/brand-days-remote.ics"


def find_adb(explicit: str | None) -> str:
    import os
    if explicit:
        return explicit
    env = os.environ.get("ADB")
    if env and Path(env).exists():
        return env
    found = shutil.which("adb")
    if found:
        return found
    for c in (Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
              Path("D:/Android/Sdk/platform-tools/adb.exe")):
        if c.exists():
            return str(c)
    print("找不到 adb，请用 --adb 指定。", file=sys.stderr)
    raise SystemExit(2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", default=None)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--open", action="store_true",
                    help="下载后让手机日历打开该文件，触发真实导入")
    args = ap.parse_args(argv)

    adb = find_adb(args.adb)
    r = subprocess.run([adb, "devices"], capture_output=True, timeout=30)
    if not any(l.strip().endswith("device")
               for l in r.stdout.decode().splitlines()[1:]):
        print("没有已连接的设备。", file=sys.stderr)
        return 2

    def sh(cmd: str, timeout: int = 120) -> str:
        p = subprocess.run([adb, "shell", cmd], capture_output=True, timeout=timeout)
        return p.stdout.decode("utf-8", "replace").strip()

    host = re.sub(r"^https?://", "", args.url).split("/")[0]
    print(f"订阅地址: {args.url}")
    print(f"CDN 主机: {host}")
    print()

    print("=== 1) 手机能否访问该主机（手机网络 ≠ 电脑网络）===")
    ping = sh(f"ping -c 2 -W 3 {host} 2>&1 | tail -2")
    print(" ", ping or "(ping 无输出，可能被 ICMP 策略拦，不代表不通)")

    print()
    print("=== 2) 手机下载 ics ===")
    sh(f"rm -f {REMOTE_PATH}")
    out = sh(f"curl -sS -L -o {REMOTE_PATH} "
             f"-w 'HTTP=%{{http_code}} size=%{{size_download}} time=%{{time_total}}s' "
             f"{args.url} 2>&1")
    print(" ", out or "(curl 无输出)")
    if "HTTP=200" not in out:
        print("  [FAIL] 手机没能成功下载。若手机无 curl，可手动在浏览器打开该地址验证。")
        return 1

    print()
    print("=== 3) 下载到的文件换行形态（关键）===")
    ls = sh(f"ls -l {REMOTE_PATH}")
    print(" ", ls)
    n_cr = sh(f"grep -c $'\\r' {REMOTE_PATH} 2>/dev/null")
    n_line = sh(f"wc -l < {REMOTE_PATH} 2>/dev/null")
    n_ev = sh(f"grep -c 'BEGIN:VEVENT' {REMOTE_PATH} 2>/dev/null")
    print(f"  含 CR 的行数: {n_cr}")
    print(f"  行数        : {n_line}")
    print(f"  VEVENT 数量 : {n_ev}")
    try:
        cr, ln = int(n_cr), int(n_line)
        style = "CRLF（符合 RFC 5545）" if cr >= ln - 1 else "LF（CDN 归一化过）"
    except ValueError:
        style = "无法判断"
    print(f"  → {style}")

    # 下载回来的内容是否仍然是结构完整的 ics
    print()
    print("=== 4) 结构完整性（下载后是否还能被解析）===")
    for k in ("BEGIN:VCALENDAR", "END:VCALENDAR", "BEGIN:VTIMEZONE", "BEGIN:VALARM"):
        print(f"  含 {k:18}: {sh(f'grep -c \"{k}\" {REMOTE_PATH} 2>/dev/null')}")

    if args.open:
        print()
        print("=== 5) 让手机日历打开它（真实导入路径）===")
        before = sh("content query --uri content://com.android.calendar/events "
                    "| grep -c '^Row:'")
        print("  导入前事件数:", before)
        p = subprocess.run([adb, "shell", "am", "start",
                            "-a", "android.intent.action.VIEW",
                            "-d", f"file://{REMOTE_PATH}", "-t", "text/calendar"],
                           capture_output=True, timeout=60)
        msg = (p.stdout.decode("utf-8", "replace") +
               p.stderr.decode("utf-8", "replace")).strip()
        print(" ", msg[:200] or "(已发出 intent)")
        time.sleep(6)
        top = sh("dumpsys activity activities | grep topResumedActivity | head -1")
        print("  当前前台:", top)
        print()
        print("  → 若前台是日历的导入页面，请在手机上确认导入。")
        print("    导入完成后跑 python tools/verify_on_phone.py 比对结果。")
    else:
        print()
        print("提示：加 --open 可让手机日历直接打开该文件，走真实的导入路径。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
