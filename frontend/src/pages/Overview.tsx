import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Overview as OverviewData } from "../api/types";
import { JobStatus } from "../components/JobStatus";
import { useJobs } from "../components/JobsContext";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Stat } from "../components/ui";
import { fmtBytes, fmtDate, fmtTime } from "../lib/format";
import { useAsync } from "../lib/hooks";

export function Overview() {
  const { summary, tick } = useJobs();
  const { data, error, loading } = useAsync(() => api.get<OverviewData>("/api/overview"), [tick]);

  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return null;

  const pending = data.candidates.by_status["pending"] ?? 0;
  const ready = data.clips.by_status["ready"] ?? 0;
  const activeJobs = summary?.active ?? [];

  return (
    <div className="stack">
      <PageHeader
        title="Visão geral"
        subtitle="Resumo do que existe na sua biblioteca local. Nenhum número aqui é estimado: tudo vem do banco de dados do aplicativo."
      />

      {(!data.setup.ffmpeg || !data.setup.profile_filled || !data.setup.has_recording) && (
        <Card title="Primeiros passos">
          <ul className="stack small">
            <li>
              <Badge tone={data.setup.ffmpeg ? "ok" : "danger"}>{data.setup.ffmpeg ? "ok" : "pendente"}</Badge>{" "}
              FFmpeg instalado (necessário para analisar e renderizar).{" "}
              {!data.setup.ffmpeg && <Link to="/settings">Veja como instalar em Configurações</Link>}
            </li>
            <li>
              <Badge tone={data.setup.profile_filled ? "ok" : "warn"}>{data.setup.profile_filled ? "ok" : "recomendado"}</Badge>{" "}
              Perfil do canal preenchido (melhora as recomendações). <Link to="/settings">Abrir perfil</Link>
            </li>
            <li>
              <Badge tone={data.setup.has_recording ? "ok" : "warn"}>{data.setup.has_recording ? "ok" : "pendente"}</Badge>{" "}
              Importar uma gravação. <Link to="/import">Importar vídeo</Link>
            </li>
          </ul>
        </Card>
      )}

      <div className="grid grid-stats">
        <Stat label="Gravações" value={data.recordings.total} />
        <Stat label="Candidatos pendentes" value={pending} hint={`${data.candidates.total} no total`} />
        <Stat label="Cortes prontos" value={ready} hint={`${data.clips.total} cortes no total`} />
        <Stat label="Publicações" value={data.publications.published} hint={`${data.publications.planned} planejadas`} />
        <Stat label="Ideias ativas" value={data.ideas} />
        <Stat label="Espaço em exports" value={fmtBytes(data.disk.exports_bytes)} hint={`prévias: ${fmtBytes(data.disk.previews_bytes)}`} />
      </div>

      <div className="grid grid-2">
        <Card title="Tarefas em andamento">
          {activeJobs.length === 0 ? (
            <Empty>Nenhuma tarefa ativa. Análises e renderizações só começam quando você pede.</Empty>
          ) : (
            <div className="jobs-panel">
              {activeJobs.map((job) => (
                <JobStatus key={job.id} job={job} />
              ))}
            </div>
          )}
        </Card>

        <Card title="Melhores candidatos aguardando revisão" actions={<Link to="/candidates">ver todos</Link>}>
          {data.top_pending_candidates.length === 0 ? (
            <Empty>Nenhum candidato pendente. Analise uma gravação para gerar sugestões.</Empty>
          ) : (
            <table>
              <tbody>
                {data.top_pending_candidates.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <Link to={`/candidates/${c.id}`}>{c.title}</Link>
                      <div className="muted small">
                        {c.recording_name} · {fmtTime(c.start_s)}–{fmtTime(c.end_s)}
                      </div>
                    </td>
                    <td className="nowrap">
                      <Badge>{c.score.toFixed(0)} pts</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted small">A pontuação ordena a revisão; não é uma previsão de desempenho.</p>
        </Card>

        <Card title="Gravações recentes" actions={<Link to="/recordings">ver todas</Link>}>
          {data.recent_recordings.length === 0 ? (
            <Empty>Nada importado ainda.</Empty>
          ) : (
            <table>
              <tbody>
                {data.recent_recordings.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/recordings/${r.id}`}>{r.name}</Link>
                      <div className="muted small">importada em {fmtDate(r.imported_at)}</div>
                    </td>
                    <td className="nowrap">{fmtTime(r.duration_s)}</td>
                    <td>
                      <Badge>{r.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Radar de tendências" actions={<Link to="/trends">abrir</Link>}>
          <dl className="kv">
            {Object.entries(data.radar).map(([source, run]) => (
              <div key={source} style={{ display: "contents" }}>
                <dt>{source}</dt>
                <dd>{run ? `coletado em ${fmtDate(run.collected_at)} (${run.sample_size} itens)` : "ainda não coletado"}</dd>
              </div>
            ))}
          </dl>
          <p className="muted small">
            YouTube: {data.setup.integrations.youtube ? "configurado" : "não configurado"} · Twitch:{" "}
            {data.setup.integrations.twitch ? "configurado" : "não configurado"}
          </p>
        </Card>
      </div>
    </div>
  );
}
