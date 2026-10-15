#!/usr/bin/env python3
"""生成用于手机端验证的通知测试日历。

目的：验证客户端是否真的尊重 ics 里的 VALARM（定时事件弹通知）。
不能等到晚上 20:00 碰运气 —— 这里的事件安排在导入后几分钟内触发。

用法：
    python tools/make_test_ics.py            # 默认 5 / 10 / 15 分钟后
    python tools/make_test_ics.py --after 2  # 改成 2 / 4 / 6 分钟后
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gen  # noqa: E402

from icalendar import Alarm, Calendar, Event  # noqa: E402


def alarm(summary: str, minutes_before: int = 0) -> Alarm:
    a = Alarm()
    a.add("action", "DISPLAY")
    a.add("description", summary)
    a.add("trigger", timedelta(minutes=-minutes_before))
    return a


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", type=int, default=5,
                    help="第一个测试事件的分钟数（默认 5）")
    ap.add_argument("--tz", default="Asia/Shanghai")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent
                                        / "deals-test.ics"))
    args = ap.parse_args(argv)

    tz = ZoneInfo(args.tz)
    now = datetime.now(tz).replace(second=0, microsecond=0)
    stamp = now.strftime("%Y%m%d%H%M")
    duration = 5

    cal = Calendar()
    cal.add("prodid", "-//brand-days//notification-test//CN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "brand-days 通知测试")
    cal.add("x-wr-timezone", args.tz)
    cal.add_component(gen.build_timezone(tz, now.year - 1, 2050))

    plan = [
        (args.after, 0, "测试1/3 准点提醒",
         "如果你看到这条通知，说明【定时事件 + VALARM】在你的手机上正常工作。\n"
         "这正是 brand-days 每晚 20:00 提醒所依赖的机制。"),
        (args.after * 2, 0, "测试2/3 提前 5 分钟",
         "VALARM 的 TRIGGER 支持提前量。若这条也弹了，说明提前量也被尊重。"),
        (args.after * 3, 5, "测试3/3 事件开始前 5 分钟",
         "这条的 TRIGGER 是 -PT5M（开始前 5 分钟）。若只有这条弹，"
         "说明客户端忽略 TRIGGER 取值、一律提前固定时间提醒。"),
    ]

    for minutes, before, title, body in plan:
        start = now + timedelta(minutes=minutes)
        ev = Event()
        ev.add("uid", f"brand-days-test-{stamp}-{minutes}@brand-days")
        ev.add("summary", title)
        ev.add("description", body)
        ev.add("dtstart", start)
        ev.add("dtend", start + timedelta(minutes=duration))
        ev.add("dtstamp", now)
        ev.add_component(alarm(title, before))
        cal.add_component(ev)

    # 全天事件对照：验证全天事件是否也会弹（预期：多数客户端不弹）
    allday = Event()
    allday.add("uid", f"brand-days-test-{stamp}-allday@brand-days")
    allday.add("summary", "对照：全天事件（多数客户端不给全天事件弹通知）")
    allday.add("description",
               "这条是全天事件。如果它弹了通知而上面三条定时事件没弹，"
               "说明你的客户端对方程式处理与预期相反。")
    allday.add("dtstart", now.date())
    allday.add("dtend", now.date() + timedelta(days=1))
    allday.add("dtstamp", now)
    allday.add("transp", "TRANSPARENT")
    cal.add_component(allday)

    raw = gen.strip_tz_comment(cal.to_ical())
    out = Path(args.out)
    out.write_bytes(raw)

    print(f"[OK] 已生成 {out}")
    print(f"     基准时间 {now:%Y-%m-%d %H:%M} ({args.tz})")
    for minutes, before, title, _ in plan:
        t = now + timedelta(minutes=minutes)
        tag = f"（提前 {before} 分钟触发）" if before else "（准点触发）"
        print(f"     {t:%H:%M}  {title} {tag}")
    print(f"     {now.date()}  对照：全天事件")
    print()
    print("导入手机日历后，等这几分钟，观察哪些弹了通知。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
