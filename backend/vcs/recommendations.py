"""Idea suggestions and script skeletons, explained by their reasons.

Priority is the sum of visible reasons (profile, your own results, available material, radar
observations) - it is NOT a prediction of performance. Own-results reasons only count with a
minimum sample, and are always labelled as observation, not causation.
"""

from __future__ import annotations

from typing import Any

from .analysis.moment_types import MOMENT_TYPES, normalize_text
from .models import CreatorProfile
from .utils import median

MIN_OWN_SAMPLE = 5

FORMATS: dict[str, dict[str, Any]] = {
    "serie_jornada": {
        "title": "Série de evolução de rank",
        "keywords": ["serie", "jornada", "evolucao", "rank", "elo"],
        "moment_types": ["decisao", "clutch"],
        "themes": ["ranked_journey"],
        "why": "Uma série dá motivo para o público voltar a cada episódio e aproveita partidas que você já joga.",
        "next": "Escolha uma partida por episódio, uma decisão-chave e o resultado real (sem editar a verdade).",
    },
    "clutch": {
        "title": "Clutches das lives",
        "keywords": ["clutch"],
        "moment_types": ["clutch", "ace_multikill"],
        "themes": ["clutch", "ace"],
        "why": "Situações de desvantagem se explicam sozinhas em poucos segundos.",
        "next": "Aprove os candidatos do tipo clutch, informe a situação (ex.: 1v3) nos fatos e gere os textos.",
    },
    "erro_engracado": {
        "title": "Erros e momentos engraçados",
        "keywords": ["engracado", "erro", "fail", "humor"],
        "moment_types": ["engracado", "erro"],
        "themes": ["funny_fail"],
        "why": "Erros e reações genuínas geram identificação e comentários.",
        "next": "Comece pouco antes do erro e deixe a sua reação real aparecer.",
    },
    "tilt_reacao": {
        "title": "Tilt e reações",
        "keywords": ["tilt", "reacao"],
        "moment_types": ["tilt", "reacao"],
        "themes": ["tilt_reaction"],
        "why": "Emoção real prende a atenção quando o contexto está claro.",
        "next": "Mostre o round que causou a reação e corte antes de a situação ficar repetitiva.",
    },
    "analise_decisao": {
        "title": "O que eu faria diferente (análise de decisão)",
        "keywords": ["decisao", "analise", "aprendizado"],
        "moment_types": ["decisao"],
        "themes": ["ranked_journey", "tips_guides"],
        "why": "Mostra evolução e ensina algo, o que combina com um canal de jornada de rank.",
        "next": "Mostre a decisão, o resultado e o que você faria hoje, em até 45 s.",
    },
    "dica_rapida": {
        "title": "Dica rápida com exemplo seu",
        "keywords": ["dica", "tutorial", "guia"],
        "moment_types": ["jogada", "decisao"],
        "themes": ["tips_guides"],
        "why": "Uma dica por vídeo, com exemplo real, é fácil de assistir e de lembrar.",
        "next": "Escolha um agente/mapa que você joga e mostre a dica aplicada numa jogada sua.",
    },
    "melhores_momentos": {
        "title": "Melhores momentos da semana",
        "keywords": ["melhores", "compilacao", "highlights"],
        "moment_types": [],
        "themes": [],
        "why": "Aproveita vários cortes aprovados num único vídeo recorrente.",
        "next": "Reúna 3–5 cortes aprovados da semana e publique sempre no mesmo dia.",
    },
}

SCRIPT_BEATS = [
    ("Gancho (0–3 s)", "A frase ou imagem que abre o vídeo. Use o que realmente acontece no corte."),
    ("Contexto (3–8 s)", "Mapa, agente, situação do round, em uma linha. Só fatos que você confirmou."),
    ("Desenvolvimento", "O momento em si. Corte pausas e mantenha a ação visível no enquadramento."),
    ("Desfecho", "O resultado real do round/partida. Não prometa algo que o vídeo não mostra."),
    ("Chamada para comentário", "Uma pergunta simples ligada ao momento (ex.: você teria feito diferente?)."),
]


def _matches(text: str, keywords: list[str]) -> bool:
    norm = normalize_text(text)
    return any(kw in norm for kw in keywords)


