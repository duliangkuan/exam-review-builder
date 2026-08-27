# -*- coding: utf-8 -*-
"""
期末复习资料公开版构建引擎 v1.0
基于经过多科验证的复习讲义结构，生成不联网的离线交付件。

用法:  python build.py <项目目录>
       项目目录下须有: content.md + subject.json  (可选 figures/ 图片目录)
产物(写回项目目录):
  1. <out_html>  单文件离线交互 HTML（禁 CDN，点选项即时判分、解析与正确率统计）
  2. <out_json>  选择题题库 JSON
  3. <out_md>    静态可读 markdown（含题目+正确答案+解析）

配套约束见 references/content-contract.md 与 references/output-spec.md。
"""
import io, re, json, os, sys, base64

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
SRC = os.path.join(PROJ, "content.md")
CFG_PATH = os.path.join(PROJ, "subject.json")
if not os.path.exists(CFG_PATH):
    raise SystemExit("!! 缺 subject.json: " + CFG_PATH)
CFG = json.load(io.open(CFG_PATH, encoding="utf-8"))

# ---------- 每科参数（除此之外全部通用，不许因科目改动） ----------
QUIZ_CATS = CFG.get("quiz_cats", ["概念辨析", "公式理解", "步骤判断"])  # 恰好3个
if len(QUIZ_CATS) != 3 or len(set(QUIZ_CATS)) != 3:
    raise SystemExit("!! subject.json 的 quiz_cats 必须是三个不重复的类别")
TAGMAP = {c: t for c, t in zip(QUIZ_CATS, ["a", "b", "c"])}

# 把 figures/xxx.png 读成 base64 data URI，保证单文件离线（禁外链）
_IMG_CACHE = {}
def img_data_uri(rel):
    if rel in _IMG_CACHE:
        return _IMG_CACHE[rel]
    path = os.path.join(PROJ, rel.replace("/", os.sep))
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp"}.get(ext, "image/png")
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    uri = "data:%s;base64,%s" % (mime, b64)
    _IMG_CACHE[rel] = uri
    return uri

with io.open(SRC, encoding="utf-8") as f:
    raw = f.read()

lines = raw.split("\n")

# ---------- 1. 抽取 meta ----------
meta = {}
body = []
for ln in lines:
    if ln.startswith("＠meta "):
        kv = ln[len("＠meta "):]
        if "=" in kv:
            k, v = kv.split("=", 1)
            meta[k.strip()] = v.strip()
    else:
        body.append(ln)

TITLE = meta.get("标题", CFG.get("title", "期末速通精讲"))
SUBTITLE = meta.get("副标题", "")
NOTE = meta.get("说明", "")

OUT_HTML = CFG.get("out_html", TITLE + ".html")
OUT_JSON = CFG.get("out_json", TITLE + "题库.json")
OUT_MD = CFG.get("out_md", TITLE + ".md")

# ---------- 2. 抽取 quiz 块，替换为占位符 ----------
quizzes = []  # 每个: dict(id,belong,cat,q,opts{A..},ans,exp,section)
out_lines = []
i = 0
while i < len(body):
    ln = body[i]
    m = re.match(r"^::: quiz\s+(.*)$", ln)
    if m:
        attrs = m.group(1)
        d = {"id": "", "belong": "", "cat": ""}
        d["id"] = (re.search(r"id=(\S+)", attrs) or [None, ""])[1] if re.search(r"id=(\S+)", attrs) else ""
        bm = re.search(r"belong=(.*?)(?:\s+cat=|$)", attrs)
        d["belong"] = bm.group(1).strip() if bm else ""
        cm = re.search(r"cat=(.*)$", attrs)
        d["cat"] = cm.group(1).strip() if cm else ""
        q = {"id": d["id"], "belong": d["belong"], "cat": d["cat"],
             "opts": {}, "q": "", "ans": "", "exp": ""}
        i += 1
        while i < len(body) and body[i].strip() != ":::":
            t = body[i]
            if t.startswith("Q "):
                q["q"] = t[2:].strip()
            elif re.match(r"^[ABCD] ", t):
                q["opts"][t[0]] = t[2:].strip()
            elif t.startswith("= "):
                q["ans"] = t[2:].strip()
            elif t.startswith("> "):
                q["exp"] += (("" if not q["exp"] else " ") + t[2:].strip())
            i += 1
        quizzes.append(q)
        out_lines.append("@@QUIZ:%d@@" % (len(quizzes) - 1))
        i += 1  # 跳过 :::
        continue
    out_lines.append(ln)
    i += 1

