# Segurança e privacidade

Requisitos e decisões de projeto. Eles descrevem o que o código **deve** garantir; cada item será marcado como verificado quando houver teste ou revisão correspondente.

## Modelo de ameaça

Aplicativo de uso pessoal, executado localmente. Os riscos principais são:

1. Outra página aberta no navegador chamando a API local (CSRF, DNS rebinding).
2. Arquivos de mídia maliciosos ou malformados explorando o parser do FFmpeg.
3. Entradas da API (caminhos, nomes, parâmetros) levando a leitura/escrita fora das pastas esperadas ou a execução de comandos.
4. Vazamento de credenciais (Twitch, YouTube) em código, logs ou no repositório público.
5. Envio de vídeo ou áudio privados a serviços externos sem consentimento.

## Requisitos

### Rede

- O servidor escuta apenas em `127.0.0.1` por padrão. Nada de `0.0.0.0`, túnel, proxy reverso ou abertura automática de portas.
- CORS restrito à origem do frontend local; validação do cabeçalho `Host` para mitigar DNS rebinding.
- Ações que alteram estado exigem `Content-Type: application/json`. Um token de sessão por execução será avaliado na etapa 1.
- Conexões de saída apenas para APIs oficiais habilitadas pelo usuário (Twitch, YouTube), nunca para enviar mídia.
- Sem telemetria.

### Arquivos e caminhos

- Caminhos recebidos pela API são resolvidos (`resolve()`) e validados contra raízes permitidas: pasta de trabalho, pasta de saída e os arquivos que o usuário selecionou explicitamente.
- Gravações importadas são referenciadas por caminho, sem cópia desnecessária. O usuário configura as pastas de trabalho e de saída.
- Arquivos importados são entrada **não confiável**: validação com ffprobe, timeouts, sem execução de conteúdo.
- Limpeza só apaga arquivos criados pelo próprio aplicativo na pasta de trabalho, com confirmação explícita. Originais nunca são apagados sem autorização explícita.

### Execução de comandos

- FFmpeg/ffprobe são chamados com lista de argumentos (sem `shell=True`) e com `-nostdin`. Caminhos de arquivo entram como argumentos separados, e nunca como texto de comando.
- A interface não aceita comandos nem argumentos livres do FFmpeg. Os parâmetros expostos são um conjunto fechado e validado (resolução, CRF, preset, etc.).
- O binário usado vem de configuração local ou do `PATH`, nunca de um parâmetro da API.

### Credenciais

- Ficam fora do código: arquivo `.env` local (ignorado pelo Git) ou armazenamento do sistema operacional. O repositório só tem [.env.example](../.env.example), com valores ilustrativos.
- Tokens nunca são registrados em logs nem retornados pela API; logs mascaram segredos.
- Escopos OAuth da Twitch: o mínimo necessário, documentado na etapa 9.

### Dados e privacidade

- Vídeos, áudios, transcrições e o banco ficam apenas na máquina do usuário.
- Enviar conteúdo a qualquer serviço externo exige ação e consentimento explícitos, por operação, com aviso de custo quando houver.
- O [.gitignore](../.gitignore) bloqueia vídeos, áudios, bancos, logs, modelos, temporários e segredos. Antes de cada push, os arquivos a enviar são conferidos.

## Permissões e acessos que o aplicativo usa

| Acesso | Para quê | Quando |
|---|---|---|
| Leitura de arquivos de vídeo escolhidos pelo usuário | Importar e analisar | Sob ação do usuário |
| Escrita na pasta de trabalho e de saída | Temporários, banco, cortes exportados | Durante análise e exportação |
| Execução de FFmpeg/ffprobe locais | Probe, extração de áudio, renderização | Sob ação do usuário |
| Rede para APIs oficiais (Twitch, YouTube) | Importar VOD por link, radar de tendências | Somente se habilitado e configurado |

## Fora do escopo

- Contornar DRM, autenticação, limites de acesso ou restrições de plataformas.
- Coleta de dados privados de terceiros.
- Exposição do aplicativo à internet ou uso multiusuário.
