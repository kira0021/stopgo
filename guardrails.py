"""Hard limits, enforced in code (not just in prompts).

1. check_brief:   refuse excluded product categories before any work starts.
2. check_request: refuse requests for fake reviews, income promises,
                  impersonation, fake urgency, moving money, storing secrets.
3. scan_output:   catch the same things in model output and remove them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------- brief
EXCLUDED_CATEGORIES: dict[str, list[str]] = {
    "physical goods": [
        r"\bphysical (product|good)s?\b", r"\bt-?shirts?\b", r"\bmerch(andise)?\b", r"\bdropship",
        r"\bhardware device\b", r"\bprint(ed)? (mugs?|posters?)\b", r"\bship(ping)? (boxes|products)\b",
        r"\bsubscription box\b", r"\bcandles?\b", r"\bjewel(le)?ry\b",
    ],
    "financial, investment or crypto": [
        r"\bcrypto", r"\bbitcoin\b", r"\bethereum\b", r"\bblockchain\b", r"\bnft\b", r"\btoken sale\b",
        r"\btrading (bot|signals?|strateg)", r"\bstock (picks?|tips?|signals?)\b", r"\binvest(ing|ment) advice\b",
        r"\bforex\b", r"\bloans?\b", r"\bdefi\b", r"\bportfolio advice\b", r"\bfinancial advice\b",
    ],
    "health advice": [
        r"\bmedical\b", r"\bdiagnos", r"\bsymptom", r"\btherap(y|ist)\b", r"\bmental health\b", r"\bdiet plan",
        r"\bweight loss\b", r"\bsupplements?\b", r"\bnutrition advice\b", r"\bhealth advice\b", r"\bfitness plan",
        r"\bmedication\b",
    ],
    "legal advice": [
        r"\blegal advice\b", r"\blawyer\b", r"\battorney\b", r"\bcontract review\b", r"\bimmigration\b",
        r"\blegal counsel\b", r"\bsue\b", r"\blawsuit\b",
    ],
}


def check_brief(text: str) -> list[str]:
    """Return the excluded categories the brief falls into (empty = allowed)."""
    hits = []
    low = (text or "").lower()
    for cat, patterns in EXCLUDED_CATEGORIES.items():
        if any(re.search(p, low) for p in patterns):
            hits.append(cat)
    return hits


# ------------------------------------------------------------------- requests
@dataclass
class Refusal:
    rule: str
    message: str
    alternative: str


REQUEST_RULES: list[tuple[str, list[str], str, str]] = [
    (
        "fake_reviews",
        [r"\b(fake|write|generate|create|make)\b.{0,40}\b(reviews?|testimonials?|ratings?|endorsements?)\b",
         r"\bfive[- ]star\b", r"\b5[- ]star\b", r"\bsock ?puppet", r"\bastroturf"],
        "StopGo never writes reviews or testimonials in anyone's voice, real or invented.",
        "I can draft a short feedback request that you send to real users after you approve it, "
        "and show real reviews only once real users have written them.",
    ),
    (
        "fake_signups",
        [r"\b(fake|inflate|pad|invent|fabricate)\b.{0,30}\b(sign-?ups?|waitlist|users|downloads|numbers|metrics|traction)\b",
         r"\bbots? to sign up\b"],
        "StopGo never invents sign-ups, users or traction. Gates only use evidence you report or that we can source.",
        "If the numbers are low, the gate will say so and recommend repeat, pivot or stop.",
    ),
    (
        "fake_urgency",
        [r"\bcountdown\b", r"\bfake (scarcity|urgency|deadline)\b", r"\bonly \d+ (left|spots)\b",
         r"\blimited[- ]time\b.{0,20}\b(fake|pretend)\b", r"\bcreate (urgency|scarcity)\b"],
        "StopGo never adds countdown timers or fake scarcity.",
        "I can help you state a real launch date or a real early-adopter price, if you have one.",
    ),
    (
        "income_promise",
        [r"\b(guarantee|promise)\b.{0,40}\b(income|revenue|profit|money|earnings|success|results)\b",
         r"\bpassive income\b", r"\bget rich\b", r"\bmake \$?\d[\d,]*k?\b.{0,20}\b(a|per) (month|week|day)\b"],
        "StopGo never promises income or success, to you or to your buyers.",
        "I can describe what the product does and what evidence we have so far, with sources.",
    ),
    (
        "impersonation",
        [r"\b(pretend\w*|pose|posing|act|acting)\b.{0,20}\b(to be|as)\b.{0,40}\b(customer|founder|user|ceo|"
         r"google|apple|microsoft|github|stripe|openai|amazon|brand)\b",
         r"\bimpersonat", r"\bsign (it|this|them) as\b", r"\bin the voice of (a|our) (customer|user)\b",
         r"\bpost as (me|the founder)\b"],
        "StopGo never poses as you, a customer or another brand.",
        "I can draft text for you to review and post under your own name.",
    ),
    (
        "money_movement",
        [r"\b(transfer|move|withdraw|send)\b.{0,20}\b(money|funds|payout|payment)\b",
         r"\b(issue|process|make)\b.{0,10}\brefunds?\b.{0,20}\b(automatically|yourself|on (your|its) own)\b",
         r"\brefund\w*\b.{0,40}\b(automatically|yourself|on (your|its) own|without (asking|approval))\b",
         r"\bcharge (the|their|a) card\b", r"\breal (payment|charge)\b", r"\blive (keys?|mode)\b"],
        "StopGo never holds, moves, charges or refunds money. All payment flows here are MOCKED.",
        "I can show the mocked sale-to-cash flow, and draft a refund request for you to carry out yourself.",
    ),
    (
        "secrets",
        [r"\b(store|save|keep|remember)\b.{0,30}\b(password|card number|credit card|cvv|api key|secret)\b"],
        "StopGo never stores passwords or card numbers.",
        "Keep secrets in your own password manager; StopGo needs none to run.",
    ),
    (
        "excluded_category",
        [p for pats in EXCLUDED_CATEGORIES.values() for p in pats if "advice" in p or "crypto" in p],
        "That product category is out of scope (no physical goods, financial/crypto, health or legal advice products).",
        "I can help you find a digital developer-tool idea that uses the same skills.",
    ),
]


def check_request(text: str) -> Refusal | None:
    low = (text or "").lower()
    for rule, patterns, message, alternative in REQUEST_RULES:
        if any(re.search(p, low) for p in patterns):
            return Refusal(rule, message, alternative)
    return None


# --------------------------------------------------------------------- output
OUTPUT_RULES: list[tuple[str, str]] = [
    ("income_promise", r"(?i)\b(guarantee[sd]?|promise[sd]?)\b[^.\n]{0,60}\b(income|revenue|profit|earn|money|success|results)\b"),
    ("income_promise", r"(?i)\bpassive income\b|\bget rich\b|\bmake \$\d[\d,]*"),
    ("testimonial", r"(?i)^\s*(#+\s*)?(testimonials?|what (our|people|users|customers) (say|are saying)|reviews?)\s*:?\s*$"),
    ("testimonial", r"(?i)[\"“][^\"”\n]{10,200}[\"”]\s*[-—–]\s*[A-Z][a-z]+"),
    ("testimonial", r"★★★|⭐⭐⭐|\b[45](\.\d)?/5 stars?\b|\b(four|five)-star\b"),
    ("fake_urgency", r"(?i)\bcountdown\b|\bonly \d+ (left|spots|seats)\b|\bhurry\b|\bact now\b|\boffer ends (soon|tonight)\b"),
    ("fake_signups", r"(?i)\bjoin \d[\d,]* (developers|users|people|others)\b|\btrusted by \d"),
]


@dataclass
class ScanResult:
    clean_text: str
    violations: list[str] = field(default_factory=list)


def scan_output(text: str) -> ScanResult:
    """Remove lines that break a hard rule; report which rules fired."""
    violations: list[str] = []
    out_lines = []
    for line in (text or "").splitlines():
        hit = next((rule for rule, pat in OUTPUT_RULES if re.search(pat, line)), None)
        if hit:
            violations.append(hit)
            out_lines.append(f"[removed by guardrail: {hit}]")
        else:
            out_lines.append(line)
    return ScanResult("\n".join(out_lines), sorted(set(violations)))
