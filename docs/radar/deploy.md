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

**Última execução:** 2026-09-21 · o `start-api.sh` carrega o catálogo de ramos
em toda subida (no Docker, a busca expandia para zero ramos); achados 🔴 novos de
outros donos: manchete inventada do `FakeSearch` vira gancho com IA real, e a
tela de créditos não funciona com Stripe real.

---

## 2026-09-21 — no servidor próprio, toda busca expandia para zero ramos

### O que corrigi

**No caminho Docker, o produto subia sem o catálogo de ramos.** Em 20/09 a
segurança/Vercel separou `carregar_catalogo()` do `semear()` e pôs a carga no
build do Vercel (`scripts/vercel_build.py`). O caminho do servidor próprio ficou
de fora: o `start-api.sh` só carregava alguma coisa com `SEED_ON_START=true`, e
o `docker-compose.prod.yml` fixa `false`. A API subia `healthy`, o cadastro
funcionava, e o Cérebro expandia **qualquer** serviço para 0 ramos — a busca não
achava ninguém e não havia erro em lugar nenhum. É o item 1 (🔴) da tabela de
16/09, que o HANDOFF registrava como "só relevante se voltar ao Docker" — mas o
`COLOCAR-NO-AR` inteiro é o caminho Docker.

**Correção** (`backend/scripts/start-api.sh`): depois do `alembic upgrade head`
e **antes** do seed, sempre roda `carregar_catalogo()` (idempotente) e imprime
`catalogo de ramos: N no banco (M acrescentados agora)`. Com `N == 0` a subida
**para** (`exit 1` → container `restarting`, `ERRO: catalogo de ramos vazio` no
log), coerente com as travas `${VAR:?}` do compose: melhor parar no deploy do
que abrir para cliente um produto que não acha ninguém. O worker não é afetado
(usa `start-worker.sh`).

**Como verifiquei, sem Docker:**

- **Reproduzi o defeito:** banco SQLite migrado com a lógica antiga e
  `SEED_ON_START=false` → `ramos no banco: 0`; `ExpansorDeServico.expandir("manutencao
  de ar-condicionado para empresas", "Fortaleza, CE")` → **0 ramos**.
- **Simulei o container:** cópia de `app/`, `alembic/`, `alembic.ini` e
  `scripts/` numa pasta com o layout de `/app`, `data/` no lugar do volume, e
  `alembic`/`python`/`uvicorn` como stubs no `PATH` (o `uvicorn` só imprime).
  Quatro cenários: (1) banco novo, `SEED_ON_START=false` → migra até `0012`,
  `64 no banco (64 acrescentados agora)`, chega ao `uvicorn`, saída 0;
  (2) segunda subida → `64 no banco (0 acrescentados agora)`; (3) banco novo com
  seed → catálogo e depois `seed ok: {... 'cnaes': 0 ...}` (sem duplicar);
  (4) sem `data/` → `ERRO: catalogo de ramos vazio`, **não** chega ao `uvicorn`,
  saída 1. Depois da correção, o mesmo `expandir` → **8 ramos** (clínica,
  hotel, ...).
- `yaml.safe_load` nos dois composes: o backend roda `/app/scripts/start-api.sh`
  com `./data:/app/data:ro`; `WORKDIR /app` no `Dockerfile`, que copia
  `scripts/` e dá `chmod +x`. Fim de linha LF (`.gitattributes` força `*.sh`),
  `sh -n` limpo.

**Não verificado:** a carga contra Postgres + pgvector de verdade (sem Docker).
É a mesma função que o build do Vercel roda contra o Neon; a coluna é
`Vector(384)` → `pgvector.sqlalchemy.Vector`. Se falhar, o `ps` do passo 3.5
mostra `restarting` e o log diz o motivo.

### Também nesta execução (documentos)

