# PROGRESS

| Fase | Escopo | Estado |
|---|---|---|
| **0** | Fundação e esqueleto | ✅ concluída |
| **1** | Motor 2 — Cérebro (matching serviço → CNAE) | ✅ concluída |
| **2** | Motor 1 — Descoberta (QueryBuilder + Places + enriquecimento) | ✅ concluída |
| **3** | Motor 3 — Abordagem + Nível de Autonomia | ✅ concluída |
| **4** | Compliance (LGPD + Marco da IA) | ✅ concluída |
| **5** | Créditos, planos e pacotes de tokens | ✅ concluída |
| **6** | Frontend (React) | ✅ concluída |
| **7** | Integração e produção | ✅ código pronto — ⏳ falta virar as chaves |
| **Motor 4** | Conversa de duas pontas | ✅ concluída |
| **Motor 5** | Cadência de toques + entregabilidade | ✅ concluída |
| **Etapa 5** | Resposta manual dentro do produto | ✅ concluída |
| **Etapa 6** | Paywall no servidor + cobrar por revelação | ✅ concluída |

**Verificado nesta máquina:** 290 testes verdes · `ruff` limpo · migrations
`upgrade head` / `downgrade base` ok · frontend `npm run build` ok · fluxo
completo exercitado pela interface no navegador.

---

## Fase 0 — Fundação ✅

- `docker-compose.yml` (postgres+pgvector, redis, backend, worker, frontend),
  Dockerfiles multi-stage, usuário não-root, `HEALTHCHECK`, sem segredo em imagem.
- 12 tabelas com enums, índices de dedup, soft-delete, `provenance` e
  `embedding` (pgvector 384d). Migration `0001` cria a extensão, os índices HNSW
  e a trigger de imutabilidade do `audit_logs`.
- 7 portas com DTOs + mocks determinísticos + registry por env.
- `HttpClient` central: timeout, retry com backoff, rate limit, circuit breaker,
  idempotência, `cost_event` e **bloqueio total de rede em modo mock**.
- Máquinas de estado (lead, campanha, autonomia) e auditoria encadeada por hash.

## Fase 1 — Cérebro ✅

- Base de **64 CNAEs** vetorizada por **perfil de consumo**, não por descrição.
  Essa escolha é o núcleo do produto: vetorizar a descrição faria "ar
  condicionado" casar com *quem instala* ar condicionado (o concorrente); pelo
  perfil, casa com *quem precisa* (hotel, supermercado, clínica).
- `ExpansorDeServico`: serviço em texto livre → ramos + termos + justificativa
  auditável, com **filtro de concorrente** (lexical, explicável, sem custo de LLM).
- `ScoringService`: score 0–100 **explicável** — 6 componentes, cada um com peso
  e contribuição em pontos, exibidos na interface ("por quê?").
- `LoopAprendizado`: desfecho de lead realimenta os pesos daquele tenant, com
  mínimo de amostras, passo amortecido, piso/teto e restauração.
- Migration `0002` (`score_weights`).

## Fase 2 — Descoberta ✅

- `QueryBuilder` isolado e sem I/O: round-robin entre termos (um termo ruim não
  consome a cota da campanha), explosão por bairro, exclusões, teto de consultas
  e **custo estimado antes de gastar**.
- `DiscoveryService`: Places → filtro B2B → Receita (desempate por telefone) →
  dedup por CNPJ/place_id/telefone/domínio → lead com proveniência.
- `FakePlaces` deixou de inventar resultado quando havia empresa real — acabaram
  os leads-fantasma que sujavam score e dedup.

## Fase 3 — Abordagem e autonomia ✅

- `PersonalizationService`: gancho vindo do ramo real do lead; sinal de intenção
  (web search) só acima de score 60 e com teto por lote, porque é balde 2.
- `SendService`: **único caminho de saída** do sistema. Revalida opt-out no
  momento do envio, limites diários por campanha e por conta, guardrail de canal,
  idempotência por (campanha, lead, canal) e auditoria de cada passo.
