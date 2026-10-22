import { useState } from "react";

import { api, qs } from "../api/client";
import type { Job, ManualItem, RadarRun, RadarStatus, Trend } from "../api/types";
import { DataTree } from "../components/DataTree";
import { JobStatus } from "../components/JobStatus";
import { useJobs } from "../components/JobsContext";
import { Badge, Button, Card, Checkbox, Empty, ErrorBox, Field, Loading, Notice, NumberInput, PageHeader, Select, Tabs, TextArea, TextInput } from "../components/ui";
import { confidenceTone, fmtDate, fmtNumber } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";
import { RUN_STATUS, labelOf } from "../lib/labels";

const KIND_LABEL: Record<string, string> = {
  tema: "tema", hashtag: "hashtags", duracao: "duração", gancho_titulo: "padrões de título", agente: "agentes",
  mapa: "mapas", frequencia: "frequência", mudanca: "mudança entre coletas",
};
const SOURCE_LABEL: Record<string, string> = { youtube: "YouTube", twitch_clips: "Clipes da Twitch", manual: "Observações manuais" };

export function Trends() {
  const { tick } = useJobs();
  const [tab, setTab] = useState("trends");
  const [runFilter, setRunFilter] = useState<number | null>(null);
  const status = useAsync(() => api.get<RadarStatus>("/api/radar/status"), [tick]);

  return (
    <div className="stack">
      <PageHeader
        title="Radar de tendências"
        subtitle="O que está funcionando no conteúdo de Valorant, a partir de fontes legítimas. Cada item traz fonte, data da consulta, dados observados, estimativas e hipóteses — separados — e suas limitações."
      />
      <Notice tone="info">
        Nada aqui é promessa de viralização. A confiança vai de “muito baixa” a “média” (nunca “alta”) porque cada amostra é parcial.
        {status.data && status.data.limitations.map((l) => <div key={l} className="small">• {l}</div>)}
      </Notice>
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "trends", label: "Tendências" },
          { key: "collect", label: "Coletar dados" },
          { key: "manual", label: "Observações manuais" },
          { key: "history", label: "Histórico de coletas" },
        ]}
      />
      {tab === "trends" && <TrendList runFilter={runFilter} clearRun={() => setRunFilter(null)} />}
      {tab === "collect" && <Collect status={status.data} onDone={status.reload} />}
      {tab === "manual" && <Manual onAnalyzed={status.reload} />}
      {tab === "history" && <History onOpen={(id) => { setRunFilter(id); setTab("trends"); }} />}
    </div>
  );
}

function TrendList({ runFilter, clearRun }: { runFilter: number | null; clearRun: () => void }) {
  const { tick } = useJobs();
  const [source, setSource] = useState("");
  const [kind, setKind] = useState("");
  const [confidence, setConfidence] = useState("");
  const [latest, setLatest] = useState(true);
  const trends = useAsync(
    () => api.get<Trend[]>(`/api/radar/trends${qs({ run_id: runFilter, source, kind, confidence, latest: runFilter ? false : latest })}`),
    [runFilter, source, kind, confidence, latest, tick],
  );
  return (
    <div className="stack">
      <div className="row wrap">
        <Select
          value={source}
          onChange={setSource}
          options={[{ value: "", label: "Todas as fontes" }, ...Object.entries(SOURCE_LABEL).map(([value, label]) => ({ value, label }))]}
          style={{ maxWidth: 220 }}
        />
        <Select
          value={kind}
          onChange={setKind}
          options={[{ value: "", label: "Todos os tipos" }, ...Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label }))]}
          style={{ maxWidth: 220 }}
        />
        <Select
          value={confidence}
          onChange={setConfidence}
          options={[{ value: "", label: "Qualquer confiança" }, { value: "média", label: "média" }, { value: "baixa", label: "baixa" }, { value: "muito baixa", label: "muito baixa" }]}
          style={{ maxWidth: 200 }}
        />
        {runFilter ? (
          <Button variant="ghost" onClick={clearRun}>Mostrando a coleta #{runFilter} — voltar às mais recentes</Button>
        ) : (
          <Checkbox checked={latest} onChange={setLatest} label="Só a coleta mais recente de cada fonte" />
        )}
      </div>
      <ErrorBox error={trends.error} />
      {trends.loading && !trends.data && <Loading />}
      {trends.data && trends.data.length === 0 && (
        <Empty>
          Nenhuma tendência ainda. Vá em “Coletar dados” (YouTube / Twitch) ou cadastre observações manuais (ex.: o que você viu no TikTok
          Creative Center).
        </Empty>
      )}
      {(trends.data ?? []).map((trend) => <TrendCard key={trend.id} trend={trend} />)}
    </div>
  );
}

