import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, qs } from "../api/client";
import type { Candidate, CleanupPreview, Clip, Facets, Publication, Recording } from "../api/types";
import { useJobs } from "../components/JobsContext";
import { Badge, Button, Card, Checkbox, Empty, ErrorBox, Field, Loading, Notice, NumberInput, PageHeader, Select, Tabs, TextInput } from "../components/ui";
import { fmtBytes, fmtDate, fmtTime } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

interface Filters {
  q: string;
  map: string;
  agent: string;
  type: string;
  status: string;
  game: string;
  platform: string;
  minScore: number | null;
  dateFrom: string;
  dateTo: string;
}

const EMPTY: Filters = { q: "", map: "", agent: "", type: "", status: "", game: "", platform: "", minScore: null, dateFrom: "", dateTo: "" };

export function Library() {
  const [tab, setTab] = useState("clips");
  const [f, setF] = useState<Filters>(EMPTY);
  const facets = useAsync(() => api.get<Facets>("/api/library/facets"), []);
  const set = (partial: Partial<Filters>) => setF((prev) => ({ ...prev, ...partial }));
  const opt = (label: string, values: string[]) => [{ value: "", label }, ...values.map((v) => ({ value: v, label: v }))];

  const showMap = tab !== "pubs" && tab !== "cleanup";
  return (
    <div className="stack">
      <PageHeader
        title="Biblioteca"
        subtitle="Tudo o que existe localmente: gravações, candidatos, cortes, exportações e publicações. Os vídeos ficam em disco; o banco guarda só os metadados e caminhos."
      />
      <Tabs
        active={tab}
        onChange={(t) => { setTab(t); setF(EMPTY); }}
        tabs={[
          { key: "clips", label: "Cortes e exportações" },
          { key: "candidates", label: "Candidatos" },
          { key: "recordings", label: "Gravações" },
          { key: "pubs", label: "Publicações" },
          { key: "cleanup", label: "Limpeza de arquivos" },
        ]}
      />
      {tab !== "cleanup" && (
        <div className="row wrap">
          <TextInput placeholder="Buscar…" value={f.q} onChange={(e) => set({ q: e.target.value })} style={{ maxWidth: 200 }} />
          {showMap && <Select value={f.game} onChange={(v) => set({ game: v })} options={opt("Todos os jogos", facets.data?.games ?? [])} style={{ maxWidth: 160 }} />}
          {showMap && <Select value={f.map} onChange={(v) => set({ map: v })} options={opt("Todos os mapas", facets.data?.maps ?? [])} style={{ maxWidth: 160 }} />}
          {showMap && <Select value={f.agent} onChange={(v) => set({ agent: v })} options={opt("Todos os agentes", facets.data?.agents ?? [])} style={{ maxWidth: 170 }} />}
          {(tab === "clips" || tab === "candidates") && (
            <Select
              value={f.type}
              onChange={(v) => set({ type: v })}
              options={[{ value: "", label: "Todos os tipos" }, ...(facets.data?.moment_types ?? []).map((t) => ({ value: t.key, label: t.label }))]}
              style={{ maxWidth: 200 }}
            />
          )}
          {tab === "pubs" && <Select value={f.platform} onChange={(v) => set({ platform: v })} options={opt("Todas as plataformas", facets.data?.platforms ?? [])} style={{ maxWidth: 190 }} />}
          {(tab === "clips" || tab === "candidates") && (
            <div style={{ width: 130 }}><NumberInput value={f.minScore} onChange={(v) => set({ minScore: v })} min={0} max={100} placeholder="Pontuação mín." /></div>
          )}
          <input className="input" type="date" aria-label="De" value={f.dateFrom} onChange={(e) => set({ dateFrom: e.target.value })} style={{ maxWidth: 150 }} />
          <input className="input" type="date" aria-label="Até" value={f.dateTo} onChange={(e) => set({ dateTo: e.target.value })} style={{ maxWidth: 150 }} />
          <Button variant="ghost" onClick={() => setF(EMPTY)}>Limpar filtros</Button>
        </div>
      )}
      {tab === "clips" && <ClipsTab f={f} set={set} />}
      {tab === "candidates" && <CandidatesTab f={f} />}
      {tab === "recordings" && <RecordingsTab f={f} />}
      {tab === "pubs" && <PubsTab f={f} />}
      {tab === "cleanup" && <CleanupTab />}
    </div>
  );
}

