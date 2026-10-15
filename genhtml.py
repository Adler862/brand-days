#!/usr/bin/env python3
"""把数据与生成结果渲染成自包含的 index.html。

设计取舍
────────
* **自包含、零依赖**：不引任何 CDN、框架或外部字体。数据直接内联成 JSON，
  所以这个文件双击就能看，也能直接丢到 GitHub Pages 上。
* **服务两类读者**：想订阅的人（要一眼看到订阅地址）和想查数据的人
  （要能按品牌搜索、能看某天有什么）。所以首页是"今天"，然后是搜索与全量列表。
* **诚实展示数据状态**：待核实、超 90 天未复核的条目都如实标注，不藏起来。
  这是这个项目区别于二手汇总的地方。
"""
from __future__ import annotations

import html
import json
from datetime import date, datetime, timedelta

CN_WEEK = ["一", "二", "三", "四", "五", "六", "日"]
WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---------------------------------------------------------------- 工具

def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _recur_text(offer: dict) -> str:
    r = offer.get("recur") or {}
    days = r.get("days") or []
    if r.get("type") == "weekly":
        names = {"mon": "周一", "tue": "周二", "wed": "周三",
                 "thu": "周四", "fri": "周五", "sat": "周六", "sun": "周日"}
        return "、".join(names.get(str(d).lower(), str(d)) for d in days)
    if r.get("type") == "monthly":
        return "每月 " + "、".join(f"{d} 号" for d in days)
    return ""


def offer_records(offers: list[dict]) -> list[dict]:
    """把 YAML 条目转成前端用的扁平记录。"""
    out = []
    for o in offers:
        out.append({
            "id": o.get("id", ""),
            "brand": o.get("brand", ""),
            "offer": o.get("offer", ""),
            "recur": _recur_text(o),
            "recurType": (o.get("recur") or {}).get("type", ""),
            "recurDays": (o.get("recur") or {}).get("days", []),
            "window": (f"{o['window']['start']}-{o['window']['end']}"
                       if o.get("window") else ""),
            "tier": o.get("tier", "extended"),
            "confidence": o.get("confidence", "unverified"),
            "conditions": o.get("conditions") or [],
            "source": o.get("source", ""),
            "verifiedAt": str(o.get("verified_at") or ""),
            "notes": o.get("notes", "") or "",
            "inCalendar": (o.get("confidence") == "verified"
                           and o.get("tier") == "core"),
        })
    return out


def pending_records(pending: list[dict]) -> list[dict]:
    out = []
    for p in pending:
        out.append({
            "brand": p.get("brand", ""),
            "claim": p.get("claim", ""),
            "candidateDay": str(p.get("candidate_day") or ""),
            "reason": p.get("reason", ""),
            "source": p.get("source", ""),
            "todo": p.get("todo", "") or "",
        })
    return out


