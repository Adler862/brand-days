#!/usr/bin/env python3
"""手机上验证 brand-days 是否被正确导入（需要 adb + 已开启 USB 调试）。

它做的事：读取 Android 系统日历数据库里【落在 ics 覆盖范围内】的事件，
与 deals.ics 里的事件逐条比对时间，确认：
  1. 事件数量一致
  2. 时间逐条一致（这是时区是否偏移 8 小时的直接证据）
  3. nudge 事件确实落在 20:00

为什么需要这个工具：ics 生成正确 ≠ 手机上正确。
客户端的时区解析、全天事件存储方式、提醒入库行为都只能看真实数据。

用法：
    python tools/verify_on_phone.py
    python tools/verify_on_phone.py --adb "C:\\path\\to\\adb.exe"
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

try:
    from icalendar import Calendar
except ImportError:
    print("需要 icalendar：pip install -r requirements.txt", file=sys.stderr)
    raise SystemExit(2)

CN = timezone(timedelta(hours=8))
WEEK = "一二三四五六日"


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
              Path("D:/Android/Sdk/platform-tools/adb.exe"),
              Path(os.environ.get("USERPROFILE", "")) / "platform-tools/adb.exe"):
        if c.exists():
            return str(c)
    print("找不到 adb。请用 --adb 指定路径，或设置 ADB 环境变量。", file=sys.stderr)
    raise SystemExit(2)


def query(adb: str, uri: str, projection: str | None = None) -> list[dict]:
    """查询 calendar provider。

    注意：不要随便指定 projection。CalendarContract 的列名大小写敏感，
    写错一个列名（例如把 allDay 写成 allday），provider 会【静默返回 0 行】，
    不报任何错，很难排查。
    因此这里默认不指定投影，拿全部列；投影只用于确有把握的场景。
    """
    cmd = [adb, "shell", "content", "query", "--uri", uri]
    if projection:
        cmd += ["--projection", projection]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    rows = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip().startswith("Row:"):
            continue
        body = line.split(" ", 1)[1] if " " in line else ""
        rows.append(dict(re.findall(r"(\w+)=(.*?)(?=,\s\w+=|$)", body)))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", default=None)
    ap.add_argument("--ics", default=str(ROOT / "deals.ics"))
    args = ap.parse_args(argv)

    adb = find_adb(args.adb)
    ics_path = Path(args.ics)
    if not ics_path.exists():
        print(f"找不到 {ics_path}，先跑 python gen.py", file=sys.stderr)
        return 2

    # --- 设备 ---
    r = subprocess.run([adb, "devices"], capture_output=True, timeout=30)
    devs = [l.split()[0] for l in r.stdout.decode().splitlines()[1:]
            if l.strip().endswith("device")]
    if not devs:
        print("没有已连接的设备。请插上数据线并在手机上允许 USB 调试。", file=sys.stderr)
        return 2
    model = subprocess.run([adb, "shell", "getprop ro.product.model"],
                           capture_output=True).stdout.decode().strip()
    print(f"设备: {devs[0]}  ({model})")

    # --- ics 里的事件 ---
    cal = Calendar.from_ical(ics_path.read_bytes())
    exp: list[tuple[str, datetime]] = []
    for ev in cal.walk("VEVENT"):
        dt = ev.get("DTSTART").dt
        if isinstance(dt, datetime):
            exp.append(("nudge", dt.astimezone(CN).replace(tzinfo=None)))
        else:
            # 全天事件：Android 日历把它存成当天 00:00 或按提醒时刻
            exp.append(("digest", datetime(dt.year, dt.month, dt.day)))
    exp.sort(key=lambda x: x[1])
    lo = exp[0][1].date() - timedelta(days=1)
    hi = exp[-1][1].date() + timedelta(days=2)

    # --- 手机上的事件（只取 ics 覆盖的范围，避开用户自己的日程）---
    # 不指定 projection：拿到全部列，判断全天事件时更稳
    ph_rows = query(adb, "content://com.android.calendar/events")
    ph: list[tuple[str, datetime, str]] = []
    for row in ph_rows:
        ts = row.get("dtstart", "")
        if not ts.isdigit():
            continue
        dt = datetime.fromtimestamp(int(ts) / 1000, CN).replace(tzinfo=None)
        if not (lo <= dt.date() <= hi):
            continue
        # allDay 列名大小写敏感；不同 ROM 可能不返回该列，
        # 此时退化为按“是否落在整点 00:00 或 08:00”判断
        allday = str(row.get("allDay", row.get("allday", "")))
        if allday == "1" or (dt.hour, dt.minute) in ((0, 0), (8, 0)):
            kind = "digest"
        else:
            kind = "nudge"
        ph.append((kind, dt, row.get("title", "")))
    ph.sort(key=lambda x: x[1])

    print(f"ics 事件: {len(exp)}   手机范围内事件: {len(ph)}")
    print()

    exp_c = {}
    for k, d in exp:
        exp_c.setdefault(k, []).append(d)
    ph_c = {}
    for k, d, _ in ph:
        ph_c.setdefault(k, []).append(d)

    ok = True
    for kind, label in (("nudge", "定时提醒"), ("digest", "全天摘要")):
        e = sorted(exp_c.get(kind, []))
        p = sorted(ph_c.get(kind, []))
        # 全天事件的时间点由客户端决定，因此只比数量，且允许 0 点或 8 点两种存法
        if kind == "digest":
            en = len(e)
            pn = len({d.date() for d in p})
            good = en == pn
            print(f"{label}: ics {en} 条 / 手机 {pn} 天  "
                  f"{'[OK]' if good else '[FAIL]'}")
            ok &= good
        else:
            good = e == p
            print(f"{label}: ics {len(e)} 条 / 手机 {len(p)} 条  "
                  f"{'[OK] 逐条时间一致' if good else '[FAIL]'}")
            if not good:
                print(f"   仅 ics 有: {[d.strftime('%m-%d %H:%M') for d in e if d not in p]}")
                print(f"   仅手机有: {[d.strftime('%m-%d %H:%M') for d in p if d not in e]}")
            ok &= good
            bad_hour = [d for d in p if (d.hour, d.minute) != (20, 0)]
            print(f"   非 20:00 的提醒: {len(bad_hour)} 条  "
                  f"{'[OK]' if not bad_hour else '[FAIL]'}")
            ok &= not bad_hour

    print()
    print("=== 逐条对照 ===")
    print(f"  {'类型':<8} {'ics':<18} {'手机':<18} {'星期'}")
    for (k1, d1), (k2, d2, _) in zip(exp, ph):
        mark = "  " if (k1 == k2 and d1.replace(hour=0, minute=0) ==
                       d2.replace(hour=0, minute=0) or (k1 == k2 and d1 == d2)) else "!!"
        print(f"  {mark}{k1:<6} {d1:%Y-%m-%d %H:%M}     {d2:%Y-%m-%d %H:%M}"
              f"     周{WEEK[d1.weekday()]}")

    print()
    if ok:
        print("✅ 手机上导入的事件与 ics 一致，时区无偏移。")
        print("   提醒是否真会弹通知，取决于客户端；可用 tools/make_test_ics.py 现场验证。")
        return 0
    print("⚠️ 存在不一致，见上文。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