- Autonomia: `assistido` → nasce aguardando aprovação; `automatico` → dispara
  sozinho dentro dos limites. Trocar o nível muda só este serviço.

## Fase 4 — Compliance ✅

- **Opt-out de 1 clique** com token HMAC (o link não expõe o id do lead nem pode
  ser forjado). O próprio GET efetiva a supressão — pedir confirmação seria
  padrão escuro.
- **LIA** gerada dos dados reais do controlador (fontes efetivamente usadas,
  campos tratados), com teste de necessidade, balanceamento, 9 salvaguardas e
  hash do documento. Disponível em JSON e Markdown.
- **Direitos do titular** (art. 18): acesso, eliminação, oposição e portabilidade,
  com protocolo e prazo de 15 dias. A eliminação anonimiza **mas mantém a
  supressão** — sem isso a próxima campanha redescobriria o mesmo contato.
- **Retenção**: expurgo por prazo com `dry_run`, preservando cliente convertido.
- Política de privacidade e declaração de IA publicadas em rota pública.
- Migration `0003` (`privacy_requests`).

## Fase 5 — Créditos e tokens ✅

- Ledger append-only; saldo derivado; bloqueio **antes** da chamada externa
  (nunca pagamos provedor sem poder cobrar); overage explícito; estorno.
- **Vitrine de tokens honesta**: `tokens/mês = leads × tokens por lead`, onde
  "tokens por lead" é **medido** no consumo real do tenant. Sem histórico, a
  interface diz que é estimativa.
- Planos com teto, troca de plano, recarga avulsa e extrato.

## Fase 6 — Frontend ✅

- Onboarding em 3 passos; o passo 2 mostra **o que o Cérebro entendeu** (ramos,
  aderência e concorrentes descartados) antes de gastar um único crédito.
- Campanhas: rodar, revisar leads com score, modal "por quê?" com composição do
  score e origem do dado (LGPD), aprovar/rejeitar/disparar.
- Painel de KPIs: funil, taxas, custo nos dois baldes, margem e provedores.
- Créditos: planos com equivalência em tokens, recarga e extrato.
- Conformidade: LIA, lista de supressão e integridade da auditoria.

## Fase 7 — Integração e produção ✅ (código) / ⏳ (chaves)

- **Adaptadores reais implementados**: Google Places (New), Anthropic (com loop
  de tool use), Anthropic web search, AWS SES, WhatsApp Cloud API, Stripe.
- **20 testes de contrato sem nenhuma chave**: transporte falso (`MockTransport`)
  e dublês de SDK verificam payload, headers, field mask, parsing, custo por
  balde e o loop de tool use. A Fase 7 não é "preencher a chave e torcer".
- `HttpClient.guard()`: SDKs oficiais (Anthropic, boto3, Stripe) passam pelo
  mesmo rate limit, circuit breaker e `cost_event` do cliente central.
- `scripts/smoke.py <provedor>`: smoke isolado que **recusa rodar em modo mock**.
- **Painel de margem**: receita reconhecida × balde 1 + balde 2, por cliente,
  por campanha e por lead, com câmbio configurável.
- `docker-compose.prod.yml` + [guia de deploy](docs/DEPLOY-DIGITAL-OCEAN.md).

### O que falta para estar em produção de verdade

| Item | Por quê |
|---|---|
| **Preencher as chaves e virar os flags** | Não há chave neste ambiente; a virada é o runbook da Fase 7 |
| **`docker compose up` executado** | Docker não está instalado nesta máquina — compose e Dockerfiles escritos e validados como YAML, mas não executados |
| **Autenticação real (JWT)** | Hoje o usuário vem do header `X-User-Email` (dev-only, documentado) |
| **Webhook assinado do Stripe** | Creditar por `/billing/confirmar` permitiria auto-crédito |
| **SNS de bounce/complaint do SES** | Fecha o ciclo de supressão automática |
| **Papel de admin em `/v1/margem/consolidado`** | Hoje qualquer usuário autenticado vê o consolidado |
| **Dump completo da Receita** | A amostra tem 19 CNPJs; em produção, tabela indexada |