# 题库结构是确定性闸门；内容正确性仍需按 verification.json 独立核验。
quiz_errors = []
seen_ids = set()
for q in quizzes:
    if not q["id"]:
        quiz_errors.append("存在缺少 id 的选择题")
    elif q["id"] in seen_ids:
        quiz_errors.append("选择题 id 重复: " + q["id"])
    seen_ids.add(q["id"])
    if q["cat"] not in QUIZ_CATS:
        quiz_errors.append("%s 的 cat 不在 quiz_cats 中: %s" % (q["id"], q["cat"]))
    if set(q["opts"]) != {"A", "B", "C", "D"}:
        quiz_errors.append("%s 必须恰好包含 A-D 四个选项" % q["id"])
    if q["ans"] not in {"A", "B", "C", "D"}:
        quiz_errors.append("%s 的答案必须是 A-D" % q["id"])
    if not q["exp"]:
        quiz_errors.append("%s 缺少解析" % q["id"])
if quiz_errors:
    raise SystemExit("!! 题库结构错误:\n- " + "\n- ".join(quiz_errors))

# ---------- 3. 行内渲染 ----------
def render_frac(content):
    parts = [p.strip() for p in content.split("@@")]
    if len(parts) == 2:
        prefix, num, den, suffix = "", parts[0], parts[1], ""
    elif len(parts) == 3:
        prefix, num, den, suffix = parts[0], parts[1], parts[2], ""
    elif len(parts) == 4:
        prefix, num, den, suffix = parts
    else:
        return content
    return ('%s<span class="frac"><span class="fnum">%s</span>'
            '<span class="fden">%s</span></span>%s' % (prefix, num, den, suffix))

def esc_lt(s):
    # 转义会被浏览器误当标签的裸 < > ，但保留我们有意写的 <sub>/<sup>
    s = (s.replace("<sub>", "\x01").replace("</sub>", "\x02")
          .replace("<sup>", "\x03").replace("</sup>", "\x04"))
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = (s.replace("\x01", "<sub>").replace("\x02", "</sub>")
          .replace("\x03", "<sup>").replace("\x04", "</sup>"))
    # 矢量: 组合箭头 U+20D7 微软雅黑无字形会渲成豆腐,改 .vec 样式用 ::after 画 →
    s = re.sub(u"([A-Za-zΑ-ω])⃗", r'<span class="vec">\1</span>', s)
    return s

def inline(s):
    # 先转义裸尖括号(如 0<x<1 里的 <)，否则浏览器会把 <x... 当成标签吃掉后文
    s = esc_lt(s)
    # 粗体
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    # 行内代码
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    # frac / disp 行内（一般不出现，保险处理）
    s = re.sub(r"\[\[frac:(.*?)\]\]", lambda m: render_frac(m.group(1)), s)
    s = re.sub(r"\[\[disp:(.*?)\]\]", lambda m: m.group(1), s)
    return s

def slug(n):
    return "s%d" % n

# ---------- 4. markdown -> HTML 块解析 ----------
toc = []          # (level, text, id)
htmlparts = []
sec_counter = [0]
cur_section = ["intro"]

list_stack = []  # ('ul'/'ol', indent)

def close_lists():
    global list_stack
    while list_stack:
        tag, ind = list_stack.pop()
        htmlparts.append("</%s>" % tag)

para = []

def flush_para():
    global para
    if para:
        txt = " ".join(para).strip()
        if txt:
            htmlparts.append("<p>%s</p>" % inline(txt))
        para = []

table_buf = []

