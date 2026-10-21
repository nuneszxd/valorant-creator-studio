# Fontes de dados do Radar de Tendências e da importação de VODs

Avaliação feita em **2026-10-21**, lendo documentação pública. Nenhuma chamada de API foi executada e nenhum código de integração existe ainda.

Cada afirmação abaixo tem uma marca:

- **Confirmado:** lido na página oficial indicada.
- **A confirmar:** não consegui verificar na fonte oficial nesta rodada. Será lido na etapa de implementação antes de qualquer código depender disso.
- **Fonte secundária:** vem de resumo de terceiros, e o texto oficial deve ser lido.

Termos, cotas e políticas mudam. Esta página é um ponto de partida datado, não uma garantia.

## Resumo

| Fonte | O que dá para obter de forma legítima | Decisão |
|---|---|---|
| Twitch API (Helix) | Metadados de VODs e clipes. **Não** há endpoint de download de VOD identificado. | Importar por link = validar e ler metadados; o arquivo vem de download autorizado feito pelo usuário. |
| YouTube Data API v3 | Busca pública e estatísticas públicas de vídeos, dentro de cota. | Usar no radar, com cota baixa e resultados tratados como amostra. |
| TikTok Creative Center | Nenhuma API pública documentada encontrada. | Sem automação. Pesquisa manual assistida. |
| TikTok Research API | Restrita a pesquisadores elegíveis. | Não aplicável a este projeto. |
| TikTok Display API | Vídeos públicos de uma conta que autorize o app. | Avaliar mais tarde para as métricas do **próprio** canal. Entrada manual continua sendo o caminho principal. |
| Instagram / Reels | Não avaliado nesta rodada. | Pendente. |
| Entrada manual | Tudo que o usuário observar ou exportar legitimamente. | Caminho principal e sempre disponível. |

## Twitch

