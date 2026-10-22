"""Moment types and the default keyword lists used to classify transcribed moments.

Classification is a heuristic over transcribed speech: it suggests a type, the creator confirms it.
Keywords are matched on lower-cased, accent-free text, so write them without accents.
"""

from __future__ import annotations

import re
import unicodedata

MOMENT_TYPES: dict[str, str] = {
    "clutch": "Clutch",
    "ace_multikill": "Ace / multikill",
    "engracado": "Momento engraçado",
    "tilt": "Tilt / frustração",
    "erro": "Erro / falha",
    "reacao": "Reação",
    "decisao": "Decisão / aprendizado",
    "jogada": "Jogada",
    "pico_audio": "Pico de áudio (sem classificação)",
    "outro": "Outro",
}

DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "clutch": [
        "clutch", "1v1", "1v2", "1v3", "1v4", "1v5", "1 contra", "um contra", "um x ",
        "sobrou eu", "sobrei", "ultimo vivo",
    ],
    "ace_multikill": [
        "ace", "penta", "quadra kill", "triple", "double", "tres kills", "quatro kills",
        "limpei o time", "limpou o time", "multikill",
    ],
    "engracado": [
        "kkkk", "kkk", "haha", "rindo", "engracado", "que bizarro", "bugou", "bug ", "sem noção",
    ],
    "tilt": [
        "tilt", "tiltei", "que odio", "nao e possivel", "nao acredito que", "to puto", "cansei",
        "lixo", "ridiculo", "inacreditavel",
    ],
    "erro": [
        "errei", "errou", "whiff", "como que eu errei", "perdi", "morri a toa", "burrice",
        "vacilei", "vacilo", "erro meu", "falhei",
    ],
    "decisao": [
        "o certo era", "devia ter", "deveria ter", "a decisao", "eu deveria", "aprendi",
        "licao", "erro de decisao", "na real o que", "o problema foi",
    ],
    "jogada": [
        "que jogada", "olha essa", "olha isso", "mira", "flick", "spray transfer", "one tap",
        "headshot", "tiro na cabeca",
    ],
}

# Generic exclamations that suggest a reaction (weaker evidence than type-specific words).
DEFAULT_REACTION_KEYWORDS: list[str] = [
    "meu deus", "nao acredito", "caramba", "caraca", "nossa", "o que foi isso", "que isso",
    "socorro", "calma", "para tudo", "uau", "gente", "ai ai ai", "olha so",
]


def normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", folded.lower()).strip()


def count_keyword_hits(normalized: str, keywords: list[str]) -> int:
    """Count keyword occurrences in already-normalized text (word-boundary aware)."""
    hits = 0
    for raw in keywords:
        kw = normalize_text(raw)
        if not kw:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(kw.strip()) + r"(?![a-z0-9])"
        hits += len(re.findall(pattern, normalized))
    return hits


def default_keywords() -> dict[str, list[str]]:
    return {key: list(values) for key, values in DEFAULT_KEYWORDS.items()}


def default_reaction_keywords() -> list[str]:
    return list(DEFAULT_REACTION_KEYWORDS)