- **`COLOCAR-NO-AR`** reconferido contra o código e o HANDOFF: quadro "dois
  caminhos" (servidor próprio × Vercel, decisão do dono) no topo; ✅ de 18/09
  (limite de login, cobrança travada, margem só admin) e de 21/09 (IA,
  aquecimento automático, catálogo); a tabela de programação perdeu catálogo,
  cobrança e limite de login e ganhou "busca na web" (reescrita), "compra pela
  tela" e "painel de margem no servidor próprio"; decisões: caminho, rascunhos
  jurídicos, descadastro que acontece só de abrir o link. Passos: 3.5 confere a
  linha do catálogo no log; 5.1 não falha mais; 5.2 e 5.4 avisam da manchete
  inventada; 5.5/1.7 com o motivo novo para ficar no `sk_test_`; 6.6 explica o
  freio automático (números conferidos em `envio.py::_RAMPA_AQUECIMENTO`, conta
  todo e-mail das últimas 24 h e só barra abordagem fria); 7.3 → **15** tabelas
  (14 + `alembic_version`); 7.6 troca o `curl` da trilha (que agora responde 401)
  por `exec backend python -c "...verificar_cadeia()"`, testado aqui → `trilha
  integra`; 7.7 com as mensagens de `APP_SECRET` e do catálogo. 55 blocos
  `bash -n` ok, 19 âncoras e 9 links locais resolvem.
- **`DEPLOY-DIGITAL-OCEAN`**: trava de `APP_SECRET`; §5 explica e confere o
  catálogo; §9 com o comando da trilha; §10 marca limite de login e admin (com a
  ressalva do `ADMIN_EMAILS`) e acrescenta a busca na web.
- **`RUNBOOK-FASE7`** §2: bloqueio agora "metade resolvida", com o aviso de não
  ligar e-mail real com IA real; §8 inclui o catálogo; §9 a ressalva do admin.
- Reconferido sem rede (chave fictícia, `ANTHROPIC_BASE_URL=http://127.0.0.1:9`):
  `smoke.py llm` → `Connection error` (pedido montado — o `extra_body` de
  `1e4faed` funcionou); `smoke.py search` → ainda `unexpected keyword argument
  'output_config'`.

### O que achei e NÃO corrigi — nos MEUS arquivos (fila, em ordem)

1. **🆕 `ADMIN_EMAILS` não chega ao container.** O `docker-compose.prod.yml`
   passa variáveis só pela lista `environment:` (sem `env_file:`), e dentro do
   container não há `.env` (contexto `./backend`; `../.env` seria `/.env`).
   `ADMIN_EMAILS` não está na lista → `e_admin()` é falso para todos →
   `/v1/margem/consolidado` responde 404 **até para o dono**. O Vercel não tem o
   problema (a variável vai no painel). Mesma espécie, menor: `RETENCAO_LEADS_DIAS`
   e `RETENCAO_MENSAGENS_DIAS` estão no `.env.example` e são **ignorados** no
   servidor (vale o padrão 180/365 do código) — se o jurídico mudar o prazo no
   `.env`, nada muda e a Política promete outro número. Mapa completo (script
   `Settings.model_fields` × `environment:` × `.env.example`): no modelo e não
   repassados = `ADMIN_EMAILS`, `EMBEDDING_DIM`, `OUTBOX_DIR`,
   `RETENCAO_LEADS_DIAS`, `RETENCAO_MENSAGENS_DIAS`. Correção: acrescentar os três
   que importam ao `environment:` (com os mesmos padrões do código) e o
   `ADMIN_EMAILS` ao passo 3.4.
2. `.env.example` com placeholders não vazios e 200/500 envios/dia (item 1 de
   16/09). **Rebaixado:** desde 21/09 o warmup em `envio.py` freia a abordagem
   fria de domínio novo por código, e o passo 3.4 segue mitigando.
3. Log do Docker sem limite (item 2 de 16/09).
4. Tarefas diárias como script (item 3 de 16/09).
5. `.env.example` incompleto (item 4 de 16/09). Hoje faltam também os de 18/09:
   `LOGIN_MAX_FALHAS`, `LOGIN_JANELA_MINUTOS`, `LOGIN_MAX_FALHAS_POR_IP`,
   `CADASTRO_MAX_POR_IP_HORA`, `RETENCAO_REGISTROS_ACESSO_DIAS` (padrões ok).
6. `RUNBOOK-FASE7` fala da máquina de desenvolvimento (item 5 de 16/09, sem a
   parte do `--build`, feita em 18/09).
7. `DEPLOY` §7: cron chama `~/backup-prospector.sh`, que nenhum passo copia
   (item 6 de 16/09). A sugestão do `rate_limit` do Caddy saiu do §10 hoje.
8. Imagem do backend leva `tests/` e o `.db` de demo (item 7 de 16/09).
9. Backup só no disco do servidor (item 8 de 16/09).

### O que achei em código de OUTROS donos (só registro)