function ClipsTab({ f, set }: { f: Filters; set: (p: Partial<Filters>) => void }) {
  const navigate = useNavigate();
  const { tick } = useJobs();
  const clips = useAsync(
    () => api.get<Clip[]>(`/api/clips${qs({ q: f.q, map: f.map, agent: f.agent, type: f.type, status: f.status, min_score: f.minScore, date_from: f.dateFrom, date_to: f.dateTo, limit: 300 })}`),
    [f.q, f.map, f.agent, f.type, f.status, f.minScore, f.dateFrom, f.dateTo, tick],
  );
  return (
    <div className="stack">
      <div className="row">
        <Select
          value={f.status}
          onChange={(v) => set({ status: v })}
          options={[{ value: "", label: "Todos os estados" }, { value: "draft", label: "Rascunho" }, { value: "ready", label: "Prontos (exportados)" }]}
          style={{ maxWidth: 220 }}
        />
      </div>
      <ErrorBox error={clips.error} />
      {clips.loading && !clips.data && <Loading />}
      {clips.data && clips.data.length === 0 && <Empty>Nenhum corte com esses filtros.</Empty>}
      {clips.data && clips.data.length > 0 && (
        <Card>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Corte</th><th>Mapa / agente</th><th>Tipo</th><th>Pont.</th><th>Estado</th><th>Arquivo</th><th>Criado</th></tr></thead>
              <tbody>
                {clips.data.map((c) => (
                  <tr key={c.id} className="clickable" onClick={() => navigate(`/editor/${c.id}`)}>
                    <td>{c.title}<div className="muted small">{c.recording_name} · {fmtTime(c.duration_s)}</div>{c.copy_pack?.hooks?.[0] && <div className="small">“{c.copy_pack.hooks[0]}”</div>}</td>
                    <td>{[c.map, c.agent].filter(Boolean).join(" / ") || "–"}</td>
                    <td>{c.type_label}</td>
                    <td>{c.score !== null && c.score !== undefined ? c.score.toFixed(0) : "–"}</td>
                    <td><Badge tone={c.status === "ready" ? "ok" : "neutral"}>{c.status_label}</Badge></td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {c.has_output ? <a href={`/api/clips/${c.id}/file?download=true`}>{fmtBytes(c.output_size)} · baixar</a> : "–"}
                    </td>
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

function CandidatesTab({ f }: { f: Filters }) {
  const navigate = useNavigate();
  const { tick } = useJobs();
  const list = useAsync(
    () => api.get<Candidate[]>(`/api/candidates${qs({ q: f.q, map: f.map, agent: f.agent, type: f.type, min_score: f.minScore, limit: 300 })}`),
    [f.q, f.map, f.agent, f.type, f.minScore, tick],
  );
  const rows = (list.data ?? []).filter((c) => {
    const day = (c as unknown as { created_at?: string }).created_at ?? "";
    return (!f.dateFrom || day >= f.dateFrom) && (!f.dateTo || day <= `${f.dateTo}T23:59:59`);
  });
  return (
    <div className="stack">
      <ErrorBox error={list.error} />
      {list.loading && !list.data && <Loading />}
      {list.data && rows.length === 0 && <Empty>Nenhum candidato com esses filtros.</Empty>}
      {rows.length > 0 && (
        <Card>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Candidato</th><th>Tipo</th><th>Pont.</th><th>Confiança</th><th>Estado</th><th>Resultado</th></tr></thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="clickable" onClick={() => navigate(`/candidates/${c.id}`)}>
                    <td>{c.title}<div className="muted small">{c.recording_name} · {fmtTime(c.start_s)}–{fmtTime(c.end_s)}</div></td>
                    <td>{c.type_label}</td>
                    <td>{c.score.toFixed(0)}</td>
                    <td>{c.confidence}</td>
                    <td><Badge tone={c.status === "approved" ? "ok" : c.status === "rejected" ? "danger" : "neutral"}>{c.status_label}</Badge></td>
                    <td>{c.outcome_label ?? "–"}</td>
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

function RecordingsTab({ f }: { f: Filters }) {
  const navigate = useNavigate();
  const { tick } = useJobs();
  const list = useAsync(
    () => api.get<Recording[]>(`/api/recordings${qs({ q: f.q, game: f.game, map: f.map, agent: f.agent, date_from: f.dateFrom, date_to: f.dateTo, limit: 300 })}`),
    [f.q, f.game, f.map, f.agent, f.dateFrom, f.dateTo, tick],
  );
  return (
    <div className="stack">
      <ErrorBox error={list.error} />
      {list.loading && !list.data && <Loading />}
      {list.data && list.data.length === 0 && <Empty>Nenhuma gravação com esses filtros.</Empty>}
      {list.data && list.data.length > 0 && (
        <Card>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Gravação</th><th>Jogo</th><th>Mapa / agente</th><th>Duração</th><th>Estado</th><th>Cortes</th><th>Importada</th></tr></thead>
              <tbody>
                {list.data.map((r) => (
                  <tr key={r.id} className="clickable" onClick={() => navigate(`/recordings/${r.id}`)}>
                    <td>{r.name}{!r.file_exists && <div><Badge tone="danger">arquivo não encontrado</Badge></div>}</td>
                    <td>{r.game}</td>
                    <td>{[r.map, r.agent].filter(Boolean).join(" / ") || "–"}</td>
                    <td>{fmtTime(r.duration_s)}</td>
                    <td>{r.status}</td>
                    <td>{r.clips_count ?? 0}</td>
                    <td>{fmtDate(r.imported_at)}</td>
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

function PubsTab({ f }: { f: Filters }) {
  const list = useAsync(
    () => api.get<Publication[]>(`/api/publications${qs({ platform: f.platform, date_from: f.dateFrom, date_to: f.dateTo, limit: 500 })}`),
    [f.platform, f.dateFrom, f.dateTo],
  );
  const rows = (list.data ?? []).filter((p) => !f.q || `${p.theme ?? ""} ${p.format ?? ""} ${p.hook ?? ""} ${p.url ?? ""}`.toLowerCase().includes(f.q.toLowerCase()));
  return (
    <div className="stack">
      <ErrorBox error={list.error} />
      {list.loading && !list.data && <Loading />}
      {list.data && rows.length === 0 && <Empty>Nenhuma publicação. Cadastre em <Link to="/metrics">Métricas</Link>.</Empty>}
      {rows.length > 0 && (
        <Card>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Plataforma</th><th>Tema / formato</th><th>Estado</th><th>Quando</th><th>Visualizações</th></tr></thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <td>{p.url ? <a href={p.url} target="_blank" rel="noreferrer noopener">{p.platform}</a> : p.platform}</td>
                    <td>{[p.theme, p.format].filter(Boolean).join(" · ") || "–"}</td>
                    <td>{p.status_label}</td>
                    <td>{fmtDate(p.published_at ?? p.planned_for)}</td>
                    <td>{p.views ?? "–"}</td>
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

function CleanupTab() {
  const { run, busy } = useAction();
  const preview = useAsync(() => api.get<CleanupPreview>("/api/cleanup/preview"), []);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [partials, setPartials] = useState(false);

  if (preview.loading && !preview.data) return <Loading />;
  if (!preview.data) return <ErrorBox error={preview.error} />;
  const items = preview.data.artifacts;
  const deletable = items.filter((a) => a.deletable);
  const totalBytes = deletable.filter((a) => selected.has(a.id)).reduce((sum, a) => sum + (a.size_bytes ?? 0), 0);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function remove() {
    const message =
      `Apagar ${selected.size} arquivo(s) do disco (${fmtBytes(totalBytes)})` +
      `${partials ? ` e ${preview.data?.partials.length ?? 0} arquivo(s) parcial(is)` : ""}?\n\n` +
      "Esta ação não pode ser desfeita. Gravações originais nunca são apagadas por aqui.";
    if (!window.confirm(message)) return;
    const result = await run(() => api.post<{ deleted: string[]; failed: Array<{ path: string; reason: string }> }>("/api/cleanup", {
      artifact_ids: Array.from(selected), delete_partials: partials, confirm: true,
    }));
    if (result) {
      window.alert(`${result.deleted.length} arquivo(s) apagado(s).` + (result.failed.length ? `\n${result.failed.length} falharam:\n${result.failed.map((x) => `${x.path}: ${x.reason}`).join("\n")}` : ""));
      setSelected(new Set());
      preview.reload();
    }
  }

  return (
    <div className="stack">
      <Notice tone="info">
        Aqui aparecem só os arquivos que o próprio aplicativo criou (cortes exportados, prévias). Nada é apagado sem a sua
        confirmação, e as gravações originais nunca entram nesta lista como removíveis.
      </Notice>
      {items.length === 0 && preview.data.partials.length === 0 && <Empty>Nenhum arquivo gerado pelo aplicativo.</Empty>}
      {items.length > 0 && (
        <Card
          title="Arquivos gerados"
          actions={<Button variant="ghost" onClick={() => setSelected(new Set(deletable.map((a) => a.id)))}>Selecionar todos os removíveis</Button>}
        >
          <div className="table-wrap">
            <table>
              <thead><tr><th /><th>Tipo</th><th>Arquivo</th><th>Tamanho</th><th>Situação</th></tr></thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id}>
                    <td><input type="checkbox" disabled={!a.deletable} checked={selected.has(a.id)} onChange={() => toggle(a.id)} aria-label={`Selecionar ${a.path}`} /></td>
                    <td>{a.kind === "export" ? "exportação" : a.kind === "preview" ? "prévia" : a.kind}</td>
                    <td><code>{a.path}</code></td>
                    <td>{fmtBytes(a.size_bytes)}</td>
                    <td>{a.deletable ? <Badge tone="ok">removível</Badge> : <Badge tone="neutral">{a.reason}</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {preview.data.partials.length > 0 && (
        <Card title="Arquivos parciais (renderizações interrompidas)">
          <Checkbox checked={partials} onChange={setPartials} label={`Incluir ${preview.data.partials.length} arquivo(s) .part na limpeza`} />
          <ul className="small">{preview.data.partials.map((p) => <li key={p.path}><code>{p.path}</code> ({fmtBytes(p.size_bytes)})</li>)}</ul>
        </Card>
      )}
      <div className="row">
        <Button variant="danger" onClick={remove} busy={busy} disabled={selected.size === 0 && !partials}>Apagar selecionados…</Button>
        <span className="muted small">Selecionado: {fmtBytes(totalBytes)}</span>
      </div>
    </div>
  );
}
