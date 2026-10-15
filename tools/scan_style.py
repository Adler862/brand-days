#!/usr/bin/env python3
"""扫描文档里的对举句式、转折堆叠与多余强调词。

    python tools/scan_style.py

检查这些模式（"不是A而是B"及其变体、"而不是/而非"、"刻意"、
"没人在做"这类断言）。这些基本都有确定答案，扫出来就该改。

语气类（给项目加意义、评论性修饰）的判断更主观，交给 scan_tone.py。

本文件带有扫描标记，会被扫描器跳过，避免匹配到下面这些模式定义本身。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

# 带这个标记的文件会被扫描器跳过
SCAN_MARKER = "brand-days-scan-ignore"

PATS = [
    ("对举句式", r"不是[^。\n]{0,40}(?:而是|，是)"),
    ("对举句式", r"并" + r"非[^。\n]{0,40}而是"),
    ("转折堆叠", r"而不是"),
    ("转折堆叠", r"而" + r"非"),
    ("多余强调", r"刻" + r"意"),
    ("自我拔高", r"没人在做|没有人做|护城河|立项理由"),
    ("自述写作", r"AI " + r"味|读起来像|像 " + r"AI"),
]

FILES = (sorted(ROOT.glob("*.md")) + sorted(ROOT.glob("*.py"))
         + sorted(ROOT.glob("tools/*.py")) + [ROOT / "config.yaml"])

total = 0
skipped = []
for f in FILES:
    if not f.exists():
        continue
    text = f.read_text(encoding="utf-8")
    if SCAN_MARKER in text:
        skipped.append(f.relative_to(ROOT))
        continue
    lines = text.splitlines()
    hits = []
    for label, pat in PATS:
        for m in re.finditer(pat, text):
            ln = text[:m.start()].count("\n") + 1
            hits.append((ln, label, lines[ln - 1].strip()[:110]))
    if hits:
        print(f"\n--- {f.relative_to(ROOT)} ---")
        for ln, label, seg in sorted(set(hits)):
            print(f"  L{ln:<4} [{label}] {seg}")
            total += 1

print()
if skipped:
    print(f"跳过带扫描标记的文件：{', '.join(str(s) for s in skipped)}")
print(f"共 {total} 处。")
