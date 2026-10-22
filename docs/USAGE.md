# Guia de uso (Windows)

Tudo roda **no seu computador**: o servidor só escuta em `127.0.0.1`, e nenhum vídeo ou áudio é enviado para fora.
Este guia foi escrito para o seu PC pessoal (GPU AMD).

## 1. O que instalar

| Programa | Para quê | Obrigatório? | Como instalar |
|---|---|---|---|
| **Python 3.11 ou superior** (recomendo 3.12) | Backend | Sim | `winget install --id Python.Python.3.12 -e` ou o instalador de python.org (marque **Add python.exe to PATH**) |
| **Node.js LTS** | Compilar a interface (uma vez) | Sim | `winget install --id OpenJS.NodeJS.LTS -e` ou nodejs.org |
| **FFmpeg (build completa / “full”)** | Analisar, legendar e renderizar vídeos | Sim | `winget install --id Gyan.FFmpeg -e` ou o download “release full” em gyan.dev/ffmpeg/builds |
| Git | Baixar o projeto | Já tem | — |
| faster-whisper | Transcrição local | Opcional | `setup.bat -WithTranscription` |

Depois de instalar, **feche e abra o terminal de novo** para o PATH atualizar. Se o `winget` não existir ou o nome do pacote falhar,
use os downloads manuais. Para o FFmpeg manual: extraia, e ou adicione a pasta `bin` ao PATH, ou escreva o caminho completo em
`VCS_FFMPEG_PATH` / `VCS_FFPROBE_PATH` no arquivo `.env`.

> Use uma build **full** do FFmpeg: ela inclui o filtro `ass` (legendas gravadas no vídeo) e o encoder de GPU AMD (`h264_amf`).

## 2. Baixar e instalar o projeto

```powershell
git clone https://github.com/nuneszxd/valorant-creator-studio.git
cd valorant-creator-studio
setup.bat
```

O `setup.bat` (pode levar alguns minutos na primeira vez, baixa pacotes da internet):

1. cria um ambiente Python isolado em `.venv`;
2. instala as dependências do backend;
3. instala e compila a interface (`frontend/dist`);
4. cria o arquivo `.env` a partir de `.env.example`;
5. roda `doctor` e mostra o que está OK e o que falta.

Para incluir a transcrição local: `setup.bat -WithTranscription` (instala o faster-whisper; o **modelo** só é baixado depois, com a sua
confirmação na tela de análise).

**Resultado esperado:** uma lista com `OK` para Python, FFmpeg, ffprobe e libx264, e talvez `AVISO` para itens opcionais.
Se algo aparecer como `FALHA`, corrija e rode `doctor.bat`.

## 3. Configurar (`.env`, opcional)

O arquivo `.env` (já criado) fica na pasta do projeto e **não é enviado ao GitHub**. As chaves ficam só nele — o aplicativo nunca pede
nem mostra chaves na interface.

| Variável | Para quê |
|---|---|
| `VCS_PORT` | Porta local (padrão 8000) |
| `VCS_DATA_DIR` | Pasta de trabalho (banco, modelos, temporários, logs) — padrão `data/` |
| `VCS_OUTPUT_DIR` | Onde os cortes exportados são salvos (também dá para escolher em Configurações) |
| `VCS_FFMPEG_PATH`, `VCS_FFPROBE_PATH` | Só se o FFmpeg não estiver no PATH |
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | Ler dados de um VOD pelo link e clipes públicos (opcional) |
| `YOUTUBE_API_KEY` | Radar de tendências do YouTube (opcional) |

**Twitch (opcional):** em dev.twitch.tv/console crie um aplicativo (a Twitch exige a verificação em duas etapas ativada na sua conta),
tipo *Confidential*, com a URL de redirecionamento `http://localhost`. Copie o *Client ID* e gere um *Client Secret*. O aplicativo usa só o fluxo de
credenciais do app (dados públicos): não faz login na sua conta e **não baixa VODs**.

**YouTube (opcional):** no Google Cloud Console crie um projeto, ative a **YouTube Data API v3** e crie uma **chave de API** (restrinja-a a essa API).
A cota padrão é pequena (100 buscas por dia); o aplicativo mostra quanto já usou e recusa coletas que estourariam o limite.

Depois de editar o `.env`, reinicie o aplicativo.

## 4. Iniciar e encerrar

- **Iniciar:** `start.bat` — abre o navegador em `http://127.0.0.1:8000`.
- **Encerrar:** feche a janela / `Ctrl+C`, ou o botão **Configurações > Sistema > Encerrar o aplicativo**, ou `stop.bat`.
- Para ver o estado do ambiente: `doctor.bat` (e `doctor.bat -Deep` para testar a codificação de verdade, inclusive o encoder AMD).

Se aparecer “A porta 8000 já está em uso”, feche a outra janela do aplicativo ou use `start.bat -Port 8010`.

## 5. Primeiro uso, passo a passo

1. **Configurações > Perfil do canal:** rank atual/desejado, agentes, formatos, duração desejada, tipos de momento que prioriza.
2. **Importar vídeos:**
   - *Arquivo local:* escolha o arquivo (ou cole o caminho completo) e informe mapa/agente se quiser. Nada é copiado.
   - *Link da Twitch:* cole o link do VOD para ver os dados e as instruções. **A Twitch não permite baixar VOD pela API:** baixe o seu
     próprio VOD pelo *Painel do Criador > Conteúdo > Video Producer > Baixar* e importe o arquivo.
3. **Gravações e análise:** abra a gravação e escolha o nível:
   - **Leve** — só áudio. Comece por aqui para testar (rápido, sem downloads).
   - **Padrão** — áudio + transcrição só dos trechos candidatos.
   - **Detalhado** — inclui detecção de cenas e modelo maior.
   - **Completo** — transcreve tudo (muito lento em CPU).
   A análise só começa quando você clica em *Iniciar análise*, roda uma tarefa por vez e pode ser cancelada.
