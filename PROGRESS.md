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

**Verificado nesta consolidação (20/09, 2ª passada):** **473 testes verdes
(3 pulados)** · `ruff` limpo. Migration head em `0012` (`tentativas_acesso`, da
segurança de 18/09) — **14 tabelas** no total, sem migration nova. `upgrade head` /
`downgrade base` e o fluxo completo pela interface continuam valendo da última
verificação com código; a segurança/Vercel de 18/09 mexeu em backend e acrescentou
só `frontend/vercel.json` (nenhuma mudança em `frontend/src`), e as três correções
desta passada foram todas de backend — então o `npm run build` da última verificação
segue valendo. As três correções novas de 20/09 (Envio: reclamação de spam com teto
próprio, separado do bounce; Conversa: acento decomposto/NFD recomposto; Compliance:
eliminação alcança também as mensagens do titular) não têm migration nem decisão de
produto.

> O número já foi `428` (consolidação de 18/09), `453` (após a segurança/Vercel) e
> `465` (1ª consolidação de 20/09, seis rotinas). As três rotinas que rodaram
> **depois** dela (Envio, Conversa, Compliance) integraram ao `main` por rebase e
> levaram a contagem a **473**, reconferida com `pytest` nesta 2ª passada. As
> rotinas partem de bases diferentes; o total integrado no `main` é o que vale.

---

## Fase 0 — Fundação ✅

- `docker-compose.yml` (postgres+pgvector, redis, backend, worker, frontend),
  Dockerfiles multi-stage, usuário não-root, `HEALTHCHECK`, sem segredo em imagem.
- 10 tabelas na fundação (hoje são **14** no total — `score_weights`,
  `privacy_requests`, `ramo_weights` e `tentativas_acesso` entraram depois, nas
  migrations 0002, 0003, 0010 e 0012) com enums, índices de dedup, soft-delete,
  `provenance` e `embedding`
  (pgvector 384d). Migration `0001` cria a extensão, os índices HNSW e a trigger
  de imutabilidade do `audit_logs`.
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
  supressão** — sem isso a próxima campanha redescobriria o mesmo contato. Desde
  20/09 a eliminação é **simétrica ao acesso**: o que o relatório de acesso devolve
  como dado do titular (leads **e** as mensagens trocadas com ele) a eliminação
  agora remove — expurga corpo/assunto e mascara os dois endereços das mensagens,
  imediato; antes o e-mail e o texto do titular sobreviviam até o expurgo por prazo.
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
| **SDK da Anthropic aceitar `output_config`** | 🔴 `requirements-prod.txt` fixa `anthropic==0.69.0`, que **não tem** o kwarg `output_config` que os adaptadores passam — com `LLM_MODE=real` nenhuma função de IA sobe. Ver HANDOFF §0.3 (radar de deploy, item 14) |
| **`docker compose up` executado** | Docker não está instalado nesta máquina — compose e Dockerfiles escritos e validados como YAML, mas não executados. (O deploy hoje tem também um caminho Vercel — `backend/vercel.json` + `vercel_build.py`) |
| ~~**Autenticação real (JWT)**~~ | ✅ feito na Etapa 8: JWT com acesso de 30 min e renovação de 14 dias; `X-User-Email` não autentica mais nada |
| **Assinatura do webhook do Stripe** | O auto-crédito já foi travado (crédito só pelo que o provedor confirma, idempotente); falta **verificar a assinatura** do webhook do Stripe real |
| **SNS de bounce/complaint do SES** | Fecha o ciclo de supressão automática (tradutor pronto, falta a rota — HANDOFF §0.1 item 8) |
| ~~**Papel de admin em `/v1/margem/consolidado`**~~ | ✅ feito em 18/09: `Depends(usuario_admin)`, 404 fora de `ADMIN_EMAILS` |
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
  não suprime nada. A campanha pausa sozinha (com 20 envios de amostra) — domínio
  queimado não volta, e leva junto o e-mail com que o cliente fatura. Desde 20/09
  **bounce e reclamação têm tetos separados**: a taxa combinada pausa em 2% (como
  antes), mas a **reclamação de spam** tem freio próprio e muito mais baixo
  (`RECLAMACAO_TAXA_MAXIMA` = 0,3%), porque o SES suspende a conta perto de 0,5%
  de reclamação — a campanha pausa por spam **antes** de a conta ser suspensa.
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

## Etapa 7 — Aprendizado por intenção ✅

