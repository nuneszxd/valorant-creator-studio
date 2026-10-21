# Arquitetura

Documento de decisões da etapa 0. Ele descreve o que está **proposto**; nada abaixo foi implementado ou testado ainda. As decisões podem mudar conforme os resultados das validações no computador pessoal.

## Visão geral

```
 Navegador (localhost)                Máquina do usuário
┌────────────────────┐   HTTP/JSON   ┌───────────────────────────────┐
│ React + TypeScript │ ────────────► │ FastAPI (127.0.0.1)           │
│ (dashboard)        │ ◄──────────── │  ├─ API REST documentada      │
└────────────────────┘  OpenAPI      │  │   (OpenAPI/Swagger)        │
                                     │  ├─ Fila de tarefas (em       │
                                     │  │   processo, persistida)    │
                                     │  ├─ Serviços de domínio       │
                                     │  └─ SQLite (metadados)        │
                                     │            │                  │
                                     │   subprocess (lista de args)  │
                                     │            ▼                  │
                                     │   FFmpeg / ffprobe            │
                                     │   faster-whisper (opcional)   │
                                     └───────────────────────────────┘
                                       Pasta de trabalho / saída
                                       (vídeos ficam no disco, não no banco)
```

## Decisões

| Tema | Decisão proposta | Justificativa |
|---|---|---|
| Backend | Python 3.11+ com FastAPI | Ecossistema de áudio/ML local; OpenAPI gerado automaticamente para a API documentada. |
| Frontend | React + TypeScript + Vite | Pedido do projeto; tipagem do contrato com a API. |
| Banco | SQLite | Uso local, sem serviço adicional. Guarda metadados, caminhos, histórico e métricas, nunca os vídeos. |
| Tarefas longas | Fila em processo, com estado persistido no SQLite | Evita Celery/Redis/Docker. Estados: aguardando, em andamento, concluída, cancelada, com erro. |
| Vídeo | FFmpeg e ffprobe, instalados pelo usuário | Padrão da área; sem dependência Python pesada para renderização. |
| Transcrição | faster-whisper, extra **opcional** | Roda localmente; modelos de tamanhos diferentes permitem ajustar à máquina. |
| Cenas | Filtro de cena do FFmpeg primeiro | PySceneDetect só entrará se o filtro se mostrar insuficiente, para evitar uma dependência a mais. |
| Textos (ganchos, títulos, hashtags) | Regras locais | Gratuito e sem enviar conteúdo para fora. IA externa só como opção explícita, com custos informados e aprovação. |
| Distribuição | Duas portas locais em desenvolvimento (API + Vite); na versão final, a API pode servir o frontend compilado | Simples de iniciar e de encerrar. |

Alternativas consideradas e descartadas por enquanto:

- **Electron/Tauri:** empacotamento desktop agora seria complexidade sem necessidade comprovada.
- **Celery + Redis:** exige serviço persistente; a fila em processo cobre o uso de um único usuário.
- **Docker:** não é necessário para uso local e exigiria aprovação.
- **Modelos de visão para detectar abates/HUD:** possível no futuro, mas pesado e sem validação; fora do escopo inicial.

## Sistema de tarefas

- Cada tarefa tem tipo, estado, mensagem de erro útil e, **somente quando há informação real**, progresso.
- Fontes reais de progresso previstas: `-progress` do FFmpeg (tempo processado / duração conhecida pelo ffprobe) e segmentos transcritos / duração do áudio. Sem isso, a interface mostra apenas o estado, sem percentual.
- Cancelamento: sinal ao subprocesso, seguido de limpeza dos temporários **criados pela própria tarefa**. Nunca apaga arquivos originais.
- Tarefas pesadas só começam por ação explícita do usuário.

## Pipeline de análise (planejado)

1. `ffprobe`: duração, resolução, taxa de quadros, streams.
2. Extração de áudio mono em pasta temporária da pasta de trabalho.
3. Envelope de volume ao longo do tempo (picos e mudanças).
4. Mudanças de cena (filtro do FFmpeg).
5. Transcrição com timestamps (opcional, escolha do nível de processamento).
6. Fusão dos sinais em janelas candidatas.
7. Pontuação explicável.

Todos os sinais guardam o timestamp na gravação original para localizar o trecho.

### Limitações assumidas

- Pico de áudio **não** significa jogada importante: é um sinal para investigar, combinado com fala e mudança de cena.
- Não é possível identificar com precisão todos os eventos do Valorant (clutches, aces, abates) só por áudio ou imagem. A revisão e a correção manual são parte do fluxo.
- A pontuação é uma soma ponderada de critérios exibidos ao usuário (intensidade de áudio, presença de fala, mudança de cena, clareza de contexto, adequação à duração desejada, preferências do criador). Os pesos são configuráveis. Não é probabilidade de viralização.
- O feedback do usuário (aprovar, rejeitar, marcar bom ou ruim) ajusta recomendações futuras de forma transparente.

### Níveis de processamento (planejado)

O usuário escolhe o nível antes de iniciar, com aviso prévio de disco, memória, tempo e download de modelo:

- **Leve:** só áudio e cenas, sem transcrição.
- **Padrão:** transcrição com modelo pequeno.
- **Detalhado:** modelo maior; mais lento e com mais memória e disco.

Tamanhos de modelos e requisitos reais serão confirmados na etapa 4 antes de serem documentados como fato.

## Renderização vertical (planejado)

Gameplay de Valorant é horizontal e o HUD (minimapa, feed de abates, vida e habilidades) ocupa as bordas, então recortar de forma agressiva perde informação. Opções previstas:

1. **Gameplay inteiro com fundo desfocado** (padrão; não corta nada).
2. **Gameplay inteiro com fundo sólido.**
3. **Reenquadramento manual**, com região escolhida pelo usuário e zoom opcional. Nunca é automático.

Resolução, duração, CRF/qualidade, preset de velocidade, estilo e posição de legenda e ajuste de áudio serão parâmetros configuráveis, com explicação do efeito em qualidade, tamanho e velocidade. A saída é MP4, e a renderização só ocorre sob solicitação.

## Estrutura de diretórios prevista

```
valorant-creator-studio/
├─ backend/            # FastAPI, serviços, fila, acesso ao SQLite, testes (etapa 1)
├─ frontend/           # React + TypeScript (etapa 2)
├─ docs/               # decisões, segurança, fontes de dados
├─ .env.example
└─ data/               # criada em tempo de execução; ignorada pelo Git
```

## Testes

- Backend: pytest, com fixtures de mídia **sintéticas** geradas em tempo de teste (FFmpeg/lavfi). Nenhum vídeo real é versionado.
- Frontend: Vitest e Testing Library.
- Os testes que exigem instalação, FFmpeg ou processamento são escritos aqui e executados no computador pessoal do autor. Cada entrega informa claramente o que foi escrito, o que foi revisado estaticamente e o que foi realmente executado.
