# Radar — Preparação para colocar no ar

> Diário da rotina `preparacao-para-o-ar`. Ela cuida **só** de:
> `docker-compose.prod.yml`, `docker-compose.yml`, `backend/Dockerfile`,
> `frontend/Dockerfile`, `frontend/nginx.conf`, `.env.example`, `Makefile`,
> `backend/scripts/*.sh`, `docs/DEPLOY-DIGITAL-OCEAN.md`,
> `docs/RUNBOOK-FASE7.md`, `docs/COLOCAR-NO-AR.md` e este radar.
>
> **O que procura:** defeitos da espécie dos quatro que só apareceram rodando
> (nginx sem permissão, healthcheck do worker, IPv6, CORS) — coisas que nenhum
> teste pega e que quebram no dia em que o sistema sobe de verdade. Uma
> correção por execução; o que é código de outro dono fica registrado aqui.
>
> **Limite desta máquina:** não há Docker. A validação é por leitura, por
> script Python contra o código e por simulação do layout do container.

**Última execução:** 2026-09-16 · link de descadastro chegando ao backend na
origem do frontend; `docs/COLOCAR-NO-AR.md` criado.

---

## 2026-09-16 — o link de descadastro abria a landing

### O que corrigi

**Todo e-mail real sairia com um link de descadastro que não descadastra.**

O link é montado como `URL_PUBLICA/descadastro/<token>`
(`services/compliance.py:111`, chamado por `envio.py`, `cadencia.py` e
`conversa.py`). `URL_PUBLICA` é a origem do **frontend** (`app.`): é a origem
que o CORS libera em produção (`config.py::origens_cors`) e o retorno do Stripe
(`stripe_billing.py:54`). Só que `/descadastro/{token}` é rota do **backend**,
montada na raiz, sem `/v1`. No servidor, `app.` vai para o nginx do frontend,
cujo único bloco era o coringa de SPA: `/descadastro/<token>` devolvia o
`index.html` com **200**. O titular via a landing e continuava recebendo
e-mail. Nenhum log, nenhum teste vermelho — e é o guardrail 4 (descadastro de 1
clique) e a base do legítimo interesse.

O mesmo valia para `POST /privacidade/solicitacao` (a Política de Privacidade
aponta para ele) e `GET /legal/*`.

**Correção** (`frontend/nginx.conf`): três blocos `location` (`/descadastro/`,
`/privacidade/`, `/legal/`) repassam ao `backend:8000` pela rede interna do
compose. `resolver 127.0.0.11` + variável no `proxy_pass` fazem o nome ser
resolvido a cada 30 s: um `up -d --build backend` troca o IP do container, e um
`proxy_pass` fixo seguiria mandando para o IP antigo (502) até o frontend
reiniciar. A página de descadastro sai com `Cache-Control: no-store` e
`Referrer-Policy: no-referrer` (o token está no caminho).

**Como verifiquei, sem Docker:**

- script que lista as rotas do `app.main` fora de `/v1` e confere que cada uma
  tem `location` com `proxy_pass` no `nginx.conf`, que o alvo é o serviço
  `backend` do `docker-compose.prod.yml`, que o frontend de produção usa o
  estágio `prod` e que o `Dockerfile` copia este arquivo. **Versão antiga: 4
  rotas sem repasse. Versão nova: nenhuma falha.** Chaves balanceadas e toda
  diretiva terminada em `;`;
- `TestClient`: token falso em `/descadastro/teste` → **400** com a página de
  erro. É o teste que o `COLOCAR-NO-AR` (passos 3.6 e 4.4) e o `DEPLOY` (§6)
  mandam rodar no servidor: **400 = certo, 200 = versão antiga**;
- `pytest` e `ruff` verdes.

**Não verificado:** `nginx -t` de verdade (sem Docker aqui). Diretivas usadas
(`resolver ... ipv6=off`, `set` no `server`, `proxy_pass $variavel` sem URI)
existem no nginx 1.27. O primeiro teste do servidor pega qualquer erro: se o
nginx não subir, o `ps` do passo 3.5 mostra `restarting`.

### Também nesta execução

- **`docs/COLOCAR-NO-AR.md` criado**, do zero ao sistema com APIs reais, em
  português simples. Os comandos de configuração (passos 3.3 e 3.4) foram
  executados numa cópia do `.env.example` com valores fictícios no lugar dos
  segredos: as 8 variáveis obrigatórias do compose ficam preenchidas, nada com
  `.local`/`localhost` sobra, e a URL do banco monta com a senha em hex. Os 53
  blocos de comando passam em `bash -n`. As duas tarefas diárias do passo 7.4
  (`executar_retencao`, `executar_cadencia`) rodaram contra um banco SQLite
  migrado e semeado.
- `DEPLOY-DIGITAL-OCEAN.md`: aponta para o `COLOCAR-NO-AR` e explica o teste do
  link (§6).

### O que achei e não corrigi — nos MEUS arquivos (fila das próximas execuções)