---

## Motor 5 — Cadência e entregabilidade ✅

- **Três toques por lead** (D0, D+3, D+7), cada um com **ângulo próprio**: o
  insight, a prova, a saída. Um toque que repete o anterior é spam com outro
  nome — e "seguindo minha mensagem anterior" transfere ao lead a culpa pelo
  silêncio.
- **Sem tabela nova.** O toque é uma `messages` com número nos metadados e
  chave de idempotência por toque. Quem decide é o **estado da conversa lido
  na hora**, não um agendamento gravado: nenhuma linha velha de fila consegue
  disparar para quem já respondeu.
- **Onde para:** resposta do lead, opt-out, recusa, descarte, conversão,
  bounce, campanha pausada, ou fim do toque 3. `concluida` **não** para — é o
  estado normal de toda campanha, e tratá-la como parada faria o motor inteiro
  virar código morto.
- **Entregabilidade:** bounce permanente suprime e descarta; reclamação de spam
  suprime com origem própria e manda o lead para opt-out; retorno temporário
  não suprime nada. Acima de 2% de retorno (com 20 envios de amostra) a
  campanha pausa sozinha — dominío queimado não volta, e leva junto o e-mail
  com que o cliente fatura.
- Migration `0007` (`messages.retorno`, `reclamacao_spam`, `bounce_registrado`).

---

## Etapa 5 — Resposta manual ✅

- A pessoa escreve na thread e o `SendService` envia: a conversa **não sai do
  produto**. Antes, "assumir a conversa" abria um `mailto:` e a resposta do
  lead voltava para a caixa pessoal, fora do alcance do Motor 4.
- **Sem declaração de IA** (o Marco da IA manda declarar quando é IA, não
  mentir que é) e **com link de descadastro** (LGPD não muda conforme quem
  digitou). O texto não passa por LLM — há teste que falha se passar.
- **Opt-out não cede para humano nenhum**: envio manual para contato
  suprimido devolve 451.
- `leads.assumido_em` cala o agente enquanto a pessoa conduz — e
  `devolver-para-ia` religa. Migration `0008`.

---

## Etapa 6 — Revelação de contato ✅

- **O corte saiu da tela e foi para o servidor.** A lista inteira continua
  visível (ramo, bairro, porte, score, insight); o **contato** fica atrás da
  cota. Antes era um `slice(0, 3)` no cliente, com a API devolvendo tudo.
- **Descobrir deixou de custar crédito; revelar passou a custar.** Cobrar por
  lead descoberto punia o cliente quando o Cérebro errava a mira.
- **Duas travas no grátis:** 3 por busca e 10 por mês. Planos pagos só têm o
  teto do mês.
- **Abordar revela**, na geração da mensagem — senão o rascunho em espera de
  aprovação já entregaria o contato de graça.
- Migration `0009` (`leads.revelado_em`) com backfill de quem já tem mensagem.

---

## Decisões estruturais

| Decisão | Por quê |
|---|---|
| Python 3.12 + FastAPI síncrono | o gargalo é I/O de provedor, resolvido na fila |
| Embeddings de **384 dimensões** | `text-embedding-3-small` aceita `dimensions=384`: o schema pgvector não muda ao ligar o provedor real |
| CNAE vetorizado por **perfil de consumo** | evita casar o prestador com os próprios concorrentes |
| **RQ** em vez de Celery | Redis já está na stack; RQ é mais simples e suficiente |
| Fallback **SQLite** + fila **inline** | a suíte roda em qualquer máquina, sem Docker |
| Dinheiro em **micro-dólares** inteiros | nunca float |
| SDK oficial + `HttpClient.guard()` | usa o cliente suportado de cada provedor sem abrir mão do controle central |
| Crédito = 1 **contato revelado**; token = vitrine | o cliente entende crédito; o mercado compara token. Era "1 lead descoberto" até a Etapa 6 |
