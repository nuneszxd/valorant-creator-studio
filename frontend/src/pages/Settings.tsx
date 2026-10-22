import { useState } from "react";

import { api } from "../api/client";
import type { AppSettings, Capabilities, CreatorProfile, Facets, SettingsResponse } from "../api/types";
import { Badge, Button, Card, Checkbox, ErrorBox, Field, Loading, Notice, NumberInput, PageHeader, Select, Tabs, TextArea, TextInput } from "../components/ui";
import { useToast } from "../components/Toast";
import { useAction, useAsync } from "../lib/hooks";
import { AudioPanel, ExportPanel, FramingPanel, SubtitleStyleCard } from "./editor/panels";
import type { Draft } from "./editor/panels";

const WEIGHT_LABELS: Record<string, string> = {
  audio_intensity: "Intensidade do áudio",
  audio_burst: "Subida brusca de volume",
  tension: "Tensão (calmaria antes do pico)",
  speech: "Presença de fala",
  reaction: "Palavras de evento/reação",
  scene_activity: "Mudanças de cena",
  context: "Contexto falado antes do pico",
  story: "Início → desfecho",
  duration_fit: "Adequação à duração desejada",
  creator_pref: "Preferência do criador",
};

export function SettingsPage() {
  const [tab, setTab] = useState("profile");
  return (
    <div className="stack">
      <PageHeader title="Configurações e integrações" subtitle="Perfil do canal, análise, transcrição, renderização, pastas e estado do sistema." />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "profile", label: "Perfil do canal" },
          { key: "analysis", label: "Análise e pontuação" },
          { key: "transcription", label: "Transcrição" },
          { key: "render", label: "Renderização padrão" },
          { key: "folders", label: "Pastas e integrações" },
          { key: "system", label: "Sistema" },
        ]}
      />
      {tab === "profile" && <ProfileTab />}
      {tab === "analysis" && <AnalysisTab />}
      {tab === "transcription" && <TranscriptionTab />}
      {tab === "render" && <RenderTab />}
      {tab === "folders" && <FoldersTab />}
      {tab === "system" && <SystemTab />}
    </div>
  );
}

// ---------------------------------------------------------------------------- profile

const splitList = (text: string) => text.split(",").map((s) => s.trim()).filter(Boolean);

function ProfileTab() {
  const loaded = useAsync(() => api.get<CreatorProfile>("/api/profile"), []);
  const facets = useAsync(() => api.get<Facets>("/api/library/facets"), []);
  if (loaded.loading && !loaded.data) return <Loading />;
  if (!loaded.data) return <ErrorBox error={loaded.error} />;
  return <ProfileForm initial={loaded.data} moments={facets.data?.moment_types ?? []} />;
}

