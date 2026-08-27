# -*- coding: utf-8 -*-
"""使用本机 Chromium 系浏览器把离线 HTML 打印成 PDF。"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def browser_candidates() -> list[Path]:
    candidates: list[Path] = []
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    if sys.platform == "win32":
        for root in filter(None, [
            Path.home().drive + "\\Program Files",
            Path.home().drive + "\\Program Files (x86)",
            str(Path.home() / "AppData/Local"),
        ]):
            base = Path(root)
            candidates.extend([
                base / "Google/Chrome/Application/chrome.exe",
                base / "Microsoft/Edge/Application/msedge.exe",
                base / "Chromium/Application/chrome.exe",
            ])
    elif sys.platform == "darwin":
        candidates.extend([
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ])
    return candidates


def find_browser() -> Path | None:
    for candidate in browser_candidates():
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="把离线复习 HTML 打印成 PDF")
    parser.add_argument("course_dir")
    args = parser.parse_args()
    root = Path(args.course_dir).expanduser().resolve()
    config_path = root / "subject.json"
    if not config_path.is_file():
        print(f"ERROR：缺少 {config_path}", file=sys.stderr)
        return 1
    config = json.loads(config_path.read_text(encoding="utf-8"))
    title = config.get("title", "期末复习资料")
    source = root / config.get("out_html", title + ".html")
    output = root / config.get("out_pdf", source.stem + ".pdf")
    if not source.is_file():
        print(f"ERROR：HTML 不存在，请先运行 build.py：{source}", file=sys.stderr)
        return 1

    browser = find_browser()
    if browser is None:
        print("PDF_SKIPPED：未找到 Chrome、Chromium 或 Edge。HTML 已可离线使用；也可在浏览器中选择“打印为 PDF”。")
        return 2

    with tempfile.TemporaryDirectory(prefix="exam_review_pdf_") as temp:
        temp_dir = Path(temp)
        temp_html = temp_dir / "document.html"
        temp_pdf = temp_dir / "document.pdf"
        profile = temp_dir / "profile"
        shutil.copyfile(source, temp_html)
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=20000",
            f"--print-to-pdf={temp_pdf}",
            temp_html.as_uri(),
        ]
        try:
            result = subprocess.run(command, timeout=300, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print("ERROR：浏览器打印超过 300 秒，已停止。HTML 不受影响。", file=sys.stderr)
            return 1
        if result.returncode != 0:
            print("ERROR：浏览器打印失败。", file=sys.stderr)
            print(result.stderr[-1000:], file=sys.stderr)
            return 1
        if not temp_pdf.is_file() or temp_pdf.stat().st_size <= 50 * 1024:
            size = temp_pdf.stat().st_size if temp_pdf.is_file() else 0
            print(f"ERROR：生成的 PDF 只有 {size} 字节，可能是错误页，未采用。", file=sys.stderr)
            return 1
        shutil.copyfile(temp_pdf, output)

    print(f"PDF_OK：{output}（{output.stat().st_size / 1048576:.2f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