def flush_table():
    global table_buf
    if not table_buf:
        return
    rows = table_buf
    table_buf = []
    header = rows[0]
    body_rows = rows[2:] if len(rows) >= 2 and re.match(r"^[\s|:\-]+$", rows[1]) else rows[1:]
    def cells(r):
        r = r.strip()
        if r.startswith("|"): r = r[1:]
        if r.endswith("|"): r = r[:-1]
        return [c.strip() for c in r.split("|")]
    html = ['<div class="tablewrap"><table>']
    html.append("<thead><tr>" + "".join("<th>%s</th>" % inline(c) for c in cells(header)) + "</tr></thead>")
    html.append("<tbody>")
    for r in body_rows:
        html.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in cells(r)) + "</tr>")
    html.append("</tbody></table></div>")
    htmlparts.append("".join(html))

i = 0
while i < len(out_lines):
    ln = out_lines[i]
    s = ln.rstrip()

    # 表格行
    if re.match(r"^\s*\|.*\|\s*$", s):
        flush_para(); close_lists()
        table_buf.append(s)
        i += 1
        continue
    else:
        if table_buf:
            flush_table()

    # quiz 占位
    mq = re.match(r"^@@QUIZ:(\d+)@@$", s.strip())
    if mq:
        flush_para(); close_lists()
        htmlparts.append("@@QUIZHTML:%s@@" % mq.group(1))
        i += 1
        continue

    # 图片  ![alt](figures/x.png)  —— 内嵌 base64，单文件离线
    mi = re.match(r"^\s*!\[(.*?)\]\((.*?)\)\s*$", s)
    if mi:
        flush_para(); close_lists()
        alt = mi.group(1).strip()
        src = mi.group(2).strip()
        cap = ('<figcaption>%s</figcaption>' % inline(alt)) if alt else ""
        htmlparts.append('<figure class="fig"><img alt="%s" src="%s">%s</figure>'
                         % (re.sub(r'"', "&quot;", alt), img_data_uri(src), cap))
        i += 1
        continue

    # 空行
    if s.strip() == "":
        flush_para(); close_lists()
        i += 1
        continue

    # 分隔线
    if s.strip() == "---":
        flush_para(); close_lists()
        htmlparts.append('<hr class="sep">')
        i += 1
        continue

    # 块级公式
    mf = re.match(r"^\s*\[\[(frac|disp):(.*)\]\]\s*$", s)
    if mf:
        flush_para(); close_lists()
        if mf.group(1) == "frac":
            htmlparts.append('<div class="formula">%s</div>' % render_frac(mf.group(2)))
        else:
            htmlparts.append('<div class="formula">%s</div>' % esc_lt(mf.group(2)))
        i += 1
        continue

    # 标题
    hm = re.match(r"^(#{1,4})\s+(.*)$", s)
    if hm:
        flush_para(); close_lists()
        level = len(hm.group(1))
        text = hm.group(2).strip()
        sec_counter[0] += 1
        sid = slug(sec_counter[0])
        if level == 1:
            cur_section[0] = sid
            toc.append((1, text, sid))
            htmlparts.append('<h1 id="%s" class="h-part">%s</h1>' % (sid, inline(text)))
        elif level == 2:
            cur_section[0] = sid
            toc.append((2, text, sid))
            htmlparts.append('<h2 id="%s">%s</h2>' % (sid, inline(text)))
            htmlparts.append('<div class="secstats" id="stats-%s">本节选择题：尚未作答</div>' % sid)
        elif level == 3:
            htmlparts.append('<h3 id="%s">%s</h3>' % (sid, inline(text)))
        else:
            htmlparts.append('<h4 id="%s">%s</h4>' % (sid, inline(text)))
        i += 1
        continue

    # 引用块
    if s.lstrip().startswith("> "):
        flush_para(); close_lists()
        quote = [s.lstrip()[2:]]
        i += 1
        while i < len(out_lines) and out_lines[i].lstrip().startswith("> "):
            quote.append(out_lines[i].lstrip()[2:])
            i += 1
        htmlparts.append('<blockquote>%s</blockquote>' % inline(" ".join(quote)))
        continue

    # 列表
    lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", ln)
    if lm:
        flush_para()
        indent = len(lm.group(1))
        ordered = bool(re.match(r"\d+\.", lm.group(2)))
        tag = "ol" if ordered else "ul"
        depth = 1 if indent >= 2 else 0
        target = depth + 1
        while len(list_stack) > target:
            t, _ = list_stack.pop()
            htmlparts.append("</%s>" % t)
        while len(list_stack) < target:
            htmlparts.append("<%s>" % tag)
            list_stack.append((tag, len(list_stack)))
        htmlparts.append("<li>%s</li>" % inline(lm.group(3)))
        i += 1
        continue

    # 普通段落行
    close_lists()
    para.append(s.strip())
    i += 1