function ProfileForm({ initial, moments }: { initial: CreatorProfile; moments: Array<{ key: string; label: string }> }) {
  const { run, busy } = useAction();
  const [p, setP] = useState<CreatorProfile>(initial);
  const [agents, setAgents] = useState(initial.agents.join(", "));
  const [styles, setStyles] = useState(initial.content_style.join(", "));
  const [formats, setFormats] = useState(initial.formats_to_try.join(", "));
  const [other, setOther] = useState(initial.links.other.join(", "));
  const set = (partial: Partial<CreatorProfile>) => setP((prev) => ({ ...prev, ...partial }));
  const setLink = (partial: Partial<CreatorProfile["links"]>) => setP((prev) => ({ ...prev, links: { ...prev.links, ...partial } }));

  async function save() {
    const body: CreatorProfile = { ...p, agents: splitList(agents), content_style: splitList(styles), formats_to_try: splitList(formats), links: { ...p.links, other: splitList(other) } };
    await run(() => api.put("/api/profile", body), "Perfil salvo.");
  }

  return (
    <div className="stack">
      <Notice tone="info">O perfil orienta as recomendações e a priorização dos cortes. Fica só neste computador.</Notice>
      <Card title="Canal">
        <div className="form-grid">
          <Field label="Nome do canal"><TextInput value={p.channel_name} onChange={(e) => set({ channel_name: e.target.value })} /></Field>
          <Field label="Rank atual"><TextInput value={p.rank_current} onChange={(e) => set({ rank_current: e.target.value })} placeholder="Diamante 2" /></Field>
          <Field label="Rank desejado"><TextInput value={p.rank_target} onChange={(e) => set({ rank_target: e.target.value })} placeholder="Imortal 1" /></Field>
          <Field label="Nome da série (opcional)"><TextInput value={p.series_name} onChange={(e) => set({ series_name: e.target.value })} placeholder="Rumo ao Imortal" /></Field>
          <Field label="Frequência de publicação (vídeos/semana)">
            <NumberInput value={p.publishing_frequency_per_week} min={0} max={100} step={0.5} onChange={(v) => set({ publishing_frequency_per_week: v })} />
          </Field>
          <Field label="Agentes que você usa (separados por vírgula)"><TextInput value={agents} onChange={(e) => setAgents(e.target.value)} placeholder="Jett, Reyna" /></Field>
        </div>
        <div className="form-grid" style={{ marginTop: 12 }}>
          <Field label="Estilo de conteúdo (vírgula)"><TextInput value={styles} onChange={(e) => setStyles(e.target.value)} placeholder="humor, evolução de rank" /></Field>
          <Field label="Formatos que quer experimentar (vírgula)"><TextInput value={formats} onChange={(e) => setFormats(e.target.value)} placeholder="série de rank, clutch da live" /></Field>
        </div>
        <Field label="Público que deseja alcançar" className="mt"><TextInput value={p.target_audience} onChange={(e) => set({ target_audience: e.target.value })} /></Field>
      </Card>
      <Card title="Redes sociais">
        <div className="form-grid">
          <Field label="Twitch"><TextInput value={p.links.twitch} onChange={(e) => setLink({ twitch: e.target.value })} /></Field>
          <Field label="TikTok"><TextInput value={p.links.tiktok} onChange={(e) => setLink({ tiktok: e.target.value })} /></Field>
          <Field label="YouTube"><TextInput value={p.links.youtube} onChange={(e) => setLink({ youtube: e.target.value })} /></Field>
          <Field label="Instagram"><TextInput value={p.links.instagram} onChange={(e) => setLink({ instagram: e.target.value })} /></Field>
          <Field label="Outros (vírgula)"><TextInput value={other} onChange={(e) => setOther(e.target.value)} /></Field>
        </div>
      </Card>
      <Card title="Preferências de corte e edição">
        <div className="form-grid">
          <Field label="Duração desejada — mínima (s)"><NumberInput value={p.preferred_duration_min_s} min={5} max={180} onChange={(v) => set({ preferred_duration_min_s: v ?? 20 })} /></Field>
          <Field label="Duração desejada — máxima (s)"><NumberInput value={p.preferred_duration_max_s} min={5} max={180} onChange={(v) => set({ preferred_duration_max_s: v ?? 45 })} /></Field>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>Tipos de momento que você quer priorizar nas sugestões:</p>
        <div className="row wrap">
          {moments.filter((m) => m.key !== "pico_audio" && m.key !== "outro").map((m) => (
            <Checkbox
              key={m.key}
              checked={p.preferred_types.includes(m.key)}
              onChange={(on) => set({ preferred_types: on ? [...p.preferred_types, m.key] : p.preferred_types.filter((k) => k !== m.key) })}
              label={m.label}
            />
          ))}
        </div>
        <Field label="Preferências de edição (texto livre)" className="mt"><TextArea rows={2} value={p.editing_preferences} onChange={(e) => set({ editing_preferences: e.target.value })} /></Field>
        <Field label="Resultados de publicações anteriores (notas livres)" hint="Os números ficam em Métricas; aqui só observações gerais.">
          <TextArea rows={3} value={p.past_results_notes} onChange={(e) => set({ past_results_notes: e.target.value })} />
        </Field>
      </Card>
      <div><Button variant="primary" onClick={save} busy={busy}>Salvar perfil</Button></div>
    </div>
  );
}

// ---------------------------------------------------------------------------- shared settings loader

function useSettings() {
  return useAsync(() => api.get<SettingsResponse>("/api/settings"), []);
}

function SettingsLoader({ children }: { children: (data: SettingsResponse, reload: () => void) => JSX.Element }) {
  const s = useSettings();
  if (s.loading && !s.data) return <Loading />;
  if (!s.data) return <ErrorBox error={s.error} />;
  return children(s.data, s.reload);
}

// ---------------------------------------------------------------------------- analysis

function AnalysisTab() {
  return <SettingsLoader>{(data, reload) => <AnalysisForm data={data} reload={reload} />}</SettingsLoader>;
}

