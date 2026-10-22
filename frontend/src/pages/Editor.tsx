import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, qs } from "../api/client";
import type { Capabilities, Clip, ClipDetail, Cue, Facets, Job, RenderPlan } from "../api/types";
import { JobStatus } from "../components/JobStatus";
import { useJobs } from "../components/JobsContext";
import { Badge, Button, Card, Empty, ErrorBox, Loading, Notice, PageHeader, Tabs } from "../components/ui";
import { fmtBytes, fmtDate, fmtTime } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";
import { AudioPanel, CopyPanel, CutPanel, ExportPanel, FramingPanel, SubtitlesPanel } from "./editor/panels";
import type { Draft, PatchDraft } from "./editor/panels";

export function Editor() {
  const { id } = useParams();
  return id ? <EditorView id={Number(id)} /> : <ClipList />;
}

function ClipList() {
  const navigate = useNavigate();
  const { tick } = useJobs();
  const clips = useAsync(() => api.get<Clip[]>(`/api/clips${qs({ limit: 200 })}`), [tick]);
  return (
    <div className="stack">
      <PageHeader
        title="Editor de cortes"
        subtitle="Cortes criados a partir dos candidatos aprovados. Abra um para ajustar o enquadramento, as legendas e exportar."
        actions={<Link className="btn" to="/candidates">Ir para candidatos</Link>}
      />
      <ErrorBox error={clips.error} />
      {clips.loading && !clips.data && <Loading />}
      {clips.data && clips.data.length === 0 && (
        <Empty>Nenhum corte ainda. Aprove um candidato e clique em “Criar corte e abrir no editor”.</Empty>
      )}
      {clips.data && clips.data.length > 0 && (
        <Card>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Corte</th><th>Gravação</th><th>Duração</th><th>Estado</th><th>Criado</th></tr></thead>
              <tbody>
                {clips.data.map((c) => (
                  <tr key={c.id} className="clickable" onClick={() => navigate(`/editor/${c.id}`)}>
                    <td>{c.title}<div className="muted small">{c.type_label}</div></td>
                    <td>{c.recording_name}</td>
                    <td>{fmtTime(c.duration_s)}</td>
                    <td><Badge tone={c.status === "ready" ? "ok" : c.status === "rendering" ? "info" : "neutral"}>{c.status_label}</Badge></td>
                    <td>{fmtDate(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function EditorView({ id }: { id: number }) {
  const { tick } = useJobs();
  const [version, setVersion] = useState(0);
  const clip = useAsync(() => api.get<ClipDetail>(`/api/clips/${id}`), [id, tick, version]);
  const caps = useAsync(() => api.get<Capabilities>("/api/system/capabilities"), []);
  const facets = useAsync(() => api.get<Facets>("/api/library/facets"), []);

  if (clip.loading && !clip.data) return <Loading />;
  if (!clip.data) return <ErrorBox error={clip.error} />;
  return (
    <EditorForm
      key={clip.data.id}
      clip={clip.data}
      caps={caps.data}
      moments={facets.data?.moment_types ?? [{ key: clip.data.moment_type, label: clip.data.type_label }]}
      reload={() => setVersion((v) => v + 1)}
    />
  );
}

function EditorForm(props: {
  clip: ClipDetail;
  caps: Capabilities | null;
  moments: Array<{ key: string; label: string }>;
  reload: () => void;
}) {
  const { clip, caps, moments, reload } = props;
  const { run, busy } = useAction();
  const { summary, refresh, tick } = useJobs();
  const [tab, setTab] = useState("cut");
  const [dirty, setDirty] = useState(false);
  const [plan, setPlan] = useState<RenderPlan | null>(null);
  const cuesTouched = useRef(false);

  const [d, setD] = useState<Draft>(() => ({
    title: clip.title,
    start: clip.start_s,
    end: clip.end_s,
    type: clip.moment_type,
    map: clip.map ?? "",
    agent: clip.agent ?? "",
    facts: clip.facts ?? {},
    cfg: clip.render_config as Draft["cfg"],
    style: clip.subtitle_style as Draft["style"],
    cues: clip.subtitles ?? [],
  }));

  const patch: PatchDraft = (partial) => {
    if (partial.cues) cuesTouched.current = true;
    setD((prev) => ({ ...prev, ...partial }));
    setDirty(true);
  };
  const setCues = (cues: Cue[]) => patch({ cues });

  // Pick up subtitles written by a finished transcription, unless the user is editing them.
  const serverCues = JSON.stringify(clip.subtitles ?? []);
  useEffect(() => {
    if (!cuesTouched.current) {
      setD((prev) => ({ ...prev, cues: clip.subtitles ?? [] }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverCues]);

  const activeJobs: Job[] = (summary?.active ?? []).filter((j) => j.clip_id === clip.id);
  const rendering = activeJobs.some((j) => j.kind === "render");

  async function save(): Promise<boolean> {
    const body = {
      title: d.title,
      start_s: d.start,
      end_s: d.end,
      moment_type: d.type,
      map: d.map || null,
      agent: d.agent || null,
      facts: d.facts,
      render_config: d.cfg,
      subtitle_style: d.style,
      subtitles: d.cues.map((c) => ({ start: c.start, end: c.end, text: c.text, words: c.words ?? null })),
    };
    const updated = await run(() => api.patch<ClipDetail>(`/api/clips/${clip.id}`, body), "Corte salvo.");
    if (!updated) return false;
    setDirty(false);
    cuesTouched.current = false;
    reload();
    return true;
  }

  async function render(mode: "final" | "preview") {
    if (dirty && !(await save())) return;
    const job = await run(
      () => api.post<Job>(`/api/clips/${clip.id}/render`, { mode }),
      mode === "preview" ? "Prévia na fila." : "Renderização na fila.",
    );
    if (job) void refresh();
  }

  async function showPlan() {
    if (dirty && !(await save())) return;
    const result = await run(() => api.get<RenderPlan>(`/api/clips/${clip.id}/render-plan${qs({ mode: "final" })}`));
    if (result) setPlan(result);
  }

  const quote = (arg: string) => (/[\s;\[\]]/.test(arg) ? `"${arg}"` : arg);

  return (
    <div className="stack">
      <PageHeader
        title={d.title || clip.title}
        subtitle={<>
          <Link to={`/recordings/${clip.recording.id}`}>{clip.recording.name}</Link> · {fmtTime(d.start)}–{fmtTime(d.end)} ({(d.end - d.start).toFixed(1)} s)
          {clip.candidate ? ` · pontuação ${clip.candidate.score.toFixed(0)}` : ""}
        </>}
        actions={<>
          <Button onClick={save} disabled={!dirty} busy={busy}>{dirty ? "Salvar alterações" : "Salvo"}</Button>
          <Button onClick={() => render("preview")} disabled={rendering}>Prévia rápida</Button>
          <Button variant="primary" onClick={() => render("final")} disabled={rendering}>Renderizar MP4</Button>
        </>}
      />

      <div className="split" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(280px, 380px)" }}>
        <div>
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "cut", label: "Corte" },
              { key: "framing", label: "Enquadramento" },
              { key: "audio", label: "Áudio" },
              { key: "subs", label: "Legendas" },
              { key: "export", label: "Exportação" },
              { key: "copy", label: "Textos" },
            ]}
          />
          {tab === "cut" && <CutPanel clip={clip} d={d} patch={patch} moments={moments} />}
          {tab === "framing" && <FramingPanel d={d} patch={patch} />}
          {tab === "audio" && <AudioPanel d={d} patch={patch} />}
          {tab === "subs" && <SubtitlesPanel clip={clip} d={d} patch={patch} setCues={setCues} onReload={() => { void refresh(); reload(); }} />}
          {tab === "export" && <ExportPanel d={d} patch={patch} caps={caps} />}
          {tab === "copy" && <CopyPanel clip={clip} onChanged={reload} />}
        </div>

        <div className="stack">
          <Card title="Resultado">
            <div className="stack">
              {activeJobs.length > 0 && <div className="jobs-panel">{activeJobs.map((j) => <JobStatus key={j.id} job={j} />)}</div>}
              {clip.last_error && <Notice tone="warn">Último erro: {clip.last_error}</Notice>}
              {clip.has_preview && (
                <div>
                  <strong className="small">Prévia rápida (540 de largura)</strong>
                  <video className="vertical-video" src={`/api/clips/${clip.id}/preview?v=${tick}`} controls preload="metadata" />
                </div>
              )}
              {clip.has_output && (
                <div>
                  <strong className="small">Arquivo final</strong>
                  <video className="vertical-video" src={`/api/clips/${clip.id}/file?v=${clip.rendered_at ?? ""}`} controls preload="metadata" />
                  <div className="muted small">
                    {fmtBytes(clip.output_size)} · renderizado em {fmtDate(clip.rendered_at)}
                    <br /><code>{clip.output_path}</code>
                  </div>
                  <a className="btn" href={`/api/clips/${clip.id}/file?download=true`}>Baixar MP4</a>
                </div>
              )}
              {!clip.has_preview && !clip.has_output && activeJobs.length === 0 && (
                <Empty>Use “Prévia rápida” para ver o resultado em baixa resolução, ou “Renderizar MP4” para o arquivo final.</Empty>
              )}
              <p className="muted small">A renderização só acontece quando você clica; ela usa a CPU/GPU deste computador e pode ser cancelada.</p>
            </div>
          </Card>
          <Card title="Detalhes técnicos">
            <Button variant="ghost" onClick={showPlan}>Ver comando do FFmpeg</Button>
            {plan && (
              <div className="stack">
                <div className="muted small">Saída {plan.output_size} · {plan.duration_s.toFixed(1)} s · legendas {plan.subtitles_applied ? "aplicadas" : "não aplicadas"}</div>
                {plan.notes.map((n) => <Notice key={n} tone="warn">{n}</Notice>)}
                <pre>{plan.command.map(quote).join(" ")}</pre>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