- **O sinal estava contando errado.** O lead passa por `respondido` a caminho
  de `opt_out`, e `respondido` valia como **sucesso**: um "me tire da lista"
  primeiro ensinava que a mira estava certa e logo depois que estava errada —
  duas amostras contraditórias por um único fato. Agora quem responde ensina
  pela **intenção**, uma vez só, e as transições que o Motor 4 dispara em
  seguida passam `aprender=False`.
- **Segundo eixo de aprendizado: o ramo.** `ramo_weights` guarda um fator por
  (tenant, CNAE). O peso do CNAE vem do Cérebro e é igual para todo mundo; se
  hotel não responde para *este* prestador, só o histórico dele sabe. É a única
  parte do produto que fica mais difícil de copiar com o tempo.
- **As intenções deixaram de pesar igual.** `objecao` é **positiva** — "está
  caro" diz que o ramo compra e o momento estava errado; ensinar o Cérebro a
  fugir dali seria trocar mira certa por silêncio. `recusa` é levemente
  negativa ("já temos fornecedor" é frase de quem consome). Só
  `pedido_opt_out` vale -1. `ausencia` vale 0: resposta de férias não é
  resposta.
- **O fator multiplica, não substitui**, e anda entre 0,5 e 1,5 com mínimo de
  20 respostas por ramo. Um loop guloso apagaria hotéis da mira por causa de
  três respostas ruins — e ninguém veria, porque ausência de lead não aparece
  em tela nenhuma.
- **Por isso a mira virou tela** (cartão no Painel), com o número de respostas
  que produziu cada fator e quantas faltam para o próximo ajuste. Aprendizado
  invisível é indistinguível de superstição.
- **`restaurar` desfaz os dois eixos.** Restaurar metade daria falsa sensação
  de reset a quem clicou justamente por desconfiar do resultado.
- Migration `0010` (`ramo_weights`), sem backfill: intenção de resposta antiga
  não está gravada em lugar que permita reconstruir. **13 testes.**

---

## Etapa 8 — Autenticação de verdade ✅

- **JWT no lugar de `X-User-Email`.** O header era a autenticação inteira, com
  fallback no usuário de seed: `curl -H "X-User-Email: cliente@empresa.com"`
  devolvia os leads daquele cliente. O fallback saiu junto — não saber quem
  está perguntando agora responde 401, não "aqui estão os dados do demo".
- **Dois tipos de token, e o tipo vai assinado dentro dele.** Acesso de 30 min,
  renovação de 14 dias. Um refresh que servisse como acesso anularia a razão de
  o acesso ser curto, e nome de campo não é garantia — a distinção precisa
  estar dentro da assinatura.
- **bcrypt para senha, PyJWT para token.** Nada de esquema próprio: assinatura
  é onde se erra em silêncio (algoritmo `none`, comparação não constante), e
  errar ali não quebra nada — só passa a funcionar para qualquer um.
- **Webhooks assinados** (`/v1/inbound/*`) com HMAC-SHA256 sobre o corpo cru
  mais timestamp, janela de 5 min e comparação em tempo constante. Sem segredo
  configurado a rota **fecha**, não abre. Desde a Etapa 7 uma resposta forjada
  não suja só a thread: move a mira do aprendizado daquele cliente.
- **Isolamento de tenant testado por HTTP.** Havia filtro por `user_id` nos
  repositórios e nenhum teste que tentasse ler dado alheio pela API.
- **A aplicação recusa subir** em `APP_ENV=producao` com o `JWT_SECRET` de
  desenvolvimento ou com menos de 32 caracteres.
- **`EventSource` virou `fetch` com stream.** Ele não aceita cabeçalho, e a
  saída comum — token na query string — o deixaria em log de servidor,
  histórico e Referer. De quebra sumiu a reconexão automática que já custou
  256 execuções de campanha num clique só.
- Migration `0011` (`tipo_evento.usuario_criado` e unicidade de e-mail sem
  distinguir maiúscula). **36 testes.**

---

## Endurecimento das rotinas para a Fase 7 (16–18/09) ✅

Sem etapa nova: as rotinas agendadas seguiram tapando o que quebra quando os
provedores reais entrarem, uma correção por execução, todas integradas ao `main`.

- **Motor 3 — falha síncrona do SES classificada por escopo** (16/09): conta
  suspensa **pausa** a campanha e interrompe a leva (não descarta ninguém);
  endereço morto **suprime** aquele contato e descarta o lead; recusa ambígua só
  marca `FALHOU`. Antes, toda recusa era um "FALHOU" mudo e o `permanente`
  misturava falha de conta com falha de destinatário.