Em ordem de risco:

1. **`.env.example` anula as travas do compose de produção.** O compose recusa
   subir com `URL_PUBLICA`, `URL_API_PUBLICA` e `ENCARREGADO_EMAIL` vazios
   (`${VAR:?}`), mas o modelo vem com `https://app.prospector.local`,
   `http://localhost:8000` e `privacidade@prospector.local` — não vazios, então
   a trava não dispara. E `MAX_ENVIOS_POR_CAMPANHA_DIA=200` /
   `MAX_ENVIOS_POR_USUARIO_DIA=500` **passam por cima** do aquecimento do
   compose (`:-50` / `:-100`), porque quem segue o guia faz
   `cp .env.example .env`. Domínio novo a 500/dia vai para spam e não volta.
   **Mitigado** no `COLOCAR-NO-AR` 3.4 (sed + conferência). Correção: tirar os
   placeholders e os limites do modelo, sem quebrar o uso local (conferir o que
   o desenvolvimento lê dali antes de mexer).
2. **Log do Docker sem limite.** Nenhum serviço de `docker-compose.prod.yml` tem
   `logging:`; o driver padrão (`json-file`) cresce sem teto e enche o disco em
   meses — o Postgres para junto. Correção: âncora com `max-size`/`max-file`.
3. **Tarefas diárias como script.** O passo 7.4 agenda expurgo e cadência com
   linhas longas de `crontab`; o `DEPLOY` §8 só diz "coloque no cron". Um
   `backend/scripts/tarefas-diarias.sh <retencao|cadencia>` deixaria a linha
   curta e testável. Some quando a fila 0.1 item 5 agendar no worker.
4. **`.env.example` incompleto.** `config.py` lê e o modelo não documenta:
   `CADENCIA_*`, `BOUNCE_*`, `HTTP_*`, `CIRCUIT_BREAKER_*`, `DEBUG`,
   `SEED_ON_START`, `APP_NAME`, `API_PREFIX`, `FIXTURES_PATH`. Nenhuma linha diz
   se é obrigatória em produção. `APP_ENV` no `.env` é ignorado pelo compose de
   produção (fixo em `producao`), mas o `DEPLOY` §3 o lista como obrigatório.
5. **`RUNBOOK-FASE7.md` fala da máquina de desenvolvimento.** Os smokes usam
   `.venv/Scripts/python`; no servidor é
   `docker compose -f docker-compose.prod.yml exec backend python scripts/smoke.py <api>`
   (já assim no `COLOCAR-NO-AR`). §10 "Reverter" usa `up -d` sem `--build`
   (funciona para troca de `.env`, mas contraria a regra). §5 manda clicar no
   link do e-mail de teste, que é fictício.
6. **`DEPLOY-DIGITAL-OCEAN.md` §7:** o cron chama `~/backup-prospector.sh`, mas
   nenhum passo copia o script para lá — e ele está no git como `100644`, sem
   permissão de execução. O `COLOCAR-NO-AR` chama `sh <repo>/backend/scripts/...`.
   O teste de restauração fixa `-U prospector` (o `COLOCAR-NO-AR` fixa
   `POSTGRES_USER=prospector` por isso). §10 sugere o `rate_limit` do Caddy, que
   não vem no Caddy padrão (é módulo à parte) — conferir antes de recomendar.
7. **Imagem do backend leva o que não devia.** O contexto é `./backend`, então
   o `.dockerignore` da raiz não vale ali, e não existe `backend/.dockerignore`
   (não é meu arquivo). Entram na imagem `tests/` e o
   `backend/prospector.db.backup-20260831-110506` versionado (banco de demo).
   Baixo risco. Correção possível no `backend/Dockerfile`: copiar só `app/`,
   `alembic/`, `alembic.ini` e `scripts/`.
8. **Backup só no disco do servidor** — o que se perdeu em 11/09. O
   `COLOCAR-NO-AR` 7.2 oferece cópia semanal manual; cópia automática para fora
   depende de o dono escolher onde.

### O que achei em código de OUTROS donos (só registro)