function TrendCard({ trend }: { trend: Trend }) {
  const { run, busy } = useAction();
  const hasEstimates = Object.keys(trend.observed.estimated ?? {}).length > 0;

  async function saveIdea() {
    const title = `${trend.label}: ${trend.suggestion ?? "testar um vídeo"}`.slice(0, 160);
    await run(
      () => api.post("/api/ideas", {
        title,
        rationale: [{
          kind: "radar", evidence: "hipotese",
          text: `Radar ${SOURCE_LABEL[trend.source] ?? trend.source} de ${fmtDate(trend.collected_at)} (confiança ${trend.confidence}, n=${trend.sample_size}). ${trend.relevance ?? ""}`.trim(),
        }],
        source: "sugestao",
      }),
      "Salvo em Ideias e roteiros.",
    );
  }

  return (
    <Card
      title={trend.label}
      actions={<>
        <Badge>{KIND_LABEL[trend.kind] ?? trend.kind}</Badge>
        <Badge tone={confidenceTone(trend.confidence)} title="Depende do tamanho da amostra e do tipo de fonte; nunca passa de “média”.">
          confiança {trend.confidence}
        </Badge>
      </>}
    >
      <div className="stack">
        <div className="muted small">
          Fonte: {trend.source_url ? <a href={trend.source_url} target="_blank" rel="noreferrer noopener">{SOURCE_LABEL[trend.source] ?? trend.source}</a> : (SOURCE_LABEL[trend.source] ?? trend.source)}
          {" · "}consultado em {fmtDate(trend.collected_at)} · amostra: {fmtNumber(trend.sample_size)} itens
        </div>
        <div>
          <Badge tone="ok">dados observados</Badge>
          <div style={{ marginTop: 6 }}><DataTree value={trend.observed.observed} /></div>
        </div>
        {hasEstimates && (
          <div>
            <Badge tone="info">estimativas (calculadas a partir dos dados)</Badge>
            <div style={{ marginTop: 6 }}><DataTree value={trend.observed.estimated} /></div>
          </div>
        )}
        <div>
          <Badge tone="warn">hipóteses — não são fatos</Badge>
          <ul className="small">
            {trend.observed.hypotheses.map((h) => <li key={h}>{h}</li>)}
            {trend.relevance && <li><strong>Por que pode ser relevante para o seu canal:</strong> {trend.relevance}</li>}
            {trend.suggestion && <li><strong>Sugestão de vídeo:</strong> {trend.suggestion}</li>}
          </ul>
        </div>
        {trend.limitations && <div className="muted small"><strong>Limitações dos dados:</strong> {trend.limitations}</div>}
        <div><Button onClick={saveIdea} busy={busy}>Salvar como ideia</Button></div>
      </div>
    </Card>
  );
}

