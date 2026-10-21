# Valorant Creator Studio

Aplicativo **local** para transformar lives e VODs de Valorant em vídeos curtos (TikTok, Reels, YouTube Shorts) e orientar a criação de conteúdo com base em dados reais e resultados mensuráveis.

> **Status: etapa 0 - esqueleto e documentação.**
> Nenhuma funcionalidade foi implementada ainda e nada foi testado em execução. Este repositório contém, por enquanto, apenas a estrutura, as decisões de arquitetura e as regras de segurança. As seções abaixo descrevem o que está **planejado**, não o que já existe.

## Objetivo

Ajudar um criador pequeno de Valorant a aproveitar melhor o conteúdo que já produz:

- importar gravações (arquivo local ou link de VOD da Twitch, quando a API permitir);
- encontrar candidatos a cortes com sinais explicáveis (áudio, fala, mudança de cena);
- revisar, ajustar e exportar cortes verticais 9:16 em MP4 com FFmpeg;
- sugerir ganchos, títulos, legendas e hashtags por regras locais;
- registrar o desempenho das publicações e comparar formatos, temas, ganchos e duração;
- pesquisar tendências do nicho em **fontes legítimas**, informando origem, data e limitações.

Não há promessa de viralização. As pontuações são critérios explicáveis para priorizar a revisão, não probabilidades.

## Princípios

- **Local primeiro.** Servidor apenas em `127.0.0.1`; vídeos e áudios nunca saem da máquina sem consentimento explícito.
- **Sem dados falsos.** Funcionalidade pendente aparece como pendente; modo de demonstração, se existir, é identificado como tal.
- **Sem progresso inventado.** Percentuais só são exibidos quando há informação real.
- **Dados observados ≠ estimativas ≠ hipóteses.** O radar de tendências separa os três e registra fonte, data da consulta e limitações.
- **Nada de scraping proibido** nem contorno de autenticação, limites de acesso ou restrições de plataforma.
- **Nada é apagado sem confirmação explícita**, e nunca os arquivos originais sem autorização.

## Roadmap

Cada etapa termina com uma validação no computador pessoal do autor antes da seguinte.

| Etapa | Conteúdo | Situação |
|---|---|---|
| 0 | Esqueleto do repositório, arquitetura, segurança, avaliação das fontes de dados | pronto para revisão |
| 1 | Backend base: FastAPI, configuração, esquema SQLite, sistema de tarefas, testes | planejado |
| 2 | Casca do dashboard (React + TypeScript), navegação, estados das tarefas | planejado |
| 3 | Importação de arquivo local (ffprobe) e biblioteca | planejado |
| 4 | Análise (picos de áudio, cenas, transcrição) e ranking explicável de cortes | planejado |
| 5 | Revisão de cortes, editor e renderização vertical com FFmpeg | planejado |
| 6 | Ganchos, títulos, legendas e hashtags (regras locais) | planejado |
| 7 | Registro de publicações e relatórios, com ressalvas sobre amostra | planejado |
| 8 | Perfil do criador e recomendações personalizadas | planejado |
| 9 | Radar de tendências e importação de VOD da Twitch (OAuth) | planejado |

## Documentação

- [Arquitetura](docs/architecture.md)
- [Segurança e privacidade](docs/security.md)
- [Fontes de dados do radar e da importação de VODs](docs/data-sources.md)

## Instalação e uso

Ainda não há o que instalar ou executar. As instruções de instalação, configuração, inicialização e encerramento serão adicionadas na etapa 1, junto com o primeiro código executável, e só passarão a constar aqui depois de validadas.

## Direitos autorais e termos das plataformas

- Use o aplicativo apenas com conteúdo seu ou que você tenha direito de usar.
- Lives costumam conter música e outros materiais protegidos; publicar cortes com esse áudio pode resultar em silenciamento ou remoção na plataforma de destino. O aplicativo não resolve isso: revise o áudio antes de publicar.
- O acesso a dados de plataformas (Twitch, YouTube, TikTok) segue os termos e as APIs oficiais de cada uma.

## Licença

[MIT](LICENSE)
