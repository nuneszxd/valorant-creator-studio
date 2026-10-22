import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, qs } from "../api/client";
import type { Candidate, CandidateDetail, Clip, Facets, Recording } from "../api/types";
import { useJobs } from "../components/JobsContext";
import { RangePlayer } from "../components/RangePlayer";
import { TimeInput } from "../components/TimeInput";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, NumberInput, PageHeader, Select, TextInput } from "../components/ui";
import { confidenceTone, fmtTime, scoreTone } from "../lib/format";
import { useAction, useAsync } from "../lib/hooks";

export function Candidates() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { tick } = useJobs();
  const facets = useAsync(() => api.get<Facets>("/api/library/facets"), []);
  const recordings = useAsync(() => api.get<Recording[]>("/api/recordings?limit=500"), []);
  const [recordingId, setRecordingId] = useState("");
  const [status, setStatus] = useState("pending");
  const [type, setType] = useState("");
  const [minScore, setMinScore] = useState<number | null>(null);
  const [sort, setSort] = useState("score");
  const [version, setVersion] = useState(0);
  const list = useAsync(
    () => api.get<Candidate[]>(`/api/candidates${qs({ recording_id: recordingId, status, type, min_score: minScore, sort })}`),
    [recordingId, status, type, minScore, sort, tick, version],
  );
  const selectedId = id ? Number(id) : null;
  const reload = () => setVersion((v) => v + 1);

  return (
    <div className="stack">
      <PageHeader
        title="Candidatos a cortes"
        subtitle="Revise as sugestões: assista, ajuste os tempos, aprove ou rejeite. Seu feedback ajusta as próximas pontuações."
      />
      <div className="row wrap">
        <Select
          value={recordingId}
          onChange={setRecordingId}
          options={[{ value: "", label: "Todas as gravações" }, ...(recordings.data ?? []).map((r) => ({ value: String(r.id), label: r.name }))]}
          style={{ maxWidth: 260 }}
        />
        <Select
          value={status}
          onChange={setStatus}
          options={[
            { value: "", label: "Todos os estados" },
            { value: "pending", label: "Pendentes" },
            { value: "approved", label: "Aprovados" },
            { value: "rejected", label: "Rejeitados" },
          ]}
          style={{ maxWidth: 170 }}
        />
        <Select
          value={type}
          onChange={setType}
          options={[{ value: "", label: "Todos os tipos" }, ...(facets.data?.moment_types ?? []).map((t) => ({ value: t.key, label: t.label }))]}
          style={{ maxWidth: 220 }}
        />
        <div style={{ width: 130 }}><NumberInput value={minScore} onChange={setMinScore} min={0} max={100} placeholder="Pontuação mín." /></div>
        <Select
          value={sort}
          onChange={setSort}
          options={[
            { value: "score", label: "Maior pontuação" },
            { value: "time", label: "Ordem no vídeo" },
            { value: "recent", label: "Mais recentes" },
          ]}
          style={{ maxWidth: 170 }}
        />
      </div>
      <ErrorBox error={list.error} />

      <div className="split">
        <div className="stack">
          <ManualCandidate recordings={recordings.data ?? []} onCreated={(c) => { reload(); navigate(`/candidates/${c.id}`); }} />
          {list.loading && !list.data && <Loading />}
          {list.data && list.data.length === 0 && <Empty>Nenhum candidato com esses filtros.</Empty>}
          {list.data && list.data.length > 0 && (
            <Card>
              <table>
                <tbody>
                  {list.data.map((c) => (
                    <tr key={c.id} className={`clickable ${selectedId === c.id ? "selected" : ""}`} onClick={() => navigate(`/candidates/${c.id}`)}>
                      <td>
                        <div>{c.title}</div>
                        <div className="muted small">
                          {c.recording_name} · {fmtTime(c.start_s)}–{fmtTime(c.end_s)} ({c.duration_s.toFixed(0)} s)
                        </div>
                        <div className="row wrap" style={{ marginTop: 4 }}>
                          <Badge>{c.type_label}</Badge>
                          <Badge tone={c.status === "approved" ? "ok" : c.status === "rejected" ? "danger" : "neutral"}>{c.status_label}</Badge>
                          {c.outcome_label && <Badge tone={c.outcome === "good" ? "ok" : "warn"}>resultado: {c.outcome_label}</Badge>}
                        </div>
                      </td>
                      <td className="nowrap">
                        <Badge tone={scoreTone(c.score)} title="Pontuação de prioridade para a sua revisão (não é previsão de desempenho)">
                          {c.score.toFixed(0)} pts
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>

        <div>
          {selectedId ? (
            <CandidateView key={selectedId} id={selectedId} onChanged={reload} />
          ) : (
            <Empty>Selecione um candidato à esquerda para assistir e revisar.</Empty>
          )}
        </div>
      </div>
    </div>
  );
}

function ManualCandidate({ recordings, onCreated }: { recordings: Recording[]; onCreated: (c: Candidate) => void }) {
  const { run, busy } = useAction();
  const [open, setOpen] = useState(false);
  const [recordingId, setRecordingId] = useState("");
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(30);

  if (!open) {
    return <div><Button variant="ghost" onClick={() => setOpen(true)}>+ Criar corte manual</Button></div>;
  }
  async function create() {
    const created = await run(
      () => api.post<Candidate>("/api/candidates", { recording_id: Number(recordingId), start_s: start, end_s: end }),
      "Corte manual criado.",
    );
    if (created) onCreated(created);
  }
  return (
    <Card title="Novo corte manual">
      <div className="stack">
        <Field label="Gravação">
          <Select
            value={recordingId}
            onChange={setRecordingId}
            options={[{ value: "", label: "Escolha…" }, ...recordings.map((r) => ({ value: String(r.id), label: r.name }))]}
          />
        </Field>
        <div className="form-grid">
          <Field label="Início (m:ss)"><TimeInput value={start} onChange={setStart} /></Field>
          <Field label="Fim (m:ss)"><TimeInput value={end} onChange={setEnd} /></Field>
        </div>
        <div className="row">
          <Button variant="primary" onClick={create} busy={busy} disabled={!recordingId}>Criar</Button>
          <Button variant="ghost" onClick={() => setOpen(false)}>Fechar</Button>
        </div>
      </div>
    </Card>
  );
}

function CandidateView({ id, onChanged }: { id: number; onChanged: () => void }) {
  const navigate = useNavigate();
  const { run, busy } = useAction();
  const detail = useAsync(() => api.get<CandidateDetail>(`/api/candidates/${id}`), [id]);
  const facets = useAsync(() => api.get<Facets>("/api/library/facets"), []);
  const [edit, setEdit] = useState<{ title: string; start: number; end: number; type: string } | null>(null);

  if (detail.loading && !detail.data) return <Loading />;
  if (!detail.data) return <ErrorBox error={detail.error} />;
  const c = detail.data;
  const form = edit ?? { title: c.title, start: c.start_s, end: c.end_s, type: c.moment_type };
  const dirty = edit !== null;
  const maxTime = c.recording.duration_s ?? undefined;

  async function patch(fields: Record<string, unknown>, message?: string) {
    const updated = await run(() => api.patch<CandidateDetail>(`/api/candidates/${id}`, fields), message);
    if (updated) {
      setEdit(null);
      detail.reload();
      onChanged();
    }
  }

  async function toClip() {
    if (c.clip_id) {
      navigate(`/editor/${c.clip_id}`);
      return;
    }
    const clip = await run(() => api.post<Clip>("/api/clips", { candidate_id: id }), "Corte criado e candidato aprovado.");
    if (clip) {
      onChanged();
      navigate(`/editor/${clip.id}`);
    }
  }

  async function remove() {
    if (!window.confirm("Excluir este candidato? (O vídeo original não é afetado.)")) return;
    await run(() => api.del(`/api/candidates/${id}`), "Candidato excluído.");
    onChanged();
    navigate("/candidates");
  }

  return (
    <div className="stack">
      <Card
        title={c.title}
        actions={<>
          <Badge tone={scoreTone(c.score)}>{c.score.toFixed(0)} pts</Badge>
          <Badge tone={confidenceTone(c.confidence)} title="Concordância entre os sinais detectados; não é probabilidade de acerto nem de viralização.">
            confiança {c.confidence}
          </Badge>
        </>}
      >
        <div className="stack">
          <div className="muted small">
            <Link to={`/recordings/${c.recording.id}`}>{c.recording.name}</Link> · {c.manual ? "criado manualmente" : "sugerido automaticamente"}
          </div>
          <RangePlayer
            src={`/api/recordings/${c.recording.id}/stream`}
            start={form.start}
            end={form.end}
            onMark={(kind, seconds) => {
              const t = Number(seconds.toFixed(1));
              setEdit(kind === "start" ? { ...form, start: t } : { ...form, end: t });
            }}
          />
          <div className="form-grid">
            <Field label="Início"><TimeInput value={form.start} max={maxTime} onChange={(v) => setEdit({ ...form, start: v })} /></Field>
            <Field label="Fim"><TimeInput value={form.end} max={maxTime} onChange={(v) => setEdit({ ...form, end: v })} /></Field>
            <Field label="Duração"><div className="input">{(form.end - form.start).toFixed(1)} s</div></Field>
          </div>
          <div className="form-grid">
            <Field label="Título provisório">
              <TextInput value={form.title} onChange={(e) => setEdit({ ...form, title: e.target.value })} maxLength={120} />
            </Field>
            <Field label="Tipo de momento" hint="Sugestão automática por palavras da fala; corrija se estiver errada.">
              <Select
                value={form.type}
                onChange={(v) => setEdit({ ...form, type: v })}
                options={(facets.data?.moment_types ?? [{ key: c.moment_type, label: c.type_label }]).map((t) => ({ value: t.key, label: t.label }))}
              />
            </Field>
          </div>
          <div className="row wrap">
            <Button
              variant="primary"
              disabled={!dirty}
              busy={busy}
              onClick={() => patch({ title: form.title, start_s: form.start, end_s: form.end, moment_type: form.type }, "Alterações salvas.")}
            >
              Salvar alterações
            </Button>
            {dirty && <Button variant="ghost" onClick={() => setEdit(null)}>Descartar</Button>}
          </div>
        </div>
      </Card>

      <Card title="Revisão e feedback">
        <div className="stack">
          <div className="row wrap">
            <Button variant={c.status === "approved" ? "primary" : "default"} onClick={() => patch({ status: "approved" }, "Aprovado.")}>Aprovar</Button>
            <Button variant={c.status === "rejected" ? "danger" : "default"} onClick={() => patch({ status: "rejected" }, "Rejeitado.")}>Rejeitar</Button>
            <Button variant="ghost" onClick={() => patch({ status: "pending" })}>Voltar a pendente</Button>
            <span className="right" />
            <Button variant="primary" onClick={toClip}>{c.clip_id ? "Abrir no editor" : "Criar corte e abrir no editor"}</Button>
          </div>
          <div className="row wrap">
            <span className="muted small">Resultado do vídeo publicado:</span>
            <Button variant={c.outcome === "good" ? "primary" : "ghost"} onClick={() => patch({ outcome: c.outcome === "good" ? null : "good" })}>👍 Bom</Button>
            <Button variant={c.outcome === "bad" ? "danger" : "ghost"} onClick={() => patch({ outcome: c.outcome === "bad" ? null : "bad" })}>👎 Ruim</Button>
          </div>
          <p className="muted small">
            Aprovar, rejeitar e marcar resultado ajusta levemente (no máximo ±10 pontos) a pontuação de candidatos do mesmo tipo nas
            próximas análises. Um único resultado não prova nada: use como pista.
          </p>
          <div><Button variant="danger" onClick={remove}>Excluir candidato</Button></div>
        </div>
      </Card>

      <Card title="Por que este trecho foi sugerido">
        {!c.reasons || c.reasons.length === 0 ? (
          <Empty>Corte criado manualmente: sem pontuação automática.</Empty>
        ) : (
          <div>
            {c.reasons.map((r) => (
              <div key={r.key} className="reason">
                <div>
                  <strong>{r.label}</strong>
                  <div className="muted small">{r.detail}</div>
                </div>
                <div className="nowrap">{r.value === null ? <span className="muted">n/d</span> : `${r.points >= 0 ? "+" : ""}${r.points.toFixed(1)} pts`}</div>
                {r.value !== null && <div className="reason-bar"><span style={{ width: `${Math.min(Math.abs(r.value), 1) * 100}%` }} /></div>}
              </div>
            ))}
            <p className="muted small">
              A pontuação soma esses critérios (pesos configuráveis em Configurações). “n/d” = informação indisponível neste nível de
              análise; não conta contra o trecho.
            </p>
          </div>
        )}
      </Card>

      <Card title="Fala no trecho">
        {c.transcript.length === 0 ? (
          <Empty>Sem transcrição para este trecho (nível Leve ou trecho fora das janelas transcritas).</Empty>
        ) : (
          <div className="stack small">
            {c.transcript.map((s) => (
              <div key={s.id}><span className="muted">{fmtTime(s.start_s)}</span> {s.text}</div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
