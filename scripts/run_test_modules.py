"""Isolate legacy tests that can shut down the process or hang on real services."""

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default=".validation/suite")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    def run(path):
        name = path.stem
        home = output / name
        home.mkdir(exist_ok=True)
        code = (
            "from pathlib import Path; "
            f"Path.home=classmethod(lambda cls: Path({str(home)!r})); "
            "import pytest; raise SystemExit(pytest.main(['-q','--disable-warnings','--tb=short',"
            f"{str(path)!r}]))"
        )
        try:
            process = subprocess.run(
                [sys.executable, "-c", code],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            text = process.stdout + process.stderr
            counts = {
                key: sum(
                    map(
                        int,
                        re.findall(
                            r"(\d+) " + key + r"\b",
                            text.split("short test summary info")[-1].split("====")[-1],
                        ),
                    )
                )
                for key in ("passed", "failed", "skipped", "errors")
            }
            # Summary is always the last line with a duration, when pytest exits normally.
            summary = next(
                (
                    line
                    for line in reversed(text.splitlines())
                    if re.search(r"\d+ (passed|failed|skipped|error).* in ", line)
                ),
                "",
            )
            counts = {
                key: int((re.search(r"(\d+) " + key + r"\b", summary) or [None, 0])[1])
                for key in ("passed", "failed", "skipped")
            }
            result = dict(module=name, exit_code=process.returncode, summary=summary, **counts)
            if not summary:
                result["abnormal_exit"] = True
        except subprocess.TimeoutExpired as e:
            text = (
                (e.stdout or b"").decode("utf-8", errors="replace")
                if isinstance(e.stdout, bytes)
                else (e.stdout or "")
            )
            result = dict(module=name, timeout=True)
        (output / (name + ".log")).write_text(text, encoding="utf-8")
        print(json.dumps(result), flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, sorted((root / "tests").glob("test_*.py"))))
    report = dict(
        results=results,
        passed=sum(r.get("passed", 0) for r in results),
        failed=sum(r.get("failed", 0) for r in results),
        skipped=sum(r.get("skipped", 0) for r in results),
    )
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}))
    raise SystemExit(1 if any(r.get("exit_code", 1) != 0 for r in results) else 0)


if __name__ == "__main__":
    main()
