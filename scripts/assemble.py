# -*- coding: utf-8 -*-
"""
通用总装：把 <项目目录>/content/ 下的分章 md 拼成 content.md（供 build.py 编译）。

用法:  python assemble.py <项目目录>

拼接规则:
  1. 只收 content/*.md，跳过 _CONTRACT* 开头的契约文件。
  2. 顺序 = 文件名排序：_header.md 天然最先，chNN.md 按章号，zz_*.md（考前冲刺）天然最后。
  3. 可选 content/_parts.json 在指定章前插入一级"编"标题:
       [{"before": "ch01.md", "title": "第一编　社会研究基础"},
        {"before": "ch05.md", "title": "第二编　定量研究方式"},
        {"before": "zz_chongci.md", "title": "考前冲刺 · 简答论述速查"}]
"""
import io, os, sys, json

PROJ = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
CT = os.path.join(PROJ, "content")
if not os.path.isdir(CT):
    raise SystemExit("!! 缺 content/ 目录: " + CT)

parts_cfg = []
pj = os.path.join(CT, "_parts.json")
if os.path.exists(pj):
    parts_cfg = json.load(io.open(pj, encoding="utf-8"))
part_before = {p["before"]: p["title"] for p in parts_cfg}

files = sorted(f for f in os.listdir(CT)
               if f.endswith(".md") and not f.startswith("_CONTRACT"))
if not files:
    raise SystemExit("!! content/ 下没有 md 文件")

parts = []
for name in files:
    if name in part_before:
        parts.append("\n# %s\n" % part_before[name])
    txt = io.open(os.path.join(CT, name), encoding="utf-8").read().rstrip()
    if txt:
        parts.append(txt + "\n")
    print("  +", name)

out = "\n".join(parts)
io.open(os.path.join(PROJ, "content.md"), "w", encoding="utf-8", newline="\n").write(out)
print("content.md 生成完成，%d 字符，%d 个文件" % (len(out), len(files)))
