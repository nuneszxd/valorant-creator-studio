import { useState } from "react";

import { api } from "../api/client";
import type { Idea, IdeaReason, IdeaSuggestion } from "../api/types";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, Notice, PageHeader, Select, TextArea, TextInput } from "../components/ui";
import type { Tone } from "../components/ui";
import { useAction, useAsync } from "../lib/hooks";

const KIND_LABEL: Record<string, string> = {
  perfil: "seu perfil",
  dados_proprios: "seus resultados",
  radar: "radar",
  material: "material disponível",
  hipotese: "hipótese",
};

// The badge follows the kind of EVIDENCE, so a hypothesis is never shown as an observation.
const EVIDENCE_LABEL: Record<string, { label: string; tone: Tone }> = {
  observado: { label: "observado", tone: "ok" },
  estimativa: { label: "estimativa", tone: "info" },
  hipotese: { label: "hipótese", tone: "warn" },
  perfil: { label: "informado por você", tone: "info" },
};

const STATUSES = [
  { value: "idea", label: "ideia" },
  { value: "planned", label: "planejada" },
  { value: "recorded", label: "gravada" },
  { value: "published", label: "publicada" },
  { value: "discarded", label: "descartada" },
];

function Reasons({ reasons }: { reasons: IdeaReason[] }) {
  return (
    <ul className="small stack" style={{ paddingLeft: 18 }}>
      {reasons.map((r, i) => {
        const info = EVIDENCE_LABEL[r.evidence] ?? { label: r.evidence, tone: "neutral" as Tone };
        return (
          <li key={i}>
            <Badge tone={info.tone}>{`${KIND_LABEL[r.kind] ?? r.kind}: ${info.label}`}</Badge> {r.text}
          </li>
        );
      })}
    </ul>
  );
}

export function Ideas() {
  const { run, busy } = useAction();
  const saved = useAsync(() => api.get<Idea[]>("/api/ideas"), []);
  const [suggestions, setSuggestions] = useState<IdeaSuggestion[] | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [title, setTitle] = useState("");

  async function suggest() {
    const result = await run(() => api.post<{ ideas: IdeaSuggestion[]; notes: string[] }>("/api/ideas/suggest"));
    if (result) {
      setSuggestions(result.ideas);
      setNotes(result.notes);
    }
  }

  async function save(s: IdeaSuggestion) {
    await run(
      () => api.post("/api/ideas", { title: s.title, format: s.format, rationale: s.reasons, source: "sugestao" }),
      "Ideia salva.",
    );
    saved.reload();
  }

  async function create() {
    if (!title.trim()) return;
    await run(() => api.post("/api/ideas", { title: title.trim() }), "Ideia criada.");
    setTitle("");
    saved.reload();
  }

  return (
    <div className="stack">
      <PageHeader
        title="Ideias e roteiros"
        subtitle="Sugestões baseadas no seu perfil, nos seus resultados e no radar. Cada sugestão mostra os motivos; nada é uma garantia de desempenho."
        actions={<Button variant="primary" onClick={suggest} busy={busy}>Gerar sugestões</Button>}
      />

      {notes.map((n) => <Notice key={n} tone="warn">{n}</Notice>)}
      {suggestions && (
        <Card title="Sugestões (ordenadas pela soma dos motivos)">
          {suggestions.length === 0 ? <Empty>Sem sugestões.</Empty> : (
            <div className="grid grid-2">
              {suggestions.map((s) => (
                <div key={s.format} className="card" style={{ boxShadow: "none" }}>
                  <div className="card-head">
                    <h3>{s.title}</h3>
                    <Badge title={s.priority_note}>prioridade {s.priority.toFixed(2)}</Badge>
                  </div>
                  <Reasons reasons={s.reasons} />
                  <p className="small"><strong>Próximo passo:</strong> {s.next_step}</p>
                  <Button onClick={() => save(s)}>Salvar ideia</Button>
                </div>
              ))}
            </div>
          )}
          <p className="muted small">{suggestions[0]?.priority_note}</p>
        </Card>
      )}

      <Card title="Minhas ideias e roteiros">
        <div className="row" style={{ marginBottom: 12 }}>
          <TextInput placeholder="Nova ideia (ex.: Jornada Diamante → Imortal, ep. 1)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <Button onClick={create}>Adicionar</Button>
        </div>
        <ErrorBox error={saved.error} />
        {saved.loading && !saved.data && <Loading />}
        {saved.data && saved.data.length === 0 && <Empty>Nenhuma ideia salva ainda.</Empty>}
        <div className="stack">
          {(saved.data ?? []).map((idea) => <IdeaCard key={idea.id} idea={idea} onChanged={saved.reload} />)}
        </div>
      </Card>
    </div>
  );
}

function IdeaCard({ idea, onChanged }: { idea: Idea; onChanged: () => void }) {
  const { run, busy } = useAction();
  const [beats, setBeats] = useState(idea.script?.beats ?? null);

  async function setStatus(status: string) {
    await run(() => api.patch(`/api/ideas/${idea.id}`, { status }));
    onChanged();
  }
  async function makeScript() {
    const updated = await run(() => api.post<Idea>(`/api/ideas/${idea.id}/script`), "Roteiro criado.");
    if (updated?.script) setBeats(updated.script.beats);
    onChanged();
  }
  async function saveScript() {
    if (!idea.script || !beats) return;
    await run(() => api.patch(`/api/ideas/${idea.id}`, { script: { ...idea.script, beats } }), "Roteiro salvo.");
    onChanged();
  }
  async function remove() {
    if (!window.confirm("Excluir esta ideia?")) return;
    await run(() => api.del(`/api/ideas/${idea.id}`));
    onChanged();
  }

  return (
    <div className="card" style={{ boxShadow: "none" }}>
      <div className="card-head">
        <h3>{idea.title}</h3>
        <div className="row">
          <Select value={idea.status} onChange={setStatus} options={STATUSES} style={{ width: 140 }} />
          <Button variant="ghost" onClick={remove}>Excluir</Button>
        </div>
      </div>
      {idea.rationale && idea.rationale.length > 0 && <Reasons reasons={idea.rationale} />}
      {!beats ? (
        <Button onClick={makeScript} busy={busy}>Criar roteiro (esqueleto para preencher)</Button>
      ) : (
        <div className="stack">
          <div className="muted small">Duração-alvo: {idea.script?.target_duration}. Preencha só com fatos reais do seu vídeo.</div>
          {beats.map((beat, i) => (
            <Field key={beat.beat} label={beat.beat} hint={beat.guide}>
              <TextArea
                rows={2}
                value={beat.your_text}
                onChange={(e) => setBeats(beats.map((b, j) => (j === i ? { ...b, your_text: e.target.value } : b)))}
              />
            </Field>
          ))}
          <ul className="small">{idea.script?.checklist.map((c) => <li key={c}>{c}</li>)}</ul>
          <div><Button onClick={saveScript} busy={busy}>Salvar roteiro</Button></div>
        </div>
      )}
    </div>
  );
}
