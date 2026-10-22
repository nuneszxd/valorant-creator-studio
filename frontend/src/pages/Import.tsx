import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { Recording, TwitchResolve } from "../api/types";
import { Button, Card, Checkbox, ErrorBox, Field, Notice, PageHeader, TextArea, TextInput } from "../components/ui";
import { fmtDate, fmtTime } from "../lib/format";
import { useAction } from "../lib/hooks";

export function ImportPage() {
  const navigate = useNavigate();
  const { run, busy } = useAction();
  const [path, setPath] = useState("");
  const [game, setGame] = useState("Valorant");
  const [map, setMap] = useState("");
  const [agent, setAgent] = useState("");
  const [notes, setNotes] = useState("");
  const [twitchUrl, setTwitchUrl] = useState("");
  const [resolved, setResolved] = useState<TwitchResolve | null>(null);
  const [linkToTwitch, setLinkToTwitch] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [imported, setImported] = useState<Recording | null>(null);
  const [importing, setImporting] = useState(false);

  async function pick() {
    const result = await run(() => api.post<{ path: string | null }>("/api/system/pick-file", { kind: "video" }));
    if (result?.path) setPath(result.path);
  }

  async function resolve() {
    setError(null);
    setResolved(null);
    try {
      const data = await api.post<TwitchResolve>("/api/imports/twitch/resolve", { url: twitchUrl });
      setResolved(data);
      setLinkToTwitch(data.kind === "vod");
    } catch (err) {
      setError(err);
    }
  }

  async function importFile() {
    if (importing) return;
    setError(null);
    setImporting(true);
    try {
      const recording = await api.post<Recording>("/api/recordings", {
        path,
        source: linkToTwitch ? "twitch" : "local",
        twitch_url: linkToTwitch ? twitchUrl : null,
        game: game || "Valorant",
        map: map || null,
        agent: agent || null,
        notes: notes || null,
      });
      setImported(recording);
    } catch (err) {
      setError(err);
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="stack">
      <PageHeader
        title="Importar vídeos"
        subtitle="O arquivo continua onde está: o aplicativo guarda só o caminho e os metadados (nada é copiado nem enviado)."
      />
      <ErrorBox error={error} />

      {imported && (
        <Notice tone="ok">
          <strong>{imported.name}</strong> importada ({fmtTime(imported.duration_s)}, {imported.width}×{imported.height}
          {imported.fps ? ` @ ${imported.fps} fps` : ""}).{" "}
          {(imported.warnings ?? []).map((w) => (
            <div key={w} className="small">⚠ {w}</div>
          ))}
          <div className="row" style={{ marginTop: 8 }}>
            <Button variant="primary" onClick={() => navigate(`/recordings/${imported.id}`)}>
              Ir para a análise
            </Button>
            <Button variant="ghost" onClick={() => setImported(null)}>Importar outro</Button>
          </div>
        </Notice>
      )}

      <div className="grid grid-2">
        <Card title="1. Arquivo de vídeo local">
          <div className="stack">
            <Field label="Caminho do arquivo" hint="Ex.: D:\Gravações\partida.mp4 — ou use o botão para escolher.">
              <div className="row">
                <TextInput value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\caminho\do\video.mp4" />
                <Button onClick={pick} busy={busy}>Escolher…</Button>
              </div>
            </Field>
            <div className="form-grid">
              <Field label="Jogo"><TextInput value={game} onChange={(e) => setGame(e.target.value)} /></Field>
              <Field label="Mapa (opcional)"><TextInput value={map} onChange={(e) => setMap(e.target.value)} placeholder="Ascent" /></Field>
              <Field label="Agente (opcional)"><TextInput value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="Jett" /></Field>
            </div>
            <Field label="Observações (opcional)">
              <TextArea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
            </Field>
            {linkToTwitch && <Notice tone="info">Esta gravação será ligada ao VOD da Twitch informado ao lado.</Notice>}
            <div className="row">
              <Button variant="primary" onClick={importFile} busy={importing} disabled={!path.trim()}>Importar</Button>
            </div>
            <p className="muted small">
              O vídeo é lido pelo FFmpeg local só para obter duração, resolução e quadros por segundo. Formatos aceitos: mp4, mkv,
              mov, webm, avi, flv, m4v, wmv, mpg, ts.
            </p>
          </div>
        </Card>

        <Card title="2. Link de VOD ou live da Twitch">
          <div className="stack">
            <Field label="Link">
              <div className="row">
                <TextInput value={twitchUrl} onChange={(e) => setTwitchUrl(e.target.value)} placeholder="https://www.twitch.tv/videos/123456789" />
                <Button onClick={resolve} disabled={!twitchUrl.trim()}>Consultar</Button>
              </div>
            </Field>
            <Notice tone="warn">
              A API oficial da Twitch <strong>não permite baixar VODs</strong>. Este passo só confere o link e mostra os dados
              do VOD; o arquivo vem de um download autorizado feito por você.
            </Notice>

            {resolved && (
              <div className="stack">
                {resolved.video && (
                  <dl className="kv">
                    <dt>Título</dt><dd>{resolved.video.title}</dd>
                    <dt>Canal</dt><dd>{resolved.video.user_name}</dd>
                    <dt>Duração</dt><dd>{fmtTime(resolved.video.duration_s)}</dd>
                    <dt>Criado em</dt><dd>{fmtDate(resolved.video.created_at)}</dd>
                    <dt>Tipo</dt><dd>{resolved.video.type}</dd>
                  </dl>
                )}
                {resolved.live && (
                  <Notice tone={resolved.live.is_live ? "warn" : "info"}>
                    Canal {resolved.live.login}: {resolved.live.is_live ? "ao vivo agora" : "offline"}.
                  </Notice>
                )}
                {resolved.messages.map((m) => (
                  <div key={m} className="small">• {m}</div>
                ))}
                <div>
                  <strong className="small">Como obter o arquivo:</strong>
                  <ol className="small">
                    {resolved.download_steps.map((s) => <li key={s}>{s}</li>)}
                  </ol>
                  <p className="muted small">{resolved.retention_note}</p>
                </div>
                {resolved.kind === "vod" && (
                  <Checkbox
                    checked={linkToTwitch}
                    onChange={setLinkToTwitch}
                    label="Ligar o arquivo escolhido ao lado a este VOD (compara a duração e guarda a origem)"
                  />
                )}
              </div>
            )}
          </div>
        </Card>
      </div>

      <p className="muted small">
        Depois de importar, <Link to="/recordings">abra a gravação</Link> e escolha o nível de análise. Nada pesado roda antes disso.
      </p>
    </div>
  );
}
