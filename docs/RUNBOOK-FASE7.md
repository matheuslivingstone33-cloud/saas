# Runbook — Fase 7: virada de mock para produção

> **Regra de ouro: um provedor por vez.** Vire um `*_MODE` para `real`, rode o
> smoke test daquele provedor, confira o custo real contra o estimado, e só
> então passe ao próximo. Nunca vire todos juntos.

Os adaptadores reais **já estão implementados e testados por contrato** (com
transporte falso, sem chave — `tests/integration/test_fase7_adaptadores_reais.py`).
O que falta na virada é só: chave no `.env`, flag para `real`, smoke test.

```bash
cd backend && .venv/Scripts/python -m pytest tests/integration/test_fase7_adaptadores_reais.py -q
```

---

## 0. Antes de começar

```bash
cp .env.example .env
```

- [ ] `.env` não está versionado (confira o `.gitignore`).
- [ ] Nenhuma chave em imagem Docker — só variável de runtime.
- [ ] Tudo em `mock`: `GET /v1/providers` (exige login) ou, sem login,
      `python -c "from app.core.config import get_settings; print(get_settings().modes())"`
      (no servidor, dentro do container: `docker compose -f docker-compose.prod.yml exec backend ...`).
- [ ] Suíte verde: `pytest -q`.
- [ ] Painel de margem funcionando com valores estimados: `GET /v1/margem`.

O comando de verificação de cada etapa é sempre o mesmo:

```bash
cd backend && .venv/Scripts/python scripts/smoke.py <provedor>
```

O script **recusa rodar** se o provedor ainda estiver em modo mock — assim ele
não "passa" por engano contra o adaptador falso.

---

## 1. `EnrichmentPort` (Receita Federal) — **não tem chave**

Dado aberto. Em produção muda apenas o tamanho do dataset.

- [ ] Importar o dump completo de CNPJ no lugar da amostra.
- [ ] Apontar `RECEITA_DATASET_PATH`.
- [ ] Com o dump completo, migrar a busca para tabela indexada no PostgreSQL —
      o `EnrichmentPort` não muda, só a implementação por trás.

```bash
cd backend && .venv/Scripts/python scripts/smoke.py enrichment
```

---

## 2. `LLM_MODE=real` — Anthropic

- [ ] `ANTHROPIC_API_KEY` preenchida; `LLM_MODEL=claude-opus-5`.
- [ ] `OPENAI_API_KEY` preenchida **se** for usar embeddings reais
      (`text-embedding-3-small` com `dimensions=384` — o schema pgvector é
      `vector(384)` desde a Fase 0 e não deve mudar).

O que o adaptador já faz: loop de tool use com `buscar_empresas` (delegando ao
`PlacesPort`, nunca à Google direto) e `web_search_20260209`, `thinking:
adaptive`, `output_config.effort`, contagem de tokens virando `cost_event` no
balde 2, e `is_error` de volta ao modelo quando uma ferramenta falha.

```bash
cd backend && .venv/Scripts/python scripts/smoke.py llm
```

