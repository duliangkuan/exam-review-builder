# -*- coding: utf-8 -*-
"""校验期末复习资料项目的结构、来源、题库与离线边界。"""

import argparse
import json
import re
import sys
from pathlib import Path


SOURCE_ID = re.compile(r"^S\d{2,}$")
SOURCE_CITE = re.compile(r"\[S\d{2,}\s+[^\]]+\]")
URL_OR_NETWORK = re.compile(
    r"https?://|fetch\s*\(|XMLHttpRequest|WebSocket|api[_ -]?key|bearer\s+",
    re.IGNORECASE,
)


def load_json(path: Path, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"无法读取 JSON {path.name}：{exc}")
        return None


def parse_quizzes(text: str) -> list[dict]:
    quizzes = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^::: quiz\s+(.*)$", lines[index])
        if not match:
            index += 1
            continue
        attrs = match.group(1)
        item = {
            "id": (re.search(r"\bid=(\S+)", attrs) or [None, ""])[1],
            "cat": (re.search(r"\bcat=(.*)$", attrs) or [None, ""])[1].strip(),
            "options": {},
            "answer": "",
            "explanation": [],
        }
        index += 1
        while index < len(lines) and lines[index].strip() != ":::":
            line = lines[index]
            if re.match(r"^[ABCD] ", line):
                item["options"][line[0]] = line[2:].strip()
            elif line.startswith("= "):
                item["answer"] = line[2:].strip()
            elif line.startswith("> "):
                item["explanation"].append(line[2:].strip())
            index += 1
        quizzes.append(item)
        index += 1
    return quizzes


def main() -> int:
    parser = argparse.ArgumentParser(description="校验期末复习资料项目")
    parser.add_argument("course_dir")
    args = parser.parse_args()
    root = Path(args.course_dir).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    required = [
        "subject.json",
        "sources.json",
        "verification.json",
        "content.md",
    ]
    for name in required:
        if not (root / name).is_file():
            errors.append(f"缺少必需文件：{name}")
    if errors:
        print(json.dumps({"status": "error", "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1

    subject = load_json(root / "subject.json", errors)
    sources_doc = load_json(root / "sources.json", errors)
    verification = load_json(root / "verification.json", errors)
    content = (root / "content.md").read_text(encoding="utf-8")

    if subject:
        cats = subject.get("quiz_cats")
        if not isinstance(cats, list) or len(cats) != 3 or len(set(cats)) != 3:
            errors.append("subject.json.quiz_cats 必须是三个不重复的字符串")
        for field, default in (("out_html", "复习资料.html"), ("out_json", "题库.json"), ("out_md", "复习资料.md")):
            output = root / subject.get(field, default)
            if not output.is_file():
                errors.append(f"缺少构建产物：{output.name}")

    source_ids: set[str] = set()
    if sources_doc:
        items = sources_doc.get("sources")
        if not isinstance(items, list) or not items:
            errors.append("sources.json.sources 至少登记一份材料")
        else:
            for item in items:
                sid = item.get("id", "") if isinstance(item, dict) else ""
                if not SOURCE_ID.match(sid):
                    errors.append(f"来源 ID 不合法：{sid!r}")
                elif sid in source_ids:
                    errors.append(f"来源 ID 重复：{sid}")
                source_ids.add(sid)
                if isinstance(item, dict) and re.match(r"^[A-Za-z]:[\\/]", item.get("local_file", "")):
                    errors.append(f"来源 {sid} 写入了本机绝对路径")

    cited_ids = set(re.findall(r"\[(S\d{2,})\s+[^\]]+\]", content))
    unknown = sorted(cited_ids - source_ids)
    if unknown:
        errors.append("正文引用了未登记来源：" + ", ".join(unknown))

    headings = list(re.finditer(r"(?m)^###\s+.+$", content))
    for idx, heading in enumerate(headings):
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(content)
        block = content[heading.start():end]
        if not SOURCE_CITE.search(block) and "补充知识" not in block:
            errors.append(f"考点缺少来源或补充标记：{heading.group(0)}")

    quizzes = parse_quizzes(content)
    quiz_ids: set[str] = set()
    cats = set(subject.get("quiz_cats", [])) if subject else set()
    for quiz in quizzes:
        qid = quiz["id"]
        if not qid or qid in quiz_ids:
            errors.append(f"选择题 ID 缺失或重复：{qid!r}")
        quiz_ids.add(qid)
        if set(quiz["options"]) != {"A", "B", "C", "D"}:
            errors.append(f"{qid} 必须恰好有 A-D 四个选项")
        if quiz["answer"] not in {"A", "B", "C", "D"}:
            errors.append(f"{qid} 答案必须是 A-D")
        if quiz["cat"] not in cats:
            errors.append(f"{qid} 类别不在 subject.json.quiz_cats 中")
        explanation = " ".join(quiz["explanation"])
        if "依据：" not in explanation or not SOURCE_CITE.search(explanation):
            errors.append(f"{qid} 解析缺少有效的“依据：”来源")
        if "核验：" not in explanation:
            errors.append(f"{qid} 解析缺少“核验：”说明")

    checks = {}
    if verification:
        for check in verification.get("checks", []):
            if isinstance(check, dict) and check.get("id"):
                checks[check["id"]] = check
        if verification.get("status") != "passed":
            errors.append("verification.json.status 尚未为 passed")
        if verification.get("unresolved"):
            errors.append("verification.json 仍有 unresolved 项")
    for qid in sorted(quiz_ids):
        check = checks.get(qid)
        if not check:
            errors.append(f"{qid} 未进入 verification.json")
        elif check.get("first_pass") != "passed" or check.get("second_pass") != "passed":
            errors.append(f"{qid} 尚未完成两次核验")

    if subject:
        html_path = root / subject.get("out_html", "复习资料.html")
        if html_path.is_file():
            html = html_path.read_text(encoding="utf-8")
            network_hits = sorted(set(match.group(0) for match in URL_OR_NETWORK.finditer(html)))
            if network_hits:
                errors.append("HTML 含网络或凭据相关能力：" + ", ".join(network_hits))
            if "#D97757" not in html:
                warnings.append("HTML 未发现默认陶土橙主色 #D97757")

        json_path = root / subject.get("out_json", "题库.json")
        if json_path.is_file():
            bank = load_json(json_path, errors)
            if isinstance(bank, list) and len(bank) != len(quizzes):
                errors.append("题库 JSON 数量与 content.md 中的 quiz 数量不一致")

    result = {"status": "passed" if not errors else "error", "errors": errors, "warnings": warnings,
              "summary": {"sources": len(source_ids), "topics": len(headings), "quizzes": len(quizzes)}}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
