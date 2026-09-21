> **ESTADO INTEGRADO NA VERSÃO PRINCIPAL — 15/09/2026**
>
> De 12 a 15/09 as rotinas trabalharam em cópias separadas e não enxergavam o
> trabalho umas das outras — a mesma correção chegou a ser feita quatro vezes.
> As correções abaixo foram escolhidas, testadas juntas e integradas no `main`.
> **Leia esta lista antes de agir: o que coincidir com ela já está resolvido e
> não deve ser refeito.** Os hashes citados são dos commits originais; no `main`
> eles têm hash novo, com a mesma mensagem.
>
> - **Taxa por token em float, arredondamento só no total** (versão de 14/09, `6da0795`; a de 12/09, `7e12599`, era equivalente e ficou de fora).
> - **Preço do Sonnet 5 = US$ 2 / US$ 10 por milhão** (`5d069ec`) — conferido na tabela oficial da Anthropic.
> - **Embedding não cobra mais saída fantasma no mock** (`4e7994f`).
>
> O que vem abaixo é o diário da execução de 15/09, mantido como estava.

---

# Radar — Custo, crédito e margem

> Guarda-costas de: `backend/app/core/pricing.py`, `services/cost.py`,
> `services/creditos.py`, `services/margem.py`, `services/revelacao.py` e testes.
>
> **O que está em jogo:** hoje o custo é estimado (`modo="mock"`) e o painel de
> margem roda em cima dessa estimativa. Quando as APIs reais entrarem (Fase 7), o
> custo passa a ser faturado de verdade. Se a estimativa estiver errada — ou se o
> mock registrar um custo que não existe — a margem que o produto mostra é ficção.
> Este radar existe para manter três pilares de pé: **(1) tabela de preços correta
> e atual, (2) todo custo externo no balde certo (1=dados, 2=IA), (3) nada gasta
> sem registrar** — e o seu inverso, tão perigoso quanto: **nada registra sem
> gastar.** O eixo de cobrança continua sendo o **contato revelado**, nunca o lead
> descoberto.
>
> Uma correção por execução. Cada run acrescenta uma entrada datada aqui.

---

## 2026-09-15 — custo-fantasma de "saída" no embedding

### Corrigido
- **Toda chamada de embedding registrava ~25 micros de "saída" que nunca
  existiram — só no mock, que é o que roda hoje.** `services/cost.py::registrar_llm`
  emitia **sempre** dois eventos (entrada e saída). Para embedding, o adaptador
  mock (`adapters/mock/fake_llm.py`) chama com `tokens_saida=0`. Nesse evento de
  saída: a chave `llm.embedding.output` **não existe** na tabela → cai no fallback
  `llm.mock.output` (25 micros/token); e como `tokens_saida=0`, o `registrar`
  usava a `quantidade` default (1.0). Resultado: **~25 micros de saída fantasma
  por chamada de embedding**, no balde 2 (IA). Embedding roda em todo serviço do
  Cérebro e em todo lead do scoring, então isso inflava em silêncio o custo de IA
  do painel de margem — margem pior que a real, escondida dentro de um número que
  ninguém questiona.
  - **Correção:** `registrar_llm` passou a emitir o evento de saída **só quando
    `tokens_saida > 0`**. Uma completude sempre gera texto, então continua com
    dois eventos; operação só-de-entrada (embedding não produz texto) gera um
    único evento de entrada — **igual ao que o adaptador real já faz**
    (`adapters/real/anthropic_llm.py` registra embedding como evento único de
    entrada, via `http.request(..., custo=...)`, sem passar por `registrar_llm`).
    O mock agora casa com o real.
  - Não é só de embedding: qualquer chamada de LLM com `tokens_saida=0` deixava
    de custar 1 unidade de saída ao preço cheio (para Opus, 25 micros). Agora não
    custa saída que não houve.
  - **Retorno:** mudou de `tuple[CostEvent, CostEvent]` para `list[CostEvent]`
    (1 ou 2 eventos). Nenhum chamador usava o retorno — verificado nos quatro
    call sites (`fake_llm` x2, `anthropic_llm`, `anthropic_search`).
  - **Testes:** `tests/unit/test_cost.py` (novo) trava a regressão — completude
    normal gera dois eventos; embedding gera um só, sem `.output`, sem
    `llm.mock.output`, e o balde 2 soma só a entrada real. `pytest` 343 passed /
    3 skipped, `ruff` limpo.

