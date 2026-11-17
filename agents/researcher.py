"""Phase 1 Discover, steps 1-2: find and score opportunities, define the market."""
from __future__ import annotations

import math
import os

import evidence
import gates
from agents.base import Agent, label_claims


def _keywords_from_idea(idea: str) -> str:
    stop = {"a", "an", "the", "for", "to", "of", "and", "that", "which", "with", "tool", "cli", "app", "small",
            "simple", "who", "their", "in", "on", "by", "is", "it", "helps", "help", "developers", "teams"}
    words = [w.strip(".,:;()\"'").lower() for w in idea.split()]
    return " ".join([w for w in words if w and w not in stop][:4]) or idea[:40]


def score_candidate(pub: dict, fit: float) -> tuple[float | None, str]:
    """Transparent score in [0,1]; None when no public evidence is available."""
    so = (pub.get("stackoverflow") or {}).get("count")
    stars = (pub.get("github") or {}).get("top_stars")
    if so is None and stars is None:
        return None, "no public evidence available; not scored"
    pain = min(math.log10(1 + so) / 3, 1.0) if so is not None else 0.5
    crowd = min(math.log10(1 + stars) / 5, 1.0) if stars is not None else 0.5
    score = round(0.5 * pain + 0.2 * (1 - crowd) + 0.3 * fit, 2)
    return score, f"0.5*pain({pain:.2f}) + 0.2*(1-crowding {crowd:.2f}) + 0.3*fit({fit:.2f})"