flush_para(); close_lists(); flush_table()

content_html = "\n".join(htmlparts)

# ---------- 5. 渲染 quiz 为交互 HTML ----------
def quiz_section_map(html):
    secs = {}
    cur = "intro"
    order = []
    for m in re.finditer(r'id="stats-(s\d+)"|@@QUIZHTML:(\d+)@@', html):
        if m.group(1):
            cur = m.group(1)
        else:
            order.append((int(m.group(2)), cur))
    for qi, sid in order:
        secs[qi] = sid
    return secs

qsec = quiz_section_map(content_html)

def quiz_html(idx):
    q = quizzes[idx]
    sid = qsec.get(idx, "intro")
    q["section"] = sid
    cat = q["cat"]
    opts_html = []
    for k in ["A", "B", "C", "D"]:
        if k in q["opts"]:
            opts_html.append(
                '<button class="opt" data-k="%s" onclick="ans(this)">'
                '<b>%s.</b> %s</button>' % (k, k, inline(q["opts"][k])))
    exp = ('<div class="explain"><span class="ansline">✅ 正确答案：%s</span>'
           '<div class="expbody">%s</div></div>' % (q["ans"], inline(q["exp"])))
    return ('<div class="quiz" id="quiz-%s" data-correct="%s" data-section="%s">'
            '<div class="qhead"><span class="qtag tag-%s">%s</span>'
            '<span class="qtext">%s</span></div>'
            '<div class="opts">%s</div>%s</div>'
            % (q["id"], q["ans"], sid, TAGMAP.get(cat, "a"),
               cat, inline(q["q"]), "".join(opts_html), exp))

content_html = re.sub(r"@@QUIZHTML:(\d+)@@", lambda m: quiz_html(int(m.group(1))), content_html)

# ---------- 6. 生成 TOC ----------
toc_html = ['<nav id="toc"><div class="toc-title">目录</div><ul>']
for level, text, sid in toc:
    cls = "toc-part" if level == 1 else "toc-sec"
    toc_html.append('<li class="%s"><a href="#%s">%s</a></li>' % (cls, sid, re.sub("<.*?>", "", text)))
toc_html.append("</ul></nav>")
toc_html = "\n".join(toc_html)

