"""Phase 3 Build (Core step: build the product).

Generates a small, tested Python CLI for the validated idea:
  product/<slug>/
    <pkg>/core.py      model-written `process(text: str) -> str`
    <pkg>/cli.py       reads a file or stdin, prints the result, exit codes
    tests/test_core.py model-proposed examples + scaffold tests
    README.md          user docs
    pyproject.toml
The gate is the test run. Model code runs only inside this container, in a
subprocess with a timeout. If the model is STUBBED or keeps failing, the core
is a labelled stub and the gate says so.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap

from agents.base import Agent

STUB_CORE = '''"""Core feature. STUBBED: not implemented by a model in this run."""

STUBBED = True


def process(text: str) -> str:
    """STUBBED: returns the input unchanged. Replace with the real feature."""
    return text
'''

CLI = '''"""Command-line entry point."""
import argparse
import sys

from {pkg}.core import process


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="{slug}", description={summary!r})
    p.add_argument("path", nargs="?", help="input file (default: stdin)")
    args = p.parse_args(argv)
    text = open(args.path, encoding="utf-8").read() if args.path else sys.stdin.read()
    out = process(text)
    sys.stdout.write(out if out.endswith("\\n") else out + "\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

SCAFFOLD_TESTS = '''import subprocess
import sys

from {pkg}.core import process


def test_process_returns_text():
    assert isinstance(process(""), str)


def test_cli_help_runs():
    r = subprocess.run([sys.executable, "-m", "{pkg}.cli", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
'''


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:30].strip("-") or "mvp-tool")


class Builder(Agent):
    role = "builder"

    def build(self) -> dict:
        opp = self.ctx.state["opportunities"][0]
        prev = self.ctx.state.get("build") or {}
        attempts = int(prev.get("attempts", 0))
        name = slugify(self.ctx.state.get("product_name") or opp.get("keywords") or opp["idea"])
        pkg = name.replace("-", "_")
        root = os.path.join(self.ctx.run_dir, "product", name)
        os.makedirs(os.path.join(root, pkg), exist_ok=True)
        os.makedirs(os.path.join(root, "tests"), exist_ok=True)

        stub = {"summary": opp["idea"][:120], "core_code": STUB_CORE, "examples": []}
        feedback = prev.get("last_error", "")
        data, res = self.ask_json(
            "write_mvp_core",
            f"Idea: {opp['idea']}\n\nWrite the core of a tiny Python 3 CLI tool for this idea. Return JSON with: "
            "summary (one line), core_code (a complete Python module, standard library only, defining "
            "`def process(text: str) -> str` that implements the main feature on the input text), examples (3 objects "
            "with input and expected_output strings that `process` must satisfy exactly). No network, no file writes."
            + (f"\n\nYour previous attempt failed its tests:\n{feedback[-1500:]}" if feedback else ""),
            stub_obj=stub,
        )
        core = data.get("core_code") or STUB_CORE
        if "def process" not in core:
            core, res.stubbed = STUB_CORE, True
        core_stubbed = res.stubbed or core == STUB_CORE
        examples = [e for e in (data.get("examples") or []) if isinstance(e, dict) and "input" in e
                    and "expected_output" in e][:5]
        summary = str(data.get("summary") or stub["summary"])

        files = {
            os.path.join(pkg, "__init__.py"): '__version__ = "0.1.0"\n',
            os.path.join(pkg, "core.py"): core,
            os.path.join(pkg, "cli.py"): CLI.format(pkg=pkg, slug=name, summary=summary),
            os.path.join("tests", "test_scaffold.py"): SCAFFOLD_TESTS.format(pkg=pkg),
            "pyproject.toml": textwrap.dedent(f"""\
                [project]
                name = "{name}"
                version = "0.1.0"
                description = {json.dumps(summary)}
                license = {{text = "MIT"}}
                requires-python = ">=3.9"

                [project.scripts]
                {name} = "{pkg}.cli:main"
                """),
        }
        if examples:
            cases = ",\n    ".join(repr((e["input"], e["expected_output"])) for e in examples)
            files[os.path.join("tests", "test_examples.py")] = (
                f"import pytest\n\nfrom {pkg}.core import process\n\nCASES = [\n    {cases},\n]\n\n\n"
                "@pytest.mark.parametrize('given,expected', CASES)\n"
                "def test_example(given, expected):\n    assert process(given) == expected\n")
        for rel, content in files.items():
            with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
                f.write(content)

        attempts += 1
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                           cwd=root, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PYTHONPATH": root})
        passed = r.returncode == 0
        tail = (r.stdout + r.stderr)[-2000:]
        self.log("run_mvp_tests", model=None, outcome="pass" if passed else "fail", detail=tail.splitlines()[-1:] or None)
        build = {"name": name, "pkg": pkg, "root": root, "attempts": attempts, "passed": passed,
                 "core_stubbed": core_stubbed, "summary": summary, "last_error": "" if passed else tail,
                 "n_examples": len(examples)}
        self.ctx.state["build"] = build

        report = [
            "# Phase 3 / Step 1: MVP build",
            "",
            f"**Product:** `{name}`: {summary}",
            f"**Core feature:** {'STUBBED (no model code this run)' if core_stubbed else 'written by the model'}",
            f"**Test result:** {'PASS' if passed else 'FAIL'} (attempt {attempts})",
            "",
            "## Files",
            "",
            *[f"- `{name}/{rel}`" for rel in sorted(files)],
            "",
            "## core.py",
            "",
            "```python",
            core.strip(),
            "```",
            "",
            "## pytest output (tail)",
            "",
            "```",
            tail.strip()[-1200:],
            "```",
        ]
        self.ctx.write_output("phase3_step1_mvp_build.md", "\n".join(report), stubbed=core_stubbed)
        self.user_docs(build)
        return build

    def user_docs(self, build: dict) -> None:
        stub = (f"## Install\n\n```bash\npip install .\n```\n\n## Use\n\n```bash\n{build['name']} input.txt\n"
                f"cat input.txt | {build['name']}\n```\n\n## What it does\n\n{build['summary']}\n\n"
                "## Limits\n\nEarly version. Report problems in the project's issue tracker.")
        res = self.ask("write_user_docs",
                       f"Write short user docs (markdown: Install, Use, What it does, Limits) for CLI `{build['name']}`: "
                       f"{build['summary']}. Install with `pip install .`. Be factual; no claims about results.",
                       stub_text=stub)
        doc = f"# {build['name']}\n\n" + res.text
        if build["core_stubbed"]:
            doc += "\n\n> STUBBED: the core feature in this build is a placeholder.\n"
        with open(os.path.join(build["root"], "README.md"), "w", encoding="utf-8") as f:
            f.write(doc)
        self.ctx.write_output("phase3_step2_user_docs.md", "# Phase 3 / Step 2: User docs\n\n" + doc,
                              stubbed=res.stubbed)
