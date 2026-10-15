#!/usr/bin/env python3
"""扫描文档里语气可疑的句子，供人工判断。

    python tools/scan_tone.py

与 scan_style.py 的分工：那边查句式，答案比较确定；这边查语气，
包括给项目加意义、评论性修饰、谈论文档自身、多余的强调词。
语气没有机械判定标准，所以这里只列出来，由人决定改不改。

明显误报的例子：「日历事件本身仍然只覆盖 N 天」里的「本身」是正常用法，
「列名大小写敏感」里的「敏感」也不是问题。看到列表先判断再改。

本文件带有扫描标记，会被扫描器跳过。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SCAN_MARKER = "brand-days-scan-ignore"

RULES = [
    ("给项目加意义", r"没人在做|没有人做|无人做|这才是|恰恰是|正是为了|"
                     r"护城" + r"河|底层逻辑|根本原因|真正的价值|最大的价值"),
    ("断言行业现状", r"说明(?:了)?问题|反映(?:了)?(?:一个)?问题|暴露了|折射"),
    ("评论性修饰", r"本身(?:就)?(?:也)?|反而是|无非|显然|其实|说到底|"
                   r"值得一提|不可否认|众所周知|说白了"),
    ("多余强调", r"确实|真的(?:是)?|非常|极其|相当|格外|尤为|充分说明"),
    ("谈论文档自身", r"本文档|本说明|如上所述|如前所述|值得注意的是|"
                     r"需要指出|综上"),
    ("对举句式", r"不是[^。\n]{0,40}(?:而是|，是)|并" + r"非[^。\n]{0,40}而是"),
    ("自述写作过程", r"这句话|读起来像|像 ?AI|AI " + r"味"),
]

FILES = (sorted(ROOT.glob("*.md")) + sorted(ROOT.glob("*.py"))
         + sorted(ROOT.glob("tools/*.py")) + [ROOT / "config.yaml"])

total = 0
for f in FILES:
    if not f.exists():
        continue
    text = f.read_text(encoding="utf-8")
    if SCAN_MARKER in text:
        continue
    lines = text.splitlines()
    hits = []
    for label, pat in RULES:
        for m in re.finditer(pat, text):
            ln = text[:m.start()].count("\n") + 1
            hits.append((ln, label, lines[ln - 1].strip()[:110]))
    if hits:
        print(f"\n--- {f.relative_to(ROOT)} ---")
        for ln, label, seg in sorted(set(hits)):
            print(f"  L{ln:<4} [{label}] {seg}")
            total += 1

print()
print(f"共 {total} 处待人工判断。")
