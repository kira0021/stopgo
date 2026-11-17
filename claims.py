"""Claims audit: every market claim cites a URL or is labelled.

Run on a run's outputs before they are exported (orchestrator.export refuses on
any problem) and on the committed outputs/ in the smoke tests.

A "claim line" is any bullet in a file that makes market or business claims.
It passes if it contains a URL or one of the honest labels below.
"""
from __future__ import annotations

import os
import re
import sys

LABELS = ("http://", "https://", "ASSUMPTION", "founder-reported", "founder-cited", "Founder-cited",
          "unavailable", "MOCKED", "DEMO FIXTURE")
# Files whose bullets are market or business claims.
CLAIM_FILES = re.compile(r"phase1_step[12]_|phase2_step1_|phase4_step1_|phase6_step1_")


def audit_text(text: str) -> list[str]:
    bad = []
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s[:2] in ("- ", "* ") and not any(lbl in s for lbl in LABELS):
            bad.append(f"line {n}: {s[:120]}")
    return bad


def audit_dir(path: str) -> dict[str, list[str]]:
    problems = {}
    for name in sorted(os.listdir(path)):
        if name.endswith(".md") and CLAIM_FILES.search(name):
            with open(os.path.join(path, name), encoding="utf-8") as f:
                bad = audit_text(f.read())
            if bad:
                problems[name] = bad
    return problems


def summary(path: str) -> dict:
    """Counts for the run report: sourced vs. labelled claim lines."""
    sourced = assumed = other = 0
    for name in sorted(os.listdir(path)):
        if name.endswith(".md") and CLAIM_FILES.search(name):
            for line in open(os.path.join(path, name), encoding="utf-8"):
                s = line.strip()
                if s[:2] not in ("- ", "* "):
                    continue
                if "http" in s:
                    sourced += 1
                elif "ASSUMPTION" in s:
                    assumed += 1
                else:
                    other += 1
    return {"sourced": sourced, "assumption": assumed, "founder_reported_or_unavailable": other}


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "outputs"
    probs = audit_dir(target)
    for f, lines in probs.items():
        for l in lines:
            print(f"{f}: {l}")
    print("claims audit:", "FAIL" if probs else "PASS", summary(target))
    sys.exit(1 if probs else 0)