# ---------- 7. CSS + JS（公开版稳定视觉与离线交互） ----------
CSS = r"""
:root{--orange:#D97757;--ink:#1f2430;--soft:#5b6472;--line:#e6e3dd;--bg:#faf8f5;--card:#fff;--right:#1f9d57;--wrong:#d8453a;}
*{box-sizing:border-box;}
html{-webkit-text-size-adjust:100%;}
body{margin:0;font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB","Source Han Sans SC",SimSun,sans-serif;
  color:var(--ink);background:var(--bg);line-height:1.85;font-size:16.5px;}
#wrap{display:flex;max-width:1180px;margin:0 auto;align-items:flex-start;}
#toc{position:sticky;top:0;max-height:100vh;overflow:auto;width:248px;flex:0 0 248px;
  padding:18px 12px 40px;border-right:1px solid var(--line);font-size:13.5px;background:var(--bg);}
.toc-title{font-weight:700;color:var(--orange);margin:6px 8px 12px;font-size:15px;}
#toc ul{list-style:none;margin:0;padding:0;}
#toc li{margin:1px 0;}
#toc a{display:block;text-decoration:none;color:var(--soft);padding:4px 8px;border-radius:6px;}
#toc a:hover{background:#f0ece5;color:var(--ink);}
.toc-part>a{font-weight:700;color:var(--ink);margin-top:8px;}
.toc-sec>a{padding-left:18px;font-size:13px;}
#main{flex:1 1 auto;min-width:0;padding:28px 38px 120px;}
h1.h-part{font-size:26px;border-bottom:3px solid var(--orange);padding-bottom:10px;margin:38px 0 18px;}
h2{font-size:21px;margin:34px 0 6px;padding-left:11px;border-left:5px solid var(--orange);}
h3{font-size:17.5px;margin:22px 0 6px;color:#2b3550;}
h4{font-size:16px;margin:16px 0 4px;color:var(--orange);}
p{margin:9px 0;}
strong{color:#b8492c;}
code{background:#f1ede6;border:1px solid #e3ddd2;border-radius:4px;padding:1px 5px;font-size:.92em;
  font-family:Consolas,"Courier New",monospace;color:#6a4d33;}
hr.sep{border:none;border-top:2px dashed var(--line);margin:30px 0;}
blockquote{margin:12px 0;padding:11px 16px;background:#fbf3ec;border-left:4px solid var(--orange);
  border-radius:0 8px 8px 0;color:#4a4034;font-size:15px;}
ul,ol{margin:8px 0;padding-left:26px;}
li{margin:4px 0;}
.tablewrap{overflow-x:auto;margin:14px 0;}
table{border-collapse:collapse;width:100%;font-size:14.5px;min-width:480px;}
th,td{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top;}
th{background:#f3ede4;color:#5a3b27;}
tr:nth-child(even) td{background:#fcfaf7;}
sub,sup{font-size:.72em;}
.vec{position:relative;display:inline-block;}
.vec::after{content:"\2192";position:absolute;left:0;right:0;top:-.4em;text-align:center;font-size:.6em;}
.fig{margin:16px 0;text-align:center;}
.fig img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:10px;
  background:#fff;padding:10px;box-shadow:0 1px 4px rgba(0,0,0,.05);cursor:zoom-in;}
#lightbox{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:200;
  cursor:zoom-out;align-items:center;justify-content:center;padding:14px;}
#lightbox.open{display:flex;}
#lightbox img{max-width:97%;max-height:92%;background:#fff;border-radius:8px;padding:8px;
  box-shadow:0 6px 30px rgba(0,0,0,.5);}
#lightbox .lbhint{position:fixed;top:14px;left:0;right:0;text-align:center;color:#fff;
  font-size:14px;opacity:.85;}
.fig figcaption{margin-top:7px;font-size:13.5px;color:var(--soft);}
.formula{margin:14px 0;padding:12px 16px;background:#fff;border:1px solid var(--line);
  border-radius:10px;text-align:center;font-size:18px;overflow-x:auto;}
.frac{display:inline-flex;flex-direction:column;vertical-align:middle;text-align:center;margin:0 .25em;}
.frac .fnum{padding:0 .5em 2px;}
.frac .fden{padding:2px .5em 0;border-top:1.6px solid var(--ink);}
.secstats{font-size:13px;color:var(--soft);background:#f3ede4;border-radius:6px;
  padding:5px 12px;margin:6px 0 4px;display:inline-block;}
.quiz{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:15px 18px;margin:15px 0;box-shadow:0 1px 3px rgba(0,0,0,.03);}
.qhead{margin-bottom:11px;}
.qtag{display:inline-block;font-size:11.5px;padding:2px 9px;border-radius:20px;margin-right:8px;
  color:#fff;vertical-align:middle;}
.tag-a{background:#5b8def;}.tag-b{background:#9a6ad8;}.tag-c{background:#e08a3c;}
.qtext{font-weight:600;}
.opts{display:flex;flex-direction:column;gap:8px;}
.opt{text-align:left;border:1.5px solid var(--line);background:#fcfbf9;border-radius:9px;
  padding:9px 13px;font-size:15px;cursor:pointer;font-family:inherit;color:var(--ink);
  transition:.12s;line-height:1.6;}
.opt:hover{border-color:var(--orange);background:#fbf3ec;}
.opt.right{border-color:var(--right);background:#e9f8ef;color:#15703f;font-weight:600;}
.opt.wrong{border-color:var(--wrong);background:#fdeceb;color:#a82b22;font-weight:600;}
.opt.disabled{cursor:default;}
.opt b{color:var(--orange);margin-right:4px;}
.opt.right b,.opt.wrong b{color:inherit;}
.explain{display:none;margin-top:11px;padding:11px 14px;background:#f6f4ef;border-radius:9px;
  font-size:14.5px;border-left:4px solid var(--right);}
.ansline{font-weight:700;color:var(--right);}
.expbody{margin-top:5px;color:#444;}
#pdfbtn{position:fixed;right:20px;bottom:86px;z-index:50;background:var(--orange);color:#fff;
  border:none;border-radius:30px;padding:13px 22px;font-size:15px;font-weight:700;cursor:pointer;
  box-shadow:0 4px 14px rgba(217,119,87,.4);font-family:inherit;}
#pdfbtn:hover{background:#c5633f;}
#prog{position:fixed;left:50%;transform:translateX(-50%);bottom:22px;z-index:50;background:#fff;
  border:1px solid var(--line);border-radius:30px;padding:9px 20px;font-size:13.5px;color:var(--soft);
  box-shadow:0 3px 12px rgba(0,0,0,.08);}
#prog b{color:var(--orange);}
.titlebox{margin:6px 0 10px;}
.titlebox h1{font-size:30px;margin:0 0 8px;border:none;}
.titlebox .sub{color:var(--soft);font-size:15px;}
.titlebox .note{margin-top:12px;font-size:13.5px;color:#8a8070;background:#f3ede4;
  padding:9px 14px;border-radius:8px;border-left:4px solid var(--orange);}
@media (max-width:820px){
  #wrap{flex-direction:column;width:100%;}
  #toc{position:static;width:100%;min-width:0;flex:none;max-height:none;border-right:none;
    border-bottom:1px solid var(--line);}
  #toc ul{column-count:2;column-gap:8px;}
  #main{width:100%;max-width:100%;min-width:0;padding:18px 16px 96px;}
  #main p,#main li,#main blockquote,.qtext,.opt,.expbody{overflow-wrap:anywhere;word-break:break-word;}
  .quiz{padding:13px 12px;}
  #pdfbtn{right:12px;bottom:16px;max-width:calc(100vw - 24px);padding:10px 14px;font-size:13px;}
  #prog{display:none;}
}
@media print{
  @page{size:A4;margin:15mm 14mm;}
  body{background:#fff;font-size:12pt;line-height:1.6;}
  #toc,#pdfbtn,#prog{display:none!important;}
  #wrap{display:block;max-width:none;}
  #main{padding:0;}
  .quiz{break-inside:avoid;box-shadow:none;border:1px solid #ccc;}
  .opt{cursor:default;border:1px solid #ddd;background:#fff!important;color:#000!important;font-weight:400!important;}
  .opt.right{border:1.5px solid #1f9d57;}
  .explain{display:block!important;background:#f4f4f4;border-left:3px solid #1f9d57;}
  h1.h-part,h2,h3{break-after:avoid;}
  .formula{break-inside:avoid;}
  .fig{break-inside:avoid;}
  .fig img{max-width:78%;box-shadow:none;}
  blockquote{break-inside:avoid;}
  a{color:#000;text-decoration:none;}
}
"""

