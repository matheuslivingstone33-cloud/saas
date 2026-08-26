# Prospector AI

SaaS que **descobre, qualifica e inicia conversa** com os clientes ideais de um
prestador de serviço. MVP **100% B2B**.

> **Princípio central:** o sistema inteiro roda **sem nenhuma chave de API**.
> Toda dependência externa fica atrás de uma **porta** com **mock** funcional. Ir
> para produção é preencher o `.env`, virar os flags `*_MODE=real` **um por vez**
> e rodar os smoke tests — sem refatorar nada.

**Estado:** Fases 0 a 7 implementadas. 164 testes verdes, lint limpo.
Detalhes por fase em [`PROGRESS.md`](PROGRESS.md).

---

## O que o produto faz

```
serviço em texto livre                    "instalo e faço manutenção de ar condicionado"
        │
        ▼  MOTOR 2 — Cérebro
ramos que COMPRAM esse serviço            hotel, supermercado, clínica, colégio…
(e descarta quem o PRESTA: concorrente)   ✗ 4322302 instalação de ar condicionado
        │
        ▼  MOTOR 1 — Descoberta
empresas reais + CNPJ + contato           Google Places → Receita Federal → dedup
        │
        ▼  score explicável (0–100)
        │
        ▼  MOTOR 3 — Abordagem
e-mail personalizado, declarando ser IA    assistido: você aprova
                                           automático: o agente dispara
```

## Subir tudo (Docker)

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

Sobe `postgres` (pgvector), `redis`, `backend`, `worker` e `frontend`.
**Nenhuma chave necessária** — `PROVIDER_MODE=mock` é o padrão. O backend aplica
migrations e seed sozinho.

| Serviço | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| Documentação (Swagger) | http://localhost:8000/docs |

## Rodar sem Docker

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
```

```bash
cd backend && .venv/Scripts/alembic upgrade head && .venv/Scripts/python -m app.db.seed
```

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Sem `DATABASE_URL` o backend usa **SQLite** local; sem `REDIS_URL` a fila roda
**inline**. É o modo usado pela suíte de testes.

## Ver funcionando em um comando

```bash
cd backend && .venv/Scripts/python scripts/demo_fase0.py
```

Provedores em mock → campanha **assistida** (nada sai sem aprovação) → campanha
**automática** (dispara para `outbox/`) → leads com score e CNPJ → custo por
balde → integridade da auditoria.

## Testes

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

```bash
cd backend && .venv/Scripts/ruff check app tests scripts alembic
```

Roda **sem Docker, sem Redis, sem rede e sem chave** — inclusive os testes de
contrato dos adaptadores reais.

---

## Arquitetura — portas e adaptadores

O domínio depende **só das portas**. Um registry escolhe mock ou real por env.
Detalhes em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

| Dependência | Porta | Mock | Adaptador real | Flag |
|---|---|---|---|---|
| Google Places (New) | `PlacesPort` | `FakePlaces` | `GooglePlacesAdapter` | `PLACES_MODE` |
| LLM | `LLMPort` | `FakeLLM` determinístico | `AnthropicAdapter` (tool use) | `LLM_MODE` |
| Web search | `SearchPort` | `FakeSearch` | `AnthropicWebSearchAdapter` | `SEARCH_MODE` |
| E-mail | `EmailPort` | `FakeEmail` → `outbox/` | `SESAdapter` | `EMAIL_MODE` |
| WhatsApp | `WhatsAppPort` | `FakeWhatsApp` | `BSPAdapter` | `WHATSAPP_MODE` |
| CNPJ (Receita) | `EnrichmentPort` | dataset local | **o mesmo** (dado aberto) | — sem chave |
| Pagamento | `BillingPort` | `FakeBilling` | `StripeAdapter` | `BILLING_MODE` |

`GET /v1/providers` mostra o modo de cada porta em tempo real.

### Guardrails que são código, não promessa

- **Modo mock não toca a rede.** `HttpClient` levanta exceção em qualquer
  tentativa — inclusive no `guard()` que embrulha SDKs oficiais.
- **Sem scraping.** Descoberta só via Places API oficial.
- **Sem WhatsApp frio para PF.** E-mail é o canal; template exige flag explícita.
- **Opt-out consultado no momento do envio**, não na geração da mensagem.
- **Toda mensagem declara ser IA** e leva link de descadastro de 1 clique.
- **Todo custo em dois baldes que nunca se misturam**: 1 = dados, 2 = IA.
- **Auditoria imutável**, encadeada por hash + trigger no PostgreSQL.
- **Sem saldo, não há chamada externa** — o bloqueio vem antes de gastar.

## Estrutura

```
backend/app/
  core/          config, logging, pricing, http_client (retry, breaker, guard)
  db/            tipos portáveis (pgvector ↔ JSON), sessão, seed
  models/        12 tabelas + enums
  repositories/  Repository pattern + paginação (nada de SQL nas rotas)
  ports/         interfaces + DTOs — o domínio só conhece isto
  adapters/      mock/ (Fases 0–6) · real/ (Fase 7) · registry.py
  domain/        máquinas de estado (lead, campanha, assinatura)
  services/      cerebro, scoring, aprendizado, query_builder, descoberta,
                 personalizacao, envio, compliance, creditos, margem, audit
  api/           rotas FastAPI + schemas
  workers/       fila (RQ ou inline) e tarefas
frontend/src/    React + Vite + Tailwind (onboarding, campanhas, KPIs, créditos)
data/            CNAE (Cérebro), Receita (dado aberto), fixtures
docs/            arquitetura, runbook da Fase 7, deploy, LGPD, declaração de IA
```

## Documentação

| Documento | Para quê |
|---|---|
| [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) | como as peças se encaixam |
| [`docs/RUNBOOK-FASE7.md`](docs/RUNBOOK-FASE7.md) | virar mock → real, um provedor por vez |
| [`docs/DEPLOY-DIGITAL-OCEAN.md`](docs/DEPLOY-DIGITAL-OCEAN.md) | do droplet vazio ao ar |
| [`docs/POLITICA-DE-PRIVACIDADE.md`](docs/POLITICA-DE-PRIVACIDADE.md) | LGPD, em português claro |
| [`docs/DECLARACAO-DE-IA.md`](docs/DECLARACAO-DE-IA.md) | Marco da IA: o que é automatizado |

## Segredos

Nunca commite chave. `.env` está no `.gitignore`; `.env.example` tem **todas as
chaves vazias** (há teste que falha se alguma vier preenchida). Nenhum segredo
entra em imagem Docker — tudo é injetado em runtime.