def oneoff_records(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        out.append({
            "brand": it.get("brand", ""),
            "offer": it.get("offer", ""),
            "conditions": it.get("conditions") or [],
            "confidence": it.get("confidence", "unverified"),
            "source": it.get("source", ""),
            "notes": it.get("notes", "") or "",
        })
    return out


def build_occurrences(offers: list[dict], matches, start: date, days: int) -> list[dict]:
    """未来 days 天内每天命中了哪些条目（用于“今天”和“未来 14 天”）。"""
    result = []
    for i in range(days):
        d = start + timedelta(days=i)
        hit = [o for o in offers if matches(o, d)]
        result.append({
            "date": d.isoformat(),
            "md": f"{d.month}月{d.day}日",
            "week": CN_WEEK[d.weekday()],
            "ids": [o.get("id") for o in hit],
            "brands": [o.get("brand") for o in hit],
        })
    return result


# ---------------------------------------------------------------- 页面

CSS = """
:root{
  --bg:#ffffff; --fg:#1a1a1a; --dim:#6b6b6b; --line:#e6e6e6;
  --card:#fafafa; --accent:#c0392b; --ok:#1f7a4d; --warn:#b7791f;
  --radius:10px;
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#16181c; --fg:#e8e8e8; --dim:#9aa0a6; --line:#2c2f35;
         --card:#1d2025; --accent:#ff6b5e; --ok:#5dd39e; --warn:#e0b050; }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; padding:0 16px 64px; background:var(--bg); color:var(--fg);
  font:15px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",
       "Hiragino Sans GB","Source Han Sans SC",sans-serif;
}
.wrap{max-width:820px;margin:0 auto}
header{padding:28px 0 8px}
h1{margin:0 0 6px;font-size:22px;letter-spacing:.2px}
.sub{color:var(--dim);font-size:13px;margin:0 0 18px}
h2{font-size:16px;margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
a{color:inherit}
code,kbd{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}

.sub-box{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  padding:14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sub-box code{flex:1 1 340px;min-width:0;overflow-wrap:anywhere;
  background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px 10px}
button{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--bg);
  color:var(--fg);border-radius:6px;padding:7px 12px}
button:hover{border-color:var(--dim)}
button.on{background:var(--accent);border-color:var(--accent);color:#fff}

.card{border:1px solid var(--line);border-radius:var(--radius);padding:14px;
  margin:0 0 10px;background:var(--card)}
.card.plain{background:transparent}
.card-head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.brand{font-weight:600}
.offer{color:var(--fg)}
.meta{color:var(--dim);font-size:12.5px}
.cond{margin:8px 0 0;padding-left:18px;color:var(--dim);font-size:13px}
.cond li{margin:2px 0}
.src{margin-top:8px;font-size:12px;color:var(--dim);overflow-wrap:anywhere}
.src a{color:var(--dim)}

.tag{display:inline-block;font-size:11.5px;line-height:1.6;padding:1px 7px;
  border-radius:99px;border:1px solid var(--line);color:var(--dim);white-space:nowrap}
.tag.core{color:var(--ok);border-color:var(--ok)}
.tag.warn{color:var(--warn);border-color:var(--warn)}
.tag.off{opacity:.55}

.day{border-bottom:1px solid var(--line);padding:10px 0}
.day:last-child{border-bottom:0}
.day-head{display:flex;gap:10px;align-items:baseline}
.day-head b{font-size:15px}
.day-head .meta{margin-left:auto}
.empty{color:var(--dim);font-size:13.5px;padding:8px 0}

.searchbar{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}
input[type=search]{flex:1 1 240px;font:inherit;padding:9px 12px;border-radius:8px;
  border:1px solid var(--line);background:var(--bg);color:var(--fg)}
input[type=search]:focus{outline:none;border-color:var(--accent)}

table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:500;font-size:12.5px;white-space:nowrap}
tr:last-child td{border-bottom:0}
td.nowrap{white-space:nowrap}

details{border:1px solid var(--line);border-radius:var(--radius);padding:0 14px;
  margin:0 0 10px;background:var(--card)}
details[open]{padding-bottom:14px}
summary{cursor:pointer;padding:12px 0;font-weight:600;list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸ ";color:var(--dim)}
details[open] summary::before{content:"▾ "}
summary .meta{font-weight:400}

footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--dim);font-size:12.5px}
.hint{color:var(--dim);font-size:13px;margin:8px 0 0}
.hint.warn{color:var(--warn)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 12px}
"""

JS = """
const DATA = window.__BRAND_DAYS__;

function el(tag, cls, text){
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function offerById(id){
  return DATA.offers.find(o => o.id === id);
}

/* ---------- 今天 + 未来 14 天 ---------- */
function renderUpcoming(){
  const box = document.getElementById('upcoming');
  const today = DATA.occurrences[0];
  const rest = DATA.occurrences.slice(1, 15);

  // 展示与提醒必须一致：
  // 有能进日历的条目时只显示这些（它们才真的会发提醒）；
  // 没有时才显示不进日历的，并注明“仅记录，不会发提醒”。
  function pick(day){
    const all = day.ids.map(offerById).filter(Boolean);
    const cal = all.filter(o => o.inCalendar);
    return { list: cal.length ? cal : all, note: cal.length ? false : true };
  }

  // 今天
  const t = el('div');
  if (today && today.ids.length){
    const p = pick(today);
    p.list.forEach(o => t.appendChild(card(o)));
    if (p.note){
      t.appendChild(el('div', 'hint',
        '今天没有会发提醒的优惠；上面这些不进日历、不会通知，仅作记录。'));
    }
  } else {
    t.appendChild(el('div', 'empty', '今天没有收录的周期性优惠。'));
  }
  box.appendChild(t);

  // 未来 14 天
  const wrap = el('div');
  rest.forEach(day => {
    const d = el('div', 'day');
    const p = pick(day);
    const head = el('div', 'day-head');
    const b = el('b', null, `${day.md} 周${day.week}`);
    head.appendChild(b);
    if (!p.list.length){
      head.appendChild(el('span', 'meta', '无'));
    } else {
      head.appendChild(el('span', 'meta',
        p.list.map(o => o.brand).join('、') + (p.note ? '（仅记录）' : '')));
    }
    d.appendChild(head);
    p.list.forEach(o => d.appendChild(card(o, true)));
    wrap.appendChild(d);
  });
  const det = el('details');
  const sum = el('summary');
  sum.appendChild(document.createTextNode('未来 14 天'));
  const m = el('span', 'meta');
  const n = rest.filter(dd => dd.ids.length).length;
  m.textContent = `　共 ${n} 天有记录`;
  sum.appendChild(m);
  det.appendChild(sum);
  det.appendChild(wrap);
  box.appendChild(det);
}

/* ---------- 卡片 ---------- */
function card(o, compact){
  if (!o) return el('div');
  const c = el('div', compact ? 'card plain' : 'card');
  const head = el('div', 'card-head');
  head.appendChild(el('span', 'brand', o.brand));
  const off = el('span', 'offer', o.offer);
  head.appendChild(off);
  if (o.window) head.appendChild(el('span', 'tag', o.window));
  if (o.tier === 'core') head.appendChild(el('span', 'tag core', '进日历'));
  else head.appendChild(el('span', 'tag off', '仅记录'));
  if (o.confidence !== 'verified') head.appendChild(el('span', 'tag warn', '未核实'));
  c.appendChild(head);

  const meta = el('div', 'meta');
  meta.style.marginTop = '4px';
  meta.textContent = o.recur + (o.verifiedAt ? `　核对于 ${o.verifiedAt}` : '');
  c.appendChild(meta);

  if (!compact && o.conditions.length){
    const ul = el('ul', 'cond');
    o.conditions.forEach(x => ul.appendChild(el('li', null, x)));
    c.appendChild(ul);
  }
  if (!compact && o.notes){
    const p = el('div', 'meta');
    p.style.marginTop = '6px';
    p.textContent = '注：' + o.notes;
    c.appendChild(p);
  }
  if (!compact && o.source){
    const s = el('div', 'src');
    s.appendChild(document.createTextNode('来源：'));
    if (/^https?:/.test(o.source)){
      const a = el('a', null, o.source);
      a.href = o.source; a.target = '_blank'; a.rel = 'noopener noreferrer';
      s.appendChild(a);
    } else {
      s.appendChild(document.createTextNode(o.source));
    }
    c.appendChild(s);
  }
  return c;
}

/* ---------- 搜索与全量列表 ---------- */
function renderTable(){
  const q = (document.getElementById('q').value || '').trim().toLowerCase();
  const onlyCore = document.getElementById('onlyCore').classList.contains('on');
  const rows = DATA.offers.filter(o => {
    if (onlyCore && !o.inCalendar) return false;
    if (!q) return true;
    return (o.brand + o.offer + o.recur + (o.notes||'') + o.conditions.join(''))
      .toLowerCase().includes(q);
  });
  const tbody = document.getElementById('tbody');
  tbody.textContent = '';
  if (!rows.length){
    const tr = el('tr');
    const td = el('td', 'empty', '没有匹配的条目。');
    td.colSpan = 5;
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  rows.forEach(o => {
    const tr = el('tr');
    tr.appendChild(el('td', 'nowrap', o.brand));
    tr.appendChild(el('td', null, o.offer));
    tr.appendChild(el('td', 'nowrap', o.recur));
    const tdTags = el('td', 'nowrap');
    if (o.inCalendar) tdTags.appendChild(el('span', 'tag core', '进日历'));
    else if (o.confidence !== 'verified') tdTags.appendChild(el('span', 'tag warn', '未核实'));
    else tdTags.appendChild(el('span', 'tag off', '不进日历'));
    tr.appendChild(tdTags);
    const tdSrc = el('td');
    if (/^https?:/.test(o.source)){
      const a = el('a', null, '来源');
      a.href = o.source; a.target = '_blank'; a.rel = 'noopener noreferrer';
      tdSrc.appendChild(a);
    } else if (o.source){
      tdSrc.appendChild(document.createTextNode(o.source));
    }
    tr.appendChild(tdSrc);
    tbody.appendChild(tr);
  });
  document.getElementById('count').textContent = `匹配 ${rows.length} 条`;
}

/* ---------- 待核实 ---------- */
function renderPending(){
  const box = document.getElementById('pending');
  box.textContent = '';
  if (!DATA.pending.length){
    box.appendChild(el('div', 'empty', '暂无待核实线索。'));
    return;
  }
  const t = el('table');
  const thead = el('thead');
  const hr = el('tr');
  ['品牌', '素材说法', '线索周期', '为什么没进日历'].forEach(h => hr.appendChild(el('th', null, h)));
  thead.appendChild(hr);
  t.appendChild(thead);
  const tb = el('tbody');
  DATA.pending.forEach(p => {
    const tr = el('tr');
    tr.appendChild(el('td', 'nowrap', p.brand));
    tr.appendChild(el('td', null, p.claim));
    tr.appendChild(el('td', 'nowrap', p.candidateDay));
    const td = el('td');
    td.appendChild(document.createTextNode(p.reason));
    if (p.todo){
      const d = el('div', 'meta');
      d.style.marginTop = '4px';
      d.textContent = '待办：' + p.todo;
      td.appendChild(d);
    }
    tr.appendChild(td);
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  box.appendChild(t);
}

/* ---------- 时效型 ---------- */
function renderOneoff(){
  const box = document.getElementById('oneoff');
  box.textContent = '';
  if (!DATA.oneoff.length){
    box.appendChild(el('div', 'empty', '暂无条目。'));
    return;
  }
  DATA.oneoff.forEach(o => {
    const c = el('div', 'card');
    const head = el('div', 'card-head');
    head.appendChild(el('span', 'brand', o.brand));
    head.appendChild(el('span', 'offer', o.offer));
    if (o.confidence !== 'verified') head.appendChild(el('span', 'tag warn', '未核实'));
    c.appendChild(head);
    if (o.conditions.length){
      const ul = el('ul', 'cond');
      o.conditions.forEach(x => ul.appendChild(el('li', null, x)));
      c.appendChild(ul);
    }
    if (o.notes){
      const p = el('div', 'meta');
      p.style.marginTop = '6px';
      p.textContent = '注：' + o.notes;
      c.appendChild(p);
    }
    box.appendChild(c);
  });
}

/* ---------- 订阅地址 ---------- */
function renderSubscribe(){
  const url = DATA.baseUrl + '/deals.ics';
  document.getElementById('icsUrl').textContent = url;
  const btn = document.getElementById('copyBtn');
  btn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(url);
      btn.textContent = '已复制';
    } catch (e) {
      // 剪贴板 API 在 file:// 下可能不可用，退回选中文本
      const r = document.createRange();
      r.selectNodeContents(document.getElementById('icsUrl'));
      const s = getSelection();
      s.removeAllRanges(); s.addRange(r);
      btn.textContent = '已选中，请手动复制';
    }
    setTimeout(() => { btn.textContent = '复制'; }, 2000);
  });
}

/* ---------- 初始化 ---------- */
renderSubscribe();
renderUpcoming();
renderTable();
renderPending();
renderOneoff();
document.getElementById('q').addEventListener('input', renderTable);
document.getElementById('onlyCore').addEventListener('click', e => {
  e.currentTarget.classList.toggle('on');
  renderTable();
});
"""


def render_html(cfg: dict, offers: list[dict], pending: list[dict],
                oneoff: list[dict], matches, start: date, stats: dict) -> str:
    data = {
        "generatedAt": start.isoformat(),
        "baseUrl": cfg.get("base_url", ""),
        "remindAt": cfg.get("remind_at", "20:00"),
        "windowDays": stats.get("window_days_total", 365),
        "offers": offer_records(offers),
        "occurrences": build_occurrences(offers, matches, start, 15),
        "pending": pending_records(pending),
        "oneoff": oneoff_records(oneoff),
    }
    payload = json.dumps(data, ensure_ascii=False, indent=None, separators=(",", ":"))

    in_cal = sum(1 for o in data["offers"] if o["inCalendar"])
    n_pending = len(data["pending"])
    url = _esc(cfg.get("base_url", "")) + "/deals.ics"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>品牌日提醒 · brand-days</title>
<meta name="description" content="中国大陆品牌会员日 / 周期性优惠的日历订阅，每晚 {_esc(cfg.get('remind_at','20:00'))} 提醒次日优惠。">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>品牌日提醒</h1>
  <p class="sub">
    中国大陆餐饮/零售品牌的<strong>周期性优惠</strong>——
    疯狂星期四、每月 8 号零食会员日这类，做成一订阅就走的日历，
    每晚 <strong>{_esc(cfg.get('remind_at','20:00'))}</strong> 提醒你明天有什么。
  </p>

  <div class="sub-box">
    <code id="icsUrl"></code>
    <button id="copyBtn">复制</button>
    <a href="{url}"><button>下载 ics</button></a>
  </div>
  <p class="hint">
    支持订阅日历的客户端（Google 日历 / Apple 日历 / Outlook）直接粘这个地址；
    国产手机自带日历多数只能<strong>导入</strong>，下载后用日历打开即可。
  </p>
</header>

<h2>今天</h2>
<div id="upcoming"></div>

<h2>全部数据</h2>
<div class="searchbar">
  <input id="q" type="search" placeholder="搜索品牌、优惠内容、条件…">
  <button id="onlyCore" class="on">只看进日历的</button>
</div>
<p class="hint" id="count"></p>
<table>
  <thead>
    <tr><th>品牌</th><th>优惠</th><th>周期</th><th>状态</th><th>来源</th></tr>
  </thead>
  <tbody id="tbody"></tbody>
</table>

<h2>待核实（{n_pending} 条）</h2>
<p class="hint">
  这些是从网络素材收集来、但<strong>没能找到可靠来源</strong>或与素材不符的条目。
  它们<strong>不会</strong>进日历——日历是唯一会被信任的东西，错一条就会让人怀疑全部。
  欢迎按"待办"栏核实后提 PR。
</p>
<div id="pending"></div>

<h2>时效型优惠（不进日历）</h2>
<p class="hint">
  抢券、限时段优惠多属"到点抢"，日历无法在抢券前叫你，提醒了也是过期信息。
  本项目采用纯日历方案，因此这类只在此收录备查。
</p>
<div id="oneoff"></div>

<footer>
  共 {len(data['offers'])} 条周期性优惠（{in_cal} 条进日历）·
  {n_pending} 条待核实 ·
  生成于 {_esc(data['generatedAt'])} ·
  <a href="https://github.com/Adler862/brand-days">GitHub</a> ·
  MIT License<br>
  数据由人工核对，不保证始终准确；请以商家当前公示为准。
</footer>

</div>
<script>window.__BRAND_DAYS__ = {payload};</script>
<script>{JS}</script>
</body>
</html>
"""
