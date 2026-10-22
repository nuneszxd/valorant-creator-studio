# Segurança e privacidade

O que o código garante e como cada item é verificado. “Teste” = coberto por teste automático; “Revisão” = verificado por leitura, sem teste automático.

## Modelo de ameaça

Aplicativo pessoal, local. Riscos considerados: (1) páginas abertas no navegador chamando a API local (CSRF, DNS rebinding); (2) arquivos de mídia
malformados; (3) entradas da API levando a leitura/escrita fora do esperado ou a execução de comandos; (4) vazamento de credenciais; (5) envio de
mídia privada a terceiros.

## Garantias

| Área | Garantia | Verificação |
|---|---|---|
| Rede | Servidor só em `127.0.0.1`; outros endereços exigem `VCS_ALLOW_NON_LOCAL=1` explícito | Teste |
| Rede | Cabeçalho `Host` precisa ser local (anti DNS rebinding) | Teste |
| Rede | Escritas (POST/PUT/PATCH/DELETE) com `Origin` estranho ou `Sec-Fetch-Site: cross-site` são recusadas (anti CSRF); CORS restrito à origem local | Teste |
| Rede | Qualquer requisição marcada pelo navegador como `Sec-Fetch-Site: cross-site` é recusada (inclusive GET: um site não consegue embutir `<video>`/`<img>` da API); caminhos com `\` ou `//` são recusados (evita acesso a compartilhamentos de rede no Windows pela rota de arquivos estáticos) | Teste |
| Rede | Respostas levam `X-Frame-Options: DENY` e `frame-ancestors 'none'` (sem clickjacking) | Teste |
| Rede | A origem do servidor de desenvolvimento (`localhost:5173`) só é confiável com `VCS_DEV=1`; a página Swagger (CDN) só liga com `VCS_DEV=1`/`VCS_API_DOCS=1` | Teste |
| Rede | Sem telemetria; saída de rede só para APIs oficiais habilitadas (Twitch, YouTube) | Revisão |
| Execução | O caminho do `whisper-cli` (executado de fato) precisa ter “whisper” no nome e o modelo precisa ser `.bin`/`.gguf` | Teste |
| Mídia | ffmpeg/ffprobe rodam com `-protocol_whitelist file` nas entradas: um arquivo de mídia malicioso não consegue abrir URLs ou outros protocolos | Teste (os comandos) e revisão |
| Arquivos | Caminhos importados: absolutos, existentes, arquivo, extensão de vídeo; caminhos de rede (UNC) recusados | Teste |
| Arquivos | O arquivo importado é referenciado, nunca copiado; remover da biblioteca não apaga o original | Teste |
| Arquivos | Limpeza só apaga arquivos que o app registrou (inclusive os `.part` de renderizações interrompidas; nunca varre pastas), exige `confirm=true`, e **nunca** um caminho de gravação original (comparação por caminho real, sem diferenciar maiúsculas no Windows) | Teste |
| Arquivos | Vídeos servidos só por ID registrado (sem caminho vindo da URL), com suporte a Range | Teste |
| Comandos | FFmpeg/ffprobe/whisper-cli/seletor de arquivos são chamados com **lista de argumentos** (sem shell). A API só aceita parâmetros de um conjunto fechado e validado (encoder, preset, resolução par, cores `#RRGGBB`, fonte com caracteres seguros) | Teste (validação dos parâmetros) e revisão (ausência de shell) |
| Comandos | Texto de legenda é higienizado (sem `{ } \`) antes de virar ASS | Teste |
| Credenciais | Chaves só em `.env`/ambiente; a API e a interface só informam “configurada/não configurada”; o PATCH de configurações recusa campos desconhecidos | Teste |
| Credenciais | Chave do YouTube vai no cabeçalho (não na URL); logs do `httpx` são silenciados; formatador de logs mascara tokens/chaves | Teste (cabeçalho e máscara) e revisão (silêncio do `httpx`) |
| Privacidade | Vídeos, áudios, transcrições e banco ficam na máquina; transcrição usa modelos locais (download do modelo só com consentimento) | Revisão |
| Repositório | `.gitignore` bloqueia vídeos, áudios, bancos, logs, modelos, temporários e segredos; fixtures de teste são geradas em tempo de execução | Revisão |

## Permissões e acessos usados

| Acesso | Para quê | Quando |
|---|---|---|
| Leitura de vídeos escolhidos | Importar e analisar | Sob ação do usuário |
| Escrita em `data/` e na pasta de saída | Banco, temporários, cortes, prévias, logs | Durante análise/exportação |
| Execução de FFmpeg/ffprobe | Probe, áudio, cenas, render | Sob ação do usuário |
| Janela de seleção de arquivo (tkinter, processo separado) | Escolher arquivo/pasta | Sob ação do usuário |
| Rede para Twitch/YouTube | Dados de VOD por link, radar | Somente se houver credenciais e o usuário disparar |
| Download de modelo de transcrição (Hugging Face, via faster-whisper) | Primeira transcrição | Somente com a caixa de consentimento marcada |

## O que este modelo NÃO protege

O aplicativo não tem login: **qualquer programa rodando na sua conta do Windows** (ou outro usuário da mesma máquina que alcance `127.0.0.1`) pode
chamar a API, e isso equivale ao que esse programa já poderia fazer com a sua conta. As proteções acima servem para impedir que **páginas web**
e **outros sites** usem o aplicativo. Não exponha a porta na rede (o servidor recusa endereços não locais).

## Fora do escopo

Contornar DRM/autenticação/limites de plataformas; coleta de dados privados de terceiros; exposição à internet; uso multiusuário.
Antes de publicar cortes, revise o áudio: música protegida pode gerar silenciamento ou bloqueio.
