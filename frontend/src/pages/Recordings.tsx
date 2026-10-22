import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, qs } from "../api/client";
import type { AnalysisLevels, Candidate, Job, Recording, RecordingDetail, Signals } from "../api/types";
import { DataTree } from "../components/DataTree";
import { JobStatus } from "../components/JobStatus";
import { useJobs } from "../components/JobsContext";
import { Timeline } from "../components/Timeline";
import {
  Badge, Button, Card, Checkbox, Empty, ErrorBox, Field, Loading, Notice, PageHeader, Select, TextArea, TextInput,
} from "../components/ui";
import { fmtBytes, fmtDate, fmtTime } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";
import { LEVEL_LABEL, RECORDING_STATUS, RUN_STATUS, labelOf } from "../lib/labels";

const STATUS_TONE: Record<string, "neutral" | "ok" | "info" | "danger"> = {
  imported: "neutral",
  analyzing: "info",
  analyzed: "ok",
  error: "danger",
};
const STATUS_LABEL = RECORDING_STATUS;

export function Recordings() {
  const { id } = useParams();
  return id ? <RecordingView id={Number(id)} /> : <RecordingList />;
}

function RecordingList() {
  const navigate = useNavigate();
  const { tick } = useJobs();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const { data, error, loading } = useAsync(
    () => api.get<Recording[]>(`/api/recordings${qs({ q, status })}`),
    [q, status, tick],
  );

  return (
    <div className="stack">
      <PageHeader
        title="Gravações e análise"
        subtitle="Gravações importadas. Escolha uma para analisar e ver os cortes sugeridos."
        actions={<Link className="btn btn-primary" to="/import">Importar vídeo</Link>}
      />
      <div className="row wrap">
        <TextInput placeholder="Buscar por nome…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 280 }} />
        <Select
          value={status}
          onChange={setStatus}
          options={[
            { value: "", label: "Todos os estados" },
            { value: "imported", label: "Importadas" },
            { value: "analyzed", label: "Analisadas" },
            { value: "analyzing", label: "Analisando" },
          ]}
          style={{ maxWidth: 200 }}
        />
      </div>
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && data.length === 0 && <Empty>Nenhuma gravação encontrada.</Empty>}
      {data && data.length > 0 && (
        <Card>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nome</th><th>Duração</th><th>Resolução</th><th>Origem</th><th>Estado</th><th>Candidatos</th><th>Importada</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id} className="clickable" onClick={() => navigate(`/recordings/${r.id}`)}>
                    <td>
                      {r.name}
                      {!r.file_exists && <div><Badge tone="danger">arquivo não encontrado</Badge></div>}
                    </td>
                    <td>{fmtTime(r.duration_s)}</td>
                    <td>{r.width}×{r.height}{r.fps ? ` @${Math.round(r.fps)}` : ""}</td>
                    <td>{r.source === "twitch" ? "VOD Twitch" : "arquivo local"}</td>
                    <td><Badge tone={STATUS_TONE[r.status] ?? "neutral"}>{STATUS_LABEL[r.status] ?? r.status}</Badge></td>
                    <td>{r.candidates_count ?? 0} ({r.approved_count ?? 0} aprov.)</td>
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

function RecordingView({ id }: { id: number }) {
  const navigate = useNavigate();
  const { tick } = useJobs();
  const { run } = useAction();
  const rec = useAsync(() => api.get<RecordingDetail>(`/api/recordings/${id}`), [id, tick]);
  const signals = useAsync(() => api.get<Signals>(`/api/recordings/${id}/signals`), [id, tick]);
  const candidates = useAsync(() => api.get<Candidate[]>(`/api/candidates${qs({ recording_id: id, sort: "time" })}`), [id, tick]);
  const jobs = useAsync(() => api.get<Job[]>(`/api/jobs${qs({ recording_id: id, limit: 6 })}`), [id, tick]);
  const { summary } = useJobs();
  const active = (summary?.active ?? []).filter((j) => j.recording_id === id);
  const shownJobs = active.length > 0 ? active : (jobs.data ?? []).slice(0, 2);

  if (rec.loading && !rec.data) return <Loading />;
  if (rec.error && !rec.data) return <ErrorBox error={rec.error} />;
  const r = rec.data;
  if (!r) return null;
  const counts = `${r.candidates_count ?? 0} candidato(s), ${r.clips_count ?? 0} corte(s)`;

  async function remove() {
    if (
      !window.confirm(
        `Remover esta gravação da biblioteca?\n\nSerão removidos do aplicativo: a análise, a transcrição, ${counts} (com suas edições, legendas e textos).\n` +
          "O arquivo de vídeo original NÃO será apagado do disco, nem os MP4 já exportados.",
      )
    )
      return;
    await run(() => api.del(`/api/recordings/${id}`), "Gravação removida da biblioteca.");
    navigate("/recordings");
  }

  return (
    <div className="stack">
      <PageHeader
        title={r.name}
        subtitle={<>
          {fmtTime(r.duration_s)} · {r.width}×{r.height}{r.fps ? ` @ ${r.fps} fps` : ""} · {r.video_codec}/{r.audio_codec ?? "sem áudio"} ·{" "}
          {fmtBytes(r.size_bytes)} · importada em {fmtDate(r.imported_at)}
        </>}
        actions={<Button variant="danger" onClick={remove}>Remover da biblioteca</Button>}
      />
      {!r.file_exists && (
        <Notice tone="warn">O arquivo não foi encontrado em <code>{r.path}</code>. Se você o moveu, importe-o de novo pelo novo local.</Notice>
      )}
      {r.last_error && <Notice tone="warn">Último erro: {r.last_error}</Notice>}
      <div className="muted small">
        Origem: {r.source === "twitch" ? `VOD da Twitch ${r.source_ref ?? ""}` : "arquivo local"} · caminho: <code>{r.path}</code>
      </div>

      {shownJobs.length > 0 && (
        <Card title="Tarefas desta gravação">
          <div className="jobs-panel">{shownJobs.map((j) => <JobStatus key={j.id} job={j} />)}</div>
        </Card>
      )}

      <AnalysisPanel recording={r} />

      <Card title="Linha do tempo do áudio e cortes sugeridos">
        {signals.data && signals.data.rms_db.length > 0 && r.duration_s ? (
          <Timeline
            rms={signals.data.rms_db}
            windowS={signals.data.window_s ?? 0.5}
            duration={r.duration_s}
            scenes={signals.data.scenes}
            markers={(candidates.data ?? []).map((c) => ({ id: c.id, start: c.start_s, end: c.end_s, score: c.score, status: c.status }))}
            onSelect={(cid) => navigate(`/candidates/${cid}`)}
          />
        ) : (
          <Empty>Sem análise ainda. Escolha um nível acima e comece.</Empty>
        )}
        <p className="muted small">
          A curva mostra o volume. Um pico é só um sinal para investigar — não prova que houve uma jogada importante. Clique em
          um trecho marcado para revisá-lo.
        </p>
      </Card>

      <div className="grid grid-2">
        <Card title={`Candidatos (${candidates.data?.length ?? 0})`} actions={<Link to={`/candidates${qs({})}`}>revisar todos</Link>}>
          {!candidates.data || candidates.data.length === 0 ? (
            <Empty>Nenhum candidato. Você também pode criar cortes manualmente na tela de candidatos.</Empty>
          ) : (
            <table>
              <tbody>
                {candidates.data.map((c) => (
                  <tr key={c.id}>
                    <td className="nowrap">{fmtTime(c.start_s)}–{fmtTime(c.end_s)}</td>
                    <td><Link to={`/candidates/${c.id}`}>{c.title}</Link></td>
                    <td><Badge>{c.score.toFixed(0)}</Badge></td>
                    <td><Badge tone={c.status === "approved" ? "ok" : c.status === "rejected" ? "danger" : "neutral"}>{c.status_label}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Dados da gravação">
          <MetaForm key={`${r.id}-${r.map}-${r.agent}`} recording={r} onSaved={rec.reload} />
          {r.latest_analysis && (
            <div style={{ marginTop: 12 }}>
              <strong className="small">
                Última análise (nível {labelOf(LEVEL_LABEL, r.latest_analysis.level)}, {labelOf(RUN_STATUS, r.latest_analysis.status)}):
              </strong>
              {r.latest_analysis.error && <div className="notice notice-danger small">{r.latest_analysis.error}</div>}
              <DataTree value={r.latest_analysis.stats} />
              <div className="muted small">Trechos transcritos guardados: {r.transcript_segments}</div>
            </div>
          )}
        </Card>
      </div>

      {r.file_exists && (
        <Card title="Reprodução">
          {r.browser_playable ? (
            <video className="player-full" src={`/api/recordings/${r.id}/stream`} controls preload="metadata" style={{ width: "100%", maxHeight: 360, background: "#000", borderRadius: 8 }} />
          ) : (
            <Notice tone="warn">O navegador provavelmente não reproduz este formato ({r.video_codec}). A análise e a renderização funcionam normalmente.</Notice>
          )}
        </Card>
      )}
    </div>
  );
}

function MetaForm({ recording, onSaved }: { recording: RecordingDetail; onSaved: () => void }) {
  const { run, busy } = useAction();
  const [map, setMap] = useState(recording.map ?? "");
  const [agent, setAgent] = useState(recording.agent ?? "");
  const [game, setGame] = useState(recording.game);
  const [notes, setNotes] = useState(recording.notes ?? "");

  async function save() {
    await run(
      () => api.patch(`/api/recordings/${recording.id}`, { map: map || null, agent: agent || null, game, notes: notes || null }),
      "Dados salvos.",
    );
    onSaved();
  }

  return (
    <div className="stack">
      <div className="form-grid">
        <Field label="Jogo"><TextInput value={game} onChange={(e) => setGame(e.target.value)} /></Field>
        <Field label="Mapa"><TextInput value={map} onChange={(e) => setMap(e.target.value)} /></Field>
        <Field label="Agente"><TextInput value={agent} onChange={(e) => setAgent(e.target.value)} /></Field>
      </div>
      <Field label="Observações"><TextArea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} /></Field>
      <div><Button onClick={save} busy={busy}>Salvar</Button></div>
    </div>
  );
}

function AnalysisPanel({ recording }: { recording: RecordingDetail }) {
  const { run, busy } = useAction();
  const { refresh } = useJobs();
  const levels = useAsync(() => api.get<AnalysisLevels>("/api/analysis/levels"), []);
  const [level, setLevel] = useState("padrao");
  const [allowDownload, setAllowDownload] = useState(false);

  if (levels.loading && !levels.data) return <Card title="Analisar"><Loading /></Card>;
  if (!levels.data) return <Card title="Analisar"><ErrorBox error={levels.error} /></Card>;
  const info = levels.data.levels[level];
  const needsTranscription = info.transcription !== "off";
  const blocked = needsTranscription && !levels.data.provider_ready;
  const model = info.model ? levels.data.models[info.model] : undefined;

  async function start() {
    const job = await run(
      () => api.post<Job>(`/api/recordings/${recording.id}/analyze`, { level, allow_model_download: allowDownload }),
      "Análise na fila.",
    );
    if (job) void refresh();
  }

  return (
    <Card title="Analisar esta gravação">
      <div className="stack">
        <Notice tone="info">
          A análise só começa quando você clicar em “Iniciar análise” e roda no seu computador, uma tarefa por vez. Você pode
          cancelá-la a qualquer momento.
        </Notice>
        <Field label="Nível de processamento">
          <Select
            value={level}
            onChange={setLevel}
            options={Object.entries(levels.data.levels).map(([key, item]) => ({ value: key, label: item.label }))}
          />
        </Field>
        <div className="small">
          <p>{info.description}</p>
          <ul>
            <li>Detecção de cenas: {info.scenes ? "sim" : "não"}</li>
            <li>
              Transcrição: {info.transcription === "off" ? "não" : info.transcription === "full" ? "gravação inteira" : "só dos trechos candidatos"}
              {info.model ? ` (modelo ${info.model}${model ? `, ${model.approx_download}` : ""})` : ""}
            </li>
          </ul>
          {info.warnings.map((w) => <div key={w} className="muted">⚠ {w}</div>)}
        </div>
        {blocked && <Notice tone="warn">{levels.data.provider_message} Escolha “Leve” para analisar só pelo áudio.</Notice>}
        {needsTranscription && !blocked && (
          <Checkbox
            checked={allowDownload}
            onChange={setAllowDownload}
            label={`Permitir baixar o modelo de transcrição${model ? ` (${model.approx_download})` : ""} caso ele ainda não esteja no computador`}
          />
        )}
        <div>
          <Button variant="primary" onClick={start} busy={busy} disabled={blocked || !recording.file_exists || recording.status === "analyzing"}>
            Iniciar análise
          </Button>
        </div>
        <p className="muted small">
          A transcrição usa a CPU (GPU AMD não acelera o faster-whisper no Windows). No nível “Padrão” só os trechos candidatos são
          transcritos para economizar tempo.
        </p>
      </div>
    </Card>
  );
}
