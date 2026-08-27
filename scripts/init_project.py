# -*- coding: utf-8 -*-
"""初始化一个可由本 Skill 构建的科目目录。仅使用 Python 标准库。"""

import argparse
import json
from pathlib import Path


def write_new(path: Path, text: str) -> None:
    if path.exists():
        raise SystemExit(f"拒绝覆盖已有文件：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化期末复习资料科目目录")
    parser.add_argument("course_dir", help="新建或空的科目目录")
    parser.add_argument("--title", default="示例课程 · 期末复习")
    args = parser.parse_args()

    root = Path(args.course_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    content = root / "content"
    figures = root / "figures"
    content.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)

    subject = {
        "title": args.title,
        "out_html": "复习资料.html",
        "out_json": "题库.json",
        "out_md": "复习资料.md",
        "out_pdf": "复习资料.pdf",
        "quiz_cats": ["概念辨析", "公式理解", "步骤判断"],
    }
    sources = {
        "course": args.title.replace(" · 期末复习", ""),
        "scope_note": "请填写考试范围与明确排除项",
        "sources": [
            {
                "id": "S01",
                "type": "course_material",
                "title": "请替换为材料名称",
                "edition": "",
                "local_file": "请填写相对文件名",
                "locator": "章节或页码",
                "coverage": "请填写覆盖范围",
                "rights": "用户提供，仅本地整理",
            }
        ],
    }
    verification = {
        "status": "passed",
        "checks": [
            {
                "id": "ch01-q01",
                "kind": "quiz",
                "source": "S01 第一节",
                "first_pass": "passed",
                "second_pass": "passed",
                "notes": "初始化样例；替换真实内容后重新核验",
            }
        ],
        "unresolved": [],
    }

    write_new(root / "subject.json", json.dumps(subject, ensure_ascii=False, indent=2) + "\n")
    write_new(root / "sources.json", json.dumps(sources, ensure_ascii=False, indent=2) + "\n")
    write_new(root / "verification.json", json.dumps(verification, ensure_ascii=False, indent=2) + "\n")
    write_new(
        content / "_header.md",
        "＠meta 标题=" + args.title + "\n"
        "＠meta 副标题=依据用户提供的课程材料整理 · 初始化样例\n"
        "＠meta 说明=替换示例内容后，请更新来源账本与核验记录。\n\n"
        "# 开篇：怎么使用这份资料\n\n"
        "## 材料与范围\n\n"
        "当前为初始化样例。正式制作时写清教材版本、考试范围、真题样本数量和缺口。\n",
    )
    write_new(
        content / "ch01.md",
        "# 第一部分　课程基础\n\n"
        "## 第一章　示例章节\n\n"
        "### 1. 示例考点\n\n"
        "📖 [S01 第一节]\n\n"
        "**一句话认识**：这是用于验证构建流程的示例考点。\n\n"
        "> 🧠 大白话：正式制作时，把抽象概念换成不改变定义的具体解释。\n\n"
        "**⚡ 解题步骤**\n\n1. 回到来源定位。\n2. 写出条件与结论。\n\n"
        "**⚠️ 易错反例**：不要把没有来源的补充内容写成教材原话。\n\n"
        "::: quiz id=ch01-q01 belong=第一章 cat=概念辨析\n"
        "Q 制作指定教材的复习资料时，下面哪种做法正确？\n"
        "A 没有页码时估一个页码\nB 把高频写成今年必考\n"
        "C 结论回查来源并标出定位\nD 直接照抄未经核验的答案\n"
        "= C\n"
        "> 解析：C 保留了可追溯性；其余做法都会制造不确定性或错误承诺。\n"
        "> 依据：[S01 第一节]\n"
        "> 核验：已从空白状态重解；第二次核验通过。\n:::\n",
    )
    print(f"项目已初始化：{root}")
    print("下一步：替换示例材料与内容，然后运行 assemble.py、build.py、validate_project.py。")


if __name__ == "__main__":
    main()
