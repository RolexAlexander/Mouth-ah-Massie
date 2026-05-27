"""Source quality stratification.

A pragmatic heuristic that classifies URLs into tiers so the Critic can
demand evidence quality and the Writer can flag low-confidence claims.

This is deliberately a rule-based heuristic, not an LLM call — we want it
to be fast, cheap, and deterministic so it can run on every source without
budget concerns.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .schemas import SourceTier

# Domains we recognize as Tier 1 (peer-reviewed / academic)
_TIER1_PATTERNS = (
    r"\.edu$", r"\.edu\.", r"\bnature\.com$", r"\bscience\.org$",
    r"\barxiv\.org$", r"\bpubmed\.ncbi\.nlm\.nih\.gov$",
    r"\bsciencedirect\.com$", r"\bspringer\.com$", r"\bwiley\.com$",
    r"\bjstor\.org$", r"\bssrn\.com$", r"\bcambridge\.org$",
    r"\boxford\b.*\.com$", r"\bnih\.gov$", r"\bplos\.org$",
    r"\bacm\.org$", r"\bieee\.org$", r"\bbiorxiv\.org$",
)

# Tier 2 — government, regulatory, official
_TIER2_PATTERNS = (
    r"\.gov$", r"\.gov\.", r"\.mil$",
    r"\bimf\.org$", r"\bworldbank\.org$", r"\bwto\.org$", r"\bun\.org$",
    r"\beuropa\.eu$", r"\boecd\.org$", r"\bwho\.int$",
    r"\bsec\.gov$", r"\beur-lex\.europa\.eu$",
    r"\bbankofguyana\.org\.gy$", r"\bparliament\.gov\.gy$",
)

# Tier 3 — major reputable news
_TIER3_PATTERNS = (
    r"\breuters\.com$", r"\bbloomberg\.com$", r"\bft\.com$",
    r"\bwsj\.com$", r"\bnytimes\.com$", r"\beconomist\.com$",
    r"\bbbc\.(co\.uk|com)$", r"\bapnews\.com$", r"\bguardian\.com$",
    r"\btheguardian\.com$", r"\bnpr\.org$", r"\bwashingtonpost\.com$",
    r"\baljazeera\.com$", r"\bcnbc\.com$",
    r"\bstabroeknews\.com$", r"\bkaieteurnewsonline\.com$",
    r"\bdemerarawaves\.com$", r"\binewsguyana\.com$",
)

# Tier 5 — explicitly low-quality / unverified
_TIER5_PATTERNS = (
    r"\breddit\.com$", r"\bquora\.com$", r"\btwitter\.com$", r"\bx\.com$",
    r"\bfacebook\.com$", r"\binstagram\.com$", r"\btiktok\.com$",
    r"\bmedium\.com$", r"\bsubstack\.com$", r"\bblogspot\.",
    r"\bwordpress\.com$", r"\byoutube\.com$",
)


def _match_any(host: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, host) for p in patterns)


def classify_url(url: str) -> SourceTier:
    """Return the SourceTier for a given URL. Defaults to INDUSTRY."""
    if not url:
        return SourceTier.UNVERIFIED
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return SourceTier.UNVERIFIED
    host = host.lower()
    if not host:
        return SourceTier.UNVERIFIED

    if _match_any(host, _TIER1_PATTERNS):
        return SourceTier.PEER_REVIEWED
    if _match_any(host, _TIER2_PATTERNS):
        return SourceTier.OFFICIAL
    if _match_any(host, _TIER3_PATTERNS):
        return SourceTier.MAJOR_NEWS
    if _match_any(host, _TIER5_PATTERNS):
        return SourceTier.UNVERIFIED
    return SourceTier.INDUSTRY


def tier_label(tier: SourceTier) -> str:
    return {
        SourceTier.PEER_REVIEWED: "peer-reviewed",
        SourceTier.OFFICIAL: "official",
        SourceTier.MAJOR_NEWS: "major-news",
        SourceTier.INDUSTRY: "industry",
        SourceTier.UNVERIFIED: "unverified",
    }[tier]
