#!/usr/bin/env python3
"""校验生成的 index.html。

分三层，逐层加强：
  1. 静态检查：自包含（无外部资源）、JSON 可解析、数字与数据文件一致
  2. JS 语法检查：把内联脚本交给 node --check
  3. JS 运行时检查：在 node 里喂一个最小 DOM 实现，真正执行渲染函数

第 3 层是关键 —— 只看语法正确不够，渲染函数里的错字、拼错的变量名、
用错的方法名都只有真跑才会暴露。

用法：python tools/check_html.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
FAILED: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(("  [OK]   " if cond else "  [FAIL] ") + label + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILED.append(label)


html_path = ROOT / "index.html"
if not html_path.exists():
    print("找不到 index.html，先跑 python gen.py", file=sys.stderr)
    raise SystemExit(2)
html = html_path.read_text(encoding="utf-8")
print(f"index.html: {len(html.encode('utf-8'))} 字节\n")

# ─────────────────────────────── 1. 静态检查
print("=== 1. 静态检查 ===")
check("有 DOCTYPE", html.lstrip().startswith("<!DOCTYPE html>"))
check("声明 utf-8", 'charset="utf-8"' in html)
check("有 viewport（移动端）", "viewport" in html)
check("有 lang=zh-CN", 'lang="zh-CN"' in html)

# 自包含：不应有任何外部资源引用
ext = re.findall(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', html)
# 允许 GitHub 链接和来源链接（它们是 <a> 不是资源加载）
bad_ext = [u for u in ext if not re.search(r'github\.com', u)]
check("无外部脚本/样式依赖（自包含）",
      "<script src" not in html and "link rel=\"stylesheet\"" not in html,
      f"发现 {bad_ext[:3]}")
check("无 iframe", "<iframe" not in html)
check("无外链字体", "@import" not in html and "fonts.googleapis" not in html)

# 内联数据
m = re.search(r"window\.__BRAND_DAYS__\s*=\s*(\{.*?\});\s*</script>", html, re.S)
check("找到内联数据", bool(m))
if m:
    try:
        data = json.loads(m.group(1))
        check("内联 JSON 可解析", True)
    except Exception as e:
        check("内联 JSON 可解析", False, str(e)[:120])
        data = None
else:
    data = None

# 内联样式与脚本
check("有内联 <style>", "<style>" in html)
check("有内联渲染脚本", "renderUpcoming" in html and "renderTable" in html)

# ─────────────────────────────── 2. JS 语法检查
print()
print("=== 2. JS 语法检查（node --check）===")
node = (shutil.which("node")
        or r"C:\Users\30627\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe")
has_node = Path(node).exists() if "\\" in str(node) else bool(node)
if not has_node:
    print("  [skip] 找不到 node，跳过语法与运行时检查")
else:
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    # 第一个 script 是数据，第二个是逻辑
    logic = scripts[-1] if scripts else ""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(logic)
        jsfile = f.name
    r = subprocess.run([node, "--check", jsfile], capture_output=True, text=True)
    check("渲染脚本语法正确", r.returncode == 0,
          (r.stderr or "").strip().splitlines()[0] if r.stderr else "")

    # ─────────────────────────── 3. JS 运行时检查
    print()
    print("=== 3. JS 运行时检查（最小 DOM 实现里真跑一遍）===")
    harness = r"""
// ---- 最小 DOM 实现：只实现渲染代码用到的部分 ----
class Node {
  constructor(tag){ this.tagName=(tag||'').toUpperCase(); this.children=[];
    this._text=''; this.className=''; this.style={}; this.attrs={}; this.listeners={}; }
  appendChild(c){ this.children.push(c); return c; }
  set textContent(v){ this.children=[]; this._text=String(v); }
  get textContent(){ return this._text || this.children.map(c=>c.textContent).join(''); }
  setAttribute(k,v){ this.attrs[k]=v; }
  get classList(){ const self=this; return {
    add:c=>{ if(!self.className.includes(c)) self.className+=' '+c; },
    toggle:c=>{ self.className = self.className.includes(c)
      ? self.className.replace(c,'').trim() : self.className+' '+c; },
    contains:c=>self.className.includes(c) }; }
  addEventListener(t,f){ (this.listeners[t]=this.listeners[t]||[]).push(f); }
  querySelector(){ return null; }
}
const byId = {};
function mk(id){ const n=new Node('div'); n.id=id; byId[id]=n; return n; }
['upcoming','q','onlyCore','tbody','count','pending','oneoff','icsUrl','copyBtn']
  .forEach(mk);
byId['q'].value = '';

global.document = {
  createElement: t => new Node(t),
  createTextNode: t => { const n=new Node('#text'); n.textContent=t; return n; },
  getElementById: id => byId[id] || null,
  createRange: () => ({ selectNodeContents(){} }),
};
global.window = {};
global.navigator = { clipboard: { writeText: async () => {} } };
global.getSelection = () => ({ removeAllRanges(){}, addRange(){} });
global.setTimeout = (f) => 0;