function Collect({ status, onDone }: { status: RadarStatus | null; onDone: () => void }) {
  const { run, busy } = useAction();
  const { summary, refresh } = useJobs();
  const [queries, setQueries] = useState("valorant\nvalorant clutch\nvalorant ranked\nvalorant brasil");
  const [region, setRegion] = useState("BR");
  const [language, setLanguage] = useState("pt");
  const [days, setDays] = useState<number | null>(14);
  const [order, setOrder] = useState("viewCount");
  const [pages, setPages] = useState<number | null>(1);
  const [tDays, setTDays] = useState<number | null>(7);
  const [tPages, setTPages] = useState<number | null>(2);
  const [tLang, setTLang] = useState("pt");
  const list = queries.split("\n").map((q) => q.trim()).filter(Boolean);
  const cost = list.length * (pages ?? 1);
  const active = (summary?.active ?? []).filter((j) => j.kind.startsWith("radar_"));
  const remaining = status?.youtube.quota.search_calls_remaining ?? 0;
  const overQuota = status?.youtube.configured === true && cost > remaining;
  const recent = useAsync(() => api.get<Job[]>("/api/jobs?limit=10"), [summary?.active.length ?? 0]);
  const lastRadarJob = (recent.data ?? []).find((j) => j.kind.startsWith("radar_"));

  async function startYoutube() {
    const job = await run(
      () => api.post<Job>("/api/radar/runs/youtube", { queries: list, region, language: language || null, days: days ?? 14, order, pages: pages ?? 1 }),
      "Coleta do YouTube na fila.",
    );
    if (job) { void refresh(); onDone(); }
  }
  async function startTwitch() {
    const job = await run(
      () => api.post<Job>("/api/radar/runs/twitch-clips", { days: tDays ?? 7, pages: tPages ?? 2, language: tLang || null }),
      "Coleta de clipes da Twitch na fila.",
    );
    if (job) { void refresh(); onDone(); }
  }

  return (
    <div className="stack">
      {active.length > 0 && <div className="jobs-panel">{active.map((j) => <JobStatus key={j.id} job={j} />)}</div>}
      {active.length === 0 && lastRadarJob && lastRadarJob.state === "failed" && (
        <Notice tone="warn">A última coleta falhou ({lastRadarJob.label}): {lastRadarJob.error ?? "sem detalhes"}</Notice>
      )}
      <div className="grid grid-2">
        <Card title="YouTube (API oficial)">
          <div className="stack">
            {status && !status.youtube.configured && (
              <Notice tone="warn">
                Falta a chave: coloque <code>YOUTUBE_API_KEY</code> no arquivo <code>.env</code> (veja docs/USAGE.md) e reinicie o aplicativo.
              </Notice>
            )}
            {status?.youtube.configured && (
              <Notice tone="info">
                Cota de buscas hoje: {status.youtube.quota.search_calls_used}/{status.youtube.quota.search_calls_limit} usadas. Esta coleta usaria{" "}
                <strong>{cost}</strong> busca(s).
              </Notice>
            )}
            <Field label="Consultas (uma por linha)"><TextArea rows={4} value={queries} onChange={(e) => setQueries(e.target.value)} /></Field>
            <div className="form-grid">
              <Field label="Região"><TextInput value={region} maxLength={2} onChange={(e) => setRegion(e.target.value.toUpperCase())} /></Field>
              <Field label="Idioma"><TextInput value={language} maxLength={3} onChange={(e) => setLanguage(e.target.value.toLowerCase())} /></Field>
              <Field label="Últimos (dias)"><NumberInput value={days} min={1} max={90} onChange={setDays} /></Field>
              <Field label="Páginas por consulta"><NumberInput value={pages} min={1} max={3} onChange={setPages} /></Field>
            </div>
            <Field label="Ordenar por">
              <Select
                value={order}
                onChange={setOrder}
                options={[{ value: "viewCount", label: "Mais vistos" }, { value: "date", label: "Mais recentes" }, { value: "relevance", label: "Relevância" }]}
              />
            </Field>
            <p className="muted small">
              Vídeos curtos (&lt; 4 min) retornados pela busca pública. A API não separa Shorts com segurança e o gancho falado não é acessível.
            </p>
            {overQuota && (
              <Notice tone="warn">
                Esta coleta usaria {cost} busca(s), mas restam {remaining} hoje. Reduza as consultas/páginas ou espere a cota renovar
                (meia-noite, horário do Pacífico).
              </Notice>
            )}
            <div>
              <Button variant="primary" onClick={startYoutube} busy={busy} disabled={!status?.youtube.configured || list.length === 0 || overQuota}>
                Coletar do YouTube
              </Button>
            </div>
          </div>
        </Card>

        <Card title="Clipes da Twitch (API oficial)">
          <div className="stack">
            {status && !status.twitch.configured && (
              <Notice tone="warn">
                Faltam <code>TWITCH_CLIENT_ID</code> e <code>TWITCH_CLIENT_SECRET</code> no arquivo <code>.env</code> (veja docs/USAGE.md).
              </Notice>
            )}
            <div className="form-grid">
              <Field label="Últimos (dias)"><NumberInput value={tDays} min={1} max={30} onChange={setTDays} /></Field>
              <Field label="Páginas (100 clipes cada)"><NumberInput value={tPages} min={1} max={5} onChange={setTPages} /></Field>
              <Field label="Idioma do clipe"><TextInput value={tLang} maxLength={3} onChange={(e) => setTLang(e.target.value.toLowerCase())} /></Field>
            </div>
            <p className="muted small">
              Clipes públicos mais vistos da categoria VALORANT no período. São momentos curtos escolhidos por quem assiste, um bom
              retrato de “o que gera reação” — mas não de vídeos de TikTok.
            </p>
            <div><Button variant="primary" onClick={startTwitch} busy={busy} disabled={!status?.twitch.configured}>Coletar clipes da Twitch</Button></div>
          </div>
        </Card>
      </div>
      <Card title="TikTok">
        <p className="small">
          O TikTok não oferece, para criadores, uma API pública de tendências que este aplicativo possa usar, e os termos da plataforma proíbem
          coleta automatizada. Pesquise manualmente (por exemplo, no Creative Center do TikTok) e registre o que observar na aba
          “Observações manuais”: o app guarda a data e a origem de cada número.
        </p>
      </Card>
    </div>
  );
}

