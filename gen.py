#!/usr/bin/env python3
"""brand-days 生成器：把 data/*.yaml 渲染成可订阅的 deals.ics

设计要点（全部经过实测验证）：
  * 生成【未来 window_days 天的具体 VEVENT】，不用 RRULE。
    原因：RRULE 表达不了“本周停办”“日期改了”“同一天两个时段”这类真实情况，
    硬用 RRULE 只会把裁剪逻辑挪进 EXDATE 里，代码更长。
  * VTIMEZONE 必须【显式内嵌】。icalendar 默认只写 TZID=Asia/Shanghai 这个引用，
    不写定义块，某些客户端解析不出时事件会整体偏移 8 小时且不报错。
  * 定时事件 + VALARM 负责主动弹通知；每天再加一条全天摘要事件兜底，
    万一手机不弹通知，翻日历仍能看到今天有什么。
  * DTSTAMP 使用固定值（生成日 00:00），保证同一天重复生成的文件逐字节一致，
    git 里不会出现无意义的 diff。
  * 只用标准库 + PyYAML + icalendar。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from icalendar import Alarm, Calendar, Event, Timezone

ROOT = Path(__file__).resolve().parent
WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CN_WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
CN_NUM = "零一二三四五六七八九十"


# ---------------------------------------------------------------- 基础工具

def cn_date(d: date) -> str:
    return f"{d.month}月{d.day}日"


def cn_weekday(d: date) -> str:
    return CN_WEEKDAY[d.weekday()]


def cn_time(hhmm: str) -> str:
    """'14:00' -> '14:00'；'09:30' -> '9:30'（口语写法）"""
    h, m = hhmm.split(":")
    return f"{int(h)}:{m}"


def load_yaml(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or []


# ---------------------------------------------------------------- 周期规则

def matches(offer: dict, day: date) -> bool:
    """这条优惠在 day 这一天是否生效。"""
    start = offer.get("start")
    if start is not None:
        if isinstance(start, str):
            start = date.fromisoformat(start)
        if day < start:
            return False

    recur = offer.get("recur") or {}
    rtype = recur.get("type")
    days = recur.get("days") or []

    if rtype == "weekly":
        return WEEKDAY_NAMES[day.weekday()] in [str(d).lower() for d in days]
    if rtype == "monthly":
        return day.day in [int(d) for d in days]

    # 没有 recur 的条目不应出现在 offers.yaml 里
    return False


def is_calendar_eligible(offer: dict, tiers_in_calendar: list[str]) -> bool:
    """只有 verified + 指定 tier 才进日历。"""
    if offer.get("confidence", "unverified") != "verified":
        return False
    return offer.get("tier", "extended") in tiers_in_calendar


# ---------------------------------------------------------------- 文案渲染

def offer_line(offer: dict) -> str:
    """一行式描述：品牌｜优惠（时段）"""
    text = f"{offer['brand']}｜{offer['offer']}"
    win = offer.get("window")
    if win:
        text += f"（{cn_time(win['start'])}-{cn_time(win['end'])}）"
    return text


def offer_detail(offer: dict, index: int) -> str:
    """多行详情，含条件与来源。"""
    lines = [f"{index}. {offer_line(offer)}"]
    for c in offer.get("conditions") or []:
        lines.append(f"   ・{c}")
    if offer.get("source"):
        lines.append(f"   来源：{offer['source']}")
    return "\n".join(lines)


def digest_title(day: date, offers: list[dict]) -> str:
    names = "、".join(o["brand"] for o in offers)
    return f"今日优惠 {len(offers)} 条｜{names}"


def nudge_title(day: date, offers: list[dict]) -> str:
    names = "、".join(o["brand"] for o in offers)
    return f"明天（{cn_date(day)} {cn_weekday(day)}）{len(offers)} 条｜{names}"


# ---------------------------------------------------------------- ics 构建

def build_timezone(tz: ZoneInfo, first_year: int, last_year: int) -> Timezone:
    return Timezone.from_tzinfo(
        tz, first_date=date(first_year, 1, 1), last_date=date(last_year, 12, 31)
    )


def _fold_line(line: str, limit: int = 75) -> str:
    """按 RFC 5545 折叠单行：每行 <= limit 字节，续行以单个空格开头。

    必须在 UTF-8 字符边界处切分 —— 汉字占 3 字节，从中间截断会产生乱码。
    """
    if len(line.encode("utf-8")) <= limit:
        return line

    parts: list[str] = []
    cur = ""
    cur_len = 0
    # 续行以空格开头，所以后续行的可用字节数要减 1
    for ch in line:
        ch_len = len(ch.encode("utf-8"))
        cap = limit if not parts else limit - 1
        if cur_len + ch_len > cap:
            parts.append(cur)
            cur, cur_len = ch, ch_len
        else:
            cur += ch
            cur_len += ch_len
    parts.append(cur)
    return "\r\n ".join(parts)


def strip_tz_comment(raw: bytes) -> bytes:
    """去掉 icalendar 自动生成的 'This timezone only works from ...' COMMENT。

    那行注释会把内部实现细节暴露给用户，且对某些客户端是噪音；
    它不是标准要求，删掉不影响任何客户端的解析。

    实现要点（踩过的坑）：
      * 长注释可能被行折叠器拆成多行，续行以单个空格开头，
        所以必须先按 RFC 5545 展开折叠行，否则单行正则匹配不到；
      * 但【展开之后必须重新折叠】—— 直接写出展开后的文本会产生超长行，
        违反 RFC 5545 的 75 字节上限，某些客户端会解析失败；
      * 重新拼接时必须【补回末尾换行】—— str.splitlines() 会连同末尾的
        CRLF 一起吃掉，直接 join 出来的文件以 END:VCALENDAR 结尾而没有换行，
        不符合 RFC 5545（组件行应以 CRLF 结束），部分严格解析器会报错。
    """
    text = raw.decode("utf-8")
    had_trailing_newline = text.endswith(("\r\n", "\n"))
    # 1) 展开折叠行（CRLF/LF + 空格 -> 空）
    unfolded = re.sub(r"\r?\n ", "", text)
    # 2) 删除目标注释行
    cleaned = re.sub(
        r"^COMMENT:This timezone only works[^\r\n]*\r?\n",
        "",
        unfolded,
        flags=re.MULTILINE,
    )
    # 3) 重新折叠，保持 75 字节上限
    folded = "\r\n".join(_fold_line(ln) for ln in cleaned.splitlines())
    # 4) 补回末尾换行
    if had_trailing_newline:
        folded += "\r\n"
    return folded.encode("utf-8")


def make_alarm(summary: str, minutes_before: int = 0) -> Alarm:
    al = Alarm()
    al.add("action", "DISPLAY")
    al.add("description", summary)
    al.add("trigger", timedelta(minutes=-minutes_before))
    return al


def build(
    cfg: dict,
    offers: list[dict],
    *,
    start: date,
    window_days: int,
    verbose: bool = False,
) -> tuple[bytes, dict]:
    tzname = cfg.get("timezone", "Asia/Shanghai")
    tz = ZoneInfo(tzname)
    uid_domain = cfg.get("uid_domain", "brand-days")
    remind_at = cfg.get("remind_at", "20:00")
    duration = int(cfg.get("nudge_duration_minutes", 20))
    tiers = cfg.get("tiers_in_calendar", ["core"])
    tz_last_year = int(cfg.get("tz_last_year", 2050))

    hh, mm = (int(x) for x in remind_at.split(":"))
    nudge_time = time(hh, mm)

    # DTSTAMP 固定为生成日 00:00，保证同日重复生成结果一致
    dtstamp = datetime.combine(start, time(0, 0), tzinfo=tz)

    eligible = [o for o in offers if is_calendar_eligible(o, tiers)]
    skipped = len(offers) - len(eligible)

    cal = Calendar()
    cal.add("prodid", f"-//{uid_domain}//brand-days//CN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", cfg.get("calendar_name", "品牌日提醒"))
    cal.add("x-wr-timezone", tzname)

    # VTIMEZONE 必须在事件之前
    first_year = min(start.year, 2010)
    cal.add_component(build_timezone(tz, first_year, tz_last_year))

    events = 0
    days_with_content = 0
    per_day: list[tuple[date, int]] = []

    # 注意：nudge 是“前一晚提醒次日”，所以窗口内每一天都需要知道“次日”有什么。
    # 若只在窗口内查次日，最后一天的通知会被永久跳过（每次滚动都补不上）。
    # 因此这里把“次日”的查询范围放宽到 window_days + 1，
    # 日历事件本身仍然只覆盖 window_days 天。
    matching_days = {
        d: [o for o in eligible if matches(o, d)]
        for d in (start + timedelta(days=i) for i in range(window_days + 1))
    }

    for offset in range(window_days):
        day = start + timedelta(days=offset)
        todays = matching_days[day]
        tomorrows = matching_days[day + timedelta(days=1)]

        # ---- 1) 当天全天摘要（兜底可见性）----
        if todays and cfg.get("digest", True):
            ev = Event()
            ev.add("uid", f"{uid_domain}-digest-{day:%Y%m%d}@{uid_domain}")
            ev.add("summary", digest_title(day, todays))
            ev.add("description", "\n".join(
                offer_detail(o, i) for i, o in enumerate(todays, 1)
            ))
            ev.add("dtstart", day)                      # 全天事件
            ev.add("dtend", day + timedelta(days=1))
            ev.add("dtstamp", dtstamp)
            ev.add("transp", "TRANSPARENT")             # 不占用“忙碌”
            cal.add_component(ev)
            events += 1

        # ---- 2) 前一晚 20:00 定时提醒（主动通知来源）----
        if tomorrows:
            nxt = day + timedelta(days=1)
            title = nudge_title(nxt, tomorrows)
            ev = Event()
            ev.add("uid", f"{uid_domain}-nudge-{day:%Y%m%d}@{uid_domain}")
            ev.add("summary", title)
            ev.add("description", "\n".join(
                offer_detail(o, i) for i, o in enumerate(tomorrows, 1)
            ))
            ev.add("dtstart", datetime.combine(day, nudge_time, tzinfo=tz))
            ev.add("dtend", datetime.combine(
                day, nudge_time, tzinfo=tz) + timedelta(minutes=duration))
            ev.add("dtstamp", dtstamp)
            ev.add("transp", "TRANSPARENT")
            ev.add_component(make_alarm(title))
            cal.add_component(ev)
            events += 1

        if todays:
            days_with_content += 1
            per_day.append((day, len(todays)))

    raw = strip_tz_comment(cal.to_ical())

    stats = {
        "events": events,
        "days_with_content": days_with_content,
        "eligible": len(eligible),
        "skipped": skipped,
        "bytes": len(raw),
        "per_day": per_day,
    }
    if verbose:
        print(f"[i] offers.yaml 共 {len(offers)} 条，进日历 {len(eligible)} 条"
              f"（跳过 {skipped} 条 tier/confidence 不符）")
        for d, n in per_day:
            print(f"    {d} {cn_weekday(d)}  {n} 条 core")
    return raw, stats


# ---------------------------------------------------------------- 入口

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="brand-days: YAML -> deals.ics + index.html")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--offers", default=str(ROOT / "data" / "offers.yaml"))
    ap.add_argument("--pending", default=str(ROOT / "data" / "pending.yaml"))
    ap.add_argument("--oneoff", default=str(ROOT / "data" / "oneoff.yaml"))
    ap.add_argument("--window", type=int, default=None, help="覆盖 window_days")
    ap.add_argument("--start", default=None, help="覆盖起始日 YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="覆盖 ics 输出路径")
    ap.add_argument("--no-html", action="store_true", help="不生成网页")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    offers = load_yaml(Path(args.offers))
    if not offers:
        print(f"[!] {args.offers} 里没有条目", file=sys.stderr)

    window = args.window or int(cfg.get("window_days", 30))

    if args.start:
        start = date.fromisoformat(args.start)
    elif cfg.get("start_date"):
        sd = cfg["start_date"]
        start = date.fromisoformat(sd) if isinstance(sd, str) else sd
    else:
        start = date.today()

    raw, stats = build(cfg, offers, start=start, window_days=window,
                       verbose=args.verbose)
    stats["window_days_total"] = window

    out = Path(args.out or (ROOT / cfg.get("outputs", {}).get("ics", "deals.ics")))
    out.write_bytes(raw)

    print(f"[OK] {out}  起始 {start}  窗口 {window} 天")
    print(f"     事件 {stats['events']} 条 | 有内容的天数 {stats['days_with_content']}"
          f" | {stats['bytes']} 字节")

    # ---- 网页 ----
    if not args.no_html:
        import genhtml

        pending = load_yaml(Path(args.pending))
        oneoff = load_yaml(Path(args.oneoff))
        # 网页要展示"进日历 + 不进日历"的全部条目，
        # 所以这里不能只用 build() 里筛过的 eligible，得重新算一遍匹配
        page = genhtml.render_html(cfg, offers, pending, oneoff,
                                   matches, start, stats)
        html_path = ROOT / cfg.get("outputs", {}).get("html", "index.html")
        # 显式用 LF 写入。不指定 newline 的话，Windows 上会把 \n 转成 \r\n，
        # 于是生成结果的字节数取决于操作系统，跨平台生成会得到不同文件。
        with html_path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(page)
        print(f"[OK] {html_path}  自包含、无外部依赖 | {len(page.encode('utf-8'))} 字节")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
