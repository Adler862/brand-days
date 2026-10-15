#!/usr/bin/env python3
"""brand-days 自测：验证周期规则匹配、tier/confidence 过滤、生成确定性。

运行：python tools/test_gen.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import yaml  # noqa: E402

import gen  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAILED: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    if cond:
        print(f"  [OK]   {label}")
    else:
        print(f"  [FAIL] {label} {extra}")
        FAILED.append(label)


def load(name: str) -> list[dict]:
    with (ROOT / "data" / name).open(encoding="utf-8") as f:
        return yaml.safe_load(f) or []


print("=== 1. 周期规则匹配 ===")
# 2026-10-15 是周四；10-19 周一；10-20 周二；10-21 周三
cases = [
    ("kfc-crazy-thursday", date(2026, 10, 15), True, "周四"),
    ("kfc-crazy-thursday", date(2026, 10, 16), False, "周五"),
    ("kfc-crazy-thursday", date(2026, 10, 22), True, "下个周四"),
    ("mcdonalds-monday", date(2026, 10, 19), True, "周一"),
    ("mcdonalds-monday", date(2026, 10, 20), False, "周二"),
    ("dominoes-tue-thu", date(2026, 10, 20), True, "周二"),
    ("dominoes-tue-thu", date(2026, 10, 21), True, "周三"),
    ("dominoes-tue-thu", date(2026, 10, 22), True, "周四"),
    ("dominoes-tue-thu", date(2026, 10, 23), False, "周五"),
    ("haoxianglai-8th", date(2026, 11, 8), True, "每月8号"),
    ("haoxianglai-8th", date(2026, 11, 7), False, "每月7号不匹配"),
    ("haoxianglai-8th", date(2026, 12, 8), True, "下个月8号"),
    ("zhaoyiming-8th", date(2026, 12, 8), True, "每月8号"),
]

offers = {o["id"]: o for o in load("offers.yaml")}
for oid, day, expected, why in cases:
    got = gen.matches(offers[oid], day)
    check(f"{oid} @ {day} ({why}) -> {expected}", got == expected, f"实际 {got}")

print()
print("=== 2. start 日期生效边界 ===")
fake = {"id": "x", "brand": "X", "offer": "y",
        "recur": {"type": "weekly", "days": ["thu"]}, "start": "2026-11-01"}
check("start 之前不匹配", gen.matches(fake, date(2026, 10, 29)) is False)
check("start 当天匹配", gen.matches(fake, date(2026, 11, 5)) is True)

print()
print("=== 3. tier / confidence 过滤 ===")
all_offers = load("offers.yaml")
core = gen.is_calendar_eligible(offers["kfc-crazy-thursday"], ["core"])
ext = gen.is_calendar_eligible(offers["dominoes-tue-thu"], ["core"])
check("core+verified 进日历", core is True)
check("extended 不进日历（当只允许 core）", ext is False)
check("extended 在允许时进日历",
      gen.is_calendar_eligible(offers["dominoes-tue-thu"], ["core", "extended"]) is True)
unverified = dict(offers["kfc-crazy-thursday"], confidence="unverified")
check("unverified 永不进日历，即使 tier=core",
      gen.is_calendar_eligible(unverified, ["core"]) is False)

print()
print("=== 4. 生成确定性（同输入两次生成必须逐字节一致）===")
with (ROOT / "config.yaml").open(encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
a, sa = gen.build(cfg, all_offers, start=date(2026, 10, 15), window_days=30)
b, sb = gen.build(cfg, all_offers, start=date(2026, 10, 15), window_days=30)
check("两次生成字节一致", a == b, f"{len(a)} vs {len(b)}")

print()
print("=== 5. nudge 触发规则（这是最容易被误判的一节）===")
# 真正的不变量有两个方向：
#   a) 明天有 core 内容  -> 今晚必须有 nudge
#   b) 明天没有 core 内容 -> 今晚不该发 nudge（避免制造无意义的通知）
# 注意“有内容的日子”与“有 nudge 的日子”并不相等：
# 周四只有肯德基，而周五无 core 内容，所以周四当晚不发通知。
text = a.decode("utf-8")
content_days = {d for d, _ in sa["per_day"]}
window = [date(2026, 10, 15) + timedelta(days=i) for i in range(30)]

missing_nudge, spurious_nudge = [], []
for day in window:
    has_tomorrow = (day + timedelta(days=1)) in content_days
    has_nudge = f"-nudge-{day:%Y%m%d}" in text
    if has_tomorrow and not has_nudge:
        missing_nudge.append(str(day))
    if has_nudge and not has_tomorrow:
        spurious_nudge.append(str(day))

check("明天有内容的日子都有 nudge", not missing_nudge, f"缺失 {missing_nudge}")
check("明天无内容的日子不发 nudge", not spurious_nudge, f"多余 {spurious_nudge}")

# nudge 总数 = 存在“次日也有内容”的天数
expected_nudges = sum(1 for d in window if (d + timedelta(days=1)) in content_days)
check(f"nudge 总数 = {expected_nudges}",
      sa["events"] - len(content_days) == expected_nudges,
      f"实际 {sa['events'] - len(content_days)}")

print()
print("   说明：周四（只有肯德基）当晚不发通知，因为周五没有 core 优惠。")
print("   这是刻意行为——宁可不发，也不要每晚都发一条没有内容的通知。")

print()
print("=== 6. 跨年正确性（每月几号的规则最容易在跨年时出错）===")
cross, sc = gen.build(cfg, all_offers, start=date(2026, 12, 1), window_days=45)
ctext = cross.decode("utf-8")
check("12-08 生成了 2 条 core（好想来 + 赵一鸣）",
      "SUMMARY:今日优惠 2 条｜好想来、赵一鸣零食" in ctext)
check("跨年后的 2027-01-08 同样生成（每月规则不因跨年丢失）",
      "-digest-20270108" in ctext)
check("2027-01-08 也是 2 条 core（两条 monthly 规则都跨过了年）",
      "SUMMARY:今日优惠 2 条｜好想来、赵一鸣零食" in ctext)
# 12-31 是周四；1-1 是周五无 core 内容，故当晚不应有 nudge
check("12-31 不发 nudge（元旦无 core 内容，符合规则 b）",
      "-nudge-20261231" not in ctext)
check("跨年期间时段渲染正常", "9:30-23:00" in ctext)
check("窗口跨年后仍有事件", sc["events"] > 0 and sc["days_with_content"] >= 8)

print()
print("=== 7. 时段字段渲染 ===")
line = gen.offer_line(offers["kfc-crazy-thursday"])
check("带时段渲染为 9:30-23:00", "9:30-23:00" in line, line)
check("不带时段的条目无括号",
      "（" not in gen.offer_line(offers["mcdonalds-monday"]))

print()
print("=== 8. 数据文件健康度 ===")
pending = load("pending.yaml")
oneoff = load("oneoff.yaml")
check(f"pending.yaml 有 {len(pending)} 条待核实线索", len(pending) > 0)
check("offers.yaml 每条都有 source", all(o.get("source") for o in all_offers),
      str([o["id"] for o in all_offers if not o.get("source")]))
check("offers.yaml 每条都有 verified_at",
      all(o.get("verified_at") for o in all_offers))
check("所有 id 唯一", len({o["id"] for o in all_offers}) == len(all_offers))
check("所有 recur.days 合法",
      all(str(d).lower() in gen.WEEKDAY_NAMES or isinstance(d, int)
          for o in all_offers for d in (o.get("recur") or {}).get("days", [])))
check(f"oneoff.yaml 有 {len(oneoff)} 条（仅网页展示，不进日历）", len(oneoff) > 0)

print()
if FAILED:
    print(f"!!! {len(FAILED)} 项失败:")
    for f_ in FAILED:
        print("   -", f_)
    raise SystemExit(1)
print("全部通过。")