**16. 🔴 🆕 Manchete inventada vira gancho de e-mail real.** Com `LLM_MODE=real`
e `SEARCH_MODE=mock` — a combinação natural agora que a IA real funciona e a
busca real ainda quebra —, `PersonalizationService._sinais_de_intencao`
(`personalizacao.py:193`) chama o `FakeSearch`, que devolve títulos fabricados
(`"{empresa} anuncia expansao de unidade"`, `"... abre vaga para manutencao
predial"`); `_melhor_gancho` usa o 1º como gancho, e o `anthropic_llm.completar`
anexa o contexto (com `gancho` e `sinais`) ao pedido da IA real. Vale para lead
com score ≥ 60, até 5 por lote, 1º toque. E a mensagem ainda sai marcada
`usou_web_search=True`. Prova, sem rede: `gerar()` com a busca em mock e um LLM
que só guarda o pedido → `gancho = "Supermercado Bom Preco Ltda anuncia expansao
de unidade"`. Nenhum setting desliga (`usar_intencao` só é `False` na cadência).
Hoje **não há combinação segura** de IA real + e-mail real: busca real →
`TypeError` (item 14); busca mock → fato inventado para uma empresa real.
Correção possível: só usar sinais quando `portas.search.modo == "real"` (e
nunca marcar `usou_web_search` com resultado mock). `personalizacao.py` → Motor 3
/ Envio. **Mitigado** nos documentos: não ligar `EMAIL_MODE=real` com
`LLM_MODE=real` antes de o item 14 fechar.

**17. 🔴 🆕 A tela de créditos só funciona em mock.** `Creditos.tsx:49-53` chama
`api.comprar` e, na mesma hora, `api.confirmarCompra` — o botão diz "comprar
(mock)". Com `BILLING_MODE=real` o checkout ainda não foi pago, o `confirmar`
responde 402 (trava de 18/09), e a tela nunca manda o cliente ao `checkout.url`
do Stripe. Se ele pagar por outro caminho, a volta (`success_url =
URL_PUBLICA/creditos?compra=ok&sessao=...`) cai na landing (o app roteia por
`#/`) e nada chama `confirmar`. Engloba o item 7 de 16/09. `frontend/src/pages/
Creditos.tsx` + `stripe_billing.py` → frontend + Custo. Mitigado no documento:
`sk_test_` até a tela ficar pronta.

**14. 🟡 (era 🔴) SDK da Anthropic — metade fechada.** `anthropic_llm.py` usa
`extra_body` desde `1e4faed`; `anthropic_search.py:70` ainda passa o kwarg.
Reconferido hoje (acima). Sem dono. Agora pesa mais por causa do 16.

**15. ✅ `/v1/audit/integridade` exige login** (`usuario_atual`, conferido em
`system.py:152`). O risco 🟢 fechou; o efeito colateral foi quebrar o `curl` do
`COLOCAR-NO-AR` 7.6 e do `DEPLOY` §9 — trocados hoje.

**Tabela de 16/09 — estado em 21/09:** #1 catálogo → ✅ nos dois caminhos (Vercel
20/09, Docker hoje); #2 vetores do mock → aberto; #3 Receita → aberto; #4
resposta do lead → aberto (`/v1/inbound/email` só aceita o formato próprio com
HMAC); #5 retorno do SES → aberto (= 0.1 item 8); #6 cobrança → ✅ 18/09; #7
retorno do Stripe → absorvido pelo 17; #8 política 404 → aberto **no Docker**; o
build do Vercel já copia `docs/POLITICA-DE-PRIVACIDADE.md` (o texto antigo, não
o rascunho), então os dois caminhos publicam coisas diferentes — vale o dono
saber; #9 descadastro 1 clique → aberto; #10 smokes → aberto (`smoke.py:124`
ainda fixa `app.prospector.local`); #11 trava → `APP_SECRET` ✅, sobra
`WEBHOOK_SECRET`; #12 margem → ✅ 18/09 (mas ver meu item 1); #13 `/docs`
público → aberto.

### O que depende de outra rotina ou de decisão do dono

- **Itens 14 e 16 juntos** → quem assumir `anthropic_search.py` (sem dono) e
  Motor 3/Envio (`personalizacao.py`). Até lá, IA real e e-mail real não andam
  juntos.
- **Item 17** → frontend + Custo. Bloqueia `BILLING_MODE=real` com chave de
  produção.
