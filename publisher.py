"""Every outward action (publish / send / spend) lives here, behind @gated.

All of them are MOCKED in this prototype: "publishing" copies the approved
content into runs/<id>/published/ and nothing leaves the machine. The gate
still runs, so swapping in a real integration later cannot skip approval.
"""
from __future__ import annotations

import os

from approval import gated

MOCKED = True


def _write(state: dict, name: str, content: str) -> str:
    d = os.path.join(state["run_dir"], "published")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


@gated("publish_landing_page")
def publish_landing_page(state: dict, approval_id: str, payload: str) -> dict:
    return {"mocked": True, "where": _write(state, "landing_page.html", payload)}


@gated("publish_store_page")
def publish_store_page(state: dict, approval_id: str, payload: str) -> dict:
    return {"mocked": True, "where": _write(state, "store_page.html", payload)}


@gated("post_launch_posts")
def post_launch_posts(state: dict, approval_id: str, payload: str) -> dict:
    return {"mocked": True, "where": _write(state, "launch_posts.md", payload)}


@gated("spend")
def spend(state: dict, approval_id: str, payload: dict) -> dict:
    """Placeholder for any spend (e.g. a domain). MOCKED: never spends."""
    return {"mocked": True, "spent_usd": 0, "requested": payload}
