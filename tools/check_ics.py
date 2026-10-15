"""校验 deals.ics 是否符合纯日历方案的全部技术要求"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ICS = Path(r"D:\DSH_workspace\repo\brand-days\deals.ics")
raw = ICS.read_bytes()
text = raw.decode("utf-8")

print("=== 文件基本信息 ===")
print("路径:", ICS)
print("字节:", len(raw))
print("行数:", len(text.splitlines()))

# --- 1) 结构自检 ---
print()
print("=== 结构自检 ===")
checks = {
    "有 VCALENDAR 包裹": text.startswith("BEGIN:VCALENDAR") and text.rstrip().endswith("END:VCALENDAR"),
    "内嵌 VTIMEZONE": "BEGIN:VTIMEZONE" in text,
    "VTIMEZONE 在第一个 VEVENT 之前": text.find("BEGIN:VTIMEZONE") < text.find("BEGIN:VEVENT"),
    "VTIMEZONE 声明 Asia/Shanghai": "TZID:Asia/Shanghai" in text,
    "事件引用 TZID=Asia/Shanghai": "TZID=Asia/Shanghai" in text,
    "含 TZOFFSETFROM/TO": "TZOFFSETFROM" in text and "TZOFFSETTO" in text,
    "已删除库自动生成的 COMMENT": "COMMENT:This timezone only works" not in text,
    "含 VALARM": "BEGIN:VALARM" in text,
    "VALARM 有 ACTION:DISPLAY": "ACTION:DISPLAY" in text,
    "含全天事件 VALUE=DATE": "DTSTART;VALUE=DATE" in text,
    "确认时间为 +0800": "TZOFFSETTO:+0800" in text,
}
for k, v in checks.items():
    print(("  [OK]   " if v else "  [FAIL] ") + k)

# --- 2) 行折叠合规（按字节算，汉字占 3 字节）---
print()
print("=== 行折叠合规性（RFC 5545 要求每行 <=75 字节，折叠续行以空格开头）===")
bad = []
for ln in text.splitlines():
    if len(ln.encode("utf-8")) > 75:
        bad.append(ln)
print(f"  超长行数: {len(bad)}", "  [OK]" if not bad else "  [FAIL]")
for ln in bad[:5]:
    print("    ", len(ln.encode("utf-8")), ln[:60])

# --- 3) 事件清点 ---
print()
print("=== 事件清点 ===")
vevents = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S)
nudges = [v for v in vevents if "-nudge-" in v]
digests = [v for v in vevents if "-digest-" in v]
alarms = text.count("BEGIN:VALARM")
print(f"  VEVENT 总数      : {len(vevents)}")
print(f"  定时提醒(nudge)  : {len(nudges)}  （应每条带 1 个 VALARM）")
print(f"  全天摘要(digest) : {len(digests)}")
print(f"  VALARM 总数      : {alarms}")
print(f"  nudge 与 VALARM 匹配: {'[OK]' if alarms == len(nudges) else '[FAIL]'}")

# --- 4) 定时提醒的时间必须是 20:00 ---
print()
print("=== 定时提醒时刻（应全部为本地 20:00）===")
starts = re.findall(r"DTSTART;TZID=Asia/Shanghai:(\d{8}T\d{6})", text)
times = {s[9:] for s in starts}
print("  出现的时刻:", sorted(times))
print("  全部为 200000:", "[OK]" if times == {"200000"} else "[FAIL] " + str(sorted(times)))

# --- 5) UID 稳定且唯一 ---
print()
print("=== UID 检查 ===")
uids = re.findall(r"UID:([^\r\n]+)", text)
print(f"  UID 数量: {len(uids)}  唯一: {len(set(uids))}")
print("  无重复:", "[OK]" if len(uids) == len(set(uids)) else "[FAIL]")
dup = [u for u in set(uids) if uids.count(u) > 1]
if dup:
    print("  重复项:", dup[:5])

# --- 6) 抽样打印 ---
print()
print("=== 抽样：今天的 nudge 与 digest ===")
def show(kind, datepart):
    for v in vevents:
        if f"-{kind}-" in v and datepart in v:
            blob = ("BEGIN:VEVENT" + v + "END:VEVENT")
            for ln in blob.splitlines():
                if ln.startswith(("UID:", "SUMMARY:", "DTSTART", "DESCRIPTION:", "ACTION", "TRIGGER")):
                    print("   ", ln)
            print("    ---")

show("digest", "20261015")
show("nudge", "20261015")

print()
print("=== 抽样：每月8号那条（11月8日应为 2 条 core）===")
show("digest", "20261108")

# --- 7) 确定性检查：同日重复生成应逐字节一致 ---
print()
print("=== 确定性 ===")
print("  DTSTAMP 固定值检查（不应含当前时间的动态值）:")
dstamps = set(re.findall(r"DTSTAMP:([^\r\n]+)", text))
print("   DTSTAMP 取值集合:", sorted(dstamps), "[OK]" if len(dstamps) == 1 else "[FAIL 不唯一]")