- **Decisões do dono:** caminho (servidor próprio × Vercel) e quando subir;
  domínio; quais APIs e teto de gasto; ritmo do aquecimento; onde guardar a cópia
  fora do servidor; horário das tarefas diárias; aprovar os rascunhos jurídicos
  (libera o #8 no Docker); descadastro que acontece só de abrir o link.

### Próxima execução: por onde começar

Item 1 da fila dos meus arquivos (`ADMIN_EMAILS` e `RETENCAO_*` no `environment:`
do compose de produção + `ADMIN_EMAILS` no passo 3.4). Depois, reconferir os
itens 14, 16 e 17 e, se fecharem, tirar os avisos dos passos 1.7, 5.2, 5.4 e 5.5.

---

## 2026-09-18 — a imagem de produção não tinha os SDKs dos adaptadores reais

### O que corrigi

**Três das seis APIs reais quebrariam no dia da virada, e uma delas em
silêncio.** O `backend/Dockerfile` instalava só `requirements.txt`. Os SDKs que
os adaptadores reais usam — `anthropic` (LLM e busca), `boto3` (SES) e `stripe`
— moram em `requirements-prod.txt`, que **nenhum arquivo de build lia** (só o
`requirements-dev.txt`, por isso tudo passa nesta máquina). Os adaptadores fazem
`import` **dentro** da propriedade `cliente`, na primeira chamada real — então a
imagem sobe `healthy` em mock, sobe `healthy` com `*_MODE=real`, e quebra na
primeira chamada:

- `LLM_MODE`/`SEARCH_MODE=real` → `ModuleNotFoundError: anthropic` na primeira
  pergunta (500 na tela);
- `BILLING_MODE=real` → na primeira compra;
- `EMAIL_MODE=real` → o pior: o `SESAdapter` captura a exceção, o código do erro
  vira `ModuleNotFoundError`, que `classificar_falha_ses` classifica como
  **transitória** — nada pausa, ninguém é avisado, e **todo** e-mail vira
  `FALHOU`. Depois de 5, o circuito abre e o motivo passa a ser `CircuitOpen`,
  escondendo a causa. Simulado com `sys.modules["boto3"] = None`, sem rede: 8
  envios → 5 × `(False, transitoria, ModuleNotFoundError)` + 3 × `CircuitOpen`.

Places e WhatsApp usam `httpx` e não eram afetados. Os testes não pegam: injetam
cliente falso e nunca executam o `import`. É da espécie dos quatro de 09–11/09:
build passa, container sobe, e a falha só aparece rodando.

**Correção** (`backend/Dockerfile`): o estágio `builder` copia e instala os dois
arquivos (`pip install -r requirements.txt -r requirements-prod.txt`), e o
estágio `runtime` ganhou uma trava de build — `RUN python -c "import anthropic,
boto3, stripe"` — para que remover um SDK dos requirements quebre o **build**, e
não a primeira chamada paga. O `docker-compose.yml` de dev usa o mesmo alvo e
herda a correção.

**Como verifiquei, sem Docker:**

- script que lê o `Dockerfile`, pega os `-r` instalados e confere que cada um é
  copiado, fecha as dependências transitivas pelos metadados do venv, e cruza
  com **todo** `import` de `backend/app`, `backend/scripts` e `backend/alembic`
  (inclusive os de dentro de função, via AST). **Antes:** falha com `anthropic`
  (`anthropic_llm.py:100`, `anthropic_search.py:57`), `boto3`
  (`ses_email.py:83`) e `stripe` (`stripe_billing.py:48`). **Depois:** ok, 57
  pacotes, nada faltando;
- `pip check` limpo no venv que tem os dois arquivos instalados juntos (as
  versões fixadas convivem);
- `pytest` 428 verdes / 3 pulados e `ruff` limpo.

**Não verificado:** o build de verdade (sem Docker). O `RUN python -c "import
..."` roda com o `PATH` do venv já definido no estágio e com
`PYTHONDONTWRITEBYTECODE=1`; se falhar, o `up -d --build` do passo 3.5 para com
a mensagem na tela, antes de trocar qualquer container.

### Também nesta execução (documentos)

- **`GET /v1/providers` exige login** (responde 401 — conferido com
  `TestClient`), mas o `COLOCAR-NO-AR` (fase 5), o `DEPLOY` (§5 e §9) e o
  `RUNBOOK` (§0) mandavam usar `curl` sem token. Trocado por
  `docker compose ... exec backend python -c "...get_settings().modes()"`,
  testado aqui (`PLACES_MODE=real` → `'places': 'real'`).
- `RUNBOOK-FASE7` §10 "Reverter" passou a usar `up -d --build` (item 5 da fila
  de 16/09, parte do `--build`).
- `COLOCAR-NO-AR`: data de conferência, 428 testes, o link no corpo (item 7 da
  fila, fechado pelo Motor 3 em 18/09) e o bloqueio da Anthropic abaixo — na
  tabela do topo, no 5.1 e no 5.2, com o erro exato que o dono vai ver.

### O que achei e NÃO corrigi — código de OUTRO dono

**14. 🔴 O SDK da Anthropic fixado recusa a chamada que os adaptadores fazem.**
`requirements-prod.txt` fixa `anthropic==0.69.0`; `anthropic_llm.py:119`,
`:199` e `anthropic_search.py:70` passam `output_config={"effort": ...}` para
`messages.create`, e essa versão **não tem o parâmetro**. O Python recusa o
kwarg antes de montar a requisição. Prova, sem rede (chave fictícia e
`ANTHROPIC_BASE_URL=http://127.0.0.1:9`):

```
smoke.py llm → [falhou] Messages.create() got an unexpected keyword argument 'output_config'
```

`inspect.signature(Messages.create).bind(...)` confirma: sem `output_config`, a
chamada é aceita. O teste `test_fase7_adaptadores_reais.py:336` **afirma** que
`output_config` é passado — para um cliente falso, que aceita tudo. Efeito: com
`LLM_MODE=real`, **nenhuma** função de IA funciona (onboarding, Cérebro,
personalização, Motor 4) nem a busca na web. Correção possível: subir o
`anthropic` para uma versão que tenha `output_config` (conferir no changelog do
SDK qual) ou mandar por `extra_body`. `requirements-prod.txt` não tem dono nas
rotinas; os adaptadores `anthropic_*` ficam entre Custo e Cérebro. Minha trava
de build **não** pega isto (o `import` passa) — quem pega é o `smoke.py llm` do
passo 5.1, que agora avisa o dono do erro esperado.

Conferido também, sem achado: `botocore` 1.35.99 (o que o `boto3==1.35.76`
puxa) aceita `Content.Simple.Headers` no `SendEmail` do SESv2 (o
`List-Unsubscribe` vai por ali); `stripe` 11.4.1 aceita
`sessions.create(params=...)`.

**15. 🟢 `GET /v1/audit/integridade` é público** — responde 200 sem login com o
número de registros da trilha (conferido). Útil para a vigia do dia a dia
(`COLOCAR-NO-AR` 7.6), mas expõe o volume de atividade a quem conhecer o
endereço `api.`. Baixo risco. `api/routes/system.py:148` — rotas.

### Fila dos MEUS arquivos (de 16/09, sem mudança)

Itens 1 a 8 da entrada de 16/09 seguem abertos, na mesma ordem. O 5 perdeu a
parte do `--build` (feita hoje). O **1** (`.env.example` anulando as travas
`${VAR:?}` e o aquecimento) continua o próximo: segue mitigado pelo passo 3.4
do `COLOCAR-NO-AR`, e hoje o maior risco era o desta entrada — mitigação
nenhuma cobria a falta dos SDKs.

### O que depende de outra rotina ou de decisão do dono

- **Item 14** (SDK da Anthropic) → quem cuidar de `requirements-prod.txt` /
  `adapters/real/anthropic_*`. Bloqueia `LLM_MODE` e `SEARCH_MODE` reais.
- Da tabela de 16/09 (outros donos), nada foi fechado desde então. O item 9
  (descadastro sem "1 clique") mudou de figura: o link agora vai **visível no
  corpo** (Motor 3, `186f018`); segue faltando o `List-Unsubscribe-Post`
  (RFC 8058) e o link no corpo da resposta **manual** (`conversa.py`).
- Decisões do dono: as mesmas de 16/09 (domínio, provedor e quando subir, quais
  APIs e teto de gasto, aquecimento, onde guardar a cópia fora do servidor,
  horário das tarefas diárias, texto jurídico da Política).

### Próxima execução: por onde começar

Item 1 da fila dos meus arquivos (`.env.example`: tirar os placeholders não
vazios e os limites de 200/500, conferindo antes o que o desenvolvimento local
lê dali). Depois, reconferir se o item 14 foi corrigido e, se foi, tirar o aviso
dos passos 5.1/5.2 e a linha da tabela do `COLOCAR-NO-AR`.

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