def suggest_ideas(
    profile: CreatorProfile,
    *,
    publications: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    trends: list[dict[str, Any]],
    limit: int = 6,
) -> list[dict[str, Any]]:
    measured = [p for p in publications if p.get("status") == "published" and p.get("views") is not None]
    overall = median(p["views"] for p in measured)
    ideas: list[dict[str, Any]] = []
    for key, fmt in FORMATS.items():
        if key == "serie_jornada" and not (profile.rank_current and profile.rank_target) and not profile.series_name:
            continue
        priority = 1.0
        reasons: list[dict[str, str]] = [{"kind": "hipotese", "evidence": "hipotese", "text": fmt["why"]}]

        if any(_matches(t, fmt["keywords"]) for t in profile.formats_to_try):
            priority += 1.0
            reasons.append({"kind": "perfil", "evidence": "perfil",
                            "text": "Você listou um formato parecido entre os que quer experimentar."})
        if any(t in profile.preferred_types for t in fmt["moment_types"]):
            priority += 0.75
            reasons.append({"kind": "perfil", "evidence": "perfil",
                            "text": "Combina com os tipos de momento que você prioriza no perfil."})

        material = [c for c in candidates if c["moment_type"] in fmt["moment_types"] and c["status"] != "rejected"]
        if len(material) >= 3:
            priority += 0.5
            reasons.append({"kind": "material", "evidence": "observado",
                            "text": f"Você já tem {len(material)} candidatos/cortes desse tipo na biblioteca."})

        labels = {MOMENT_TYPES[t] for t in fmt["moment_types"] if t in MOMENT_TYPES}
        own = [p for p in measured if p.get("theme") in labels or (p.get("format") and _matches(p["format"], fmt["keywords"]))]
        if own and len(own) >= MIN_OWN_SAMPLE and overall:
            ratio = median(p["views"] for p in own) / overall
            if ratio >= 1.2:
                priority += 1.0
                reasons.append({"kind": "dados_proprios", "evidence": "observado",
                                "text": f"Nos seus vídeos desse formato (n={len(own)}) a mediana de visualizações é "
                                        f"{ratio:.1f}× a mediana geral. É uma observação, não prova de causa."})
            elif ratio <= 0.8:
                priority -= 0.5
                reasons.append({"kind": "dados_proprios", "evidence": "observado",
                                "text": f"Nos seus vídeos desse formato (n={len(own)}) a mediana de visualizações é "
                                        f"{ratio:.1f}× a mediana geral. Pode valer testar outro gancho/duração antes de descartar."})
        elif own:
            reasons.append({"kind": "dados_proprios", "evidence": "observado",
                            "text": f"Só {len(own)} vídeo(s) seu(s) nesse formato: amostra insuficiente "
                                    f"(mínimo {MIN_OWN_SAMPLE}) para concluir qualquer coisa."})

        for trend in trends:
            if trend.get("kind") != "tema" or trend.get("confidence") == "muito baixa":
                continue
            label = trend.get("label", "")
            comparison = ((trend.get("observed") or {}).get("estimated") or {}).get("comparado_a_amostra") or ""
            if any(_matches(label, [normalize_text(t)]) for t in fmt["themes"]) or _theme_label_match(label, fmt["themes"]):
                if "×" in comparison:
                    try:
                        ratio = float(comparison.split("×")[0].replace(",", "."))
                    except ValueError:
                        ratio = 1.0
                    if ratio >= 1.15:
                        priority += 0.5
                        reasons.append({
                            "kind": "radar", "evidence": "observado",
                            "text": f"Radar ({trend.get('source')}, {str(trend.get('collected_at'))[:10]}): tema "
                                    f"'{label}' com mediana de views/dia estimada em {comparison} "
                                    f"(confiança {trend.get('confidence')}).",
                        })
                        break

        title = fmt["title"]
        if key == "serie_jornada":
            title = profile.series_name or f"Jornada {profile.rank_current} → {profile.rank_target}"
        ideas.append({
            "format": key, "title": title, "priority": round(priority, 2), "reasons": reasons,
            "next_step": fmt["next"],
            "priority_note": "Prioridade = soma dos motivos listados, não uma previsão de desempenho.",
        })
    ideas.sort(key=lambda i: i["priority"], reverse=True)
    return ideas[:limit]


def _theme_label_match(label: str, theme_keys: list[str]) -> bool:
    from .radar.analyzer import THEMES

    return any(THEMES[k][0] == label for k in theme_keys if k in THEMES)


def build_script(title: str, fmt: str | None, profile: CreatorProfile) -> dict[str, Any]:
    """A fill-in skeleton: guidance only, with blanks for the real facts."""
    beats = [{"beat": name, "guide": guide, "your_text": ""} for name, guide in SCRIPT_BEATS]
    duration = f"{profile.preferred_duration_min_s}–{profile.preferred_duration_max_s} s"
    return {
        "title": title,
        "format": fmt,
        "target_duration": duration,
        "beats": beats,
        "checklist": [
            "Todos os fatos (mapa, agente, resultado) são reais e conferidos.",
            "O gancho aparece nos primeiros 3 segundos do corte.",
            "Legendas revisadas (nomes de agentes, gírias).",
            "Áudio sem música protegida que possa ser silenciada na plataforma.",
        ],
    }
