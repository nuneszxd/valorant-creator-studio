# Valorant Creator Studio

![CI](https://github.com/nuneszxd/valorant-creator-studio/actions/workflows/ci.yml/badge.svg)

Aplicativo **local** para transformar lives e VODs de Valorant em vídeos curtos verticais (TikTok, Reels, YouTube Shorts) e orientar a
criação de conteúdo com base em dados reais e resultados mensuráveis. Backend em Python (FastAPI + SQLite + FFmpeg) e interface em React + TypeScript.

> **Status: versão 0.1, funcional e testada de forma automática com vídeos sintéticos** (Windows e Linux, no CI do GitHub).
> Ainda **não** foi validada com gravações reais de Valorant, com GPU AMD nem com modelos de transcrição reais — isso depende do seu teste.
> Veja [docs/USAGE.md](docs/USAGE.md).

## Começar (Windows)

1. Instale **Python 3.12**, **Node.js LTS** e **FFmpeg (build full)** — detalhes em [docs/USAGE.md](docs/USAGE.md).
2. `git clone https://github.com/nuneszxd/valorant-creator-studio.git`
3. `setup.bat` (uma vez) e depois `start.bat`.

## O que faz

| Área | O que existe |
|---|---|
| **Importação** | Arquivo local (só o caminho é guardado) e leitura de dados de VOD da Twitch pelo link (API oficial; **não baixa VODs**, orienta o download autorizado) |
| **Análise local** | Volume do áudio, picos, mudanças de cena (opcional), transcrição local com faster-whisper (CPU) ou whisper.cpp (experimental), em níveis escolhidos por você |
| **Candidatos** | Lista com pontuação **explicável**, tipo do momento sugerido, confiança, trecho da fala; assistir, ajustar, aprovar/rejeitar, marcar resultado; o feedback ajusta levemente as próximas pontuações |
| **Editor** | Corte 9:16 em MP4: gameplay inteiro com fundo desfocado/sólido, ou preencher; recorte manual; legendas editáveis com destaque da palavra falada; ajuste de áudio; prévia rápida; encoders libx264 (CPU) e h264_amf (AMD) |
| **Textos** | Ganchos, títulos, legenda, hashtags, descrição, capa e chamada para comentários por regras locais (só usam fatos conhecidos) |
| **Biblioteca** | Filtros por jogo, mapa, agente, tipo, data, estado e pontuação; limpeza de arquivos gerados com confirmação |
| **Métricas** | Cadastro manual de publicações e comparação por formato/tema/gancho/duração, com ressalvas de amostra |
| **Radar** | YouTube Data API e clipes da Twitch (oficiais) + observações manuais (TikTok); fonte, data e limitações em cada item; dado observado, estimativa e hipótese separados; histórico das coletas |
| **Perfil e ideias** | Perfil do canal; sugestões de ideias explicadas pelos motivos; esqueleto de roteiro |

## Princípios

- **Local primeiro.** O servidor só escuta em `127.0.0.1`; nada é enviado para fora sem a sua ação.
- **Nada de dados inventados.** Funcionalidade indisponível aparece como indisponível. Progresso só aparece em percentual quando é real.
- **Dado observado ≠ estimativa ≠ hipótese**, e a confiança nunca passa de “média”.
- **Sem scraping proibido** nem contorno de autenticação ou limites de plataformas.
- **Nada é apagado sem confirmação**; gravações originais nunca são apagadas.

## Limites importantes

- A detecção de momentos é por áudio/fala (e cenas): **não lê o kill feed**. São sugestões para revisão, não um detector de aces.
- A pontuação ordena a revisão; **não prevê viralização**.
- A Twitch não permite baixar VODs pela API; o TikTok não oferece API pública de tendências para este uso.
- Lives costumam ter música protegida: revise o áudio antes de publicar (pode ser silenciado/bloqueado).

## Documentação

- [Guia de uso e instalação](docs/USAGE.md)
- [Arquitetura](docs/architecture.md)
- [Segurança e privacidade](docs/security.md)
- [Fontes de dados do radar e da importação de VODs](docs/data-sources.md)
- API interativa (com o app rodando): `http://127.0.0.1:8000/api/docs`

## Estrutura

```
backend/    FastAPI, SQLite, fila de tarefas, FFmpeg, análise, radar (Python)
frontend/   React + TypeScript (Vite)
docs/       guias e decisões
scripts/    setup/start/stop/doctor (PowerShell) e scripts de CI
```

## Testes

Os testes rodam automaticamente no GitHub Actions: pytest no Linux e no Windows (com FFmpeg real e vídeos sintéticos gerados no teste),
checagem de tipos, testes e build da interface, e um teste que executa o `setup.ps1` e inicia o aplicativo num Windows limpo.
Nenhum vídeo real é versionado.

## Direitos autorais e termos das plataformas

- Use o aplicativo apenas com conteúdo seu ou que você tenha direito de usar.
- O acesso a dados de plataformas (Twitch, YouTube, TikTok) segue os termos e as APIs oficiais de cada uma.

## Licença

[MIT](LICENSE)
