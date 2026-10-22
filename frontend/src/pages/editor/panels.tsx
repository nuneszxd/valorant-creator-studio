import { useState } from "react";

import { api } from "../../api/client";
import type { Capabilities, ClipDetail, CopyPack, Cue, RenderConfig, SubtitleStyle } from "../../api/types";
import { RangePlayer } from "../../components/RangePlayer";
import { TimeInput } from "../../components/TimeInput";
import { Button, Card, Checkbox, Empty, Field, Notice, NumberInput, Select, TextArea, TextInput } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useAction } from "../../lib/hooks";
import { fmtTime } from "../../lib/format";

export interface Draft {
  title: string;
  start: number;
  end: number;
  type: string;
  map: string;
  agent: string;
  facts: Record<string, string>;
  cfg: RenderConfig;
  style: SubtitleStyle;
  cues: Cue[];
}

export type PatchDraft = (partial: Partial<Draft>) => void;

const RESOLUTIONS = [
  { value: "1080x1920", label: "1080 × 1920 (padrão TikTok / Reels / Shorts)", w: 1080, h: 1920 },
  { value: "720x1280", label: "720 × 1280 (mais leve e rápido)", w: 720, h: 1280 },
  { value: "540x960", label: "540 × 960 (rascunho)", w: 540, h: 960 },
];

function pct(value: number): number {
  return Math.round(value * 1000) / 10;
}

// ---------------------------------------------------------------------------- cut