### ATENÇÃO — este bug (e outros) foram corrigidos VÁRIAS vezes em branches paralelas
Ao ler o histórico de `docs/radar/custo.md` em outras branches, ficou claro que
**as rotinas estão repetindo trabalho** (é o padrão "rotinas em cópias
separadas"): cada execução ramifica a partir de `main`, que **não tem** nenhuma
dessas correções, então cada run reencontra o mesmo bug e o conserta de novo, na
sua própria branch, sem que nada chegue ao `main`.

O que já foi corrigido **fora do `main`** e ainda está aberto **no `main`** (e,
portanto, nesta branch quando comecei):

| Bug | Corrigido em | Estado no `main` |
|---|---|---|
| Preço do **Sonnet 5** (US$3/15 → deveria ser US$2/10 por 1M) | `magical-elion-160612` (`5d069ec`) | ❌ ainda US$3/15 |
| **Embedding input arredonda para 0** (`_por_milhao(0.02)`=0) | `c7fc277` **e de novo** `quirky-williams-ae351d` (`6da0795`) — corrigido **duas vezes** | ❌ ainda 0 |
| **Custo-fantasma de saída no embedding** (este run) | só aqui, até agora | ❌ (corrigido nesta branch) |

Fui atrás do único achado de custo que **ninguém** tinha resolvido ainda — e
que, diferente dos outros dois (que só mordem na Fase 7, com provedor real),
**distorce o painel HOJE**, porque tudo roda em mock.

**Consolidação (a pedido do Matheus, na sequência da run).** Em vez de deixar as
três correções de custo espalhadas em três branches — nenhuma no `main` —, trouxe
as outras duas para **esta** branch por `git cherry-pick -x` (não reconserto,
não duplico esforço): `6da0795` (embedding-input, taxa `float`) e `5d069ec`
(Sonnet 5, US$2/10). Agora esta branch é **o único lugar onde o domínio de custo
está inteiro e correto**, com os testes das três correções juntos (349 passed /
3 skipped, `ruff` limpo). É uma PR pronta para o `main` — o caminho certo é
integrar isto, não recriar em branch nova.

> **O bloqueio real não é técnico, é de integração.** Enquanto as branches
> `claude/*` não forem integradas ao `main` (ou as correções cereja-escolhidas
> para lá), o `main` seguirá com bugs de preço já resolvidos, e as próximas
> rotinas vão continuar gastando execução para reconsertá-los. Isso é decisão de
> quem coordena o repositório — está **fora do meu escopo** (só toco os cinco
> arquivos de custo + testes; integrar branch mexe no repositório inteiro).

### Achado e NÃO corrigido (fica para outra execução ou outro dono)
- **Embedding-input ainda arredonda para 0 no `main`.** Nesta branch **já não**
  — a consolidação trouxe `6da0795`, que torna `micros_por_unidade` um `float` e
  arredonda só no total (`estimar_micros`). Mas enquanto esta branch não for
  integrada, o `main` segue com `round(0.02)=0` micros/token e o embedding custa
  0 lá. É o retrato do problema de integração acima.
- **A raiz do fantasma é o *caller* usar `registrar_llm` para operação
  só-de-entrada.** O conserto que fiz é uma defesa em `cost.py` (só-de-entrada →
  um evento). A limpeza completa seria o mock (`fake_llm.py:103`) registrar
  embedding como evento único de entrada, como o real já faz — mas `fake_llm.py`
  está **fora do meu escopo**. A defesa em `cost.py` é a rede que vale mesmo que
  algum caller futuro esqueça.
- **Fallback silencioso de modelo para preço de mock.** `cost.py::chave_llm()` —
  se um modelo real não estiver na tabela, o custo usa **em silêncio** o preço do
  mock (espelho do Opus 5) em vez de falhar. Hoje **não é bug ativo** (o padrão
  `claude-opus-5` está precificado). O risco é na Fase 7: trocar/adicionar modelo
  sem cadastrar o preço faria o custo mentir sem avisar. `preco()` já levanta
  `KeyError` para chave desconhecida; `chave_llm` deveria ao menos logar aviso em
  `modo="real"`. Candidato a "uma coisa" futura, no meu escopo.

### Decisão de preço — NÃO decido, registro e paro
- **Os preços de token dos modelos são estimativas de tiers** (Opus 5 US$5/US$25,
  Sonnet 5 US$3/US$15 **[desatualizado — ver acima; deveria ser US$2/US$10]**,
  Haiku 4.5 US$1/US$5 por 1M in/out). Não invento valor de tabela de provedor.
  Ponto de atenção humano: Opus a US$5/US$25 está bem abaixo do tier Opus
  histórico (US$15/US$75) — conferir se é intencional antes de ligar o provedor.
  Places, WhatsApp e SES estão na mesma categoria ("revalidar F7"). O caminho de
  reconciliação já está previsto: o smoke test de cada provedor compara estimado
  × faturado na virada.
- **Preços de PLANO (o que a gente COBRA)** — `CATALOGO` (Trial/Starter/Pro/Scale)
  e `PACOTES`. Não toquei. Se algum valor estiver errado é decisão de negócio
  (HANDOFF §0.2), não correção de tabela de custo.

### Depende de outros
- **Integração das branches ao `main`** (ver "ATENÇÃO" acima) — é o que faria o
  `main` parar de mentir preço e as rotinas pararem de repetir trabalho. Decisão
  de coordenação do repositório.
- **`settings.usd_brl` fixo no `config.py`.** A margem em BRL (`margem.py`)
  multiplica por essa taxa; câmbio velho = margem errada. `config.py` está fora
  do meu escopo. Em produção precisa vir de fonte real (ou atualização manual
  disciplinada).
- **Registro de custo dos provedores reais** mora nos adaptadores
  (`adapters/real/*`, `adapters/mock/*`) e no `http_client.py` — fora do meu
  escopo. Meu domínio garante que, **dado** um evento, ele cai no balde certo, é
  precificado certo e não fabrica custo; garantir que **todo** provedor emita o
  evento é dos adaptadores.
- **Fase 7 (chaves + cartão)** — item de "PRECISA DE VOCÊ" (HANDOFF §0.2). A
  revalidação dos preços de dados e o teste do custo real de embedding só fecham
  depois disso.

### Verificado e OK (sem ação) — confirmado nesta branch, não herdado de nota
- **Eixo de cobrança = contato revelado, não lead descoberto.**
  `CUSTO_CREDITOS["lead_qualificado"] = 0` (descoberta não custa crédito);
  `contato_revelado = 1`; em `creditos.debitar()` **só** `contato_revelado`
  incrementa `leads_consumidos_mes` (o teto do mês); `revelacao.revelar()` debita
  `contato_revelado` e é **idempotente** (guarda `lead.revelado_em`, um duplo
  clique não custa dois créditos). `mensagem_enviada` cobra 1 crédito
  (redação+disparo) mas **não** mexe no teto de contatos — sem dupla contagem no
  eixo de cobrança. Nada voltou a cobrar por descoberta.
- **Baldes derivados centralmente.** `cost.py` grava `balde` a partir da chave de
  preço, não de quem chama — impossível um custo cair no balde errado por
  descuido do adaptador. `test_baldes_nunca_se_misturam` fixa a partição.

---

## 2026-09-16 — preço de LLM sem cadastro deixa de mentir calado

### Corrigido
- **Modelo de LLM sem preço na tabela caía, em silêncio, no preço-espelho do
  mock (Opus 5, US$5/US$25) — e a margem passaria a mentir na Fase 7.**
  `cost.py::chave_llm` tinha fallback `llm.{modelo}.{tipo}` → `llm.mock.{tipo}`
  sem aviso nem marca. **Hoje não é bug ativo** (o padrão `claude-opus-5` está
  cadastrado, e Sonnet 5 e Haiku 4.5 também), mas quando um provedor real usar
  um modelo ainda não cadastrado, o custo apareceria com o preço do Opus: para
  um modelo mais barato, caro demais; margem pior que a real, escondida num
  número que ninguém questiona.
  - **Por que NÃO levantar erro:** o registro de custo acontece **depois** da
    chamada externa. Abortar ali seria gastar no provedor e não registrar —
    exatamente o inverso que este radar existe para impedir. O meio-termo:
    registrar com o único preço conhecido (mock) e **marcar** o evento.
  - **Correção:** o evento de LLM sem preço cadastrado passa a carregar
    `metadados.preco_fallback=True`, e em `modo="real"` o `cost.py` emite
    `log.warning("preco_llm_sem_cadastro", ...)`. O caminho normal (modelo
    cadastrado) segue **idêntico** — mesma chave, mesmos metadados
    `{"modelo": ...}`, mesmo valor. Só-refatoração: `chave_llm` delega a
    `_resolver_llm` (devolve chave + se houve fallback) e `registrar_llm` monta
    os specs por `_spec_llm`.
  - **Testes:** `tests/unit/test_cost.py` (novos) — modelo real sem preço gera 2
    eventos marcados `preco_fallback`, com chave `llm.mock.*`, sempre no balde 2;
    modelo com preço **não** marca. `pytest` 391 passed / 3 skipped, `ruff` limpo.

### Verificado e OK (sem ação) — tabela conferida contra a fonte oficial nesta execução
- **Os preços de LLM estão corretos e atuais.** Conferi Opus 5 (US$5/US$25 por
  1M), Sonnet 5 (US$2/US$10) e Haiku 4.5 (US$1/US$5) contra a tabela oficial da
  Anthropic (skill `claude-api`, cache 2026-06-24). **Batem exatamente.** O
  alerta da execução anterior — "Opus a US$5/US$25 parece baixo demais vs. o
  tier histórico US$15/US$75" — era **falso alarme**: a tabela oficial confirma
  US$5/US$25 para o Opus 5. Não há mais dúvida de preço de LLM em aberto.
- **Os três consertos do bloco ESTADO INTEGRADO já estão no `main`** (taxa em
  float, Sonnet 5 US$2/US$10, embedding sem saída fantasma) — confirmados no
  código, não refeitos.
- **Eixo de cobrança = contato revelado.** Reconferido: `lead_qualificado=0`,
  `contato_revelado=1` conta no teto do mês, `revelar()` idempotente,
  `mensagem_enviada` não mexe no teto. Nada voltou a cobrar por descoberta.

### Achado e NÃO corrigido (fica para outro dono)
- **A raiz é de configuração, não de registro.** O lugar certo de **falhar
  fechado** por modelo sem preço é a validação de startup (recusar subir com
  `llm_model` sem preço na tabela), como já se faz com `JWT_SECRET`. Isso mora
  em `config.py`, **fora do meu escopo** (só toco os cinco arquivos de custo +
  testes). A marca + o aviso que adicionei são a rede em `cost.py`; a trava dura
  seria no boot.
- **Preços de dados seguem "revalidar F7".** Places, SES e WhatsApp são
  estimativas de tabela pública — não invento valor de provedor. A reconciliação
  (estimado × faturado) já está prevista no smoke test de cada provedor na virada.

### Depende de outros / decisão humana
- **Integração ao `main`** — este commit precisa chegar ao `main` (rebase + push
  desta execução). Enquanto branches `claude/*` não integram, o `main` repete
  trabalho.
- **`settings.usd_brl` fixo** (`config.py`, fora do escopo) — câmbio velho =
  margem BRL errada. Em produção precisa vir de fonte real.
- **Registro de custo dos provedores reais** mora nos adaptadores
  (`adapters/*`, `http_client.py`, fora do escopo). Meu domínio garante que,
  **dado** um evento, ele cai no balde certo, é precificado certo (ou marcado
  como estimativa) e não fabrica custo; garantir que **todo** provedor emita o
  evento é dos adaptadores.
- **Fase 7 (chaves + cartão)** — item de "PRECISA DE VOCÊ" (HANDOFF §0.2). A
  revalidação dos preços de dados fecha depois disso.

---

## 2026-09-18 — custo-fantasma de ENTRADA: o outro lado do guarda

### Corrigido
- **`registrar_llm` fabricava 1 unidade de ENTRADA fantasma quando a chamada
  vinha com `tokens_entrada=0`.** A execução de 15/09 fechou o custo-fantasma de
  **saída** (evento de saída só quando `tokens_saida > 0`), mas deixou o evento
  de **entrada** sendo registrado **sempre**. É o mesmo defeito, do outro lado:
  um evento de lado com zero token cai no ramo de `quantidade` default (1.0) de
  `registrar` e vira 1 unidade ao preço cheio — para o mock (espelho Opus 5),
  5 micros de entrada fantasma; para uma completude Opus real, os mesmos 5.
  Fere o inverso do eixo deste radar: **nada registra sem gastar.**
  - **Onde mordia:** hoje, quase nunca — completude sempre tem prompt e o mock
    conta tokens reais (> 0). O gatilho real aparece na Fase 7: um `usage` que
    reporta `input_tokens=0` (resposta vazia, recusa, ou tudo servido de cache)
    passando por `registrar_llm` — inclusive o caminho de web search
    (`adapters/real/anthropic_search.py::_registrar` chama `registrar_llm` sempre
    que há `usage`, mesmo com 0/0). Aí o balde 2 do painel ganhava um custo que
    não existiu.
  - **Correção:** simetria total. Cada lado (entrada, saída) só vira evento
    quando teve `token > 0`. O caminho real (entrada > 0) segue **idêntico** —
    mesma chave, mesmo valor, mesmo número de eventos para toda completude e todo
    embedding de verdade. Só muda o degenerado: `(0, N)` gera um evento só de
    saída; `(0, 0)` não registra nada — chamada sem token gasto não fabrica custo.
  - **Retorno:** continua `list[CostEvent]`, agora podendo vir **vazio** para
    `(0, 0)`. Nenhum chamador usa o retorno (reconferido: `fake_llm` x2,
    `anthropic_llm`, `anthropic_search` — todos ignoram o valor).
  - **Testes:** `tests/unit/test_cost.py` (2 novos) — `(0, 50)` gera só o evento
    de saída, sem `.input` e sem fantasma no balde 2; `(0, 0)` não registra nada.
    Falham antes (2 eventos / 1 evento fantasma), passam depois. `pytest` 422
    tests, exit 0 (3 skipped), `ruff` limpo.

### Verificado e OK (sem ação) — reconferido nesta execução
- **Tabela de LLM correta e atual.** Conferi Opus 5 (US$5/US$25 por 1M), Sonnet 5
  (US$2/US$10) e Haiku 4.5 (US$1/US$5) contra a tabela oficial da Anthropic
  (skill `claude-api`, cache 2026-06-24) — **batem exatamente**. Os IDs canônicos
  (`claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5`) casam com as chaves da
  tabela, e o padrão `settings.llm_model="claude-opus-5"` resolve sem cair no
  fallback. Sem dúvida de preço de LLM em aberto.
- **Embedding-input em `float`, sem arredondar por token** — no `main` (herdado
  da integração de 15/09): `micros_por_unidade: float`, `_por_milhao(0.02)` não
  arredonda, arredondamento só em `estimar_micros`. `test_pricing` guarda.
- **Web search registra os DOIS custos.** `anthropic_search.py::_registrar` emite
  a taxa por busca (`search.web_search`, balde 2) **e** os tokens da conversa
  (`registrar_llm`). Nenhum lado gasta sem registrar.
- **Eixo de cobrança = contato revelado.** Reconferido: `lead_qualificado=0`,
  `contato_revelado=1` conta no teto do mês, `revelar()` idempotente
  (`lead.revelado_em`), `mensagem_enviada` cobra 1 crédito mas **não** mexe no
  teto de contatos. Nada voltou a cobrar por descoberta.
- **Baldes derivados centralmente.** `cost.py` grava `balde` a partir da chave de
  preço, não de quem chama — impossível um custo cair no balde errado por
  descuido do adaptador.

### Achado e NÃO corrigido (fica para outro dono)
- **A raiz do fantasma continua sendo o *caller* usar `registrar_llm` para
  operação só-de-entrada.** O guarda que fiz é a rede em `cost.py` (só-de-entrada
  → um evento; sem token → nenhum). A limpeza completa seria o mock
  (`fake_llm.py`) registrar embedding como evento único de entrada, como o real
  já faz — mas `fake_llm.py` está **fora do meu escopo**.
- **Preço sem cadastro falha fechado só no boot, não aqui.** O lugar de recusar
  subir com `llm_model` sem preço na tabela é a validação de startup em
  `config.py` (fora do escopo), como já se faz com `JWT_SECRET`. A marca
  `preco_fallback` + aviso (execução de 16/09) é a rede em `cost.py`.
- **Preços de dados seguem "revalidar F7".** Places, SES e WhatsApp são
  estimativas de tabela pública — não invento valor de provedor. A reconciliação
  (estimado × faturado) já está prevista no smoke test de cada provedor na virada.

### Depende de outros / decisão humana
- **Integração ao `main`** — este commit precisa chegar ao `main` (rebase + push
  desta execução). Enquanto branches `claude/*` não integram, o `main` repete
  trabalho.
- **`settings.usd_brl` fixo** (`config.py`, fora do escopo) — câmbio velho =
  margem BRL errada. Em produção precisa vir de fonte real.
- **Registro de custo dos provedores reais** mora nos adaptadores
  (`adapters/*`, `http_client.py`, fora do escopo). Meu domínio garante que,
  **dado** um evento, ele cai no balde certo, é precificado certo (ou marcado
  como estimativa) e não fabrica custo; garantir que **todo** provedor emita o
  evento é dos adaptadores.
- **Fase 7 (chaves + cartão)** — item de "PRECISA DE VOCÊ" (HANDOFF §0.2). A
  revalidação dos preços de dados fecha depois disso.

---

## 2026-09-20 — receita de overage no painel de margem: fim da subestimativa

### Corrigido
- **O painel de margem valorizava o crédito de OVERAGE pelo preço-base do plano,
  não pelo preço de overage que o cliente de fato paga.** `margem.py` conta o
  crédito de overage como receita reconhecida (`TipoCredito.OVERAGE` está em
  `CONSUMO`), mas `receita = créditos × preço-base` usava **um único** preço para
  todos os créditos. O crédito de overage é cobrado do cliente ao
  `overage_centavos_por_credito` do plano — mais caro que o crédito-base
  amortizado (Pro: R$0,70/crédito de overage vs. R$0,4975/crédito-base). Ou seja:
  o painel contava o **custo** de servir o lead de overage, mas subestimava a
  **receita** dele → a margem do overage aparecia pior do que a real, dentro de um
  número que ninguém questiona. É o mesmo eixo deste radar ("a margem não pode ser
  ficção"), do lado da receita.
  - **Por que NÃO é decisão de preço:** o preço de overage já está **decidido** —
    mora no `CATALOGO` e é o mesmo que o painel de billing mostra ao cliente
    (`POST /v1/billing/overage`, `conta.py`). Aqui só **aplicamos** esse preço já
    existente; não escolho quanto cobrar.
  - **Correção:** `_creditos_consumidos` passou a devolver `(base, overage)`
    (agrupando o ledger por `tipo`), e `_receita(user, base, overage)` valoriza
    `base × preço-base + overage × preço-overage`. `por_usuario` monta a receita a
    partir disso; `_montar` recebe a receita pronta (não mais `créditos ×
    preço`). O `consolidado()` soma a receita por cliente, então herda a correção
    sem mudança própria. O caminho **sem overage** segue idêntico (overage=0 →
    mesma conta de antes): trial continua receita zero, Pro sem overage continua
    igual.
  - **Testes:** `tests/integration/test_fase7_margem.py::test_overage_conta_receita_pelo_preco_de_overage`
    (novo) — Pro com overage ligado, 4 créditos consumidos sem saldo (viram
    overage): receita tem de ser `4 × R$0,70`, **não** `4 × R$0,4975`. Falha antes
    (1,99), passa depois (2,80). `pytest` 454 passed / 3 skipped, `ruff` limpo.

### Verificado e OK (sem ação) — reconferido nesta execução
- **Tabela de LLM correta e atual — conferida contra a fonte autoritativa.**
  Opus 5 (US$5/US$25 por 1M), Sonnet 5 (US$2/US$10) e Haiku 4.5 (US$1/US$5) batem
  **exatamente** com a tabela da skill `claude-api` (cache 2026-06-24). Os IDs
  canônicos **não levam sufixo de data** (a própria fonte diz "never append date
  suffixes"), então `llm.claude-opus-5.*` / `llm.claude-sonnet-5.*` /
  `llm.claude-haiku-4-5.*` casam com o modelo real e não caem no fallback.
- **Todo `chave_preco` usado no código existe na tabela.** Varri os call sites
  (`adapters/*`, `services/*`, `http_client.py`): `places.text_search`,
  `places.place_details`, `enrichment.receita_cnpj`, `email.ses.send`,
  `whatsapp.template.{utility,marketing}`, `search.web_search`,
  `llm.embedding.input` e os `llm.*` via `registrar_llm` — **nenhum** cai em
  `preco()` sem cadastro (que seria KeyError = gastar sem registrar).
  (`places.nearby_search` está cadastrado e ainda sem uso — sobra inofensiva.)
- **Balde certo, derivado centralmente; custos-fantasma dos dois lados fechados.**
  `cost.py` grava `balde` a partir da chave (DADOS→1, IA→2), não de quem chama;
  `registrar_llm` só emite evento do lado com token > 0, e `(0,0)` não registra
  nada.
- **Places é cobrado por REQUISIÇÃO, não por resultado.** `fake_places` passa
  `len(itens)` mas o `CostSpec` usa `quantidade=1` (a contagem vai só para
  `metadados`). Sem inflar o balde 1 hoje (tudo em mock).
- **Eixo de cobrança = contato revelado.** `lead_qualificado=0`,
  `contato_revelado=1` conta no teto do mês, `revelar()` idempotente
  (`lead.revelado_em`), `mensagem_enviada` não mexe no teto. `mascarar()` esconde
  todos os campos de contato (`CAMPOS_OCULTOS`) e **não** expõe `place_id`,
  `resumo` nem `contexto` — o paywall não vaza por um campo esquecido. Nada
  voltou a cobrar por descoberta.

### Achado e NÃO corrigido (fica para outro dono / outra execução)
- **[adaptador, fora do escopo] O adaptador REAL de WhatsApp cobra template de
  MARKETING ao preço de UTILITY.** `adapters/real/bsp_whatsapp.py` (linhas 81 e
  91) fixa `chave_preco="whatsapp.template.utility"` nos **dois** ramos, nunca
  usando `whatsapp.template.marketing` (~7,8× mais caro: 62.500 vs 8.000 micros).
  Quando o WhatsApp virar canal real (não é hoje), o balde 1 sairia subestimado. A
  tabela de preços (meu escopo) tem as duas chaves certas; quem escolhe a chave é
  o adaptador. O mock (`fake_whatsapp.py`) faz distinção diferente — os dois
  deveriam concordar. **Dono: Envio/adaptadores.** Some com a revalidação F7.
- **[observabilidade, meu escopo, baixo] `latencia_ms` só é gravada no evento de
  ENTRADA.** Numa completude o evento de saída nasce com `latencia_ms=None`; numa
  chamada só-de-saída (entrada cacheada) a latência some. Não afeta os três
  pilares (preço/balde/fantasma) — é ruído no painel de latência, não no de
  margem. Candidato a "uma coisa" futura, sem urgência.
- **[ambíguo, meu escopo] `tokens_por_lead().custo_medio_lead_micros` soma os
  DOIS baldes** (dados + IA), enquanto `tokens_por_lead` conta só tokens de IA.
  Como "custo total por lead" está certo; como "custo de IA por lead" estaria
  errado. Não mexi para não trocar a semântica no chute — decisão de produto sobre
  o que a vitrine quer mostrar.

### Depende de outros / decisão humana
- **Modelo de reconhecimento de receita do overage — confirmar com o dono.** A
  correção acima assume que a receita de um crédito de overage é o
  `overage_centavos_por_credito` (o que o cliente paga). Se o produto quiser
  mostrar a margem só pela economia do plano-base e tratar overage à parte, é
  decisão de finanças/produto — mas aí o painel de billing e o painel de margem
  contariam coisas diferentes, o que é pior. O comportamento agora bate com a
  cobrança que o cliente recebe.
- **[adaptador] Tokens de leitura de cache (`cache_read_input_tokens`) na F7.** Se
  o adaptador real da Anthropic passar só `input_tokens` a `registrar_llm` e
  ignorar os tokens de cache, esse custo (reduzido, mas real) não é registrado —
  "gasta sem registrar". Mora em `adapters/real/anthropic_llm.py`, fora do escopo.
- **`settings.usd_brl` fixo** (`config.py`, fora do escopo) — câmbio velho =
  margem BRL errada. Em produção precisa vir de fonte real.
- **Preço sem cadastro falha fechado só no boot** — a trava dura (recusar subir
  com `llm_model` sem preço, como o `JWT_SECRET`) mora em `config.py`, fora do
  escopo. A marca `preco_fallback` + aviso em `cost.py` é a rede.
- **Fase 7 (chaves + cartão)** — revalidar os preços de DADOS (Places, SES,
  WhatsApp; incluindo o modelo de cobrança do WhatsApp, que a Meta mudou de
  conversa para por-mensagem) contra o faturado real. Não invento valor de
  provedor.

---

## 2026-09-20 (2ª execução) — margem POR CAMPANHA: a receita de envio deixava de somar

### Corrigido
- **A margem por campanha contava o CUSTO inteiro da campanha, mas só a receita
  de REVELAÇÃO — dropava a receita de envio e de sinal de intenção.** Em
  `margem.py::_creditos_consumidos`, quando há `campaign_id`, o consumo era
  filtrado por `CreditLedger.referencia_id.in_(leads_da_campanha)`. Só que os três
  consumos referenciam coisas diferentes: `contato_revelado` é debitado com
  `referencia_id = lead.id` (`revelacao.py`), mas `mensagem_enviada` e
  `sinal_intencao` com `referencia_id = mensagem.id` (`envio.py`). O filtro só
  casava id de lead → **os créditos de envio (`CONSUMO_ENVIO`) e de IA
  (`CONSUMO_IA`) sumiam** do total da campanha. O comentário do código já dizia
  "leads dela **+ mensagens dela**" — a intenção estava lá, a implementação parou
  na metade. Resultado: a margem da campanha (o número que o painel mostra
  por-campanha) aparecia **pior do que a real** — custo cheio, receita parcial —,
  dentro de um número que ninguém questiona. É o mesmo eixo deste radar ("a margem
  não pode ser ficção"), do lado da receita, e o irmão por-escopo da correção de
  overage da 1ª execução de hoje.
  - **Por que NÃO é decisão de preço:** não escolho quanto cobrar; só faço a
    receita **já reconhecida** (créditos consumidos × preço já decidido do plano)
    ser somada no escopo certo. O eixo de cobrança segue sendo o contato revelado;
    o crédito de `mensagem_enviada`/`sinal_intencao` já existia e já era contado no
    escopo do USUÁRIO — só não descia para o da CAMPANHA.
  - **Correção:** o filtro por campanha passou a aceitar `referencia_id` que seja
    lead da campanha **ou** mensagem da campanha (`Message.campaign_id`, que a
    mensagem já carrega), via `or_(... .in_(leads), ... .in_(mensagens))`. O escopo
    de USUÁRIO (sem `campaign_id`) segue **idêntico** — nunca teve filtro de
    referência, então já somava tudo. O overage também é apanhado nos dois lados
    (um `OVERAGE` de envio referencia a mensagem).
  - **Testes:** `tests/integration/test_fase7_margem.py::test_margem_por_campanha_conta_receita_de_envio_nao_so_de_revelacao`
    (novo) — Pro, uma campanha; a margem por-campanha tem de bater com a do usuário
    e ter **mais** créditos que revelações (o envio consome crédito além da
    revelação). Falha antes (`3 > 3`: só as 3 revelações), passa depois (revela +
    envia). `pytest` 473 passed / 3 skipped, `ruff` limpo.

### Verificado e OK (sem ação) — reconferido nesta execução
- **Tabela de LLM correta e atual — conferida contra a fonte autoritativa HOJE.**
  Opus 5 (US$5/US$25 por 1M), Sonnet 5 (US$2/US$10) e Haiku 4.5 (US$1/US$5) batem
  **exatamente** com a tabela oficial da Anthropic na skill `claude-api` (cache
  2026-06-24). Os IDs canônicos **não levam sufixo de data** (a própria fonte:
  "never append date suffixes"), então `llm.claude-opus-5.*` etc. casam com o
  modelo real e não caem no fallback do mock. Sem dúvida de preço de LLM em aberto.
- **Eixo de cobrança = contato revelado.** Reconferido: `lead_qualificado=0`,
  `contato_revelado=1` conta no teto do mês, `revelar()` idempotente
  (`lead.revelado_em`), `mensagem_enviada`/`sinal_intencao` **não** mexem no teto
  de contatos — a correção acima não muda o eixo de cobrança, só o de contabilidade
  de receita já reconhecida. Nada voltou a cobrar por descoberta.
- **Balde certo e custos-fantasma dos dois lados** seguem fechados (`cost.py`
  deriva balde da chave; `registrar_llm` só emite lado com token > 0). Não toquei.

### Achado e NÃO corrigido (fica para outro dono / outra execução)
- **[meu escopo, edge estreita] Débito que ATRAVESSA o zero é 100% classificado
  como OVERAGE.** `creditos.py::debitar` faz `overage = estado.creditos < custo` e
  marca o lançamento inteiro como `OVERAGE` quando verdadeiro. Com saldo 1 e custo
  2 (só `sinal_intencao` custa 2), os **dois** créditos viram overage — o crédito
  que ainda existia no plano é valorizado ao preço de overage (mais caro),
  superestimando um tico a receita/margem. Cenário raro (exige saldo == 1 e op de
  custo 2) e o "certo" (1 base + 1 overage num único débito) mexe na estrutura do
  ledger — candidato a "uma coisa" futura, com cuidado contábil. Não é o mesmo bug
  de hoje.
- **[observabilidade, meu escopo, baixo] `latencia_ms` só no evento de ENTRADA.**
  Numa completude o evento de saída nasce `latencia_ms=None`. Não afeta os três
  pilares (preço/balde/fantasma); e replicar a latência nos dois eventos pode
  dobrar num painel que soma latência — a semântica é ambígua, então não mexi.
- **[adaptador, fora do escopo] WhatsApp: template de MARKETING cobrado ao preço de
  UTILITY** (`adapters/real/bsp_whatsapp.py`) — segue aberto (some com a revalidação
  F7). A tabela (meu escopo) tem as duas chaves certas; quem escolhe a chave é o
  adaptador.
- **[ambíguo, meu escopo] `custo_medio_lead_micros` soma os DOIS baldes** enquanto
  `tokens_por_lead` conta só tokens de IA — decisão de produto sobre o que a vitrine
  quer mostrar. Não mexi no chute.

### Depende de outros / decisão humana
- **Integração ao `main`** — este commit precisa chegar ao `main` (rebase + push).
- **`settings.usd_brl` fixo** (`config.py`, fora do escopo) — câmbio velho = margem
  BRL errada. Em produção precisa vir de fonte real.
- **Preço sem cadastro falha fechado só no boot** — a trava dura (recusar subir com
  `llm_model` sem preço, como o `JWT_SECRET`) mora em `config.py`, fora do escopo. A
  marca `preco_fallback` + aviso em `cost.py` é a rede.
- **Fase 7 (chaves + cartão)** — revalidar preços de DADOS (Places, SES, WhatsApp)
  contra o faturado real. Não invento valor de provedor.

---

## 2026-09-21 — débito que ATRAVESSA o teto: o crédito-base deixava de custar overage

### Corrigido
- **Um débito que cruzava o teto do plano marcava 100% como OVERAGE — inflava a
  receita/margem do painel.** `creditos.py::debitar` fazia `overage =
  estado.creditos < custo` e gravava o lançamento **inteiro** com
  `TipoCredito.OVERAGE` quando verdadeiro. Com saldo 1 e uma operação de custo 2
  (`sinal_intencao`, overage habilitado), os **dois** créditos viravam overage:
  o crédito que **ainda cabia no plano** (base) era valorizado ao preço de
  overage — mais caro (Pro: R$0,70/crédito de overage vs. R$0,4975/crédito-base).
  Como `margem.py` valoriza receita agrupando o ledger por `tipo`, o painel via
  `2 × R$0,70` em vez de `1 base + 1 overage`, e a margem aparecia **melhor do que
  a real**, dentro de um número que ninguém questiona. É o mesmo eixo deste radar
  ("a margem não pode ser ficção"), do lado da receita — o irmão exato das
  correções de overage/campanha de 20/09, agora no **cruzamento** do teto. Este
  achado estava **nomeado e adiado** na execução de 20/09 (2ª): "candidato a 'uma
  coisa' futura, com cuidado contábil".
  - **Por que NÃO é decisão de preço:** base e overage **já têm preço decidido**
    (o `CATALOGO`: `preço-base amortizado` e `overage_centavos_por_credito`).
    Aqui só **aplico** cada preço já existente ao crédito certo — a mesma lógica
    que a 1ª execução de 20/09 usou para dizer que o overage-receita "NÃO é
    decisão de preço". Não escolho quanto cobrar.
  - **Correção (só em `creditos.py::debitar`):** a parte do débito que **cabe no
    saldo** vira consumo-base (`disponivel = max(0, saldo)`; `parte_base =
    custo − parte_overage`); só o **excedente** (`parte_overage = max(0, custo −
    disponivel)`) vira `OVERAGE`. Quando o débito **não** cruza o teto — tudo
    base, tudo overage, ou custo 0 (`lead_qualificado`) — segue **uma única
    parcela, idêntica ao que era antes** (mesmo tipo, mesmo `metadados.overage`,
    mesmo `saldo_apos`, mesmo evento de auditoria). Só o **cruzamento** passa a
    gerar duas parcelas (base + overage). O `saldo_apos` final e o campo
    `overage` da auditoria ficam com o **mesmo valor** de antes (`parte_overage >
    0` == o antigo `saldo < custo` para saldo ≥ 0).
  - **Escopo do impacto HOJE:** só o **painel de margem** (`margem.py`), o único
    lugar do código que multiplica crédito de overage pelo preço de overage. Não
    há fatura ao cliente calculada a partir de lançamentos `OVERAGE` no código
    atual (Stripe é F7) — quando essa fatura existir, lerá a classificação já
    correta. Corrige o painel hoje e não estraga a cobrança amanhã.
  - **Cenário estreito, de propósito:** só dispara com overage habilitado **e**
    `0 < saldo < custo` (na prática, `sinal_intencao` de custo 2 com saldo 1, ou
    um débito com `quantidade > 1`). Sem overage, o débito é bloqueado antes —
    não cruza.
  - **Testes:** `tests/integration/test_fase7_margem.py::test_debito_que_cruza_o_teto_nao_valoriza_o_base_como_overage`
    (novo) — Pro, overage ligado, saldo 1, `sinal_intencao` (custo 2): a receita
    do painel tem de ser `R$0,4975 + R$0,70` (1 base + 1 overage), **não**
    `2 × R$0,70`. Falha antes (1,40), passa depois (1,20). Suíte inteira:
    `pytest` 480 passed / 3 skipped, `ruff` limpo.

### Verificado e OK (sem ação) — reconferido nesta execução
- **Tabela de LLM correta e atual — conferida contra a fonte autoritativa HOJE.**
  Opus 5 (US$5/US$25 por 1M), Sonnet 5 (US$2/US$10) e Haiku 4.5 (US$1/US$5) batem
  **exatamente** com a tabela da skill `claude-api` (cache 2026-06-24). Os IDs
  canônicos **não levam sufixo de data** (a própria fonte: "never append date
  suffixes") e o padrão `settings.llm_model="claude-opus-5"` resolve sem cair no
  fallback do mock. Sem dúvida de preço de LLM em aberto.
- **Eixo de cobrança = contato revelado.** Reconferido: `lead_qualificado=0`,
  `contato_revelado=1` (único que conta no teto do mês), `revelar()` idempotente
  (`lead.revelado_em`), `mensagem_enviada`/`sinal_intencao` **não** mexem no teto.
  A correção acima **não muda o eixo de cobrança** — só corrige a contabilidade da
  receita já reconhecida no cruzamento do teto. Nada voltou a cobrar por descoberta.
- **`mascarar()` não vaza contato por campo novo.** Cruzei `CAMPOS_OCULTOS` com o
  modelo `Lead` atual: todos os campos de contato/identidade (razão social, nome
  fantasia, CNPJ, e-mail, telefone[+normalizado], site, domínio, endereço) estão
  mascarados; `cep`, `latitude`, `longitude`, `place_id`, `resumo`, `contexto` e
  `embedding` **não** aparecem na saída da API; `provenance` carrega só a *fonte*
  do campo, não o valor. O paywall não vaza por um campo esquecido.
- **Balde certo e custos-fantasma dos dois lados** seguem fechados (`cost.py`
  deriva balde da chave; `registrar_llm` só emite o lado com token > 0, e (0,0)
  não registra nada). Não toquei.

### Achado e NÃO corrigido (fica para outro dono / outra execução)
- **[observabilidade, meu escopo, baixo] `latencia_ms` só no evento de ENTRADA.**
  Numa completude o evento de saída nasce `latencia_ms=None`. Não afeta os três
  pilares (preço/balde/fantasma); replicar nos dois pode dobrar num painel que
  soma latência — semântica ambígua, então não mexi (segue como em 20/09).
- **[ambíguo, meu escopo] `custo_medio_lead_micros` soma os DOIS baldes** enquanto
  `tokens_por_lead` conta só tokens de IA — decisão de produto sobre o que a
  vitrine quer mostrar. Não mexi no chute (segue como em 20/09).
- **[adaptador, fora do escopo] WhatsApp: template de MARKETING cobrado ao preço de
  UTILITY** (`adapters/real/bsp_whatsapp.py`) — segue aberto (some com a
  revalidação F7). A tabela (meu escopo) tem as duas chaves certas; quem escolhe a
  chave é o adaptador.

### Depende de outros / decisão humana
- **Integração ao `main`** — este commit precisa chegar ao `main` (rebase + push).
- **Modelo de reconhecimento de receita no cruzamento — confirmar com finanças.**
  A correção assume o óbvio: crédito dentro do plano = preço-base; excedente =
  overage. Se finanças quiser tratar o crédito de fronteira de outro jeito, é
  decisão do dono — mas hoje o painel bate com a definição do plano no catálogo.
- **`settings.usd_brl` fixo** (`config.py`, fora do escopo) — câmbio velho = margem
  BRL errada. Em produção precisa vir de fonte real.
- **Preço sem cadastro falha fechado só no boot** — a trava dura (recusar subir com
  `llm_model` sem preço, como o `JWT_SECRET`) mora em `config.py`, fora do escopo. A
  marca `preco_fallback` + aviso em `cost.py` é a rede.
- **Fase 7 (chaves + cartão)** — revalidar preços de DADOS (Places, SES, WhatsApp)
  contra o faturado real. Não invento valor de provedor.
