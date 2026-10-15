#!/usr/bin/env python3
"""把 brand-days 事件迁移到指定的日历（需要 adb + USB 调试）。

为什么需要它
────────────
vivo 日历导入 ics 时会默认选中"本地日历"，而且导入界面不暴露任何可以
预置目标日历的参数（IcsEventInfoActivity 只注册了 VIEW + text/calendar）。
结果是事件全部落进 Local calendar，和个人日程混在一起。

好消息是不用重新导入：事件在系统日历数据库里就是一条记录，
改 calendar_id 字段即可搬家，时间、提醒、内容都不受影响。

用法
────
    # 先看有哪些日历，拿到目标日历的 id 或名字
    python tools/move_to_calendar.py --list

    # 把 brand-days 事件搬到名字为「优惠提醒」的日历
    python tools/move_to_calendar.py --to 优惠提醒

    # 按 id 指定
    python tools/move_to_calendar.py --to 8

    # 只统计，不实际修改
    python tools/move_to_calendar.py --to 优惠提醒 --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# brand-days 生成的事件的标题前缀，用来识别"我们的事件"
TITLE_PREFIXES = ("今日优惠", "明天（")


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
        p = subprocess.run([adb, "devices"], capture_output=True, timeout=30)
        devs = [l.split()[0] for l in p.stdout.decode().splitlines()[1:]
                if l.strip().endswith("device")]
        if not devs:
            print("没有已连接的设备。插上数据线并在手机上允许 USB 调试。",
                  file=sys.stderr)
            raise SystemExit(2)
        self.serial = devs[0]

    def sh(self, cmd: str, timeout: int = 120) -> tuple[str, str]:
        p = subprocess.run([self.adb, "shell", cmd],
                           capture_output=True, timeout=timeout)
        return (p.stdout.decode("utf-8", "replace").strip(),
                p.stderr.decode("utf-8", "replace").strip())

    def rows(self, uri: str, projection: str | None = None) -> list[dict]:
        """按字段名解析 content query 输出。

        注意：NULL 字段会被省略、列顺序不固定，所以只能按字段名取，不能按位置取。
        """
        cmd = f"content query --uri {uri}"
        if projection:
            cmd += f" --projection {projection}"
        out, _ = self.sh(cmd)
        res = []
        for line in out.splitlines():
            if not line.strip().startswith("Row:"):
                continue
            body = line.split(" ", 1)[1] if " " in line else ""
            res.append(dict(re.findall(r"(\w+)=(.*?)(?=,\s\w+=|$)", body)))
        return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", default=None)
    ap.add_argument("--list", action="store_true", help="列出日历后退出")
    ap.add_argument("--to", default=None, help="目标日历的名字或 id")
    ap.add_argument("--dry-run", action="store_true", help="只统计不修改")
    args = ap.parse_args(argv)

    ph = Phone(find_adb(args.adb))
    cals = ph.rows("content://com.android.calendar/calendars",
                   "_id:calendar_displayName:account_name")
    name_of = {c.get("_id"): (c.get("calendar_displayName") or "").strip()
               for c in cals}

    events = ph.rows("content://com.android.calendar/events",
                     "_id:title:calendar_id")
    mine = [e for e in events
            if (e.get("title") or "").startswith(TITLE_PREFIXES)]

    print(f"设备: {ph.serial}")
    print(f"=== 手机上的日历（{len(cals)} 个）===")
    for c in cals:
        cid = c.get("_id")
        n_all = sum(1 for e in events if e.get("calendar_id") == cid)
        n_mine = sum(1 for e in mine if e.get("calendar_id") == cid)
        tag = f"  ← brand-days {n_mine} 条" if n_mine else ""
        print(f"  id={cid:<4} {name_of.get(cid,'?'):<18} 共 {n_all:>4} 条{tag}")

    if args.list:
        return 0

    if not args.to:
        print()
        print("请用 --to 指定目标日历（名字或 id）。")
        return 1

    # 解析目标日历
    if args.to.isdigit():
        target_id = args.to
        if target_id not in name_of:
            print(f"\n❌ 没有 id={target_id} 的日历。")
            return 1
    else:
        matches = [cid for cid, nm in name_of.items() if nm == args.to.strip()]
        if not matches:
            print(f"\n❌ 没找到名为「{args.to}」的日历。先用 --list 看看有哪些。")
            return 1
        target_id = matches[0]

    target_name = name_of[target_id]
    print()
    print(f"=== 目标日历：「{target_name}」(id={target_id}) ===")
    print(f"  brand-days 事件共 {len(mine)} 条")

    dist = Counter(e.get("calendar_id") for e in mine)
    for cid, n in dist.most_common():
        mark = "（已在目标日历，跳过）" if cid == target_id else "→ 待迁移"
        print(f"    从 id={cid} ({name_of.get(cid,'?')}): {n} 条 {mark}")

    todo = [e for e in mine if e.get("calendar_id") != target_id]
    if not todo:
        print()
        print("✅ 所有 brand-days 事件都已在目标日历里，无需迁移。")
        return 0

    if args.dry_run:
        print()
        print(f"[dry-run] 将迁移 {len(todo)} 条，未实际修改。")
        return 0

    print()
    print(f"迁移中（{len(todo)} 条）……")
    ok = fail = 0
    errors: list[str] = []
    for e in todo:
        eid = e.get("_id")
        if not eid:
            continue
        _, err = ph.sh(f'content update --uri content://com.android.calendar/events '
                       f'--bind calendar_id:i:{target_id} --where "_id={eid}"')
        if "Error" in err:
            fail += 1
            if len(errors) < 3:
                errors.append(err[:160])
        else:
            ok += 1

    print(f"  成功 {ok} 条，失败 {fail} 条")
    for e in errors:
        print("   错误:", e)

    # 复核
    after = ph.rows("content://com.android.calendar/events", "_id:title:calendar_id")
    mine_after = [e for e in after
                  if (e.get("title") or "").startswith(TITLE_PREFIXES)]
    still = [e for e in mine_after if e.get("calendar_id") != target_id]
    print()
    if not still:
        print(f"✅ 全部 {len(mine_after)} 条已迁入「{target_name}」。")
    else:
        print(f"⚠️ 仍有 {len(still)} 条未迁移。")
    print()
    print("迁移后的分布：")
    for cid, n in Counter(e.get("calendar_id") for e in after).most_common():
        nb = sum(1 for e in mine_after if e.get("calendar_id") == cid)
        print(f"  id={cid} ({name_of.get(cid,'?'):<18}) 共 {n:>4} 条"
              f"，其中 brand-days {nb} 条")
    return 0 if not still else 1


if __name__ == "__main__":
    raise SystemExit(main())