export function CutPanel(props: { clip: ClipDetail; d: Draft; patch: PatchDraft; moments: Array<{ key: string; label: string }> }) {
  const { clip, d, patch } = props;
  const playable = clip.recording.video_codec ? ["h264", "vp8", "vp9", "av1"].includes(clip.recording.video_codec) : true;
  const maxTime = clip.recording.duration_s ?? undefined;
  const setFact = (key: string, value: string) => patch({ facts: { ...d.facts, [key]: value } });
  return (
    <div className="stack">
      <RangePlayer
        src={`/api/recordings/${clip.recording.id}/stream`}
        start={d.start}
        end={d.end}
        playable={playable}
        onMark={(kind, seconds) => {
          const t = Number(seconds.toFixed(1));
          patch(kind === "start" ? { start: t } : { end: t });
        }}
      />
      <div className="form-grid">
        <Field label="Início"><TimeInput value={d.start} max={maxTime} onChange={(v) => patch({ start: v })} /></Field>
        <Field label="Fim"><TimeInput value={d.end} max={maxTime} onChange={(v) => patch({ end: v })} /></Field>
        <Field label="Duração"><div className="input">{(d.end - d.start).toFixed(1)} s</div></Field>
      </div>
      <div className="form-grid">
        <Field label="Título"><TextInput value={d.title} maxLength={120} onChange={(e) => patch({ title: e.target.value })} /></Field>
        <Field label="Tipo de momento">
          <Select value={d.type} onChange={(v) => patch({ type: v })} options={props.moments.map((m) => ({ value: m.key, label: m.label }))} />
        </Field>
        <Field label="Mapa"><TextInput value={d.map} onChange={(e) => patch({ map: e.target.value })} /></Field>
        <Field label="Agente"><TextInput value={d.agent} onChange={(e) => patch({ agent: e.target.value })} /></Field>
      </div>
      <Card title="Fatos do corte (usados nos textos sugeridos)">
        <p className="muted small">
          Preencha só o que for verdade. Os textos sugeridos usam apenas estes fatos e a fala real da transcrição — nada é inventado.
        </p>
        <div className="form-grid">
          <Field label="Situação" hint="Ex.: 1v3">
            <TextInput value={d.facts.situation ?? ""} onChange={(e) => setFact("situation", e.target.value)} />
          </Field>
          <Field label="Resultado">
            <Select
              value={d.facts.result ?? ""}
              onChange={(v) => setFact("result", v)}
              options={[{ value: "", label: "(não informar)" }, { value: "vitória", label: "vitória" }, { value: "derrota", label: "derrota" }]}
            />
          </Field>
          <Field label="Rank na partida" hint="Ex.: Diamante 2">
            <TextInput value={d.facts.rank ?? ""} onChange={(e) => setFact("rank", e.target.value)} />
          </Field>
          <Field label="Round"><TextInput value={d.facts.round ?? ""} onChange={(e) => setFact("round", e.target.value)} /></Field>
        </div>
        <Field label="Observação sobre o que acontece">
          <TextArea rows={2} value={d.facts.note ?? ""} onChange={(e) => setFact("note", e.target.value)} />
        </Field>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------- framing

export function FramingPanel({ d, patch }: { d: Draft; patch: PatchDraft }) {
  const cfg = d.cfg;
  const setCfg = (partial: Partial<RenderConfig>) => patch({ cfg: { ...cfg, ...partial } });
  const resolutionValue = RESOLUTIONS.find((r) => r.w === cfg.width && r.h === cfg.height)?.value ?? "custom";
  const crop = cfg.crop;
  const setCrop = (partial: Partial<NonNullable<RenderConfig["crop"]>>) =>
    setCfg({ crop: { ...(crop ?? { x: 0.1, y: 0, w: 0.8, h: 1 }), ...partial } });

  return (
    <div className="stack">
      <Notice tone="info">
        O vídeo da live é horizontal. O padrão mantém o gameplay <strong>inteiro</strong> (minimapa, kill feed e vida visíveis) sobre um
        fundo desfocado, sem zoom automático.
      </Notice>
      <div className="form-grid">
        <Field label="Layout">
          <Select
            value={cfg.layout}
            onChange={(v) => setCfg({ layout: v as RenderConfig["layout"] })}
            options={[
              { value: "blur", label: "Gameplay inteiro + fundo desfocado (recomendado)" },
              { value: "solid", label: "Gameplay inteiro + fundo de cor sólida" },
              { value: "fill", label: "Preencher a tela (corta as laterais)" },
            ]}
          />
        </Field>
        <Field label="Resolução de saída">
          <Select
            value={resolutionValue}
            onChange={(v) => {
              const preset = RESOLUTIONS.find((r) => r.value === v);
              if (preset) setCfg({ width: preset.w, height: preset.h });
            }}
            options={[...RESOLUTIONS, { value: "custom", label: `Personalizada (${cfg.width} × ${cfg.height})` }]}
          />
        </Field>
        <Field label="Quadros por segundo">
          <Select
            value={cfg.fps === null ? "" : String(cfg.fps)}
            onChange={(v) => setCfg({ fps: v === "" ? null : Number(v) })}
            options={[{ value: "", label: "Igual ao original" }, { value: "30", label: "30 fps (arquivo menor)" }, { value: "60", label: "60 fps" }]}
          />
        </Field>
      </div>
      {resolutionValue === "custom" && (
        <div className="form-grid">
          <Field label="Largura (par)"><NumberInput value={cfg.width} min={360} max={2160} step={2} onChange={(v) => setCfg({ width: v ?? cfg.width })} /></Field>
          <Field label="Altura (par)"><NumberInput value={cfg.height} min={640} max={3840} step={2} onChange={(v) => setCfg({ height: v ?? cfg.height })} /></Field>
        </div>
      )}
      {cfg.layout === "solid" && (
        <Field label="Cor do fundo"><input className="input" type="color" value={cfg.background_color} onChange={(e) => setCfg({ background_color: e.target.value })} /></Field>
      )}
      {cfg.layout === "fill" && (
        <>
          <Notice tone="warn">“Preencher” corta as laterais do gameplay e pode esconder o minimapa ou o kill feed. Ajuste o foco e confira na prévia.</Notice>
          <Field label={`Foco horizontal: ${pct(cfg.focus_x)}% (0% = esquerda, 100% = direita)`}>
            <input className="input" type="range" min={0} max={1} step={0.05} value={cfg.focus_x} onChange={(e) => setCfg({ focus_x: Number(e.target.value) })} />
          </Field>
        </>
      )}
      <Card title="Recorte / zoom manual (opcional)">
        <Checkbox
          checked={crop !== null}
          onChange={(on) => setCfg({ crop: on ? { x: 0.1, y: 0, w: 0.8, h: 1 } : null })}
          label="Recortar uma região do vídeo antes de encaixar na vertical"
        />
        {crop && (
          <>
            <Notice tone="warn">Zoom nunca é aplicado sozinho. Recortar pode esconder informações do HUD — confira na prévia.</Notice>
            <div className="form-grid" style={{ marginTop: 8 }}>
              <Field label="Esquerda (%)"><NumberInput value={pct(crop.x)} min={0} max={95} step={1} onChange={(v) => setCrop({ x: (v ?? 0) / 100 })} /></Field>
              <Field label="Topo (%)"><NumberInput value={pct(crop.y)} min={0} max={95} step={1} onChange={(v) => setCrop({ y: (v ?? 0) / 100 })} /></Field>
              <Field label="Largura (%)"><NumberInput value={pct(crop.w)} min={5} max={100} step={1} onChange={(v) => setCrop({ w: (v ?? 100) / 100 })} /></Field>
              <Field label="Altura (%)"><NumberInput value={pct(crop.h)} min={5} max={100} step={1} onChange={(v) => setCrop({ h: (v ?? 100) / 100 })} /></Field>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------- audio

export function AudioPanel({ d, patch }: { d: Draft; patch: PatchDraft }) {
  const cfg = d.cfg;
  const setCfg = (partial: Partial<RenderConfig>) => patch({ cfg: { ...cfg, ...partial } });
  return (
    <div className="stack">
      <div className="form-grid">
        <Field label="Volume (dB)" hint="0 = igual ao original. +3 dB ≈ um pouco mais alto.">
          <NumberInput value={cfg.volume_db} min={-30} max={20} step={0.5} onChange={(v) => setCfg({ volume_db: v ?? 0 })} />
        </Field>
        <Field label="Fade in/out (s)" hint="0 desliga.">
          <NumberInput value={cfg.fade_s} min={0} max={3} step={0.05} onChange={(v) => setCfg({ fade_s: v ?? 0 })} />
        </Field>
        <Field label="Qualidade do áudio (kbps)">
          <NumberInput value={cfg.audio_bitrate_kbps} min={64} max={320} step={16} onChange={(v) => setCfg({ audio_bitrate_kbps: v ?? 160 })} />
        </Field>
      </div>
      <Checkbox
        checked={cfg.loudnorm}
        onChange={(v) => setCfg({ loudnorm: v })}
        label="Normalizar o volume (alvo −14 LUFS). Deixa trechos baixos mais audíveis, mas altera a dinâmica; demora um pouco mais."
      />
      <Notice tone="warn">
        Antes de publicar, ouça o corte: música protegida tocando na live pode ser silenciada ou gerar bloqueio na plataforma.
      </Notice>
    </div>
  );
}

// ---------------------------------------------------------------------------- subtitles

export function SubtitlesPanel(props: { clip: ClipDetail; d: Draft; patch: PatchDraft; setCues: (cues: Cue[]) => void; onReload: () => void }) {
  const { clip, d, patch } = props;
  const { run, busy } = useAction();
  const [allowDownload, setAllowDownload] = useState(false);
  const style = d.style;
  const setStyle = (partial: Partial<SubtitleStyle>) => patch({ style: { ...style, ...partial } });
  const duration = d.end - d.start;

  async function fromTranscript() {
    const updated = await run(() => api.post<ClipDetail>(`/api/clips/${clip.id}/subtitles/from-transcript`), "Legendas preenchidas a partir da transcrição.");
    if (updated) props.setCues(updated.subtitles ?? []);
  }
  async function transcribe() {
    await run(() => api.post(`/api/clips/${clip.id}/transcribe`, { allow_model_download: allowDownload }), "Transcrição na fila.");
    props.onReload();
  }
  const setCue = (index: number, partial: Partial<Cue>) =>
    props.setCues(d.cues.map((cue, i) => (i === index ? { ...cue, ...partial } : cue)));

  return (
    <div className="stack">
      <Checkbox checked={d.cfg.subtitles} onChange={(v) => patch({ cfg: { ...d.cfg, subtitles: v } })} label="Gravar legendas no vídeo" />
      <Card title="Texto das legendas">
        <div className="row wrap">
          <Button onClick={fromTranscript} busy={busy}>Preencher da transcrição existente</Button>
          <Button onClick={transcribe} busy={busy}>Transcrever este corte</Button>
          <Checkbox checked={allowDownload} onChange={setAllowDownload} label="permitir baixar o modelo se faltar" />
        </div>
        <p className="muted small">
          A transcrição roda na CPU e pode errar nomes de agentes e gírias: revise o texto. As palavras são destacadas conforme
          são faladas (se o texto for editado, o tempo é redistribuído de forma aproximada).
        </p>
        {d.cues.length === 0 ? (
          <Empty>Sem legendas. Transcreva o corte ou adicione manualmente.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Início</th><th>Fim</th><th>Texto</th><th /></tr></thead>
              <tbody>
                {d.cues.map((cue, i) => (
                  <tr key={i}>
                    <td style={{ width: 90 }}><TimeInput value={cue.start} max={duration} onChange={(v) => setCue(i, { start: v })} ariaLabel="Início da legenda" /></td>
                    <td style={{ width: 90 }}><TimeInput value={cue.end} max={duration} onChange={(v) => setCue(i, { end: v })} ariaLabel="Fim da legenda" /></td>
                    <td><TextInput value={cue.text} onChange={(e) => setCue(i, { text: e.target.value })} maxLength={300} /></td>
                    <td><Button variant="ghost" onClick={() => props.setCues(d.cues.filter((_, j) => j !== i))}>✕</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ marginTop: 8 }}>
          <Button
            variant="ghost"
            onClick={() => {
              const last = d.cues.length > 0 ? d.cues[d.cues.length - 1].end : 0;
              props.setCues([...d.cues, { start: Math.min(last, Math.max(duration - 1, 0)), end: Math.min(last + 2, duration), text: "Nova legenda" }]);
            }}
          >
            + Adicionar legenda
          </Button>
        </div>
      </Card>

      <SubtitleStyleCard style={style} setStyle={setStyle} />
    </div>
  );
}

export function SubtitleStyleCard({ style, setStyle }: { style: SubtitleStyle; setStyle: (partial: Partial<SubtitleStyle>) => void }) {
  return (
    <Card title="Estilo das legendas">
      <div className="form-grid">
        <Field label="Fonte" hint="Precisa estar instalada no computador."><TextInput value={style.font} onChange={(e) => setStyle({ font: e.target.value })} /></Field>
        <Field label="Tamanho (% da altura)"><NumberInput value={style.size_pct} min={2} max={10} step={0.25} onChange={(v) => setStyle({ size_pct: v ?? 4.5 })} /></Field>
        <Field label="Posição (% acima da base)"><NumberInput value={style.position_pct} min={2} max={90} step={1} onChange={(v) => setStyle({ position_pct: v ?? 22 })} /></Field>
        <Field label="Palavras por linha"><NumberInput value={style.max_words_per_line} min={1} max={8} step={1} onChange={(v) => setStyle({ max_words_per_line: v ?? 4 })} /></Field>
        <Field label="Contorno (px)"><NumberInput value={style.outline_px} min={0} max={12} step={0.5} onChange={(v) => setStyle({ outline_px: v ?? 4 })} /></Field>
        <Field label="Cor do texto"><input className="input" type="color" value={style.text_color} onChange={(e) => setStyle({ text_color: e.target.value })} /></Field>
        <Field label="Cor do destaque"><input className="input" type="color" value={style.highlight_color} onChange={(e) => setStyle({ highlight_color: e.target.value })} /></Field>
        <Field label="Cor do contorno"><input className="input" type="color" value={style.outline_color} onChange={(e) => setStyle({ outline_color: e.target.value })} /></Field>
      </div>
      <div className="row wrap" style={{ marginTop: 8 }}>
        <Checkbox checked={style.highlight_words} onChange={(v) => setStyle({ highlight_words: v })} label="Destacar a palavra falada" />
        <Checkbox checked={style.bold} onChange={(v) => setStyle({ bold: v })} label="Negrito" />
        <Checkbox checked={style.uppercase} onChange={(v) => setStyle({ uppercase: v })} label="CAIXA ALTA" />
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------- export

export function ExportPanel({ d, patch, caps }: { d: Draft; patch: PatchDraft; caps: Capabilities | null }) {
  const cfg = d.cfg;
  const setCfg = (partial: Partial<RenderConfig>) => patch({ cfg: { ...cfg, ...partial } });
  const { run, busy } = useAction();
  const toast = useToast();
  const available = (name: string) => caps?.ffmpeg.encoders[name] ?? name === "libx264";

  async function test() {
    const result = await run(() => api.post<{ ok: boolean; detail: string }>("/api/system/test-encoder", { encoder: cfg.encoder }));
    if (result) toast(result.ok ? `Encoder ${cfg.encoder} funcionou neste computador.` : `Encoder ${cfg.encoder} falhou: ${result.detail}`, result.ok ? "ok" : "error");
  }

  return (
    <div className="stack">
      <div className="form-grid">
        <Field label="Encoder (como o vídeo é comprimido)">
          <Select
            value={cfg.encoder}
            onChange={(v) => setCfg({ encoder: v as RenderConfig["encoder"] })}
            options={[
              { value: "libx264", label: "libx264 — CPU (melhor qualidade por tamanho; mais lento)" },
              { value: "h264_amf", label: `h264_amf — GPU AMD (mais rápido)${available("h264_amf") ? "" : " — não encontrado neste FFmpeg"}` },
              { value: "h264_nvenc", label: `h264_nvenc — GPU NVIDIA${available("h264_nvenc") ? "" : " — não encontrado"}` },
              { value: "h264_qsv", label: `h264_qsv — Intel${available("h264_qsv") ? "" : " — não encontrado"}` },
            ]}
          />
        </Field>
        {cfg.encoder === "libx264" ? (
          <>
            <Field label="Qualidade (CRF)" hint="Menor = melhor qualidade e arquivo maior. 18–23 é um bom intervalo.">
              <NumberInput value={cfg.crf} min={12} max={35} step={1} onChange={(v) => setCfg({ crf: v ?? 20 })} />
            </Field>
            <Field label="Velocidade (preset)" hint="Mais lento = arquivo menor para a mesma qualidade.">
              <Select
                value={cfg.preset}
                onChange={(v) => setCfg({ preset: v })}
                options={["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"].map((p) => ({ value: p, label: p }))}
              />
            </Field>
          </>
        ) : cfg.encoder === "h264_amf" ? (
          <Field label="Taxa de bits (kbps)" hint="Maior = melhor qualidade e arquivo maior. 8000–12000 é comum para 1080×1920.">
            <NumberInput value={cfg.bitrate_kbps} min={1000} max={50000} step={500} onChange={(v) => setCfg({ bitrate_kbps: v ?? 10000 })} />
          </Field>
        ) : (
          <Field label="Qualidade (CQ/CRF)">
            <NumberInput value={cfg.crf} min={12} max={35} step={1} onChange={(v) => setCfg({ crf: v ?? 23 })} />
          </Field>
        )}
      </div>
      <div className="row wrap">
        <Button onClick={test} busy={busy}>Testar este encoder agora</Button>
        <span className="muted small">Codifica meio segundo de vídeo de teste para confirmar que funciona neste computador.</span>
      </div>
      <Notice tone="info">
        A prévia rápida sempre usa libx264 em baixa resolução (540×960). O arquivo final usa as opções desta aba. Encoders de GPU
        costumam ser mais rápidos, porém com qualidade um pouco pior para o mesmo tamanho; se falhar, volte para libx264.
      </Notice>
    </div>
  );
}

// ---------------------------------------------------------------------------- copy

export function CopyPanel({ clip, onChanged }: { clip: ClipDetail; onChanged: () => void }) {
  const { run, busy } = useAction();
  const toast = useToast();
  const [pack, setPack] = useState<CopyPack | null>(clip.copy_pack);

  async function generate() {
    const result = await run(() => api.post<{ copy: CopyPack }>(`/api/clips/${clip.id}/copy/generate`), "Sugestões geradas.");
    if (result) {
      setPack(result.copy);
      onChanged();
    }
  }
  async function save() {
    if (!pack) return;
    const body = {
      hooks: pack.hooks, titles: pack.titles, caption: pack.caption, hashtags: pack.hashtags,
      description: pack.description, cover_text: pack.cover_text, comment_cta: pack.comment_cta,
    };
    const result = await run(() => api.put<{ copy: CopyPack }>(`/api/clips/${clip.id}/copy`, body), "Textos salvos.");
    if (result) setPack(result.copy);
  }
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copiado.", "ok");
    } catch {
      toast("Não foi possível copiar automaticamente; selecione o texto e copie.", "error");
    }
  }
  const setList = (key: "hooks" | "titles" | "cover_text", index: number, value: string) => {
    if (!pack) return;
    const next = pack[key].map((item, i) => (i === index ? value : item));
    if (key === "hooks") setPack({ ...pack, hooks: next });
    else if (key === "titles") setPack({ ...pack, titles: next });
    else setPack({ ...pack, cover_text: next });
  };

  return (
    <div className="stack">
      <Notice tone="info">
        Textos gerados por regras locais (sem IA externa), usando só o tipo do momento, os fatos que você informou e a fala real. Edite
        livremente — e confira se cada frase é verdadeira para este corte.
      </Notice>
      <div className="row wrap">
        <Button variant="primary" onClick={generate} busy={busy}>{pack ? "Gerar novamente" : "Gerar sugestões"}</Button>
        {pack && <Button onClick={save} busy={busy}>Salvar edições</Button>}
      </div>
      {!pack ? (
        <Empty>Nenhuma sugestão ainda.</Empty>
      ) : (
        <div className="stack">
          {(pack.notes ?? []).map((n) => <Notice key={n} tone="warn">{n}</Notice>)}
          <Card title="Ganchos para os primeiros segundos">
            {pack.hooks.map((hook, i) => (
              <div key={i} className="row" style={{ marginBottom: 6 }}>
                <TextInput value={hook} onChange={(e) => setList("hooks", i, e.target.value)} />
                <Button variant="ghost" onClick={() => copy(hook)}>Copiar</Button>
              </div>
            ))}
          </Card>
          <Card title="Títulos curtos">
            {pack.titles.map((title, i) => (
              <div key={i} className="row" style={{ marginBottom: 6 }}>
                <TextInput value={title} onChange={(e) => setList("titles", i, e.target.value)} />
                <Button variant="ghost" onClick={() => copy(title)}>Copiar</Button>
              </div>
            ))}
          </Card>
          <Card title="Legenda da publicação" actions={<Button variant="ghost" onClick={() => copy(`${pack.caption}\n\n${pack.hashtags.join(" ")}`)}>Copiar com hashtags</Button>}>
            <TextArea rows={3} value={pack.caption} onChange={(e) => setPack({ ...pack, caption: e.target.value })} />
            <Field label="Hashtags (separadas por espaço)">
              <TextInput
                value={pack.hashtags.join(" ")}
                onChange={(e) => setPack({ ...pack, hashtags: e.target.value.split(/\s+/).filter(Boolean) })}
              />
            </Field>
          </Card>
          <Card title="Contexto, capa e chamada para comentários">
            <Field label="Descrição do contexto"><TextArea rows={3} value={pack.description} onChange={(e) => setPack({ ...pack, description: e.target.value })} /></Field>
            <div className="stack" style={{ marginTop: 8 }}>
              <strong className="small">Texto da capa</strong>
              {pack.cover_text.map((text, i) => (
                <TextInput key={i} value={text} onChange={(e) => setList("cover_text", i, e.target.value)} />
              ))}
              <Field label="Chamada para comentários"><TextInput value={pack.comment_cta} onChange={(e) => setPack({ ...pack, comment_cta: e.target.value })} /></Field>
            </div>
            <p className="muted small">{pack.source}{pack.generated_at ? ` · gerado em ${pack.generated_at.slice(0, 16).replace("T", " ")}` : ""}</p>
          </Card>
        </div>
      )}
      <p className="muted small">Corte de {fmtTime(clip.duration_s)} · {clip.type_label}</p>
    </div>
  );
}
