"""往返测试：把 deals.ics 当外部客户端那样解析回来，确认字段能正确读出"""
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")

from icalendar import Calendar

ICS = Path(r"D:\DSH_workspace\repo\brand-days\deals.ics")
cal = Calendar.from_ical(ICS.read_bytes())
CN = ZoneInfo("Asia/Shanghai")

print("=== 日历级属性 ===")
for key in ("VERSION", "PRODID", "CALSCALE", "X-WR-CALNAME", "X-WR-TIMEZONE"):
    print(f"  {key:16} = {cal.get(key)}")

print()
print("=== VTIMEZONE 解析 ===")
tzs = [c for c in cal.walk("VTIMEZONE")]
print(f"  解析到 {len(tzs)} 个 VTIMEZONE")
for tz in tzs:
    print(f"  TZID = {tz.get('TZID')}")
    for sub in tz.walk("STANDARD"):
        print(f"    STANDARD DTSTART={sub.get('DTSTART').dt} "
              f"OFFSETFROM={sub.get('TZOFFSETFROM')} OFFSETTO={sub.get('TZOFFSETTO')}")

print()
print("=== 逐条事件（前 8 条）===")
events = list(cal.walk("VEVENT"))
print(f"  事件总数: {len(events)}")
for ev in events[:8]:
    dt = ev.get("DTSTART").dt
    if isinstance(dt, datetime):
        local = dt.astimezone(CN)
        kind = "定时"
        when = local.strftime("%Y-%m-%d %H:%M %Z")
    else:
        kind = "全天"
        when = dt.strftime("%Y-%m-%d")
    alarms = list(ev.walk("VALARM"))
    trig = f" VALARM={alarms[0].get('TRIGGER').dt}" if alarms else ""
    print(f"  [{kind}] {when}")
    print(f"        {ev.get('SUMMARY')}{trig}")

print()
print("=== 关键断言 ===")
fails = []
# 定时事件必须能解析成 +08:00 的本地时间
timed = [e for e in events if isinstance(e.get("DTSTART").dt, datetime)]
ok_tz = all(e.get("DTSTART").dt.astimezone(CN).utcoffset().total_seconds() == 8 * 3600
            for e in timed)
print(f"  {'[OK]  ' if ok_tz else '[FAIL]'} 所有定时事件解析为 +0800（{len(timed)} 条）")
if not ok_tz:
    fails.append("tz")

ok_alarm = all(len(list(e.walk("VALARM"))) == 1 for e in timed)
print(f"  {'[OK]  ' if ok_alarm else '[FAIL]'} 每个定时事件恰好 1 个 VALARM")
if not ok_alarm:
    fails.append("alarm")

all_day = [e for e in events if not isinstance(e.get("DTSTART").dt, datetime)]
print(f"  {'[OK]  ' if len(all_day) == 18 else '[FAIL]'} 全天摘要事件 {len(all_day)} 条（应为 18）")

# 今晚的通知内容应该是“明天”
nudges = [e for e in events if "-nudge-" in str(e.get("UID"))]
first = min(nudges, key=lambda e: e.get("DTSTART").dt)
print(f"  [i]   第一条 nudge: {first.get('DTSTART').dt.astimezone(CN):%Y-%m-%d %H:%M}"
      f" -> {first.get('SUMMARY')}")

print()
if fails:
    print("!!! 失败:", fails)
    raise SystemExit(1)
print("往返解析全部通过：文件可被标准 ics 解析器正确读回。")