- **Motor 3 — link de descadastro no corpo do e-mail** (18/09): a abordagem gerada
  passa a trazer o link **visível** no corpo (rótulo e link na mesma linha, para a
  proteção do Motor 4 pegar), não só no cabeçalho `List-Unsubscribe`. Cobre os
  toques de cadência de graça. Fechou o item 7 da fila autônoma.
- **Motor 4 — corpo real decodificado antes de classificar**: bloco de cabeçalho
  do Outlook fecha o histórico citado (16/09), quoted-printable (16/09) e HTML
  (18/09) viram texto puro antes da varredura de opt-out e do corte de citação.
- **Descoberta — raio do Places grampeado em 50 km** (18/09): raio absurdo vira
  50 km em vez de derrubar a rodada com `400` do Google.
- **Custo — sem custo-fantasma nos dois lados** (18/09): evento de entrada e de
  saída só nascem com token > 0; chamada de LLM sem token não fabrica custo no
  balde 2. Completa o guarda do lado de "saída" fechado em 15/09.
- **Compliance — expurgo preserva o registro de destinatário sem `@`** (18/09):
  telefone/WhatsApp vira `[expurgado]` em vez de `NULL`, sem perder a evidência de
  que houve um contato na trilha de auditoria.

## Segurança e preparação para o Vercel (18/09) ✅

- **Cobrança:** crédito só entra por pagamento que o provedor confirma — pacote
  e valor vêm do checkout, não do navegador; o mesmo pagamento credita uma vez;
  plano pago fora do desenvolvimento responde 402; descer para o gratuito não
  dá crédito.
- **Painel de margem de todos os clientes:** só `ADMIN_EMAILS` (404 para os
  demais). Integridade da auditoria passou a exigir sessão.
- **Login e cadastro com limite** (migration 0012, `tentativas_acesso`).
- **APP_SECRET obrigatório em produção** (assina descadastro e checkout).
- **Vercel:** dependências no `pyproject.toml` (com teste de espelho dos
  requirements), Python 3.12 fixo, região São Paulo, build que traz `data/` e
  os textos jurídicos, migra o banco e carrega o catálogo de ramos só no deploy
  de produção; sem pool de conexões na função; `frontend/vercel.json` repassa
  `/descadastro`, `/privacidade` e `/legal` ao servidor.
- 453 testes verdes, ruff limpo, build do frontend limpo.

## Vazamento entre clientes fechado (16/09) ✅

- `GET /v1/compliance/solicitacoes` listava os pedidos de direitos do titular
  de todas as contas, com o e-mail de quem pediu. Agora mostra só os pedidos
  com o `user_id` do cliente ou sobre um contato dos leads dele.
- `POST /v1/compliance/retencao` removida: qualquer conta logada disparava o
  expurgo da base inteira. O expurgo roda pelo worker.
- 3 testes novos com duas contas (dois falhavam antes). 395 testes verdes.
- Texto das seis rotinas reescrito para salvar direto no `main`.

## Integração das rotinas autônomas (15/09) ✅

- Seis rotinas agendadas rodaram 24 vezes em cópias separadas e nunca salvaram
  no `main`. Consolidadas em **11 correções diferentes**, escolhidas por
  comportamento onde havia versões repetidas: busca que sobrevive a recusa do
  Places, UF do endereço real, tradutor do retorno SES/SNS, corte do histórico
  citado no Motor 4, três de custo (taxa fracionária, preço do Sonnet 5, saída
  fantasma do embedding) e quatro de retenção LGPD.
- Achado na integração: **toda resposta real virava `pedido_humano`**, porque a
  declaração de IA termina com "falar com uma pessoa" e o Motor 4 lia a mensagem
  citada. Corrigido junto, com teste.
- Proteção: a linha do nosso link de descadastro não entra na varredura de
  opt-out. Sem ela, pôr o link no corpo do e-mail faria todo "tenho interesse"
  virar descadastro terminal.
- Radares passam a viver no `main` (`docs/radar/`). **390 testes.**

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
| Aprendizado por ramo **multiplica** o peso do Cérebro | o Cérebro continua no comando e o fator só inclina; substituir deixaria o histórico apagar ramo bom |
| Sessão em **JWT**, não em cookie de servidor | a API é consumida por um SPA e, adiante, pelo app; sem estado de sessão no servidor não há o que sincronizar entre réplicas |
| SSE por **`fetch`**, não `EventSource` | é o único jeito de mandar `Authorization` sem pôr credencial na URL |
