# Arquitetura

## Regra única

> O domínio depende **só de portas**. Nenhuma regra de negócio importa um SDK,
> monta uma URL ou conhece um provedor.

```
      rotas FastAPI
            |
      services/  (pipeline, leads, audit, cost)   <- regra de negócio
            |
      ports/     (PlacesPort, LLMPort, EmailPort, ...)   <- interfaces + DTOs
            |
   adapters/registry.py   <- ÚNICO ponto que conhece adaptador concreto
        /            \
  adapters/mock/    adapters/real/
   (sem chave)       (Fase 7: Places, Anthropic, SES, BSP, Stripe)
                          |
                  core/http_client.py  <- toda chamada externa passa aqui
                  (request() para HTTP cru, guard() para SDK oficial)
```

Trocar mock ↔ real muda **uma variável de ambiente**. Nenhum arquivo de domínio.

---

## Camadas

### `core/`
- `config.py` — `Settings` (pydantic-settings). `PROVIDER_MODE` global e
  `*_MODE` por provedor; `mode_for(provider)` resolve o efetivo.
- `http_client.py` — cliente único por provedor: timeout, retry com backoff
  exponencial + jitter (só em erro transitório), rate limit por token bucket,
  circuit breaker, idempotência, log estruturado e emissão de `cost_event`.
  **Em modo mock levanta `NetworkDisabledInMockMode`** — a rede fica fisicamente
  indisponível nas Fases 0–6.
- `pricing.py` — tabela de preços versionada, em micro-dólares. Define o balde
  de cada operação.
- `logging.py` — structlog em JSON, com `request_id`, latência e custo.

### `db/`
- `types.py` — `Vector` (pgvector no PostgreSQL, JSON no SQLite) e `JSONType`
  (JSONB no PostgreSQL). É o que permite a suíte rodar sem Docker.
- `session.py` — engine, `session_scope()` e dependência do FastAPI.
- `seed.py` — dados mínimos para tudo funcionar sem provedor real.

### `models/` — 14 tabelas
Multi-tenant por `user_id` em toda tabela de dado do cliente.

| Tabela | Papel | Destaques |
|---|---|---|
| `users` / `subscriptions` | conta e plano | `autonomy_level` ∈ {assistido, automatico}, saldo |
| `campaigns` | serviço + região + filtros | `expansao` guarda a decisão do Motor 2 |
| `leads` | empresa descoberta | `provenance` (defesa LGPD), `embedding` 384d, `score_breakdown` |
| `ramos_cnae` | base do Cérebro | descrição + `embedding` + termos de busca |
| `messages` | abordagem e resposta | `declaracao_ia`, `link_descadastro`, custo e tokens |
| `opt_outs` | supressão | global (`user_id` nulo) ou por tenant |
| `credit_ledger` | livro-razão | append-only, saldo derivado |
| `audit_logs` | trilha imutável | `seq` + `hash_anterior`/`hash` + trigger no PG |
| `cost_events` | custo por chamada | `balde` 1 (dados) ou 2 (IA), `modo` mock/real |
| `score_weights` | pesos do score por tenant | saída do loop de aprendizado, com estatísticas |
| `ramo_weights` | fator de mira por (tenant, CNAE) | Etapa 7: a intenção da resposta inclina a busca e **multiplica** o peso do Cérebro (piso 0,5 / teto 1,5) |
| `privacy_requests` | direitos do titular | tipo, protocolo, prazo de 15 dias, desfecho |
| `tentativas_acesso` | login e cadastro | Etapa segurança (migration 0012): rate limit por e-mail/IP e o registro de acesso do Marco Civil (6 meses) |

### `repositories/`
Repository pattern sobre SQLAlchemy. **Nenhuma rota escreve SQL.** Toda listagem
é paginada (`Page`, teto de 200 por página). Inclui:
- dedup de lead por CNPJ / `place_id` / telefone normalizado / domínio;
- busca vetorial (`<=>` do pgvector; fallback em Python no SQLite);
- resumo de custo agrupado por balde.

### `domain/`
Máquinas de estado puras (sem I/O), validadas em código:

```
lead:      descoberto -> qualificado -> enfileirado -> abordado -> respondido -> convertido
                    \_____________ descartado / opt_out _____________/
           opt_out é TERMINAL e irreversível.

campanha:  rascunho -> descobrindo -> qualificando -> pronta -> executando -> concluida
                                    (pausada e falhou como ramos; concluida pode iniciar nova rodada)

assinatura: assistido <-> automatico   (muda onde a mensagem nasce)
```

`status_inicial_mensagem(nivel)`:
- **assistido** → `aguardando_aprovacao` (nada sai sem humano);
- **automatico** → `aprovada` (vai para a fila, respeitando limites e opt-out).