// ---- 载入数据与脚本 ----
__DATA__
__SCRIPT__

// ---- 断言渲染结果 ----
const fail = [];
function ok(label, cond, extra){
  console.log((cond ? '  [OK]   ' : '  [FAIL] ') + label + (cond ? '' : ('  ' + (extra||''))));
  if(!cond) fail.push(label);
}
ok('今天区块已渲染', byId['upcoming'].children.length > 0);
ok('全部数据表已渲染', byId['tbody'].children.length > 0,
   '行数=' + byId['tbody'].children.length);
ok('待核实区块已渲染', byId['pending'].children.length > 0);
ok('时效型区块已渲染', byId['oneoff'].children.length > 0);
ok('订阅地址已写入', byId['icsUrl'].textContent.includes('/deals.ics'),
   byId['icsUrl'].textContent);
ok('复制按钮已绑定事件', (byId['copyBtn'].listeners['click']||[]).length === 1);
ok('搜索框已绑定事件', (byId['q'].listeners['input']||[]).length === 1);
ok('“只看进日历”按钮已绑定', (byId['onlyCore'].listeners['click']||[]).length === 1);

// 搜索过滤是否真的生效
const before = byId['tbody'].children.length;
byId['q'].value = '肯德基';
byId['q'].listeners['input'][0]();
const afterSearch = byId['tbody'].children.length;
ok('搜索能过滤', afterSearch > 0 && afterSearch <= before,
   `搜索前 ${before} 行，搜索后 ${afterSearch} 行`);
byId['q'].value = '';
byId['q'].listeners['input'][0]();

// 无匹配时是否优雅降级
byId['q'].value = 'zzz不可能匹配zzz';
byId['q'].listeners['input'][0]();
ok('无匹配时给出提示且不崩溃', byId['tbody'].children.length === 1,
   '行数=' + byId['tbody'].children.length);
byId['q'].value = '';
byId['q'].listeners['input'][0]();

// 计数字符串
ok('匹配计数已写入', /匹配 \d+ 条/.test(byId['count'].textContent),
   byId['count'].textContent);

process.exit(fail.length ? 1 : 0);
"""
    harness = harness.replace("__DATA__", "window.__BRAND_DAYS__ = " + m.group(1) + ";")
    harness = harness.replace("__SCRIPT__", logic)
    hj = Path(tempfile.gettempdir()) / "branddays_harness.js"
    hj.write_text(harness, encoding="utf-8")
    r = subprocess.run([node, str(hj)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout.rstrip() or "(无输出)")
    if r.returncode != 0 and r.stderr:
        print("  --- node stderr ---")
        print("  " + (r.stderr or "").strip()[:1200])
    if r.returncode != 0:
        FAILED.append("JS 运行时检查")

    # ─────────────────────────── 4. 与数据的一致性
    print()
    print("=== 4. 页面数字与数据文件一致 ===")
    import yaml
    offers = yaml.safe_load((ROOT / "data" / "offers.yaml").read_text(encoding="utf-8")) or []
    pending = yaml.safe_load((ROOT / "data" / "pending.yaml").read_text(encoding="utf-8")) or []
    oneoff = yaml.safe_load((ROOT / "data" / "oneoff.yaml").read_text(encoding="utf-8")) or []
    if data:
        check(f"offers 条数一致（{len(offers)}）", len(data["offers"]) == len(offers))
        check(f"pending 条数一致（{len(pending)}）", len(data["pending"]) == len(pending))
        check(f"oneoff 条数一致（{len(oneoff)}）", len(data["oneoff"]) == len(oneoff))
        n_cal = sum(1 for o in offers
                    if o.get("tier") == "core" and o.get("confidence") == "verified")
        check(f"进日历条数一致（{n_cal}）",
              sum(1 for o in data["offers"] if o["inCalendar"]) == n_cal)
        check("occurrences 覆盖 15 天", len(data["occurrences"]) == 15)
        # 用生成器的规则独立算一遍"今天命中什么"，与页面内联数据对比
        sys.path.insert(0, str(ROOT))
        import gen as _gen
        from datetime import date as _date
        today = _date.fromisoformat(data["occurrences"][0]["date"])
        exp_first = [o["id"] for o in offers if _gen.matches(o, today)]
        check("今天命中数与规则计算一致",
              sorted(data["occurrences"][0]["ids"]) == sorted(exp_first),
              f"页面 {data['occurrences'][0]['ids']} vs 计算 {exp_first}")

print()
if FAILED:
    print(f"!!! {len(FAILED)} 项失败：")
    for f in FAILED:
        print("   -", f)
    raise SystemExit(1)
print("全部通过。")