function AnalysisForm({ data, reload }: { data: SettingsResponse; reload: () => void }) {
  const { run, busy } = useAction();
  const [s, setS] = useState<AppSettings>(data.settings);
  const a = s.analysis;
  const setA = (partial: Partial<AppSettings["analysis"]>) => setS({ ...s, analysis: { ...a, ...partial } });
  const kwText = (key: string) => (s.keywords[key] ?? []).join("\n");

  async function save() {
    await run(
      () => api.patch("/api/settings", { analysis: s.analysis, scoring_weights: s.scoring_weights, keywords: s.keywords, reaction_keywords: s.reaction_keywords }),
      "Configurações de análise salvas.",
    );
    reload();
  }
  function restore() {
    setS({ ...s, analysis: data.defaults.analysis, scoring_weights: data.defaults.scoring_weights, keywords: data.defaults.keywords, reaction_keywords: data.defaults.reaction_keywords });
  }

  return (
    <div className="stack">
      <Card title="Detecção de candidatos">
        <div className="form-grid">
          <Field label="Máximo de candidatos por análise"><NumberInput value={a.max_candidates} min={1} max={200} onChange={(v) => setA({ max_candidates: v ?? 25 })} /></Field>
          <Field label="Sensibilidade (intensidade mínima 0.1–1)" hint="Menor = mais picos considerados."><NumberInput value={a.min_intensity} min={0.1} max={1} step={0.05} onChange={(v) => setA({ min_intensity: v ?? 0.55 })} /></Field>
          <Field label="Segundos antes do pico"><NumberInput value={a.pre_roll_s} min={2} max={120} onChange={(v) => setA({ pre_roll_s: v ?? 18 })} /></Field>
          <Field label="Segundos depois do pico"><NumberInput value={a.post_roll_s} min={2} max={120} onChange={(v) => setA({ post_roll_s: v ?? 10 })} /></Field>
          <Field label="Distância mínima entre picos (s)"><NumberInput value={a.min_separation_s} min={5} max={600} onChange={(v) => setA({ min_separation_s: v ?? 25 })} /></Field>
          <Field label="Limiar de mudança de cena (0.05–0.95)"><NumberInput value={a.scene_threshold} min={0.05} max={0.95} step={0.05} onChange={(v) => setA({ scene_threshold: v ?? 0.35 })} /></Field>
          <Field label="Faixa de áudio a analisar (0 = primeira)" hint="Gravações do OBS podem ter várias faixas (jogo, microfone…)."><NumberInput value={a.audio_stream_index} min={0} max={16} onChange={(v) => setA({ audio_stream_index: v ?? 0 })} /></Field>
        </div>
        <Notice tone="info">Um pico de áudio é só uma pista: a pontuação combina vários sinais e você revisa cada sugestão. Não é possível identificar todos os eventos do Valorant só por áudio ou imagem.</Notice>
      </Card>

      <Card title="Pesos da pontuação (explicável)">
        <div className="form-grid">
          {Object.entries(s.scoring_weights).map(([key, value]) => (
            <Field key={key} label={WEIGHT_LABELS[key] ?? key}>
              <NumberInput value={value} min={0} max={1} step={0.01} onChange={(v) => setS({ ...s, scoring_weights: { ...s.scoring_weights, [key]: v ?? 0 } })} />
            </Field>
          ))}
        </div>
        <p className="muted small">Os pesos são relativos: o que importa é a proporção entre eles. A pontuação ordena sua revisão; não é uma probabilidade.</p>
      </Card>

      <Card title="Palavras-chave que sugerem o tipo do momento">
        <p className="muted small">Uma palavra ou expressão por linha, sem acentos. Usadas na fala transcrita para sugerir o tipo (você confirma depois).</p>
        <div className="grid grid-3">
          {Object.keys(s.keywords).map((key) => (
            <Field key={key} label={key}>
              <TextArea rows={5} value={kwText(key)} onChange={(e) => setS({ ...s, keywords: { ...s.keywords, [key]: e.target.value.split("\n").map((l) => l.trim()).filter(Boolean) } })} />
            </Field>
          ))}
          <Field label="reações genéricas">
            <TextArea rows={5} value={s.reaction_keywords.join("\n")} onChange={(e) => setS({ ...s, reaction_keywords: e.target.value.split("\n").map((l) => l.trim()).filter(Boolean) })} />
          </Field>
        </div>
      </Card>
      <div className="row">
        <Button variant="primary" onClick={save} busy={busy}>Salvar</Button>
        <Button variant="ghost" onClick={restore}>Restaurar padrões (não salva até clicar em Salvar)</Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- transcription

function TranscriptionTab() {
  return <SettingsLoader>{(data, reload) => <TranscriptionForm data={data} reload={reload} />}</SettingsLoader>;
}

function TranscriptionForm({ data, reload }: { data: SettingsResponse; reload: () => void }) {
  const { run, busy } = useAction();
  const caps = useAsync(() => api.get<Capabilities>("/api/system/capabilities"), []);
  const [s, setS] = useState<AppSettings>(data.settings);
  async function save() {
    await run(
      () => api.patch("/api/settings", {
        transcription_provider: s.transcription_provider, whisper_model: s.whisper_model, whisper_language: s.whisper_language,
        whisper_beam_size: s.whisper_beam_size, whisper_cpp_path: s.whisper_cpp_path || null, whisper_cpp_model_path: s.whisper_cpp_model_path || null,
      }),
      "Configurações de transcrição salvas.",
    );
    reload();
  }
  return (
    <div className="stack">
      <Notice tone="warn">
        Sua placa é AMD: o faster-whisper (padrão) <strong>não usa GPU AMD no Windows</strong> e roda na CPU. Por isso o nível “Padrão” transcreve apenas
        os trechos candidatos. A opção whisper.cpp (experimental) permite usar uma build com Vulkan, que pode aproveitar a GPU AMD.
      </Notice>
      {caps.data && (
        <p className="small">
          faster-whisper instalado: <Badge tone={caps.data.transcription.faster_whisper_installed ? "ok" : "warn"}>{caps.data.transcription.faster_whisper_installed ? "sim" : "não"}</Badge>
          {" "}· whisper.cpp configurado: <Badge tone={caps.data.transcription.whisper_cpp_configured ? "ok" : "neutral"}>{caps.data.transcription.whisper_cpp_configured ? "sim" : "não"}</Badge>
        </p>
      )}
      <Card title="Motor de transcrição">
        <div className="form-grid">
          <Field label="Motor">
            <Select value={s.transcription_provider} onChange={(v) => setS({ ...s, transcription_provider: v as AppSettings["transcription_provider"] })}
              options={[{ value: "faster-whisper", label: "faster-whisper (CPU) — padrão" }, { value: "whisper.cpp", label: "whisper.cpp — experimental" }]} />
          </Field>
          <Field label="Modelo do faster-whisper" hint="Baixado uma vez, só com a sua permissão. Maior = mais preciso e mais lento.">
            <Select value={s.whisper_model} onChange={(v) => setS({ ...s, whisper_model: v as AppSettings["whisper_model"] })}
              options={[
                { value: "tiny", label: "tiny (≈75 MB)" }, { value: "base", label: "base (≈145 MB)" },
                { value: "small", label: "small (≈480 MB)" }, { value: "medium", label: "medium (≈1,5 GB — muito lento em CPU)" },
              ]} />
          </Field>
          <Field label="Idioma"><TextInput value={s.whisper_language} maxLength={3} onChange={(e) => setS({ ...s, whisper_language: e.target.value.toLowerCase() })} /></Field>
          <Field label="Beam size (1 = mais rápido)"><NumberInput value={s.whisper_beam_size} min={1} max={5} onChange={(v) => setS({ ...s, whisper_beam_size: v ?? 1 })} /></Field>
        </div>
      </Card>
      {s.transcription_provider === "whisper.cpp" && (
        <Card title="whisper.cpp (você fornece os arquivos)">
          <div className="form-grid">
            <Field label="Caminho do whisper-cli.exe"><TextInput value={s.whisper_cpp_path ?? ""} onChange={(e) => setS({ ...s, whisper_cpp_path: e.target.value })} /></Field>
            <Field label="Caminho do modelo (.bin)"><TextInput value={s.whisper_cpp_model_path ?? ""} onChange={(e) => setS({ ...s, whisper_cpp_model_path: e.target.value })} /></Field>
          </div>
          <p className="muted small">O aplicativo não baixa nem compila o whisper.cpp. Veja docs/USAGE.md. Este caminho é experimental e não foi validado em GPU AMD.</p>
        </Card>
      )}
      <div><Button variant="primary" onClick={save} busy={busy}>Salvar</Button></div>
    </div>
  );
}

// ---------------------------------------------------------------------------- render defaults

function RenderTab() {
  return <SettingsLoader>{(data, reload) => <RenderForm data={data} reload={reload} />}</SettingsLoader>;
}

function RenderForm({ data, reload }: { data: SettingsResponse; reload: () => void }) {
  const { run, busy } = useAction();
  const caps = useAsync(() => api.get<Capabilities>("/api/system/capabilities"), []);
  const [s, setS] = useState<AppSettings>(data.settings);
  const draft: Draft = { title: "", start: 0, end: 0, type: "outro", map: "", agent: "", facts: {}, cfg: s.render, style: s.subtitle_style, cues: [] };
  const patch = (partial: Partial<Draft>) => {
    setS((prev) => ({ ...prev, render: partial.cfg ?? prev.render, subtitle_style: partial.style ?? prev.subtitle_style }));
  };
  async function save() {
    await run(() => api.patch("/api/settings", { render: s.render, subtitle_style: s.subtitle_style }), "Padrões de renderização salvos.");
    reload();
  }
  return (
    <div className="stack">
      <Notice tone="info">Estes são os valores iniciais de cada <strong>novo</strong> corte. Cortes já criados mantêm as próprias configurações.</Notice>
      <Card title="Enquadramento"><FramingPanel d={draft} patch={patch} /></Card>
      <Card title="Áudio"><AudioPanel d={draft} patch={patch} /></Card>
      <Card title="Exportação"><ExportPanel d={draft} patch={patch} caps={caps.data} /></Card>
      <Checkbox checked={s.render.subtitles} onChange={(v) => setS({ ...s, render: { ...s.render, subtitles: v } })} label="Gravar legendas por padrão" />
      <SubtitleStyleCard style={s.subtitle_style} setStyle={(partial) => setS({ ...s, subtitle_style: { ...s.subtitle_style, ...partial } })} />
      <div><Button variant="primary" onClick={save} busy={busy}>Salvar padrões</Button></div>
    </div>
  );
}

// ---------------------------------------------------------------------------- folders & integrations

function FoldersTab() {
  return <SettingsLoader>{(data, reload) => <FoldersForm data={data} reload={reload} />}</SettingsLoader>;
}

function FoldersForm({ data, reload }: { data: SettingsResponse; reload: () => void }) {
  const { run, busy } = useAction();
  const [out, setOut] = useState(data.settings.output_dir ?? "");
  const [hashtags, setHashtags] = useState(data.settings.base_hashtags.join(" "));
  const [quota, setQuota] = useState<number | null>(data.settings.youtube_search_daily_limit);

  async function pick() {
    const result = await run(() => api.post<{ path: string | null }>("/api/system/pick-file", { kind: "folder" }));
    if (result?.path) setOut(result.path);
  }
  async function save() {
    await run(
      () => api.patch("/api/settings", {
        output_dir: out.trim() || null,
        base_hashtags: hashtags.split(/\s+/).map((h) => h.replace(/^#/, "")).filter(Boolean),
        youtube_search_daily_limit: quota ?? 100,
      }),
      "Salvo.",
    );
    reload();
  }

  return (
    <div className="stack">
      <Card title="Pastas">
        <div className="stack">
          <Field label="Pasta de trabalho (banco de dados, modelos, temporários)" hint="Definida no arquivo .env (VCS_DATA_DIR); mudar exige reiniciar.">
            <div className="input">{data.data_dir}</div>
          </Field>
          <Field label="Pasta de saída dos cortes exportados" hint={`Em uso agora: ${data.effective_output_dir}. Deixe vazio para usar a padrão.`}>
            <div className="row"><TextInput value={out} onChange={(e) => setOut(e.target.value)} placeholder="D:\Cortes" /><Button onClick={pick}>Escolher…</Button></div>
          </Field>
        </div>
      </Card>
      <Card title="Hashtags base e cotas">
        <div className="form-grid">
          <Field label="Hashtags base dos textos sugeridos" hint="Separadas por espaço, sem #.">
            <TextInput value={hashtags} onChange={(e) => setHashtags(e.target.value)} />
          </Field>
          <Field label="Limite diário de buscas do YouTube" hint="O padrão do Google é 100 buscas por dia por projeto.">
            <NumberInput value={quota} min={1} max={10000} onChange={setQuota} />
          </Field>
        </div>
      </Card>
      <Card title="Integrações (credenciais ficam só no arquivo .env)">
        <table>
          <tbody>
            <tr>
              <td>Twitch (TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET)</td>
              <td><Badge tone={data.integrations.twitch ? "ok" : "neutral"}>{data.integrations.twitch ? "configurada" : "não configurada"}</Badge></td>
              <td className="small muted">Metadados de VOD, clipes públicos. Não baixa VODs.</td>
            </tr>
            <tr>
              <td>YouTube (YOUTUBE_API_KEY)</td>
              <td><Badge tone={data.integrations.youtube ? "ok" : "neutral"}>{data.integrations.youtube ? "configurada" : "não configurada"}</Badge></td>
              <td className="small muted">Busca pública e estatísticas para o radar.</td>
            </tr>
          </tbody>
        </table>
        <p className="muted small">
          Por segurança, o aplicativo nunca pede nem mostra chaves nesta tela. Edite o arquivo <code>.env</code> na pasta do projeto e reinicie.
          Passo a passo em docs/USAGE.md.
        </p>
      </Card>
      <div><Button variant="primary" onClick={save} busy={busy}>Salvar</Button></div>
    </div>
  );
}

// ---------------------------------------------------------------------------- system

function SystemTab() {
  const caps = useAsync(() => api.get<Capabilities>("/api/system/capabilities"), []);
  const { run, busy } = useAction();
  const toast = useToast();
  if (caps.loading && !caps.data) return <Loading />;
  if (!caps.data) return <ErrorBox error={caps.error} />;
  const c = caps.data;

  async function test(encoder: string) {
    const r = await run(() => api.post<{ ok: boolean; detail: string }>("/api/system/test-encoder", { encoder }));
    if (r) toast(r.ok ? `${encoder}: funcionou.` : `${encoder}: falhou — ${r.detail}`, r.ok ? "ok" : "error");
  }
  async function shutdown() {
    if (!window.confirm("Encerrar o Valorant Creator Studio? Tarefas em andamento serão canceladas.")) return;
    await run(() => api.post("/api/system/shutdown"), "Encerrando… você pode fechar esta aba.");
  }

  return (
    <div className="stack">
      <Card title="FFmpeg">
        {!c.ffmpeg.available && <Notice tone="danger">FFmpeg/ffprobe não encontrados. Instale-os (docs/USAGE.md) ou defina VCS_FFMPEG_PATH no .env.</Notice>}
        <dl className="kv">
          <dt>Versão</dt><dd>{c.ffmpeg.version ?? "–"}</dd>
          <dt>Caminho</dt><dd>{c.ffmpeg.ffmpeg_path ?? "–"}</dd>
        </dl>
        <p className="small"><strong>Encoders encontrados:</strong></p>
        <div className="row wrap">
          {Object.entries(c.ffmpeg.encoders).map(([name, ok]) => (
            <span key={name} className="row">
              <Badge tone={ok ? "ok" : "neutral"}>{name}: {ok ? "listado" : "ausente"}</Badge>
              {ok && <Button variant="ghost" onClick={() => test(name)} busy={busy}>testar</Button>}
            </span>
          ))}
        </div>
        <p className="small"><strong>Filtros:</strong> {Object.entries(c.ffmpeg.filters).map(([name, ok]) => `${name}: ${ok ? "ok" : "ausente"}`).join(" · ")}</p>
        {!c.ffmpeg.filters["ass"] && <Notice tone="warn">Sem o filtro “ass”, as legendas não podem ser gravadas no vídeo. Use uma build “full” do FFmpeg.</Notice>}
      </Card>
      <Card title="Ambiente">
        <dl className="kv">
          <dt>Aplicativo</dt><dd>v{c.app_version}</dd>
          <dt>Python</dt><dd>{c.python}</dd>
          <dt>Sistema</dt><dd>{c.platform}</dd>
          <dt>Pasta de dados</dt><dd>{c.paths.data_dir}</dd>
          <dt>Pasta de saída</dt><dd>{c.paths.output_dir}</dd>
          <dt>Transcrição</dt><dd>{c.transcription.note}</dd>
        </dl>
      </Card>
      <Card title="Encerrar">
        <p className="small muted">O servidor roda só neste computador (127.0.0.1) e não é exposto à internet.</p>
        <Button variant="danger" onClick={shutdown}>Encerrar o aplicativo</Button>
      </Card>
    </div>
  );
}