### `services/`
- `audit.py` — trilha encadeada por hash; `verificar_cadeia()` aponta o primeiro
  registro adulterado.
- `cost.py` — `CostRecorder` grava `cost_events` (banco) ou em memória (testes).
  LLM sempre gera **dois** eventos (input e output).
- `leads.py` — única porta de entrada para mudar `lead.status`; cria lead a
  partir de `PlaceResult` + `CompanyRecord` já com `provenance`, e dispara o
  gancho do loop de aprendizado a cada transição.
- `pipeline.py` — orquestra os três motores; cada etapa delega ao serviço dono.

---

## Fluxo de uma campanha

```
 0. CreditService.pode_consumir("contato_revelado")  -> bloqueia ANTES de gastar
    (olha a cota de REVELAÇÃO: sem saldo para revelar, descobrir só gastaria balde 1)
 1. ExpansorDeServico.expandir()                     -> ramos + termos        [balde 2]
    (LLMPort.embutir + busca vetorial + filtro de concorrente)
 2. QueryBuilder.construir()                         -> consultas + custo estimado
 3. PlacesPort.buscar()                              -> PlaceResult[]         [balde 1]
 4. filtro B2B -> EnrichmentPort.buscar()            -> CNPJ                  [sem chave]
 5. dedup por CNPJ/place_id/telefone/domínio
 6. Lead com provenance                              -> audit_log(dado_coletado)
 7. ScoringService.pontuar() com pesos aprendidos    -> score explicável      [balde 2]
 8. qualificar NÃO debita crédito (Etapa 6: descobrir é barato e não se cobra)
 9. PersonalizationService.gerar()                   -> gancho do ramo        [balde 2]
    (web search só acima do limiar de score)
    -> REVELA o contato e DEBITA 1 crédito (contato_revelado), idempotente
10. SendService.despachar(): opt-out + limites + canal
    (a rodada para por "cota_de_contatos" AQUI, não na qualificação)
11a. assistido  -> aguarda aprovação humana (o rascunho já traz o contato revelado)
11b. automatico -> EmailPort.enviar()                -> audit_log             [balde 1]
```

## Custo — dois baldes que nunca se misturam

| Balde | Provedores | Unidade |
|---|---|---|
| **1 — Dados** | Places, Receita (custo zero), e-mail, WhatsApp | requisição / mensagem |
| **2 — IA** | LLM (tokens de entrada e saída), web search | token / busca |

O mock registra o custo **estimado** com `modo="mock"`, então o painel de margem
existe desde a Fase 0 e não é surpresa na Fase 7 — lá o smoke test compara o
estimado com o faturado.

## Multi-tenant

Toda consulta de dado do cliente filtra por `user_id`. Dedup também é por
tenant: dois clientes podem prospectar a mesma empresa, mas nenhum cliente
recebe a mesma empresa duas vezes.

## Serviços por fase

| Serviço | Fase | Papel |
|---|---|---|
| `cerebro.ExpansorDeServico` | 1 | serviço → ramos que compram (+ filtro de concorrente) |
| `scoring.ScoringService` | 1 | score 0–100 explicável, 6 componentes |
| `aprendizado.LoopAprendizado` | 1 | desfecho de lead reajusta os pesos do tenant |
| `query_builder.QueryBuilder` | 2 | expansão → consultas ao Places (round-robin, teto) |
| `descoberta.DiscoveryService` | 2 | Places → B2B → Receita → dedup → lead |
| `personalizacao.PersonalizationService` | 3 | gancho por ramo; intenção só em lead caro |
| `envio.SendService` | 3 | **único caminho de saída**: opt-out, limites, canal, autonomia |
| `compliance.*` | 4 | opt-out 1 clique, LIA, direitos do titular, retenção |
| `creditos.CreditService` | 5 | ledger, bloqueio sem saldo, vitrine de tokens |
| `margem.MargemService` | 7 | receita × balde 1 + balde 2, por cliente e por lead |

## O que ainda não é definitivo

| Item | Onde | Vira o quê |
|---|---|---|
| ~~auth por header `X-User-Email`~~ | `services/auth.py` | ✅ pago na Etapa 8: JWT com acesso de 30 min e renovação de 14 dias |
| ~~`/billing/confirmar` credita sem pagamento~~ | `api/routes/billing.py` | ✅ pago na segurança de 18/09: crédito só entra pelo que `BillingPort.consultar()` confirma, idempotente por `checkout_id`, plano pago fora do dev responde 402. Falta ainda a **verificação da assinatura** do webhook do Stripe real (Fase 7) |
| ~~`/v1/margem/consolidado` aberto~~ | `api/routes/system.py` | ✅ restringido em 18/09: `Depends(usuario_admin)`, 404 para quem não está em `ADMIN_EMAILS` |
| Receita em memória | `adapters/mock/receita_local.py` | tabela indexada no Postgres com o dump completo |