| # | Risco | Onde | Dono provável |
|---|---|---|---|
| 1 | 🔴 **Catálogo de ramos vazio em produção.** `ramos_cnae` só é preenchido por `db/seed.py::semear`, junto com o usuário demo (senha pública) e as campanhas de exemplo. Produção roda `SEED_ON_START=false`. Medido em 16/09: banco migrado sem seed → `ExpansorDeServico.expandir` devolve **0 ramos**; com seed, 8. A busca perde o "quem consome" e a exclusão de concorrente. Correção: separar a carga do catálogo (idempotente) do resto do seed e rodá-la no start | `db/seed.py`, `services/cerebro.py` | Descoberta/Cérebro |
| 2 | 🔴 **Vetores do catálogo sempre do mock.** O seed vetoriza com `FakeLLM` mesmo com `LLM_MODE=real`; o serviço passa a ser vetorizado pela OpenAI e comparado com vetores de outro espaço → vizinhos sem sentido. Precisa revetorizar com o provedor ativo e guardar qual modelo gerou | `db/seed.py:148`, `services/cerebro.py:168` | Descoberta/Cérebro |
| 3 | 🔴 **Sem base da Receita, nenhum e-mail sai.** O compose aponta para `cnpj_full.csv`, que não existe e não tem importador; `ReceitaLocal` carrega tudo em memória (inviável com o dump completo em 4 GB). O Places não traz e-mail: sem a Receita, lead sem CNPJ **e sem e-mail**. **Nunca** apontar para `cnpj_sample.csv` em produção — os e-mails da amostra têm domínios com cara de reais | `adapters/mock/receita_local.py` | Descoberta |
| 4 | 🔴 **Resposta do lead não entra.** `/v1/inbound/email` espera formato próprio com HMAC; não há tradutor do recebimento do SES (MIME cru via SNS/S3). As respostas ficam na caixa do remetente e o Motor 4 não as vê | `api/routes/conversas.py` | Conversa + rotas |
| 5 | 🔴 **Retorno do SES sem rota** (= HANDOFF 0.1 item 8). Sem ela, reclamação de spam não suprime | `api/routes/entregabilidade.py` | Envio + rotas |
| 6 | 🔴 **Cobrança burlável.** `POST /v1/billing/plano` troca para qualquer plano e recarrega créditos sem pagamento. `POST /v1/billing/confirmar` credita o `pacote` do corpo (não o do checkout) e não é idempotente por `checkout_id` — o mesmo checkout pago credita de novo. Travar antes de `STRIPE_SECRET_KEY` real | `api/routes/billing.py` | Custo/Crédito + rotas |
| 7 | **Retorno do Stripe cai na landing.** `success_url` = `URL_PUBLICA/creditos?...`, mas o frontend roteia por hash (`#/creditos`) | `adapters/real/stripe_billing.py:59` | Custo + frontend |
| 8 | **Política e declaração de IA dão 404 em produção.** `resolve_path("docs/...")` procura em `/app` e `/`, e a imagem do backend não tem `docs/`. Simulado em 16/09 (layout sem `docs/` → 404 nas duas). A correção é minha (montar `./docs:/app/docs:ro` no compose), **mas publica um texto que o radar de Compliance marca como pendente de revisão jurídica** — fica para quando o dono aprovar o texto | `api/routes/compliance.py:125` + compose | Deploy, após decisão |
| 9 | **Descadastro sem o "1 clique" do Gmail/Yahoo.** Falta `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058), e a rota só aceita GET (o POST levaria 405; o nginx já repassa POST). Efeito colateral do GET que descadastra: antivírus corporativo que abre links para checar pode descadastrar lead sozinho — favorece o titular, mas some com leads em silêncio | `services/envio.py:527`, `api/routes/compliance.py:67` | Envio + Compliance (decisão de produto/jurídica sobre o GET) |
| 10 | **Smokes incompletos.** `smoke.py llm` não chama `embutir` (OpenAI é obrigatória com IA real; o `COLOCAR-NO-AR` 5.1 tem o comando extra). `smoke.py email` usa link fixo `app.prospector.local` em vez de `URL_PUBLICA` | `backend/scripts/smoke.py` (não é `*.sh`) | quem tiver a alçada dos scripts |
| 11 | **Trava de produção só olha o `JWT_SECRET`.** `APP_SECRET` (assina o token de descadastro) e `WEBHOOK_SECRET` fracos passam; `URL_PUBLICA`/`ENCARREGADO_EMAIL` com `.local` também | `services/auth.py:188` | Autenticação/config |
| 12 | `/v1/margem/consolidado` aberto a qualquer conta logada (já no `ARQUITETURA`) | `api/routes/system.py:117` | rotas |
| 13 | `/docs`, `/redoc` e `/openapi.json` públicos em produção — mapa da API exposto. Baixo risco | `main.py:79` | rotas |

### O que depende de decisão do dono

- Domínio, provedor do servidor e **quando** subir (HANDOFF 0.2).
- Quais APIs ligar e em que ordem; teto de gasto de cada uma.
- Velocidade do aquecimento do e-mail (sugestão 20 → 50 → 100 por dia no
  `COLOCAR-NO-AR` 6.6).
- Onde guardar a cópia de segurança fora do servidor.
- Horário das tarefas diárias (sugestão: expurgo 06:30 UTC, cadência 12:00 UTC).
- Aprovar o texto da Política de Privacidade (revisão jurídica) → libera o item
  8 da tabela acima.

### Próxima execução: por onde começar

Item 1 da lista "nos meus arquivos" (`.env.example` anulando as travas).
Depois, conferir se o `COLOCAR-NO-AR` ainda bate com o código e o HANDOFF —
principalmente a tabela "O que ainda precisa de programação", que muda quando
as outras rotinas fecham itens.
