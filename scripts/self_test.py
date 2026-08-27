# -*- coding: utf-8 -*-
"""在临时目录运行公开构建器的黄金样例与失败样例。"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str], expect: int = 0) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", env=env)
    if result.returncode != expect:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"命令退出码 {result.returncode}，预期 {expect}: {command}")
    return result


def main() -> None:
    scripts = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="exam_review_skill_") as temp:
        course = Path(temp) / "course"
        run([sys.executable, str(scripts / "init_project.py"), str(course)])
        run([sys.executable, str(scripts / "assemble.py"), str(course)])
        run([sys.executable, str(scripts / "build.py"), str(course)])
        valid = run([sys.executable, str(scripts / "validate_project.py"), str(course)])
        payload = json.loads(valid.stdout)
        assert payload["status"] == "passed"
        html = (course / "复习资料.html").read_text(encoding="utf-8")
        assert "#D97757" in html
        assert "http://" not in html and "https://" not in html
        assert "fetch(" not in html

        # 反例：考点来源被删除后必须失败。
        content_path = course / "content.md"
        content_path.write_text(content_path.read_text(encoding="utf-8").replace("[S01 第一节]", "[BROKEN]"), encoding="utf-8")
        invalid = run([sys.executable, str(scripts / "validate_project.py"), str(course)], expect=1)
        failed = json.loads(invalid.stdout)
        assert failed["status"] == "error"
        assert any("考点缺少来源" in item for item in failed["errors"])

    print("SELF_TEST_OK：黄金样例通过，缺少来源的反例被正确拒绝。")


if __name__ == "__main__":
    main()