function Manual({ onAnalyzed }: { onAnalyzed: () => void }) {
  const { run, busy } = useAction();
  const items = useAsync(() => api.get<ManualItem[]>("/api/radar/items?manual=true&limit=500"), []);
  const [f, setF] = useState({
    platform: "tiktok", url: "", title: "", channel: "", published_at: "", hashtags: "", format: "", hook: "", edit_style: "",
    caption_style: "", notes: "",
  });
  const [nums, setNums] = useState<{ views: number | null; likes: number | null; comments: number | null; duration_s: number | null }>({
    views: null, likes: null, comments: null, duration_s: null,
  });
  const set = (p: Partial<typeof f>) => setF((prev) => ({ ...prev, ...p }));

  async function add() {
    const created = await run(
      () => api.post("/api/radar/manual", {
        platform: f.platform, url: f.url || null, title: f.title, channel: f.channel || null,
        published_at: f.published_at ? new Date(f.published_at).toISOString() : null,
        hashtags: f.hashtags.split(/[\s,]+/).filter(Boolean), format: f.format || null, hook: f.hook || null,
        edit_style: f.edit_style || null, caption_style: f.caption_style || null, notes: f.notes || null, ...nums,
      }),
      "Observação registrada.",
    );
    if (created) {
      setF({ ...f, url: "", title: "", channel: "", hashtags: "", hook: "", notes: "" });
      setNums({ views: null, likes: null, comments: null, duration_s: null });
      items.reload();
    }
  }
  async function analyze() {
    const result = await run(() => api.post<{ trends: number }>("/api/radar/manual/analyze"), "Análise criada. Veja em “Tendências”.");
    if (result) onAnalyzed();
  }
  async function remove(id: number) {
    await run(() => api.del(`/api/radar/manual/${id}`));
    items.reload();
  }

  return (
    <div className="stack">
      <Card title="Registrar o que você observou">
        <div className="stack">
          <Notice tone="info">Registre só o que você realmente viu (links, números e a data em que viu). O app não confere esses números.</Notice>
          <div className="form-grid">
            <Field label="Plataforma">
              <Select value={f.platform} onChange={(v) => set({ platform: v })} options={["tiktok", "instagram", "youtube", "twitch", "kwai", "outro"].map((p) => ({ value: p, label: p }))} />
            </Field>
            <Field label="Link"><TextInput value={f.url} onChange={(e) => set({ url: e.target.value })} /></Field>
            <Field label="Canal"><TextInput value={f.channel} onChange={(e) => set({ channel: e.target.value })} /></Field>
            <Field label="Publicado em"><input className="input" type="date" value={f.published_at} onChange={(e) => set({ published_at: e.target.value })} /></Field>
          </div>
          <Field label="Título / descrição do vídeo"><TextInput value={f.title} onChange={(e) => set({ title: e.target.value })} /></Field>
          <div className="form-grid">
            <Field label="Visualizações"><NumberInput value={nums.views} min={0} onChange={(v) => setNums({ ...nums, views: v })} /></Field>
            <Field label="Curtidas"><NumberInput value={nums.likes} min={0} onChange={(v) => setNums({ ...nums, likes: v })} /></Field>
            <Field label="Comentários"><NumberInput value={nums.comments} min={0} onChange={(v) => setNums({ ...nums, comments: v })} /></Field>
            <Field label="Duração (s)"><NumberInput value={nums.duration_s} min={0} onChange={(v) => setNums({ ...nums, duration_s: v })} /></Field>
          </div>
          <div className="form-grid">
            <Field label="Hashtags"><TextInput value={f.hashtags} onChange={(e) => set({ hashtags: e.target.value })} placeholder="#valorant #clutch" /></Field>
            <Field label="Formato"><TextInput value={f.format} onChange={(e) => set({ format: e.target.value })} placeholder="clutch, reação, série…" /></Field>
            <Field label="Gancho (primeiros segundos)"><TextInput value={f.hook} onChange={(e) => set({ hook: e.target.value })} /></Field>
            <Field label="Estilo de edição / legenda"><TextInput value={f.edit_style} onChange={(e) => set({ edit_style: e.target.value })} /></Field>
          </div>
          <Field label="Observações"><TextArea rows={2} value={f.notes} onChange={(e) => set({ notes: e.target.value })} /></Field>
          <div><Button variant="primary" onClick={add} busy={busy} disabled={!f.title.trim()}>Registrar</Button></div>
        </div>
      </Card>

      <Card title={`Observações registradas (${items.data?.length ?? 0})`} actions={<Button onClick={analyze} busy={busy}>Analisar observações</Button>}>
        {items.data && items.data.length === 0 && <Empty>Nada registrado. A análise precisa de pelo menos 3 observações.</Empty>}
        {items.data && items.data.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Quando observou</th><th>Plataforma</th><th>Título</th><th>Views</th><th /></tr></thead>
              <tbody>
                {items.data.map((it) => (
                  <tr key={it.id}>
                    <td className="nowrap">{fmtDate(it.observed_at)}</td>
                    <td>{it.url ? <a href={it.url} target="_blank" rel="noreferrer noopener">{it.platform}</a> : it.platform}</td>
                    <td>{it.title}</td>
                    <td>{it.views ?? "–"}</td>
                    <td><Button variant="ghost" onClick={() => remove(it.id)}>✕</Button></td>
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

function History({ onOpen }: { onOpen: (id: number) => void }) {
  const { run } = useAction();
  const runs = useAsync(() => api.get<RadarRun[]>("/api/radar/runs?limit=100"), []);
  async function remove(id: number) {
    if (!window.confirm("Excluir esta coleta e as tendências geradas por ela?")) return;
    await run(() => api.del(`/api/radar/runs/${id}`));
    runs.reload();
  }
  return (
    <div className="stack">
      <p className="muted small">Cada coleta fica guardada com data e origem, para você comparar semanas diferentes.</p>
      <ErrorBox error={runs.error} />
      {runs.loading && !runs.data && <Loading />}
      {runs.data && runs.data.length === 0 && <Empty>Nenhuma coleta ainda.</Empty>}
      {runs.data && runs.data.length > 0 && (
        <Card>
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Fonte</th><th>Coletada em</th><th>Estado</th><th>Itens</th><th>Tendências</th><th /></tr></thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id}</td>
                    <td>{SOURCE_LABEL[r.source] ?? r.source}</td>
                    <td>{fmtDate(r.collected_at)}</td>
                    <td>{labelOf(RUN_STATUS, r.status)}{r.error ? ` — ${r.error}` : ""}</td>
                    <td>{r.sample_size}</td>
                    <td>{r.trends_count ?? 0}</td>
                    <td className="nowrap">
                      <Button variant="ghost" onClick={() => onOpen(r.id)}>Ver</Button>
                      <Button variant="ghost" onClick={() => remove(r.id)}>Excluir</Button>
                    </td>
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
