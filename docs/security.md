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
| Rede | Sem telemetria; saída de rede só para APIs oficiais habilitadas (Twitch, YouTube) | Revisão |
| Arquivos | Caminhos importados: absolutos, existentes, arquivo, extensão de vídeo; caminhos de rede (UNC) recusados | Teste |
| Arquivos | O arquivo importado é referenciado, nunca copiado; remover da biblioteca não apaga o original | Teste |
| Arquivos | Limpeza só apaga arquivos que o app registrou, exige `confirm=true`, e **nunca** um caminho de gravação original | Teste |
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

## Fora do escopo

Contornar DRM/autenticação/limites de plataformas; coleta de dados privados de terceiros; exposição à internet; uso multiusuário.
Antes de publicar cortes, revise o áudio: música protegida pode gerar silenciamento ou bloqueio.
