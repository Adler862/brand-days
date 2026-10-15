#!/usr/bin/env python3
"""把 deals.ics 刷新到手机的【专属日历】里（需要 adb + USB 调试）。

为什么需要这个工具
──────────────────
手机自带日历（尤其国产 ROM）通常只能【导入】ics，不能【订阅】ics，
所以数据不会自动更新。而且导入时会丢弃事件的 UID，导致：
    * 重复导入 → 不会去重，只会堆重复事件（实测：35 条变 70 条）
    * 事件默认落进系统"本地日历" → 和用户自己的日程混在一起，
      想清理旧的只能在一堆个人日程里逐条挑

本工具解决这两点：
    1. 只清空【专属日历】里的事件，绝不碰用户的个人日程
    2. 清空 + 重新导入 = 一条命令

配合 window_days: 365 使用，一年通常只需要跑 0~2 次。

用法
────
    python tools/refresh_on_phone.py --list          # 列出手机上的日历
    python tools/refresh_on_phone.py --clear         # 只清空专属日历
    python tools/refresh_on_phone.py                 # 清空 + 提示导入
    python tools/refresh_on_phone.py --push FILE     # 顺便把 ics 推到手机
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
REMOTE_ICS = "/sdcard/Download/brand-days.ics"


def find_adb(explicit: str | None) -> str:
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


class Phone:
    def __init__(self, adb: str):
        self.adb = adb

    def sh(self, cmd: str, timeout: int = 120) -> str:
        p = subprocess.run([self.adb, "shell", cmd],
                           capture_output=True, timeout=timeout)
        return p.stdout.decode("utf-8", "replace").strip()

    def rows(self, uri: str, projection: str | None = None) -> list[dict]:
        """按字段名解析 content query 输出。

        注意：输出里 NULL 字段会被省略，所以不能按位置取字段，只能按名字。
        """
        cmd = f"content query --uri {uri}"
        if projection:
            cmd += f" --projection {projection}"
        out = self.sh(cmd)
        rows = []
        for line in out.splitlines():
            if not line.strip().startswith("Row:"):
                continue
            body = line.split(" ", 1)[1] if " " in line else ""
            rows.append(dict(re.findall(r"(\w+)=(.*?)(?=,\s\w+=|$)", body)))
        return rows

    def require_device(self) -> None:
        p = subprocess.run([self.adb, "devices"], capture_output=True, timeout=30)
        devs = [l.split()[0] for l in p.stdout.decode().splitlines()[1:]
                if l.strip().endswith("device")]
        if not devs:
            print("没有已连接的设备。插上数据线并在手机上允许 USB 调试。",
                  file=sys.stderr)
            raise SystemExit(2)
        self.serial = devs[0]


def load_cfg() -> dict:
    import yaml
    with (ROOT / "config.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_calendar(ph: Phone, name: str) -> dict | None:
    for c in ph.rows("content://com.android.calendar/calendars",
                     "_id:calendar_displayName:account_name:visible"):
        if (c.get("calendar_displayName") or "").strip() == name.strip():
            return c
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", default=None)
    ap.add_argument("--calendar", default=None, help="覆盖 config 里的专属日历名")
    ap.add_argument("--list", action="store_true", help="列出手机上的日历后退出")
    ap.add_argument("--clear", action="store_true", help="只清空，不提示导入")
    ap.add_argument("--push", metavar="ICS", nargs="?", const=str(ROOT / "deals.ics"),
                    help="把 ics 推到手机 Download 目录")
    args = ap.parse_args(argv)

    cfg = load_cfg()
    target_name = args.calendar or cfg.get("phone_calendar_name", "优惠提醒")
    ph = Phone(find_adb(args.adb))
    ph.require_device()

    cals = ph.rows("content://com.android.calendar/calendars",
                   "_id:calendar_displayName:account_name")
    print(f"=== 手机上的日历（{len(cals)} 个）===")
    for c in cals:
        mark = "  ← 专属日历" if (c.get("calendar_displayName") or "").strip() == target_name.strip() else ""
        print(f"  id={c.get('_id','?'):<4} {c.get('calendar_displayName','?'):<20}"
              f" {c.get('account_name','')}{mark}")

    if args.list:
        return 0

    target = find_calendar(ph, target_name)
    if not target:
        print()
        print(f"❌ 没找到名为「{target_name}」的日历。")
        print()
        print("请在手机上先建一个专属日历，步骤：")
        print("  打开日历 App → 左上角菜单/侧栏 → 管理日历（或「日历账户」）")
        print(f"  → 新建本地日历 → 名称填「{target_name}」")
        print()
        print("建好后再跑一次本命令。也可以用 --calendar 指定别的名字。")
        print()
        print("⚠️ 不要跳过这一步。没有专属日历的话，事件会落进你的个人日历，")
        print("   以后清理旧事件时只能在一堆个人日程里逐条挑。")
        return 1

    cid = target["_id"]
    print()
    print(f"专属日历: 「{target_name}」 id={cid}")

    # --- 统计并清空 ---
    events = ph.rows("content://com.android.calendar/events",
                     "_id:title:calendar_id")
    mine = [e for e in events if e.get("calendar_id") == cid]
    print(f"该日历现有事件: {len(mine)} 条")

    if mine:
        print("清空中……")
        ok = 0
        for e in mine:
            eid = e.get("_id")
            if not eid:
                continue
            ph.sh(f'content delete --uri content://com.android.calendar/events '
                  f'--where "_id={eid}"')
            ph.sh(f'content delete --uri content://com.android.calendar/reminders '
                  f'--where "event_id={eid}"')
            ok += 1
        after = [e for e in ph.rows("content://com.android.calendar/events",
                                    "_id:calendar_id")
                 if e.get("calendar_id") == cid]
        print(f"  已删除 {ok} 条，剩余 {len(after)} 条"
              f" {'✅' if not after else '⚠️'}")
    else:
        print("  （无需清理）")

    # --- 推送 ics ---
    if args.push:
        src = Path(args.push)
        if not src.exists():
            print(f"⚠️ 找不到 {src}，跳过推送。先跑 python gen.py")
        else:
            p = subprocess.run([ph.adb, "push", str(src), REMOTE_ICS],
                               capture_output=True, timeout=180)
            okpush = p.returncode == 0
            print(f"ics 推送: {'✅' if okpush else '❌'} "
                  f"{src.name} ({src.stat().st_size} 字节) -> {REMOTE_ICS}")
            if not okpush:
                print("  ", p.stderr.decode("utf-8", "replace")[:200])

    if not args.clear:
        print()
        print("=== 接下来在手机上操作 ===")
        print(f"  打开文件管理器 → Download → 点 brand-days.ics → 导入到「{target_name}」")
        print()
        print("  导入后可用下面的命令核对：")
        print("    python tools/verify_on_phone.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
