import { useState } from "react";

import { api } from "../api/client";
import type { Clip, Publication, Report } from "../api/types";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, Notice, NumberInput, PageHeader, Select, TextArea, TextInput } from "../components/ui";
import { fmtDate, fmtNumber, fmtPercent } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

const PLATFORMS = ["tiktok", "instagram", "youtube", "twitch", "kwai", "outro"].map((p) => ({ value: p, label: p }));
const GROUPS = [
  { value: "format", label: "Formato" },
  { value: "theme", label: "Tema" },
  { value: "hook", label: "Gancho" },
  { value: "duration", label: "Duração" },
  { value: "platform", label: "Plataforma" },
];

interface Form {
  platform: string;
  url: string;
  status: "planned" | "published";
  when: string;
  format: string;
  theme: string;
  hook: string;
  duration_s: number | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  avg_watch_s: number | null;
  retention_pct: number | null;
  notes: string;
  clip_id: string;
}

const EMPTY: Form = {
  platform: "tiktok", url: "", status: "published", when: "", format: "", theme: "", hook: "", duration_s: null, views: null,
  likes: null, comments: null, shares: null, avg_watch_s: null, retention_pct: null, notes: "", clip_id: "",
};

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function Metrics() {
  const { run, busy } = useAction();
  const pubs = useAsync(() => api.get<Publication[]>("/api/publications?limit=500"), []);
  const clips = useAsync(() => api.get<Clip[]>("/api/clips?limit=300"), []);
  const [form, setForm] = useState<Form>(EMPTY);
  const [editing, setEditing] = useState<number | null>(null);
  const [groupBy, setGroupBy] = useState("format");
  const report = useAsync(() => api.get<Report>(`/api/reports/publications?group_by=${groupBy}`), [groupBy]);
  const set = (partial: Partial<Form>) => setForm((prev) => ({ ...prev, ...partial }));

  function edit(p: Publication) {
    setEditing(p.id);
    setForm({
      platform: p.platform, url: p.url ?? "", status: p.status, when: toLocalInput(p.published_at ?? p.planned_for),
      format: p.format ?? "", theme: p.theme ?? "", hook: p.hook ?? "", duration_s: p.duration_s, views: p.views, likes: p.likes,
      comments: p.comments, shares: p.shares, avg_watch_s: p.avg_watch_s, retention_pct: p.retention_pct, notes: p.notes ?? "",
      clip_id: p.clip_id ? String(p.clip_id) : "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function payload() {
    const when = form.when ? new Date(form.when).toISOString() : null;
    return {
      platform: form.platform, url: form.url || null, status: form.status,
      planned_for: form.status === "planned" ? when : null,
      published_at: form.status === "published" ? when : null,
      format: form.format || null, theme: form.theme || null, hook: form.hook || null,
      duration_s: form.duration_s, views: form.views, likes: form.likes, comments: form.comments, shares: form.shares,
      avg_watch_s: form.avg_watch_s, retention_pct: form.retention_pct, notes: form.notes || null,
      clip_id: form.clip_id ? Number(form.clip_id) : null,
    };
  }

  async function submit() {
    const result = await run(
      () => (editing ? api.patch(`/api/publications/${editing}`, payload()) : api.post("/api/publications", payload())),
      editing ? "Publicação atualizada." : "Publicação cadastrada.",
    );
    if (result) {
      setForm(EMPTY);
      setEditing(null);
      pubs.reload();
      report.reload();
    }
  }

  async function remove(id: number) {
    if (!window.confirm("Excluir esta publicação do histórico?")) return;
    await run(() => api.del(`/api/publications/${id}`), "Publicação excluída.");
    pubs.reload();
    report.reload();
  }

  return (
    <div className="stack">
      <PageHeader
        title="Métricas das publicações"
        subtitle="Cadastre manualmente os números de cada vídeo publicado. Não há coleta automática de métricas do TikTok/Instagram: a entrada manual é o caminho principal."
      />

      <Card title={editing ? `Editando publicação #${editing}` : "Nova publicação"} actions={editing ? <Button variant="ghost" onClick={() => { setEditing(null); setForm(EMPTY); }}>Cancelar edição</Button> : null}>
        <div className="stack">
          <div className="form-grid">
            <Field label="Plataforma"><Select value={form.platform} onChange={(v) => set({ platform: v })} options={PLATFORMS} /></Field>
            <Field label="Estado">
              <Select value={form.status} onChange={(v) => set({ status: v as Form["status"] })} options={[{ value: "published", label: "Publicada" }, { value: "planned", label: "Planejada" }]} />
            </Field>
            <Field label={form.status === "planned" ? "Planejada para" : "Data e horário da publicação"}>
              <input className="input" type="datetime-local" value={form.when} onChange={(e) => set({ when: e.target.value })} />
            </Field>
            <Field label="Corte de origem (opcional)">
              <Select value={form.clip_id} onChange={(v) => set({ clip_id: v })} options={[{ value: "", label: "(nenhum)" }, ...(clips.data ?? []).map((c) => ({ value: String(c.id), label: c.title }))]} />
            </Field>
          </div>
          <Field label="Link da publicação"><TextInput value={form.url} onChange={(e) => set({ url: e.target.value })} placeholder="https://www.tiktok.com/@canal/video/…" /></Field>
          <div className="form-grid">
            <Field label="Formato" hint="Ex.: clutch, erro engraçado, série de rank"><TextInput value={form.format} onChange={(e) => set({ format: e.target.value })} /></Field>
            <Field label="Tema"><TextInput value={form.theme} onChange={(e) => set({ theme: e.target.value })} /></Field>
            <Field label="Duração (s)"><NumberInput value={form.duration_s} min={0} onChange={(v) => set({ duration_s: v })} /></Field>
          </div>
          <Field label="Gancho utilizado (texto dos primeiros segundos)"><TextInput value={form.hook} onChange={(e) => set({ hook: e.target.value })} /></Field>
          <div className="form-grid">
            <Field label="Visualizações"><NumberInput value={form.views} min={0} onChange={(v) => set({ views: v })} /></Field>
            <Field label="Curtidas"><NumberInput value={form.likes} min={0} onChange={(v) => set({ likes: v })} /></Field>
            <Field label="Comentários"><NumberInput value={form.comments} min={0} onChange={(v) => set({ comments: v })} /></Field>
            <Field label="Compartilhamentos"><NumberInput value={form.shares} min={0} onChange={(v) => set({ shares: v })} /></Field>
            <Field label="Tempo médio assistido (s)"><NumberInput value={form.avg_watch_s} min={0} step={0.1} onChange={(v) => set({ avg_watch_s: v })} /></Field>
            <Field label="Retenção (%)"><NumberInput value={form.retention_pct} min={0} max={100} step={0.1} onChange={(v) => set({ retention_pct: v })} /></Field>
          </div>
          <Field label="Observações"><TextArea rows={2} value={form.notes} onChange={(e) => set({ notes: e.target.value })} /></Field>
          <div><Button variant="primary" onClick={submit} busy={busy}>{editing ? "Atualizar" : "Cadastrar"}</Button></div>
        </div>
      </Card>

      <Card title="Comparação entre formatos, temas, ganchos e durações">
        <div className="row wrap" style={{ marginBottom: 8 }}>
          <span className="muted small">Agrupar por:</span>
          <Select value={groupBy} onChange={setGroupBy} options={GROUPS} style={{ maxWidth: 200 }} />
        </div>
        <ErrorBox error={report.error} />
        {report.loading && !report.data && <Loading />}
        {report.data && (
          <div className="stack">
            <Notice tone="info">{report.data.reading_note}</Notice>
            <div className="muted small">
              {report.data.overall.published} publicadas, {report.data.overall.with_views} com visualizações. Mediana geral: {fmtNumber(report.data.overall.median_views)} visualizações · engajamento mediano {fmtPercent(report.data.overall.median_engagement_rate)}.
              Amostra mínima para qualquer leitura: {report.data.min_sample} vídeos por grupo.
            </div>
            {report.data.groups.length === 0 ? <Empty>Cadastre publicações com visualizações para comparar.</Empty> : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Grupo</th><th>n</th><th>Mediana de visualizações</th><th>vs. mediana geral</th><th>Engajamento mediano</th><th>Tempo assistido</th><th>Ressalvas</th></tr></thead>
                  <tbody>
                    {report.data.groups.map((g) => (
                      <tr key={g.group}>
                        <td>{g.group}</td>
                        <td>{g.n}</td>
                        <td>{fmtNumber(g.median_views)}</td>
                        <td>{g.vs_overall_median !== null ? `${g.vs_overall_median.toFixed(2)}×` : "–"}</td>
                        <td>{fmtPercent(g.median_engagement_rate)}</td>
                        <td>{g.median_avg_watch_s !== null ? `${g.median_avg_watch_s.toFixed(1)} s` : "–"}</td>
                        <td className="small">{g.warnings.length === 0 ? "–" : g.warnings.map((w) => <div key={w}>⚠ {w}</div>)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title="Histórico">
        <ErrorBox error={pubs.error} />
        {pubs.loading && !pubs.data && <Loading />}
        {pubs.data && pubs.data.length === 0 && <Empty>Nenhuma publicação cadastrada.</Empty>}
        {pubs.data && pubs.data.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Quando</th><th>Plataforma</th><th>Formato / tema</th><th>Gancho</th><th>Views</th><th>Curt.</th><th>Coment.</th><th>Comp.</th><th /></tr></thead>
              <tbody>
                {pubs.data.map((p) => (
                  <tr key={p.id}>
                    <td className="nowrap">{fmtDate(p.published_at ?? p.planned_for)}{p.status === "planned" && <div><Badge tone="info">planejada</Badge></div>}</td>
                    <td>{p.url ? <a href={p.url} target="_blank" rel="noreferrer noopener">{p.platform}</a> : p.platform}</td>
                    <td>{[p.format, p.theme].filter(Boolean).join(" · ") || "–"}</td>
                    <td className="small">{p.hook ?? "–"}</td>
                    <td>{p.views ?? "–"}</td><td>{p.likes ?? "–"}</td><td>{p.comments ?? "–"}</td><td>{p.shares ?? "–"}</td>
                    <td className="nowrap"><Button variant="ghost" onClick={() => edit(p)}>Editar</Button><Button variant="ghost" onClick={() => remove(p.id)}>✕</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
