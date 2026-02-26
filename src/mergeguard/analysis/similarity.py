"""AST structure similarity analysis for duplication detection.

Compares code structures across PRs to detect when two PRs
implement similar functionality independently.
"""

from __future__ import annotations

from mergeguard.models import Symbol


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets.

    Returns a value between 0.0 (no overlap) and 1.0 (identical).
    """
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def symbol_name_similarity(symbols_a: list[Symbol], symbols_b: list[Symbol]) -> float:
    """Compute similarity between two sets of symbols by name.

    Uses Jaccard similarity on the set of symbol names. High similarity
    suggests duplication between two PRs.
    """
    names_a = {s.name for s in symbols_a}
    names_b = {s.name for s in symbols_b}
    return jaccard_similarity(names_a, names_b)


def signature_similarity(sig_a: str | None, sig_b: str | None) -> float:
    """Compute similarity between two function signatures.

    Uses token-level Jaccard similarity after splitting on whitespace
    and punctuation.
    """
    if not sig_a or not sig_b:
        return 0.0

    tokens_a = _tokenize_signature(sig_a)
    tokens_b = _tokenize_signature(sig_b)
    return jaccard_similarity(tokens_a, tokens_b)


def detect_potential_duplications(
    new_symbols: list[Symbol],
    other_symbols: list[Symbol],
    name_threshold: float = 0.6,
    signature_threshold: float = 0.7,
) -> list[tuple[Symbol, Symbol, float]]:
    """Find potentially duplicated symbols between two sets.

    Returns a list of (new_symbol, other_symbol, similarity_score) tuples
    where the similarity exceeds the thresholds.
    """
    duplications: list[tuple[Symbol, Symbol, float]] = []

    for new_sym in new_symbols:
        for other_sym in other_symbols:
            # Skip if different symbol types
            if new_sym.symbol_type != other_sym.symbol_type:
                continue

            # Check name similarity
            name_sim = _name_distance(new_sym.name, other_sym.name)
            if name_sim < name_threshold:
                continue

            # Check signature similarity
            sig_sim = signature_similarity(new_sym.signature, other_sym.signature)

            # Combined score
            combined = (name_sim * 0.4) + (sig_sim * 0.6)
            if combined >= signature_threshold:
                duplications.append((new_sym, other_sym, combined))

    return duplications


def _tokenize_signature(signature: str) -> set[str]:
    """Split a signature into tokens for comparison."""
    import re

    tokens = re.findall(r"\w+", signature)
    return set(tokens)


def _name_distance(name_a: str, name_b: str) -> float:
    """Compute similarity between two symbol names.

    Uses a combination of exact match, prefix match, and
    normalized edit distance.
    """
    if name_a == name_b:
        return 1.0

    # Normalize: lowercase, remove underscores
    norm_a = name_a.lower().replace("_", "")
    norm_b = name_b.lower().replace("_", "")

    if norm_a == norm_b:
        return 0.95

    # Check prefix match (e.g., "get_user" vs "get_user_by_id")
    shorter = min(norm_a, norm_b, key=len)
    longer = max(norm_a, norm_b, key=len)
    if longer.startswith(shorter) and len(shorter) > 3:
        return 0.7

    # Simple character overlap ratio
    chars_a = set(norm_a)
    chars_b = set(norm_b)
    overlap = len(chars_a & chars_b) / max(len(chars_a | chars_b), 1)
    return overlap * 0.5  # Scale down character overlap
