"""Rule-based copy suggestions (hooks, titles, caption, hashtags) in Brazilian Portuguese.

Principles:
* Only use facts that exist: the confirmed moment type, real words from the transcript, and data the
  creator typed in (map, agent, situation like "1v3", result, rank). Templates whose facts are
  missing are skipped - nothing is invented.
* No superlatives or promises ("o clutch mais insano", "você não vai acreditar").
* Fully local and free. Suggestions are a starting point for the creator to edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..analysis.moment_types import MOMENT_TYPES, normalize_text
from ..utils import fmt_hms, utcnow

RANKS = ["ferro", "bronze", "prata", "ouro", "platina", "diamante", "ascendente", "imortal", "radiante"]

TYPE_TAGS: dict[str, list[str]] = {
    "clutch": ["clutch"],
    "ace_multikill": ["ace", "multikill"],
    "engracado": ["valorantfunny"],
    "tilt": ["tilt"],
    "erro": ["fail"],
    "reacao": ["reacao"],
    "decisao": ["gamesense"],
    "jogada": ["highlights"],
}

# (template, required fact keys)
Template = tuple[str, tuple[str, ...]]

HOOKS: dict[str, list[Template]] = {
    "clutch": [
        ("Olha como terminou esse {situation} no {map}", ("situation", "map")),
        ("Olha como terminou esse {situation}", ("situation",)),
        ("Sobrou só eu nesse round no {map}", ("map",)),
        ("Será que dá pra virar esse round?", ()),
        ("Sobrou eu pra decidir esse round", ()),
        ("“{quote}”", ("quote",)),
    ],
    "ace_multikill": [
        ("Esse round de {agent} no {map}", ("agent", "map")),
        ("Olha o que saiu nesse round de {agent}", ("agent",)),
        ("Presta atenção nesse round no {map}", ("map",)),
        ("Olha esse round do começo ao fim", ()),
        ("“{quote}”", ("quote",)),
    ],
    "engracado": [
        ("Isso aconteceu de verdade nessa partida", ()),
        ("Olha o que rolou no {map}", ("map",)),
        ("“{quote}”", ("quote",)),
        ("Foi assim que esse round terminou", ()),
    ],
    "tilt": [
        ("O tilt chegou nesse round", ()),
        ("Quando o round não ajuda", ()),
        ("Isso no {map} me tirou do sério", ("map",)),
        ("“{quote}”", ("quote",)),
    ],
    "erro": [
        ("Esse erro eu não esqueço", ()),
        ("Errei feio nesse round no {map}", ("map",)),
        ("Como eu errei isso de {agent}?", ("agent",)),
        ("“{quote}”", ("quote",)),
    ],
    "reacao": [
        ("Minha reação na hora", ()),
        ("Olha o que aconteceu no {map}", ("map",)),
        ("“{quote}”", ("quote",)),
        ("Reação ao vivo nesse momento", ()),
    ],
    "decisao": [
        ("Uma decisão que eu queria rever", ()),
        ("Qual você teria feito aqui?", ()),
        ("Revendo uma decisão no {map}", ("map",)),
        ("“{quote}”", ("quote",)),
    ],
    "jogada": [
        ("Olha essa jogada de {agent}", ("agent",)),
        ("Olha o que saiu no {map}", ("map",)),
        ("Presta atenção no começo desse round", ()),
        ("“{quote}”", ("quote",)),
    ],
}
GENERIC_HOOKS: list[Template] = [
    ("Olha o que aconteceu nesse round", ()),
    ("Presta atenção nesse momento da live", ()),
    ("Mais um momento da live", ()),
]

TITLES: list[Template] = [
    ("{label} {situation} no {map}", ("situation", "map")),
    ("{label} de {agent} no {map}", ("agent", "map")),
    ("{label} no {map}", ("map",)),
    ("{label} com {agent}", ("agent",)),
    ("{label} | {series}", ("series",)),
    ("{label} na live", ()),
    ("{label} | momento da live", ()),
]

CTAS = {
    "clutch": "Você teria feito diferente? Conta nos comentários.",
    "ace_multikill": "Qual foi o seu melhor round com esse agente?",
    "engracado": "Marca alguém que jogaria assim.",
    "tilt": "Qual foi o seu pior tilt? Comenta aí.",
    "erro": "Já passou por isso? Conta nos comentários.",
    "decisao": "O que você teria escolhido? Responde aí.",
    "reacao": "Qual teria sido a sua reação?",
    "jogada": "O que você achou dessa jogada?",
}


@dataclass
class CopyInput:
    moment_type: str
    recording_name: str
    start_s: float
    end_s: float
    excerpt: str = ""
    quote: str = ""
    map: str | None = None
    agent: str | None = None
    situation: str | None = None
    result: str | None = None  # "vitória" | "derrota"
    rank: str | None = None
    target_rank: str | None = None
    series: str | None = None
    channel: str | None = None
    note: str | None = None
    base_hashtags: list[str] = field(default_factory=list)
    clip_id: int = 0
    confirmed_type: bool = True


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_text(text))


def _fill(template: Template, facts: dict[str, str]) -> str | None:
    text, required = template
    if any(not facts.get(key) for key in required):
        return None
    return text.format_map({k: v for k, v in facts.items() if v})


def _pick(bank: list[Template], facts: dict[str, str], count: int) -> list[str]:
    """First `count` templates whose facts are all known. Banks are ordered most specific first."""
    options: list[str] = []
    for template in bank:
        filled = _fill(template, facts)
        if filled and filled not in options:
            options.append(filled)
    return options[:count]


def short_quote(excerpt: str, max_words: int = 9) -> str:
    words = excerpt.replace("“", "").replace("”", "").split()
    return " ".join(words[:max_words]).strip(" ,;:-")


def rank_tag(rank: str | None) -> str | None:
    if not rank:
        return None
    first = _slug(rank.split()[0]) if rank.split() else ""
    return first if first in RANKS else None


def generate_copy(data: CopyInput) -> dict[str, Any]:
    label = MOMENT_TYPES.get(data.moment_type, "Momento")
    facts: dict[str, str] = {
        "label": label,
        "map": data.map or "",
        "agent": (data.agent or "").strip().title(),
        "situation": data.situation or "",
        "quote": data.quote or "",
        "series": data.series or "",
    }
    notes: list[str] = []
    if not data.confirmed_type:
        notes.append("O tipo do momento ainda é uma sugestão automática: confirme-o antes de publicar.")
    missing = [name for name, value in (("mapa", data.map), ("agente", data.agent)) if not value]
    if data.moment_type in ("clutch", "ace_multikill") and not data.situation:
        missing.append("situação (ex.: 1v3)")
    if missing:
        notes.append("Para textos mais específicos, preencha nos fatos do corte: " + ", ".join(missing) + ".")

    hooks = _pick(HOOKS.get(data.moment_type, []), facts, 3)
    if len(hooks) < 3:
        for extra in _pick(GENERIC_HOOKS, facts, 3):
            if extra not in hooks and len(hooks) < 3:
                hooks.append(extra)

    titles = _pick(TITLES, facts, 3)
    titles = [t[:60] for t in titles]

    # Caption: only assembled from facts we have.
    first = label + (f" {data.situation}" if data.situation else "")
    if data.map:
        first += f" no {data.map}"
    if data.agent:
        first += f" de {facts['agent']}"
    sentences = [first + "."]
    if data.result:
        sentences.append(f"Resultado: {data.result}.")
    if data.rank and data.target_rank:
        sentences.append(f"Jornada {data.rank} → {data.target_rank}.")
    elif data.series:
        sentences.append(f"Parte da série {data.series}.")
    cta = CTAS.get(data.moment_type, "O que você achou?")
    caption = " ".join(sentences) + " " + cta

    tags: list[str] = []
    for tag in [*data.base_hashtags, _slug(data.agent or ""), _slug(data.map or ""),
                *TYPE_TAGS.get(data.moment_type, []), rank_tag(data.rank), rank_tag(data.target_rank)]:
        if tag and tag not in tags:
            tags.append(tag)
    hashtags = ["#" + t for t in tags[:8]]

    description_parts = [
        f"Trecho de {fmt_hms(data.start_s)} a {fmt_hms(data.end_s)} da gravação {data.recording_name}.",
        f"Tipo: {label}" + (" (confirmado)." if data.confirmed_type else " (sugestão automática)."),
    ]
    if data.note:
        description_parts.append(data.note.strip())
    if data.excerpt:
        description_parts.append("Fala no trecho: “" + data.excerpt.strip()[:200] + "”")

    covers = [label.upper() if len(label) <= 18 else label]
    if data.situation:
        covers.append(data.situation.upper())
    if data.map:
        covers.append(f"{label} no {data.map}")

    return {
        "hooks": hooks,
        "titles": titles,
        "caption": caption,
        "hashtags": hashtags,
        "description": " ".join(description_parts),
        "cover_text": covers[:3],
        "comment_cta": cta,
        "notes": notes,
        "generated_at": utcnow(),
        "source": "regras locais (sem IA externa)",
    }