**Confirmado** ([índice da referência da API](https://dev.twitch.tv/docs/api/reference/)): existem *Get Videos* ("informações sobre um ou mais vídeos publicados") e *Get Clips*. O índice também lista *Get Clips Download*, descrito como fornecedor de URLs para baixar arquivos de **clipes**. Não encontrei no índice um endpoint equivalente para baixar **VODs**.

**Confirmado** (ajuda da Twitch, [On-Demand Content on Twitch](https://help.twitch.tv/s/article/video-on-demand), via resultado de busca): o broadcaster pode baixar o próprio VOD pelo **Video Producer**. O armazenamento é de 60 dias para Partners, Prime e Turbo, 14 dias para Affiliates e 7 dias para os demais. A documentação de [Videos](https://dev.twitch.tv/docs/api/videos/) cita 14 dias para broadcasters comuns, o que conflita com a ajuda. Considero a página de ajuda a mais atual, mas isso precisa ser reconferido.

**Fonte secundária:** requisições ao endpoint de vídeos devem ser autenticadas com token de app ou de usuário. Filtrar por `user_id` e ordenar por visualizações é possível. Relatos em fórum indicam que `game_id` pode não vir nas respostas.

**A confirmar** (etapa 9): campos exatos de *Get Videos* (duração, visualizações, trechos silenciados), escopos OAuth necessários, restrições de *Get Clips Download* e termos do Developer Services Agreement sobre uso do conteúdo.

**Decisão para a importação por link:**

1. Validar o link e ler os metadados pela API oficial (título, duração, data, disponibilidade).
2. Se o VOD expirou, não está acessível ou exige autorização adicional, explicar o motivo.
3. Em qualquer caso, a alternativa é: o usuário baixa o próprio VOD pelo Video Producer (ou outro meio autorizado) e seleciona o arquivo local.
4. O aplicativo não tenta contornar autenticação, restrições ou limites de acesso.

## YouTube

**Confirmado** ([custo de cota](https://developers.google.com/youtube/v3/determine_quota_cost)): a alocação padrão é de **100 chamadas de `search.list` por dia**, em um balde próprio, mais **10.000 unidades por dia** para os demais métodos. `videos.list` e `channels.list` custam 1 unidade por chamada.

Uso previsto no radar: `search.list` com consulta sobre Valorant, filtros de região, idioma e duração, seguido de `videos.list` para ler estatísticas públicas. Isso gera dados **observados** (contagens públicas em um instante), com estas limitações:

- uma busca devolve uma amostra, não o universo de vídeos;
- distinguir Shorts de vídeos curtos comuns pode não ser confiável pela API (**a confirmar**);
- visualizações dependem da idade do vídeo, então comparações exigem considerar a data de publicação;
- a cota de 100 buscas por dia limita a frequência de atualização.

**A confirmar:** [Termos e políticas dos serviços de API do YouTube](https://developers.google.com/youtube/terms/developer-policies) (retenção e atualização de dados armazenados) e o uso da YouTube Analytics API, com OAuth, para as métricas do próprio canal.

## TikTok

**Creative Center.** Não encontrei nesta rodada uma API pública documentada para ele. Isso é ausência de evidência, não prova de inexistência. **Fonte secundária:** um resumo dos termos gerais do TikTok indica proibição de coleta automatizada (scraping, crawling, exportação) sem autorização. O texto oficial precisa ser lido antes de qualquer decisão diferente. Decisão atual: **nenhuma coleta automatizada**. O radar aceitará observações manuais (links, hashtags, notas e números que o usuário viu) registradas com data e origem.

**Research API.** **Confirmado** ([página oficial](https://developers.tiktok.com/products/research-api/)): acesso restrito a instituições acadêmicas, organizações sem fins lucrativos e pesquisadores verificados, para pesquisa não comercial, com aprovação (em torno de 4 semanas). Não se aplica a um criador individual.

**Display API.** **Confirmado** ([List Videos](https://developers.tiktok.com/doc/tiktok-api-v2-video-list) e [Video Object](https://developers.tiktok.com/doc/tiktok-api-v2-video-object)): o endpoint `POST /v2/video/list/` exige o escopo `video.list` e devolve os vídeos públicos de um usuário, em ordem decrescente de criação. O objeto de vídeo inclui `duration`, `view_count`, `like_count`, `comment_count` e `share_count`. **A confirmar:** se só funciona para a conta que autorizou, se exige revisão do app e quais fluxos de OAuth se aplicam a um app pessoal. Possível uso futuro: importar as métricas do **próprio** canal, mantendo a entrada manual como alternativa.

## Instagram e YouTube Shorts do próprio canal

Instagram/Reels: **não avaliado**. A API da Meta para contas profissionais pode oferecer métricas das próprias publicações, mas isso ainda não foi lido. Para Shorts, as métricas do próprio canal podem vir da YouTube Analytics API (**a confirmar**).

## Entrada manual e importação permitida

Sempre disponível, independentemente das APIs:

- links salvos de vídeos que o usuário considera referência;
- números que o usuário viu (visualizações, curtidas, etc.), com a data da observação;
- exportações de dados que o próprio usuário tem direito de obter;
- métricas das próprias publicações (ver etapa 7).

O aplicativo guarda **links e metadados**, nunca baixa nem armazena vídeos de terceiros.

## Registro de uma tendência

Cada item do radar terá:

1. tema ou formato observado;
2. fonte consultada e link, quando disponível;
3. data da consulta;
4. dados observados (cada número ligado a um item e a uma data de coleta);
5. relevância para o conteúdo do criador;
6. sugestão prática de vídeo;
7. nível de confiança;
8. limitações dos dados;
9. **tipo de evidência** de cada afirmação: *observado*, *estimativa* ou *hipótese*.

Regras:

- Nenhum número é exibido sem fonte e data de coleta.
- Nenhum conteúdo é chamado de "viral" sem evidência suficiente. Os critérios mínimos de amostra serão definidos e documentados na etapa 9.
- Atualizar o radar cria um novo registro datado, preservando os anteriores para consulta histórica.

## Próximas verificações

1. Ler a referência oficial completa de *Get Videos*, *Get Clips* e *Get Clips Download* e o Developer Services Agreement da Twitch.
2. Ler as políticas de desenvolvedor do YouTube e testar, no computador pessoal, a cota real de `search.list`.
3. Ler os termos de uso do TikTok For Business e do Creative Center, e os requisitos de revisão de app da Display API.
4. Avaliar a API da Meta para métricas de Reels.