class Researcher(Agent):
    role = "researcher"

    def find_opportunities(self) -> dict:
        b = self.ctx.brief
        idea = b["idea"]
        stub = {
            "sharpened_idea": idea,
            "product_name": "-".join(_keywords_from_idea(idea).split()[:2]),
            "keywords": _keywords_from_idea(idea),
            "alternatives": [
                {"idea": f"{idea} (narrowed to one language ecosystem)", "keywords": _keywords_from_idea(idea),
                 "why": "Smaller scope ships faster for a solo founder."},
                {"idea": f"Hosted check for: {idea}", "keywords": _keywords_from_idea(idea) + " ci",
                 "why": "Teams may prefer a CI step over a local CLI."},
            ],
        }
        data, res = self.ask_json(
            "find_opportunities",
            f"{self.ctx.brief_text()}\n\nReturn JSON with keys sharpened_idea, keywords (a 2-4 word search phrase "
            "a developer would type when facing the problem), alternatives (exactly 2 items, each with idea, "
            "keywords, why). Alternatives must stay digital developer tools.",
            stub_obj=stub,
        )
        if res.stubbed:
            self.ctx.stubbed_steps.add("phase1_step1")
        self.ctx.state["product_name"] = str(data.get("product_name") or stub["product_name"])[:30]
        fit, fit_notes = gates.founder_fit(b)
        candidates = [{"idea": data.get("sharpened_idea") or idea, "keywords": data.get("keywords") or stub["keywords"],
                       "why": "Founder's starting idea (sharpened)."}]
        candidates += [a for a in (data.get("alternatives") or [])[:2] if isinstance(a, dict) and a.get("idea")]

        run_dir = self.ctx.run_dir
        rows, all_sources = [], []
        for i, c in enumerate(candidates):
            kw = (c.get("keywords") or _keywords_from_idea(c["idea"]))[:60]
            pub = evidence.gather(kw, cache_path=os.path.join(run_dir, f"evidence_{i}.json"))
            if i == 0:
                self.ctx.state.setdefault("evidence", {})["public"] = pub
            score, formula = score_candidate(pub, fit)
            c.update({"keywords": kw, "public": pub, "score": score, "formula": formula})
            rows.append(c)
            all_sources += evidence.source_urls(pub)
        all_sources += [a["url"] for a in (b.get("known_alternatives") or []) if isinstance(a, dict) and a.get("url")]
        self.log("score_opportunities", sources=all_sources, model=None)
        self.ctx.state["opportunities"] = [{k: v for k, v in r.items() if k != "public"} for r in rows]

        def cell(src: dict, key: str) -> str:
            if src.get("status") == "ok":
                return f"[{src.get(key)}]({src['url']})"
            return "unavailable"

        lines = [
            "# Phase 1 / Step 1: Opportunities",
            "",
            f"**Founder's idea:** {idea}",
            "",
            "Scores use only numbers fetched from the linked public sources plus the founder-fit rubric. "
            "A source that could not be reached shows `unavailable`; no number is filled in.",
            "",
            "| # | Candidate | Search phrase | Stack Overflow questions | Top free alternative (GitHub stars) | Score |",
            "|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(rows, 1):
            gh = r["public"]["github"]
            top = gh["top"][0] if gh.get("top") else None
            alt = f"[{top['name']}]({top['url']}) ({top['stars']})" if top else cell(gh, "top_stars")
            lines.append(f"| {i} | {r['idea']} | `{r['keywords']}` | {cell(r['public']['stackoverflow'], 'count')} | "
                         f"{alt} | {r['score'] if r['score'] is not None else 'n/a'} |")
        lines += ["", "**Score formula:** " + rows[0]["formula"], "",
                  "## Why these alternatives", ""]
        for r in rows:
            lines.append(f"- ASSUMPTION: {r['idea']}: {r.get('why', '')}")
        lines += ["", "## Founder fit (rubric, 0-1)", "", f"Score: **{fit}**", ""]
        lines += [f"- founder-reported brief: {n}" for n in fit_notes]
        alts = [a for a in (b.get("known_alternatives") or []) if isinstance(a, dict) and a.get("url")]
        lines += ["", "## Founder-cited sources (from the brief; not fetched or verified by StopGo)", ""]
        lines += [f"- {a.get('name')}: {a.get('note', '')} ({a['url']})" for a in alts] or \
                 ["- None given in the brief."]
        hn = rows[0]["public"]["hackernews"]
        lines += ["", "## Hacker News discussion (starting idea)", ""]
        if hn.get("status") == "ok":
            lines.append(f"- {hn['count']} matching stories: {hn['url']}")
            lines += [f"- {t['title']} ({t['points']} points): {t['url']}" for t in hn.get("top", [])[:3]]
        else:
            lines.append(f"- Hacker News unavailable for this run ({hn.get('status')}); not used in scoring. "
                         f"Search: {hn['url']}")
        self.ctx.write_output("phase1_step1_opportunities.md", "\n".join(lines),
                              stubbed="phase1_step1" in self.ctx.stubbed_steps)
        return {"candidates": rows, "fit": fit}

    def define_market(self) -> None:
        opp = self.ctx.state["opportunities"][0]
        stub = ("## Target customer\n- Solo developers and small teams described in the brief.\n"
                "## Where they are\n- GitHub issues, Stack Overflow and developer forums.\n"
                "## Market size\n- Not estimated: no sourced figure available for this run.\n"
                "## Existing alternatives\n- See the GitHub column in phase1_step1_opportunities.md.")
        cited = [a for a in (self.ctx.brief.get("known_alternatives") or []) if isinstance(a, dict) and a.get("url")]
        res = self.ask(
            "define_market",
            f"{self.ctx.brief_text()}\nSharpened idea: {opp['idea']}\n\nWrite markdown with sections: Target customer, "
            "Where they are, Market size, Existing alternatives. Use bullets. Every bullet that is not backed by a "
            "URL must begin with 'ASSUMPTION:'. Do not invent statistics. Sources you may cite: "
            + "; ".join(f"{a.get('name')} {a['url']}" for a in cited),
            stub_text=stub,
            sources=[a["url"] for a in cited],
        )
        pub = self.ctx.state.get("evidence", {}).get("public", {})
        gh = pub.get("github") or {}
        sourced = ["", "## Sourced signals", ""]
        if gh.get("status") == "ok":
            sourced.append(f"- {gh['count']} public GitHub repositories match `{pub['keywords']}`: {gh['url']}")
            sourced += [f"- {t['name']} ({t['stars']} stars): {t['url']}" for t in gh.get("top", [])[:3]]
        else:
            sourced.append(f"- GitHub search unavailable for this run ({gh.get('status')}): {gh.get('url')}")
        so = pub.get("stackoverflow") or {}
        if so.get("status") == "ok":
            sourced.append(f"- {so['count']} Stack Overflow questions match: {so['url']}")
        else:
            sourced.append(f"- Stack Overflow search unavailable for this run ({so.get('status')}): {so.get('url')}")
        for a in self.ctx.brief.get("known_alternatives") or []:
            if isinstance(a, dict) and a.get("url"):
                sourced.append(f"- Founder-cited (not fetched by StopGo): {a.get('name')}: {a.get('note', '')} ({a['url']})")
        body = f"# Phase 1 / Step 2: Market definition\n\n**Idea:** {opp['idea']}\n\n" + label_claims(res.text) \
            + "\n" + "\n".join(sourced)
        self.ctx.write_output("phase1_step2_market.md", body, stubbed=res.stubbed)