> **Bloqueio conhecido — metade resolvida (21/09):** o SDK fixado em
> `requirements-prod.txt` (`anthropic==0.69.0`) não tem o parâmetro
> `output_config` em `messages.create`. `anthropic_llm.py` passou a mandá-lo por
> `extra_body` (`1e4faed`): com chave fictícia e `ANTHROPIC_BASE_URL` apontando
> para uma porta fechada, `smoke.py llm` agora para em `Connection error` — o
> pedido é montado. **`anthropic_search.py:70` ainda passa o kwarg** e
> `smoke.py search` segue com
> `Messages.create() got an unexpected keyword argument 'output_config'`.
> Enquanto isso, **não ligue `EMAIL_MODE=real` junto com `LLM_MODE=real`**: com
> `SEARCH_MODE=mock`, o `FakeSearch` devolve manchetes inventadas ("X anuncia
> expansão de unidade") que viram o gancho do e-mail para lead com score ≥ 60.
> Detalhe em `docs/radar/deploy.md`.

- [ ] Comparar o custo estimado com o faturado no console da Anthropic.
- [ ] Ajustar `app/core/pricing.py` se divergir.

---

## 3. `PLACES_MODE=real` — Google Places API (New)

- [ ] `GOOGLE_MAPS_API_KEY` preenchida, API habilitada e **restrição de chave**
      configurada no console.
- [ ] Orçamento e alerta de cota definidos no Google Cloud.
- [ ] **Field mask enxuta** — cada campo extra pode mudar o SKU cobrado.
- [ ] **Proibido scraping** de Maps/Earth. Só a API oficial.

```bash
cd backend && .venv/Scripts/python scripts/smoke.py places --termo "supermercado" --regiao "Fortaleza, CE"
```

- [ ] Conferir que o `cost_event` do balde 1 bate com a fatura do Google.

---

## 4. `SEARCH_MODE=real` — web search da Anthropic

- [ ] Usa a mesma `ANTHROPIC_API_KEY`.
- [ ] Custa à parte (~US$10 por 1.000 buscas + tokens) → o
      `PersonalizationService` já limita por score mínimo e teto por lote.

```bash
cd backend && .venv/Scripts/python scripts/smoke.py search --termo "Hotel Brisa Mar Fortaleza"
```

---

## 5. `EMAIL_MODE=real` — AWS SES

O passo mais delicado: reputação de domínio não se recupera rápido.

- [ ] Domínio verificado no SES com **SPF, DKIM e DMARC** publicados.
- [ ] Saída do sandbox aprovada.
- [ ] Configuration set com SNS de bounce/complaint alimentando `opt_outs`.
- [ ] **Warmup**: `MAX_ENVIOS_POR_USUARIO_DIA` baixo no começo, subindo ao longo
      de semanas.
- [ ] Link de descadastro de 1 clique + header `List-Unsubscribe` — já implementado.

```bash
cd backend && .venv/Scripts/python scripts/smoke.py email --para voce@seudominio.com.br
```

- [ ] Abrir a mensagem recebida e conferir no cabeçalho: `spf=pass`, `dkim=pass`,
      `dmarc=pass`.
- [ ] Clicar no link de descadastro e confirmar que o contato foi suprimido.

---

## 6. `WHATSAPP_MODE=real` — BSP (Meta Cloud API)

- [ ] `WHATSAPP_BSP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_BUSINESS_ID`.
- [ ] **Nunca disparar frio para pessoa física.** Uso preferencial: INBOUND.
- [ ] Template só com `WHATSAPP_TEMPLATE_ENABLED=true` e destino PJ.
- [ ] Templates aprovados na Meta.

```bash
cd backend && .venv/Scripts/python scripts/smoke.py whatsapp --para +55SEUNUMERO
```

Use um número que já tenha escrito para você (janela de 24h aberta).

---

## 7. `BILLING_MODE=real` — Stripe

- [ ] `STRIPE_SECRET_KEY`.
- [ ] **Webhook assinado** `checkout.session.completed` creditando o ledger —
      não deixe o crédito depender de `POST /v1/billing/confirmar`, senão o
      cliente pode se creditar sozinho.
- [ ] Conciliação com `credit_ledger`.

```bash
cd backend && .venv/Scripts/python scripts/smoke.py billing
```

---

## 8. Deploy

Guia completo: [`DEPLOY-DIGITAL-OCEAN.md`](DEPLOY-DIGITAL-OCEAN.md).

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

- [ ] Postgres gerenciado **com pgvector** (ou container com volume persistente).
- [ ] `alembic upgrade head` no deploy; `SEED_ON_START=false`; catálogo de
      ramos carregado (o `start-api.sh` faz sozinho desde 21/09 — o log do
      backend mostra `catalogo de ramos: 64 no banco`).
- [ ] `APP_SECRET` e `JWT_SECRET` fortes.
- [ ] TLS via Caddy/nginx; backend e frontend só em `127.0.0.1`.
- [ ] Backup diário do Postgres **com restore testado**.
- [ ] Job diário de retenção (`app.workers.tasks.executar_retencao`).
- [ ] Alerta em `http_esgotou_tentativas` e em circuito aberto.

---

## 9. Painel de margem

Depois de cada virada, olhe a margem antes de aumentar volume:

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/v1/margem/consolidado
```

> Desde 18/09 esta rota só responde a quem está em `ADMIN_EMAILS` (404 para os
> demais). No `docker-compose.prod.yml` essa variável ainda não chega ao
> container — ver `docs/radar/deploy.md`.

- `custo.balde_1_dados_usd` — Places, Receita, e-mail, WhatsApp
- `custo.balde_2_ia_usd` — tokens de LLM e web search
- `por_lead.margem_brl` — **o número que decide se o preço do plano está certo**

Se a margem por lead ficar negativa fora do trial, o problema é preço ou
consumo — não escale volume antes de resolver.

---

## 10. Reverter

Qualquer provedor volta para mock trocando `*_MODE=real` por `mock` e
reiniciando o serviço. O código de domínio não muda — é o mesmo binário.

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Sem `--build` a troca do `.env` também vale, mas o comando é sempre o mesmo de
propósito: se houve `git pull` antes, `up -d` sozinho sobe código velho.