JS = r"""
function ans(btn){
  var q=btn.closest('.quiz');
  if(q.dataset.done)return;
  q.dataset.done='1';
  var choose=btn.dataset.k, correct=q.dataset.correct;
  q.dataset.chosen=choose;
  var opts=q.querySelectorAll('.opt');
  for(var i=0;i<opts.length;i++){
    opts[i].classList.add('disabled');
    if(opts[i].dataset.k===correct)opts[i].classList.add('right');
  }
  if(choose!==correct)btn.classList.add('wrong');
  q.querySelector('.explain').style.display='block';
  updateStats(q.dataset.section);
  updateGlobal();
}
function updateStats(sec){
  var qs=document.querySelectorAll('.quiz[data-section="'+sec+'"]');
  if(!qs.length)return;
  var total=qs.length,done=0,right=0;
  for(var i=0;i<qs.length;i++){
    if(qs[i].dataset.done){done++;if(qs[i].dataset.chosen===qs[i].dataset.correct)right++;}
  }
  var el=document.getElementById('stats-'+sec);
  if(!el)return;
  if(done===0){el.textContent='本节选择题：尚未作答（共 '+total+' 题）';return;}
  var rate=Math.round(right/done*100);
  el.innerHTML='本节选择题：已答 '+done+'/'+total+'，正确 '+right+' 题，正确率 <b>'+rate+'%</b>';
}
function updateGlobal(){
  var qs=document.querySelectorAll('.quiz');
  var total=qs.length,done=0,right=0;
  for(var i=0;i<qs.length;i++){
    if(qs[i].dataset.done){done++;if(qs[i].dataset.chosen===qs[i].dataset.correct)right++;}
  }
  var rate=done?Math.round(right/done*100):0;
  document.getElementById('prog').innerHTML='答题进度 <b>'+done+'/'+total+'</b>　正确率 <b>'+rate+'%</b>';
}
document.addEventListener('DOMContentLoaded',updateGlobal);

/* ===== 图片灯箱:点击图片放大单独查看 ===== */
document.addEventListener('DOMContentLoaded',function(){
  var lb=document.createElement('div');lb.id='lightbox';
  var hint=document.createElement('div');hint.className='lbhint';hint.textContent='点击任意处关闭 · 可双指/滚轮缩放';
  var im=document.createElement('img');lb.appendChild(im);lb.appendChild(hint);document.body.appendChild(lb);
  function close(){lb.classList.remove('open');}
  lb.addEventListener('click',close);
  document.addEventListener('keydown',function(e){if(e.key==='Escape')close();});
  var imgs=document.querySelectorAll('.fig img');
  for(var i=0;i<imgs.length;i++){imgs[i].addEventListener('click',function(){im.src=this.src;lb.classList.add('open');});}
});
"""

