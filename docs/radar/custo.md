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