4. **Candidatos a cortes:** assista, ajuste início/fim, confirme o tipo, aprove ou rejeite. Veja “Por que este trecho foi sugerido”.
5. **Editor:** *Criar corte e abrir no editor*. Ajuste enquadramento, legendas, áudio e exportação. Use **Prévia rápida** (540×960) e depois **Renderizar MP4**.
6. **Textos:** na aba *Textos* do editor gere ganchos, títulos, legenda e hashtags (informe antes os *fatos do corte*, na aba Corte).
7. **Métricas:** cadastre cada vídeo publicado e acompanhe a comparação (com ressalvas de amostra).
8. **Radar de tendências:** colete dados do YouTube/Twitch ou registre observações manuais (TikTok).
9. **Ideias e roteiros:** gere sugestões explicadas e salve as que quiser.

## 6. Placa AMD: o que muda

- **Transcrição:** o faster-whisper **não usa a GPU AMD no Windows**; roda na CPU. Por isso o nível *Padrão* transcreve apenas os
  trechos candidatos. Modelos maiores = mais lento.
- **whisper.cpp com Vulkan (opcional, experimental):** se você conseguir uma build do `whisper-cli.exe` com Vulkan e um modelo `.bin`,
  escolha *whisper.cpp* em Configurações > Transcrição e informe os dois caminhos. O aplicativo **não baixa nem compila** isso e esse caminho
  **não foi validado** em GPU AMD.
- **Renderização:** `libx264` (CPU) é o padrão e dá a melhor qualidade por tamanho. O `h264_amf` usa a GPU AMD e costuma ser mais rápido,
  porém com qualidade um pouco pior para o mesmo tamanho. Teste em Configurações > Sistema (*testar*) ou com `doctor.bat -Deep`.
  Se falhar, volte para `libx264`.

## 7. Onde ficam os arquivos

| O quê | Onde |
|---|---|
| Banco SQLite (metadados e caminhos) | `data/app.db` |
| Cortes exportados | Pasta de saída (Configurações) — padrão `data/output/` |
| Prévias rápidas | `data/previews/` |
| Modelos de transcrição | `data/models/` |
| Temporários de tarefas | `data/work/` (apagados ao fim de cada tarefa) |
| Logs | `data/logs/app.log` (chaves e tokens são mascarados) |

Os vídeos originais **nunca** são copiados nem apagados. Em *Biblioteca > Limpeza de arquivos* você apaga, com confirmação, só o que o
aplicativo gerou.

## 8. Algo deu errado? Como me enviar o erro

Mande, nesta ordem (copie e cole o texto; não precisa ocultar nada, nenhum deles mostra chaves):

1. A saída completa de `doctor.bat` (ou `doctor.bat -Deep`).
2. A mensagem de erro exibida na tela / na tarefa (cartão vermelho em *Tarefas*, em *Gravações* ou no *Editor*).
3. As últimas ~50 linhas de `data\logs\app.log`.
4. Se for um problema visual: um print e o texto do console do navegador (`F12` > *Console*).

| Mensagem | O que fazer |
|---|---|
| “FFmpeg não encontrado” | Instale o FFmpeg full e reabra o terminal, ou defina `VCS_FFMPEG_PATH`. |
| “Legendas não aplicadas: … filtro 'ass'” | Troque por uma build **full** do FFmpeg. |
| “O modelo de transcrição … ainda não foi baixado” | Marque *Permitir baixar o modelo* na análise (download único, depende da internet). |
| “faster-whisper não instalado” | Rode `setup.bat -WithTranscription` ou use o nível *Leve*. |
| Vídeo não toca no navegador | Normal com HEVC/MKV; a análise e a renderização funcionam do mesmo jeito. Use a prévia renderizada. |
| `h264_amf` falhou | Use `libx264`; atualize o driver da GPU e rode `doctor.bat -Deep`. |

## 9. Modo desenvolvimento (opcional)

Defina `VCS_DEV=1` no `.env` (confia na origem do servidor de desenvolvimento e liga a documentação interativa) e então:

```powershell
.venv\Scripts\python.exe -m vcs serve         # API em http://127.0.0.1:8000 (docs interativas em /api/docs)
cd frontend; npm run dev                      # interface em http://127.0.0.1:5173 com proxy para a API
```

O contrato OpenAPI fica sempre disponível em `http://127.0.0.1:8000/api/openapi.json`. A página interativa (`/api/docs`, Swagger) carrega scripts
de uma CDN e por isso só liga com `VCS_DEV=1` ou `VCS_API_DOCS=1`.

Testes: `setup.bat -WithDev` e depois `.venv\Scripts\python.exe -m pytest backend` e, em `frontend/`, `npm test`.

## 10. Limitações (leia antes de confiar nos resultados)

- A detecção de momentos usa **áudio, fala e (opcionalmente) cenas**. Ela **não** lê o kill feed nem reconhece aces ou clutches pela imagem:
  são sugestões para você revisar, e o tipo do momento é um palpite por palavras da fala.
- A pontuação ordena a sua revisão; **não é previsão de viralização**.
- O radar usa só fontes oficiais (YouTube, Twitch). **TikTok** não tem coleta automática: use observações manuais.
- Ganchos falados, edição e legendas de vídeos de terceiros não são acessíveis pelas fontes; o radar analisa títulos, hashtags, duração e contagens públicas.
- Tudo foi verificado por testes automáticos em vídeos **sintéticos** (CI do GitHub, Windows e Linux). Gravações reais do Valorant,
  a GPU AMD e a transcrição com modelos reais ainda dependem do seu teste.