titlebox = '<div class="titlebox"><h1>%s</h1>' % TITLE
if SUBTITLE:
    titlebox += '<div class="sub">%s</div>' % SUBTITLE
if NOTE:
    titlebox += '<div class="note">%s</div>' % NOTE
titlebox += "</div>"

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<style>%s</style>
</head>
<body>
<div id="wrap">
%s
<main id="main">
%s
%s
</main>
</div>
<button id="pdfbtn" onclick="window.print()">📄 导出 / 打印 PDF</button>
<div id="prog">答题进度 0/0　正确率 0%%</div>
<script>%s</script>
</body>
</html>""" % (TITLE, CSS, toc_html, titlebox, content_html, JS)

with io.open(os.path.join(PROJ, OUT_HTML), "w", encoding="utf-8", newline="\n") as f:
    f.write(HTML)

# ---------- 8. 题库 JSON ----------
bank = []
for q in quizzes:
    bank.append({
        "id": q["id"],
        "belong_to": q["belong"],
        "category": q["cat"],
        "question": q["q"],
        "options": ["%s. %s" % (k, q["opts"][k]) for k in ["A", "B", "C", "D"] if k in q["opts"]],
        "answer": q["ans"],
        "explanation": q["exp"],
    })
with io.open(os.path.join(PROJ, OUT_JSON), "w", encoding="utf-8", newline="\n") as f:
    json.dump(bank, f, ensure_ascii=False, indent=2)

# ---------- 9. 静态 .md 交付件 ----------
def md_inline(s):
    s = re.sub(r"\[\[frac:(.*?)\]\]", lambda m: "(" + ")/(".join(p.strip() for p in m.group(1).split("@@")) + ")", s)
    s = re.sub(r"\[\[disp:(.*?)\]\]", lambda m: m.group(1), s)
    return s

md = []
if TITLE:
    md.append("# " + TITLE + "\n")
if SUBTITLE:
    md.append("> " + SUBTITLE + "\n")
if NOTE:
    md.append("> " + NOTE + "\n")

for ln in out_lines:
    mq = re.match(r"^@@QUIZ:(\d+)@@$", ln.strip())
    if mq:
        q = quizzes[int(mq.group(1))]
        md.append("")
        md.append("**【检验题 · %s】** %s" % (q["cat"], md_inline(q["q"])))
        for k in ["A", "B", "C", "D"]:
            if k in q["opts"]:
                md.append("- %s. %s" % (k, md_inline(q["opts"][k])))
        md.append("　**✅ 正确答案：%s**　%s" % (q["ans"], md_inline(q["exp"])))
        md.append("")
        continue
    md.append(md_inline(ln))

with io.open(os.path.join(PROJ, OUT_MD), "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(md))

print("OK  quizzes=%d  html=%dKB  -> %s" % (len(quizzes), len(HTML) // 1024, OUT_HTML))
print("sections in TOC:", len([t for t in toc if t[0] == 2]))

