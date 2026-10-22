# Arquitetura

Descreve o que está **implementado** (versão 0.1). Itens que dependem de hardware ou de gravações reais estão marcados como não validados.

## Visão geral

```
 Navegador (localhost)                    Seu computador
┌────────────────────────┐   HTTP/JSON    ┌───────────────────────────────────────────┐
│ React + TypeScript     │ ─────────────► │ FastAPI em 127.0.0.1                      │
│ (Vite; em produção é   │ ◄───────────── │  ├─ Guarda Host/Origin (anti-rebinding/   │
│ servido pelo backend)  │   OpenAPI      │  │   CSRF)                                │
└────────────────────────┘                │  ├─ Rotas REST (docs em /api/docs)        │
                                          │  ├─ Fila de tarefas (1 por vez, SQLite)   │
                                          │  ├─ Análise / renderização / radar        │
                                          │  └─ SQLite (metadados e caminhos)         │
                                          │            │ subprocess (lista de args)   │
                                          │            ▼                              │
                                          │  FFmpeg / ffprobe   faster-whisper (CPU)  │
                                          └───────────────────────────────────────────┘
                                            Vídeos ficam em disco; o banco só guarda caminhos
```

## Decisões

| Tema | Decisão | Justificativa |
|---|---|---|
| Backend | Python 3.11+ e FastAPI | Ecossistema de áudio/ML local; OpenAPI automático para a API documentada. |
| Frontend | React + TypeScript + Vite, sem biblioteca de UI | Poucas dependências; tipagem do contrato com a API. |
| Banco | SQLite com `sqlite3` da biblioteca padrão e migrações numeradas | Uso local; sem ORM para reduzir dependências. Guarda metadados e caminhos, nunca vídeos. |
| Tarefas | Fila em processo com um trabalhador, estado em SQLite | Sem Celery/Redis/Docker. Estados: aguardando, em andamento, concluída, cancelada, com erro. |
| Vídeo | FFmpeg/ffprobe externos | Padrão da área; sem dependência Python pesada. |
| Áudio | Envelope de volume via filtros `astats`/`ametadata` do FFmpeg | Sem NumPy; progresso real pelo `-progress`. |
| Cenas | Filtro `select='gt(scene,…)'` do FFmpeg | Sem PySceneDetect (dependência a menos). |
| Transcrição | faster-whisper (opcional, CPU) ou whisper.cpp (experimental) | CTranslate2 não tem backend AMD no Windows; só trechos candidatos são transcritos por padrão. |
| Textos | Regras locais | Gratuito, sem enviar conteúdo para fora; só usa fatos conhecidos. |
| Distribuição | Uma porta: o backend serve a interface compilada | Simples de iniciar e encerrar. Em desenvolvimento, Vite faz proxy de `/api`. |

Descartados por ora: Electron/Tauri (complexidade sem necessidade), Celery/Redis e Docker (serviço persistente), modelos de visão para ler
o kill feed (pesado e sem validação).

## Sistema de tarefas

- Cada tarefa tem tipo, estado, mensagem de erro útil e **progresso só quando há informação real**: `-progress` do FFmpeg (tempo processado ÷ duração
  conhecida) ou janelas transcritas ÷ janelas totais. Sem isso o campo fica `NULL` e a interface mostra uma barra indeterminada, sem percentual.
- Cancelamento: sinaliza o subprocesso, o job lança `JobCancelled`, e a pasta temporária da tarefa é removida **antes** de publicar o estado final.
- Tarefas interrompidas por um fechamento do app são marcadas como com erro na próxima inicialização (nunca “retomadas” de forma fingida).
- Tarefas pesadas só começam por ação explícita (análise, renderização, coletas do radar).

## Pipeline de análise

1. `ffprobe` na importação: duração, resolução, fps, codecs, faixas de áudio.
2. Envelope de volume (RMS por janela de 0,5 s) → normalização pela mediana/p95 **da própria gravação**.
3. Opcional: mudanças de cena (2 fps, 320 px).
4. Picos → janelas candidatas (antes/depois do pico configuráveis, distância mínima entre picos).
5. Opcional: transcrição **só das janelas** (nível Padrão/Detalhado) ou de tudo em blocos de 5 min (Completo).
6. Pontuação explicável por critérios (pesos configuráveis); sobreposições são suprimidas; candidatos já revisados são preservados.

Níveis: **Leve** (áudio), **Padrão** (+ transcrição dos candidatos, modelo base), **Detalhado** (+ cenas, modelo small), **Completo** (transcreve tudo).

### Limitações assumidas

- Pico de áudio **não** significa jogada importante: é uma pista, combinada com fala e cenas.
- Não identifica aces/clutches pela imagem nem lê o kill feed. O tipo do momento é um palpite por palavras na fala; o usuário confirma.
- A pontuação é uma soma ponderada de sinais exibidos ao usuário; não é probabilidade de viralização. A confiança mede a **concordância entre sinais**.
- O feedback (aprovar/rejeitar/resultado) ajusta no máximo ±10 pontos por tipo de momento.

## Renderização vertical

Layouts: **blur** (gameplay inteiro sobre fundo desfocado — padrão, não corta o HUD), **solid** (cor sólida) e **fill** (preenche e corta as laterais, com foco ajustável).
Recorte manual opcional. Nunca há zoom automático. Parâmetros validados (resolução par, CRF, preset, bitrate, fps, volume, loudnorm, fade).
Encoders: `libx264` (padrão), `h264_amf` (AMD), `h264_nvenc`, `h264_qsv`; só os listados pelo FFmpeg local são aceitos. Legendas em ASS (filtro `ass`),
com destaque da palavra falada. A saída é gravada em `.part` e renomeada ao final; falha ou cancelamento removem o `.part`.

## Radar de tendências

Coletores oficiais (YouTube Data API com a chave no cabeçalho, Twitch Helix com credenciais do app) → itens com fonte/data → `analyzer` puro que gera
tendências separando **observado / estimado / hipótese**. Confiança por tamanho de amostra, nunca acima de “média”. Cada coleta é um registro datado;
a comparação com a coleta anterior só é feita com a mesma consulta e amostra mínima.

## Estrutura de diretórios

```
backend/vcs/
  main.py config.py security.py db.py repos.py models.py     # base
  jobs/        fila e execução de subprocessos
  media/       ffmpeg, extração de sinais, transcrição, legendas, render
  analysis/    sinais, pontuação, pipeline
  radar/       YouTube, coletas, analisador
  integrations/twitch.py   copywriting/   recommendations.py   reports.py
  api/         rotas (system, settings, jobs, recordings, imports, analysis,
               candidates, clips, publications, ideas, radar, library)
frontend/src/  pages/ components/ api/ lib/
scripts/       setup / start / stop / doctor (PowerShell) e CI
```

## Testes

- Backend (pytest): funções puras, API, e ponta a ponta com FFmpeg real em vídeos sintéticos gerados no teste (análise, cenas, render nos três layouts, streaming com Range).
- Frontend (Vitest): formatação, cliente da API, componentes de tarefa/progresso; checagem de tipos e build de produção.
- CI (GitHub Actions): pytest no Linux e no Windows, frontend, e um teste que executa `setup.ps1`, inicia o app, confere API/interface e o encerra.
- **Não coberto**: gravações reais do Valorant, GPU AMD (`h264_amf`), transcrição com modelos reais, chamadas reais às APIs (usam transporte simulado nos testes).
