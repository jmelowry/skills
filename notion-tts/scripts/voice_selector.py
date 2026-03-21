"""
voice_selector.py — Vibe-based voice selection for notion_tts.

Given a natural-language vibe description (or a voice name/ID), resolve
to a concrete ElevenLabs voice_id using the local voices.json cache.

Resolution order:
  1. Exact voice_id match (if input looks like a UUID)
  2. Exact name match (case-insensitive)
  3. Named vibe alias (e.g. "assistant", "ted talk", "documentary")
  4. Fuzzy label/description match against the cache
  5. Fall back to DEFAULT_VOICE if nothing matches

The cache is populated by list_voices.py. If voices.json doesn't exist,
falls back to hardcoded IDs for the named defaults.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "voices.json"

# ─── Hardcoded fallbacks ──────────────────────────────────────────────────────
# These are the ElevenLabs premade voice IDs as of mid-2025.
# They may change. Run list_voices.py --refresh to update the cache.

HARDCODED_VOICES = {
    # name_lower → voice_id
    "rachel":   "21m00Tcm4TlvDq8ikWAM",  # calm, neutral American female
    "matilda":  "XrExE9yKIg1WjnnlVkGX",  # warm, approachable American female — assistant-style
    "bella":    "EXAVITQu4vr4xnSDxMaL",  # clear, confident — good for presentations / ted talk
    "adam":     "pNInz6obpgDQGcFmaJgB",  # deep American male — narration
    "elli":     "MF3mGyEYCl7XYWbV9V6O",  # young American female
    "josh":     "TxGEqnHWrfWFTfGW9XjX",  # young American male — conversational
    "arnold":   "VR6AewLTigWG4xSOukaG",  # authoritative American male
    "sam":      "yoZ06aMxZJJ28mfd3POQ",  # raspy American male
    "glinda":   "z9fAnlkpzviPz146aGWa",  # warm older female
    "charlotte":"XB0fDUnXU5powFXDhCwa",  # Swedish female — calm
    "daniel":   "onwK4e9ZLuTAKqWW03F9",  # deep British male — documentary
    "george":   "JBFqnCBsd6RMkjVDRZzb",  # warm British male
    "lily":     "pFZP5JQG7iQjIQuC4Bku",  # warm British female
    "fin":      "D38z5RcWu1voky8WS1ja",  # Irish male — storytelling
    "grace":    "oWAxZDx7w5VEj9dCyTzz",  # Southern American female
    "callum":   "N2lVS1w4EtoT3dr4eOWO",  # intense British male
    "harry":    "SOYHLrjzK2X1ezoPC6cr",  # anxious British male
    "liam":     "TX3LPaxmHKxFdv7VOQHJ",  # bright American male
    "freya":    "jsCqWAovK2LkecY7zXl4",  # warm American female
    "dorothy":  "ThT5KcBeYPX3keUQqHPh",  # gentle British female
}

# ─── Named vibe aliases ───────────────────────────────────────────────────────
# Map vibe keywords → (preferred_name, voice_id, rationale)

VIBE_ALIASES: dict[str, dict] = {
    # --- Defaults ---
    "default":       {"name": "Matilda", "id": HARDCODED_VOICES["matilda"],
                      "reason": "Warm, approachable neutral assistant voice"},
    "assistant":     {"name": "Matilda", "id": HARDCODED_VOICES["matilda"],
                      "reason": "Clear and professional, good for reading docs"},
    "neutral":       {"name": "Matilda", "id": HARDCODED_VOICES["matilda"],
                      "reason": "Balanced, unobtrusive reading voice"},

    # --- Presentation / talk styles ---
    "ted talk":      {"name": "Bella",   "id": HARDCODED_VOICES["bella"],
                      "reason": "Confident and engaging, like a keynote speaker"},
    "presentation":  {"name": "Bella",   "id": HARDCODED_VOICES["bella"],
                      "reason": "Articulate and forward-leaning delivery"},
    "keynote":       {"name": "Bella",   "id": HARDCODED_VOICES["bella"],
                      "reason": "Clear, energetic, professional"},
    "confident":     {"name": "Bella",   "id": HARDCODED_VOICES["bella"],
                      "reason": "Assertive tone with presence"},

    # --- Narration / documentary ---
    "documentary":   {"name": "Daniel",  "id": HARDCODED_VOICES["daniel"],
                      "reason": "Deep, authoritative British male — BBC narrator feel"},
    "narration":     {"name": "Daniel",  "id": HARDCODED_VOICES["daniel"],
                      "reason": "Measured and trustworthy long-form reading voice"},
    "audiobook":     {"name": "George",  "id": HARDCODED_VOICES["george"],
                      "reason": "Warm British male, great for long-form content"},
    "storytelling":  {"name": "Fin",     "id": HARDCODED_VOICES["fin"],
                      "reason": "Irish lilt with natural storytelling cadence"},
    "book":          {"name": "George",  "id": HARDCODED_VOICES["george"],
                      "reason": "Warm, measured tone for long reads"},

    # --- Conversational ---
    "conversational":{"name": "Josh",    "id": HARDCODED_VOICES["josh"],
                      "reason": "Relaxed, natural American male delivery"},
    "casual":        {"name": "Josh",    "id": HARDCODED_VOICES["josh"],
                      "reason": "Friendly and informal"},
    "podcast":       {"name": "Liam",    "id": HARDCODED_VOICES["liam"],
                      "reason": "Bright and engaging, like a podcast host"},
    "friendly":      {"name": "Freya",   "id": HARDCODED_VOICES["freya"],
                      "reason": "Warm and accessible American female"},

    # --- Authoritative ---
    "authoritative": {"name": "Arnold",  "id": HARDCODED_VOICES["arnold"],
                      "reason": "Commanding American male voice"},
    "news":          {"name": "Arnold",  "id": HARDCODED_VOICES["arnold"],
                      "reason": "Clear, credible broadcast delivery"},
    "serious":       {"name": "Callum",  "id": HARDCODED_VOICES["callum"],
                      "reason": "Intense British male, no-nonsense delivery"},

    # --- Gender-specific shortcuts ---
    "male":          {"name": "Adam",    "id": HARDCODED_VOICES["adam"],
                      "reason": "Deep, neutral American male"},
    "female":        {"name": "Matilda", "id": HARDCODED_VOICES["matilda"],
                      "reason": "Warm, neutral American female"},
    "british male":  {"name": "Daniel",  "id": HARDCODED_VOICES["daniel"],
                      "reason": "Deep British male narrator"},
    "british female":{"name": "Lily",    "id": HARDCODED_VOICES["lily"],
                      "reason": "Warm British female"},
    "british":       {"name": "George",  "id": HARDCODED_VOICES["george"],
                      "reason": "Friendly British male"},
    "irish":         {"name": "Fin",     "id": HARDCODED_VOICES["fin"],
                      "reason": "Natural Irish male voice"},

    # --- Tone-based ---
    "warm":          {"name": "Freya",   "id": HARDCODED_VOICES["freya"],
                      "reason": "Gentle, inviting tone"},
    "calm":          {"name": "Charlotte","id": HARDCODED_VOICES["charlotte"],
                      "reason": "Soft and measured delivery"},
    "gentle":        {"name": "Dorothy", "id": HARDCODED_VOICES["dorothy"],
                      "reason": "Soft British female, non-intrusive"},
    "deep":          {"name": "Adam",    "id": HARDCODED_VOICES["adam"],
                      "reason": "Resonant low American voice"},
    "energetic":     {"name": "Bella",   "id": HARDCODED_VOICES["bella"],
                      "reason": "Forward-leaning, engaged delivery"},
    "raspy":         {"name": "Sam",     "id": HARDCODED_VOICES["sam"],
                      "reason": "Distinctive raspy American male"},
    "southern":      {"name": "Grace",   "id": HARDCODED_VOICES["grace"],
                      "reason": "Southern American female, folksy warmth"},
}

# ─── Voice ID pattern ─────────────────────────────────────────────────────────

_VOICE_ID_RE = re.compile(r"^[A-Za-z0-9]{20,25}$")


@dataclass
class ResolvedVoice:
    voice_id: str
    name: str
    reason: str
    source: str  # "exact_id" | "exact_name" | "vibe_alias" | "label_match" | "fallback"


def _load_cache() -> list[dict]:
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text())
            return data.get("voices", [])
        except (json.JSONDecodeError, KeyError):
            pass
    return []


def _score_voice_against_vibe(voice: dict, vibe: str) -> int:
    """Return a relevance score for a cached voice against a vibe string."""
    vibe_tokens = set(vibe.lower().split())
    score = 0

    # Name match
    if any(t in voice["name"].lower() for t in vibe_tokens):
        score += 10

    # Label matches
    for label_val in voice["labels"].values():
        label_tokens = set(label_val.lower().split())
        overlap = vibe_tokens & label_tokens
        score += len(overlap) * 3

    # Description match
    desc_tokens = set(voice["description"].lower().split())
    score += len(vibe_tokens & desc_tokens) * 2

    return score


def resolve_voice(vibe_or_id: str) -> ResolvedVoice:
    """
    Resolve a vibe string or voice reference to a concrete voice_id.

    Priority:
      1. Raw voice_id (looks like a 20-25 char alphanumeric string)
      2. Exact name match in cache
      3. Exact name match in hardcoded fallbacks
      4. Vibe alias match (longest matching alias wins)
      5. Label/description scoring against cache
      6. Fallback to default (Matilda)
    """
    raw = vibe_or_id.strip()

    # 1. Raw voice_id
    if _VOICE_ID_RE.match(raw):
        return ResolvedVoice(
            voice_id=raw,
            name=raw,
            reason="Exact voice ID provided",
            source="exact_id",
        )

    raw_lower = raw.lower()

    # 2 & 3. Exact name match — cache first, then hardcoded
    cached = _load_cache()
    for v in cached:
        if v["name"].lower() == raw_lower:
            return ResolvedVoice(
                voice_id=v["voice_id"],
                name=v["name"],
                reason=f"Exact name match: {v['name']}",
                source="exact_name",
            )

    for name_lower, vid in HARDCODED_VOICES.items():
        if name_lower == raw_lower:
            return ResolvedVoice(
                voice_id=vid,
                name=name_lower.title(),
                reason=f"Exact name match (hardcoded): {name_lower.title()}",
                source="exact_name",
            )

    # 4. Vibe alias — find the longest matching alias key
    best_alias = None
    best_alias_len = 0
    for alias_key, alias_val in VIBE_ALIASES.items():
        if alias_key in raw_lower and len(alias_key) > best_alias_len:
            best_alias = alias_val
            best_alias_len = len(alias_key)

    if best_alias:
        # Try to find a current ID from cache for this voice name
        voice_name_lower = best_alias["name"].lower()
        for v in cached:
            if v["name"].lower() == voice_name_lower:
                return ResolvedVoice(
                    voice_id=v["voice_id"],
                    name=v["name"],
                    reason=best_alias["reason"],
                    source="vibe_alias",
                )
        # Use hardcoded ID as fallback
        return ResolvedVoice(
            voice_id=best_alias["id"],
            name=best_alias["name"],
            reason=best_alias["reason"] + " (hardcoded ID — run list_voices.py to refresh)",
            source="vibe_alias",
        )

    # 5. Label/description scoring against cache
    if cached:
        scored = [(v, _score_voice_against_vibe(v, raw)) for v in cached]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_voice, best_score = scored[0]
        if best_score > 0:
            return ResolvedVoice(
                voice_id=best_voice["voice_id"],
                name=best_voice["name"],
                reason=f"Best label match for {raw!r} (score={best_score})",
                source="label_match",
            )

    # 6. Fallback
    fallback = VIBE_ALIASES["default"]
    return ResolvedVoice(
        voice_id=fallback["id"],
        name=fallback["name"],
        reason=f"No match for {raw!r}, using default ({fallback['name']})",
        source="fallback",
    )


def describe_vibe_options() -> str:
    """Return a human-readable summary of available vibe keywords."""
    categories = {
        "Default / neutral": ["default", "assistant", "neutral"],
        "Presentation": ["ted talk", "presentation", "keynote", "confident"],
        "Narration": ["documentary", "narration", "audiobook", "storytelling", "book"],
        "Conversational": ["conversational", "casual", "podcast", "friendly"],
        "Authoritative": ["authoritative", "news", "serious"],
        "Gender shortcuts": ["male", "female", "british male", "british female", "british", "irish"],
        "Tone": ["warm", "calm", "gentle", "deep", "energetic", "raspy", "southern"],
    }
    lines = ["Available vibe keywords:"]
    for category, keywords in categories.items():
        lines.append(f"  {category}: {', '.join(keywords)}")
    lines.append("")
    lines.append("You can also pass a voice name directly (e.g. 'Daniel', 'Bella')")
    lines.append("or a raw ElevenLabs voice_id.")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(describe_vibe_options())
        sys.exit(0)
    vibe = " ".join(sys.argv[1:])
    result = resolve_voice(vibe)
    print(f"Voice:    {result.name}")
    print(f"ID:       {result.voice_id}")
    print(f"Reason:   {result.reason}")
    print(f"Source:   {result.source}")
