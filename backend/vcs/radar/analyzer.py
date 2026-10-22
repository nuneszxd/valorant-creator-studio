"""Trend analysis over collected items. Pure functions, no I/O.

Every trend separates three kinds of statements:
* observed   - counts and values read from the source (with date and links);
* estimated  - numbers derived from observed data (e.g. views per day since publication);
* hypotheses - rule-based ideas about relevance and what to try. Never presented as fact.

Confidence reflects only the sample size and the nature of the source. It is capped at "média":
search/clip samples are not the whole platform, so nothing here is called "viral" or "alta".
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from ..analysis.moment_types import normalize_text
from ..models import CreatorProfile
from ..utils import median

THEMES: dict[str, tuple[str, list[str]]] = {
    "clutch": ("Clutch / situação de desvantagem", [
        "clutch", "1v1", "1v2", "1v3", "1v4", "1v5", "1x1", "1x2", "1x3", "1x4", "1x5", "sobrou"]),
    "ace": ("Ace / multikill", ["ace", "penta", "multikill", "quadra", "triple", "tap"]),
    "ranked_journey": ("Jornada de rank / elo", [
        "ranked", "ranqueada", "rank", "elo", "subindo", "jornada", "imortal", "radiante", "diamante",
        "ascendente", "platina", "road to", "caminho"]),
    "funny_fail": ("Engraçado / erros / fails", [
        "engracado", "fail", "fails", "bug", "kkk", "funny", "meme", "errei", "vacilo", "comedia"]),
    "tilt_reaction": ("Tilt / reação", ["tilt", "reacao", "rage", "puto", "raiva"]),
    "tips_guides": ("Dicas / guias / lineups", [
        "dica", "dicas", "guia", "tutorial", "como", "aprenda", "lineup", "lineups", "setup", "tips", "guide"]),
    "pro_scene": ("Cena competitiva / pro", [
        "vct", "champions", "masters", "pro", "campeonato", "mundial", "loud", "furia", "pain"]),
    "patch_news": ("Patch / novidades", [
        "patch", "atualizacao", "novo agente", "nerf", "buff", "update", "season", "ato", "episodio"]),
    "skins": ("Skins / bundles", ["skin", "skins", "bundle", "pacote"]),
}

# Lists change with game updates: treat as editable defaults, possibly outdated.
AGENTS = [
    "brimstone", "viper", "omen", "killjoy", "cypher", "sova", "sage", "phoenix", "jett", "reyna", "raze",
    "breach", "skye", "yoru", "astra", "kay/o", "kayo", "chamber", "neon", "fade", "harbor", "gekko",
    "deadlock", "iso", "clove", "vyse", "tejo", "waylay",
]
MAPS = ["ascent", "bind", "haven", "split", "icebox", "breeze", "fracture", "pearl", "lotus", "sunset", "abyss",
        "corrode"]

DURATION_BUCKETS = [(0, 15, "até 15 s"), (15, 30, "15–30 s"), (30, 45, "30–45 s"), (45, 60, "45–60 s"),
                    (60, 120, "1–2 min"), (120, 10**9, "mais de 2 min")]

RELEVANCE: dict[str, tuple[str, str]] = {
    "clutch": ("Clutch é o tipo de momento que suas lives mais produzem quando o round aperta.",
               "Corte de 20–35 s: mostre a situação (ex.: 1v3) no começo e termine no desfecho real."),
    "ace": ("Multikills são fáceis de entender sem contexto, o que ajuda em vídeos curtos.",
            "Corte do round inteiro até a última eliminação, com o placar do round na legenda."),
    "ranked_journey": ("Combina com séries de evolução (ex.: Diamante → Imortal) e dá motivo para voltarem ao canal.",
                       "Episódio de 30–45 s: uma partida, uma decisão-chave e o resultado real."),
    "funny_fail": ("Erros e momentos engraçados geram identificação e comentário.",
                   "Comece pouco antes do erro e deixe a sua reação real aparecer; legende a fala."),
    "tilt_reaction": ("Reações sinceras funcionam bem em vídeo curto quando o contexto é claro.",
                      "Mostre o round que causou o tilt e a reação logo em seguida, sem exagerar."),
    "tips_guides": ("Dicas rápidas com exemplo da sua própria gameplay se diferenciam de guias genéricos.",
                    "Uma dica por vídeo (15–30 s) com um exemplo real seu."),
    "pro_scene": ("Conteúdo da cena competitiva tem público, mas também muita concorrência.",
                  "Comentário curto sobre uma jogada, usando só material que você tem direito de usar."),
    "patch_news": ("Mudanças de patch interessam a quem joga ranqueada e envelhecem rápido.",
                   "Comente em 20–30 s o que muda para o seu rank e para os seus agentes."),
    "skins": ("Menos ligado a gameplay; só vale se fizer parte do seu estilo.",
              "Se fizer sentido, mostre a skin em uso numa jogada real."),
}


def confidence_for(n: int) -> str:
    if n < 5:
        return "muito baixa"
    if n < 15:
        return "baixa"
    return "média"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_days(item: dict[str, Any], now: datetime) -> float | None:
    published = _parse_dt(item.get("published_at"))
    if not published:
        return None
    return max((now - published).total_seconds() / 86400.0, 0.0)


def views_per_day(item: dict[str, Any], now: datetime) -> float | None:
    """ESTIMATE: views divided by days since publication (min 0.5 day to avoid huge ratios)."""
    views = item.get("views")
    age = age_days(item, now)
    if views is None or age is None:
        return None
    return views / max(age, 0.5)


def _text_blob(item: dict[str, Any]) -> str:
    parts = [item.get("title") or "", " ".join(item.get("hashtags") or []), " ".join(item.get("tags") or [])]
    return normalize_text(" ".join(parts))


def _has_keyword(blob: str, keywords: Iterable[str]) -> bool:
    for kw in keywords:
        norm = normalize_text(kw)
        if norm and re.search(r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])", blob):
            return True
    return False


def _examples(items: list[dict[str, Any]], now: datetime, limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda i: (views_per_day(i, now) or 0, i.get("views") or 0), reverse=True)
    return [
        {"title": i.get("title"), "url": i.get("url"), "views": i.get("views"), "channel": i.get("channel"),
         "published_at": i.get("published_at")}
        for i in ranked[:limit]
    ]


def _group_stats(items: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    views = [i["views"] for i in items if i.get("views") is not None]
    vpd = [v for v in (views_per_day(i, now) for i in items) if v is not None]
    durations = [i["duration_s"] for i in items if i.get("duration_s")]
    return {
        "n": len(items),
        "median_views": median(views),
        "median_duration_s": median(durations),
        "median_views_per_day": median(vpd),
    }


def _trend(kind: str, label: str, *, source: str, source_url: str | None, collected_at: str, n: int,
           observed: dict[str, Any], estimated: dict[str, Any] | None = None,
           hypotheses: list[str] | None = None, relevance: str | None = None, suggestion: str | None = None,
           limitations: list[str]) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "source": source,
        "source_url": source_url,
        "collected_at": collected_at,
        "observed": {"observed": observed, "estimated": estimated or {}, "hypotheses": hypotheses or []},
        "evidence": "observado",
        "relevance": relevance,
        "suggestion": suggestion,
        "confidence": confidence_for(n),
        "limitations": " ".join(limitations),
        "sample_size": n,
    }


def analyze_items(
    items: list[dict[str, Any]],
    *,
    source: str,
    source_url: str | None,
    collected_at: str,
    profile: CreatorProfile,
    sample_note: str,
    previous: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Derive trends from collected items. `previous` = {"collected_at", "n", "theme_share": {...}} or None."""
    now = _parse_dt(collected_at) or datetime.now(timezone.utc)
    total = len(items)
    if total == 0:
        return []
    base_limits = [sample_note, "Contagens públicas lidas no momento da coleta; mudam com o tempo."]
    overall = _group_stats(items, now)
    overall_vpd = overall["median_views_per_day"]
    trends: list[dict[str, Any]] = []

    def ratio_text(group_vpd: float | None) -> str | None:
        if group_vpd is None or not overall_vpd:
            return None
        ratio = group_vpd / overall_vpd
        return f"{ratio:.1f}× a mediana da amostra" if ratio >= 1.15 or ratio <= 0.87 else "próximo da mediana da amostra"

    # -- themes -------------------------------------------------------------------
    blobs = [(item, _text_blob(item)) for item in items]
    theme_share: dict[str, float] = {}
    for key, (label, keywords) in THEMES.items():
        matched = [item for item, blob in blobs if _has_keyword(blob, keywords)]
        theme_share[key] = len(matched) / total
        if len(matched) < 3:
            continue
        stats = _group_stats(matched, now)
        relevance, suggestion = RELEVANCE[key]
        hypotheses = [relevance]
        if key == "clutch" and "clutch" in profile.preferred_types:
            hypotheses.append("Você já prioriza clutches no seu perfil.")
        if key == "ranked_journey" and profile.rank_current and profile.rank_target:
            hypotheses.append(f"Seu objetivo é {profile.rank_current} → {profile.rank_target}: dá para virar uma série.")
        trends.append(_trend(
            "tema", label, source=source, source_url=source_url, collected_at=collected_at, n=len(matched),
            observed={"videos_com_o_tema": len(matched), "total_na_amostra": total,
                      "participacao": round(len(matched) / total, 3),
                      "mediana_visualizacoes": stats["median_views"],
                      "mediana_duracao_s": stats["median_duration_s"],
                      "exemplos": _examples(matched, now)},
            estimated={"mediana_visualizacoes_por_dia": stats["median_views_per_day"],
                       "comparado_a_amostra": ratio_text(stats["median_views_per_day"])},
            hypotheses=hypotheses, relevance=relevance, suggestion=suggestion,
            limitations=base_limits + ["O tema foi inferido por palavras no título/hashtags/tags; pode haver erros."],
        ))

    # -- hashtags -----------------------------------------------------------------
    tag_counter: Counter[str] = Counter()
    for item in items:
        for tag in set(item.get("hashtags") or []):
            tag_counter[tag] += 1
    top_tags = [(t, c) for t, c in tag_counter.most_common(15) if c >= 2]
    if top_tags:
        trends.append(_trend(
            "hashtag", "Hashtags mais frequentes", source=source, source_url=source_url, collected_at=collected_at,
            n=sum(c for _, c in top_tags),
            observed={"hashtags": [{"tag": "#" + t, "videos": c} for t, c in top_tags], "total_na_amostra": total},
            hypotheses=["Hashtags frequentes indicam o vocabulário do nicho; use poucas e relevantes ao vídeo."],
            relevance="Referência de vocabulário do nicho (não é garantia de alcance).",
            suggestion="Combine 3–5 hashtags frequentes com 1–2 específicas do corte (agente, mapa).",
            limitations=base_limits + ["Frequência de uso não prova que a hashtag aumente visualizações."],
        ))

    # -- duration -----------------------------------------------------------------
    buckets: list[dict[str, Any]] = []
    for low, high, label in DURATION_BUCKETS:
        group = [i for i in items if i.get("duration_s") is not None and low <= i["duration_s"] < high]
        if not group:
            continue
        stats = _group_stats(group, now)
        buckets.append({"faixa": label, "videos": len(group), "mediana_visualizacoes": stats["median_views"],
                        "mediana_views_por_dia_estimada": stats["median_views_per_day"]})
    if buckets:
        best = max((b for b in buckets if b["videos"] >= 3 and b["mediana_views_por_dia_estimada"]),
                   key=lambda b: b["mediana_views_por_dia_estimada"], default=None)
        trends.append(_trend(
            "duracao", "Distribuição de duração", source=source, source_url=source_url, collected_at=collected_at,
            n=sum(b["videos"] for b in buckets),
            observed={"faixas": [{k: v for k, v in b.items() if k != "mediana_views_por_dia_estimada"} for b in buckets],
                      "faixa_mais_comum": max(buckets, key=lambda b: b["videos"])["faixa"]},
            estimated={"faixas_views_por_dia": {b["faixa"]: b["mediana_views_por_dia_estimada"] for b in buckets},
                       "faixa_com_maior_mediana_estimada": best["faixa"] if best else None},
            hypotheses=["A faixa mais comum mostra o que o nicho publica; não indica a duração ideal."],
            relevance="Referência para escolher a duração dos seus cortes.",
            suggestion="Teste duas faixas de duração com o mesmo tipo de momento e compare no seu próprio canal.",
            limitations=base_limits + ["Duração e desempenho têm muitos outros fatores envolvidos."],
        ))

    # -- title patterns (hooks visible in text only) ---------------------------------
    def pat_question(t: str) -> bool: return "?" in t
    def pat_number(t: str) -> bool: return bool(re.search(r"\d", t))
    def pat_pov(t: str) -> bool: return bool(re.search(r"\b(pov|quando)\b", normalize_text(t)))
    def pat_you(t: str) -> bool: return bool(re.search(r"\b(voce|vc|seu|sua)\b", normalize_text(t)))
    def pat_caps(t: str) -> bool:
        letters = [ch for ch in t if ch.isalpha()]
        return len(letters) >= 6 and sum(ch.isupper() for ch in letters) / len(letters) > 0.6
    patterns = {"pergunta": pat_question, "número/placar no título": pat_number, "'POV' ou 'quando…'": pat_pov,
                "fala direto com o espectador (você/vc)": pat_you, "título em CAIXA ALTA": pat_caps}
    rows = []
    for name, fn in patterns.items():
        group = [i for i in items if i.get("title") and fn(i["title"])]
        if len(group) < 3:
            continue
        stats = _group_stats(group, now)
        rows.append({"padrao": name, "videos": len(group), "participacao": round(len(group) / total, 3),
                     "mediana_visualizacoes": stats["median_views"],
                     "views_por_dia_estimada": stats["median_views_per_day"]})
    if rows:
        trends.append(_trend(
            "gancho_titulo", "Padrões de título", source=source, source_url=source_url, collected_at=collected_at,
            n=sum(r["videos"] for r in rows),
            observed={"padroes": [{k: v for k, v in r.items() if k != "views_por_dia_estimada"} for r in rows]},
            estimated={"views_por_dia": {r["padrao"]: r["views_por_dia_estimada"] for r in rows}},
            hypotheses=["Padrões de título são só uma pista de gancho: o gancho falado nos primeiros segundos "
                        "não é acessível por essas fontes."],
            relevance="Inspiração para títulos e para o texto de abertura do vídeo.",
            suggestion="Teste um título em forma de pergunta e outro com o placar/situação real, e compare.",
            limitations=base_limits + ["Só o texto do título é analisado: edição, legendas e gancho falado não são lidos."],
        ))

    # -- agents & maps --------------------------------------------------------------
    for kind, label, names in (("agente", "Agentes mais citados", AGENTS), ("mapa", "Mapas mais citados", MAPS)):
        counter: Counter[str] = Counter()
        for _item, blob in blobs:
            for name in names:
                if _has_keyword(blob, [name]):
                    counter[name] += 1
        top = [(n, c) for n, c in counter.most_common(8) if c >= 2]
        if top:
            trends.append(_trend(
                kind, label, source=source, source_url=source_url, collected_at=collected_at,
                n=sum(c for _, c in top),
                observed={"citacoes": [{"nome": n.title(), "videos": c} for n, c in top], "total_na_amostra": total},
                hypotheses=["Mostra sobre o que os títulos falam, não o que está em alta na plataforma inteira."],
                relevance="Ajuda a escolher agente/mapa para destacar quando o corte permitir.",
                suggestion="Se um dos agentes citados é um que você joga, destaque-o no título e na hashtag.",
                limitations=base_limits + ["A lista de nomes é fixa e pode estar desatualizada."],
            ))

    # -- publication frequency ------------------------------------------------------
    dates = [d for d in (_parse_dt(i.get("published_at")) for i in items) if d]
    if len(dates) >= 5:
        span_days = max((max(dates) - min(dates)).total_seconds() / 86400.0, 1.0)
        trends.append(_trend(
            "frequencia", "Volume de publicações na amostra", source=source, source_url=source_url,
            collected_at=collected_at, n=len(dates),
            observed={"videos_na_amostra": len(dates), "primeira": min(dates).isoformat(),
                      "ultima": max(dates).isoformat()},
            estimated={"videos_por_dia_na_amostra": round(len(dates) / span_days, 2)},
            hypotheses=["Serve só de referência de ritmo do nicho, não de quanto você deve postar."],
            relevance="Compara o ritmo da amostra com a sua frequência desejada.",
            suggestion=("Defina uma frequência que você consiga manter" +
                        (f" (seu perfil indica {profile.publishing_frequency_per_week:g}/semana)."
                         if profile.publishing_frequency_per_week else ".")),
            limitations=base_limits + ["A amostra de uma busca não é o total publicado."],
        ))

    # -- change vs previous collection ----------------------------------------------
    if previous and previous.get("theme_share") and previous.get("n", 0) >= 20 and total >= 20:
        changes = []
        for key, share in theme_share.items():
            before = previous["theme_share"].get(key)
            if before is None:
                continue
            delta = share - before
            if abs(delta) >= 0.10:
                changes.append({"tema": THEMES[key][0], "antes": round(before, 3), "agora": round(share, 3),
                                "variacao_pontos_percentuais": round(delta * 100, 1)})
        if changes:
            trends.append(_trend(
                "mudanca", "Mudanças desde a coleta anterior", source=source, source_url=source_url,
                collected_at=collected_at, n=min(total, previous["n"]),
                observed={"coleta_anterior": previous["collected_at"], "coleta_atual": collected_at,
                          "mudancas": changes},
                hypotheses=["Mudança de participação pode ser só diferença entre as duas buscas, não tendência real."],
                relevance="Indica temas que ganharam ou perderam espaço na amostra entre as duas datas.",
                suggestion="Se um tema do seu interesse cresceu, teste um vídeo e compare com seus números.",
                limitations=base_limits + ["Duas coletas são pouco para afirmar tendência; repita ao longo das semanas."],
            ))

    return trends


def theme_shares(items: list[dict[str, Any]]) -> dict[str, float]:
    """Share of items matching each theme (stored with the run to detect changes later)."""
    if not items:
        return {}
    blobs = [_text_blob(i) for i in items]
    return {
        key: sum(1 for blob in blobs if _has_keyword(blob, kws)) / len(items)
        for key, (_label, kws) in THEMES.items()
    }
