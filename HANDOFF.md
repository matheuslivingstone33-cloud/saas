# HANDOFF — Prospector AI

> **Leia isto primeiro ao abrir uma conversa nova.** Este arquivo é a memória do
> projeto: o que estamos construindo, por quê, o que já está pronto, o que falta
> e onde exatamente paramos.
>
> **Regra:** quem trabalhar aqui atualiza este arquivo ao terminar cada etapa.
> Um handoff desatualizado é pior que nenhum, porque leva a decisão errada com
> ar de confiança.

**Última atualização:** 2026-08-31 · Etapa 6 concluída — cobrar por revelação

---

## 0. Onde paramos — leia isto antes de qualquer coisa

**Estado em 31/08/2026:** Etapas 0 a 6 fechadas. **290 testes verdes**,
`ruff` e `tsc --noEmit` limpos, migrations sobem e descem nos dois dialetos.
Tudo commitado **e publicado**: `main` == `origin/main`, último commit
`2784efe`. Nenhuma chave de API — o sistema inteiro roda em mock.

Para retomar, três comandos (detalhe na seção 5):

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests -q
```

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd backend && .venv/Scripts/python.exe scripts/limpar_demo.py --aplicar && .venv/Scripts/python.exe scripts/demo_fase0.py
```

O terceiro devolve o banco de demonstração a um estado limpo e povoado —
útil antes de abrir a interface para conferir alguma coisa.

### A próxima é a Etapa 7 — aprendizado por intenção

**A ideia.** O `LoopAprendizado` aprende com o **desfecho** do lead, que é um
sinal raro e tardio. Desde o Motor 4 existe um sinal mais barato e muito mais
cedo: a **intenção da resposta**. Vinte `recusa` no mesmo CNAE não é azar — é
o Cérebro tendo errado o ramo. Argumento completo em
[docs/IDEIAS.md](docs/IDEIAS.md) §7.

**Comece verificando o que já chega.** Isto muda o tamanho da etapa e o
`docs/IDEIAS.md` exagera um pouco: parte do sinal de intenção **já** alimenta
o loop hoje, de carona na máquina de estados. `recusa` leva o lead a
`descartado` e `pedido_opt_out` leva a `opt_out` — os dois estão em
`FRACASSO`; qualquer resposta leva a `respondido`, que está em `SUCESSO`. E
`LeadService.transicionar` chama `aprendizado.observar` em toda transição
([services/leads.py:58](backend/app/services/leads.py)). Meça antes de
construir: pode ser que falte menos do que parece.

**O que de fato falta**, e é o coração da etapa:

1. **Aprendizado por RAMO, não só por componente de score.** Hoje
   `aprendizado.py` ajusta os pesos dos seis componentes do score
   (`COMPONENTES` em `services/scoring.py`). O peso do **CNAE** vem do
   Cérebro e é igual para todo tenant: se hotel não responde para *este*
   cliente, nada aprende isso. É aqui que mora o fosso — cada cliente afina a
   própria mira, e o ativo é o histórico dele.
2. **Distinguir as intenções entre si.** Para a máquina de estados, `recusa`
   e `pedido_opt_out` acabam no mesmo balde de fracasso. Não são a mesma
   coisa: "já temos fornecedor" diz que o ramo está certo e o momento errado;
   "me tire da lista" diz que a mira está errada. Misturar as duas ensina o
   Cérebro a fugir de ramo bom.
3. **Um lugar para guardar o peso por (tenant, CNAE).** `ScoreWeights` guarda
   pesos de componente. Peso por ramo precisa de coluna/tabela nova — e,
   pelas outras etapas, **migration** (ver guardrail 7).

**Onde mexer:** `services/aprendizado.py` (o loop), `services/conversa.py`
(onde a intenção é classificada — é de lá que sai o gancho novo),
`services/cerebro.py` (o peso do ramo, hoje sem ajuste por tenant) e
`models/learning.py`.

**A armadilha desta etapa:** aprendizado que se move rápido demais vira
superstição. O loop atual já tem as defesas certas — mínimo de 20 amostras,
passo amortecido de 0.15, piso/teto e `restaurar_padrao()`. O que for
acrescentado precisa das mesmas, e por um motivo concreto: com três respostas
ruins de hotel, um loop guloso apagaria hotéis da mira do cliente para
sempre — e ninguém veria isso acontecer, porque ausência de lead não aparece
em tela nenhuma.

---

## 1. O que é o produto

SaaS que **descobre, qualifica e conversa** com os clientes ideais de um
prestador de serviço. 100% B2B.

O pulo do gato: o cliente descreve o que ele **faz** ("manutenção de
ar-condicionado") e o sistema encontra quem **consome** isso (supermercado com
câmara fria, hotel, clínica) — não quem faz a mesma coisa. Concorrente é
descartado explicitamente.

**Público:** prestador de serviço pequeno e médio no Brasil — refrigerista,
eletricista, empresa de manutenção predial, engenheiro.

---

## 2. Visão de produto (definida com o Aislan em 30/08/2026)

A estrutura que estamos perseguindo, em ordem da jornada do usuário:

### 2.1 Landing page
Primeira visão do negócio. Tem que passar **alto valor** — parecer algo que vai
impulsionar as vendas de verdade. Dois botões:

- **"Usar de forma gratuita"** → leva ao onboarding por chat
- **Suporte** → WhatsApp com IA (ver 2.5)

### 2.2 Onboarding por chat com IA
**Substitui o formulário.** Em vez de "escolha seu serviço e localização":

- **H1:** "Me conte sobre sua empresa"
- **P:** "precisamos dessas informações para encontrar os melhores clientes para você"
- Abaixo, um chat com a IA.

Roteiro da conversa:
1. **Autônomo ou empresa?** — a pergunta personaliza o que vem depois; ela não
   desqualifica ninguém. Um refrigerista autônomo é cliente ideal. O guardrail
   B2B vale para quem é PROSPECTADO (só PJ), não para quem usa o produto.
2. Se **autônomo**: "me conta em uma ou duas linhas o que o seu negócio faz"
3. Se **empresa**: pergunta o nome, depois "me conta em uma ou duas linhas o que
   a {nome_empresa} faz?"
4. A IA configura de forma imersiva os leads que vai procurar, podendo dar dicas
   básicas sobre o negócio.

O usuário fica nessa tela até o negócio estar configurado. Só então avança.

### 2.3 Descoberta
Resultado da busca. Referência visual do protótipo:

> **"Encontramos 42 empresas precisando de Manutenção de ar-condicionado na sua região."**
> Foz do Iguaçu – PR · Dados públicos de empresas · LGPD
>
> As 3 melhores oportunidades para você — *39 empresas restantes disponíveis no plano PRO*
>
> Cartões com: nome, ramo, **score %**, **INSIGHT DA IA** ("Possui câmara fria de
> grande porte"), faixa de funcionários, bairro, botão **"Iniciar Abordagem com IA"**

### 2.4 Conversas
A tela onde o produto entrega a promessa. Lista de conversas à esquerda com
estado (**Em negociação**, **Aguardando resposta**, **Primeiro contato enviado**),
thread à direita, alternância **Abordagem IA / Manual**, botões **"Rodar ao vivo"**
e **"Piloto automático"**.

Quando o lead esquenta, aparece a faixa de conversão. O protótipo trazia:
> 🔥 O lead está aquecido e quer fechar! O Prospector AI já preparou a proposta.
> **[Assinar PRO e Agendar Reunião Automaticamente]**
> *Assumir chat manualmente de forma gratuita*

> ⚠️ **Este botão foi recusado de propósito — não o reconstrua sem decidir de
> novo.** Ele junta duas decisões diferentes (cobrar e marcar reunião) num
> clique só, usando a empolgação do momento para vender. Hoje a faixa leva a
> **"assumir a conversa"**, que abre a caixa de escrever (Etapa 5); o plano a
> pessoa decide quando quiser. **Agendamento automático não existe** e é a
> única promessa do protótipo ainda sem código — se for construir, veja
> [docs/IDEIAS.md](docs/IDEIAS.md).

### 2.5 Suporte por WhatsApp com IA
Diferencial: o suporte é feito por IA no WhatsApp, mandando áudio, soando
natural — para o cliente **ver a qualidade da nossa IA na prática**.

> ⚠️ **Restrição que não é negociável:** a IA pode soar natural, mandar áudio e
> ter jeito de gente, mas **precisa dizer que é IA**. Está no Marco da IA e no
> nosso guardrail. Na prática é uma linha na primeira mensagem — e joga a favor:
> mostra a qualidade da automação em vez de escondê-la.
>
> Isso é **inbound** (o cliente procurou a gente), então não esbarra na proibição
> de WhatsApp frio.

### 2.6 Planos
- **Grátis:** 10 **contatos revelados** por mês, sendo **3 por busca**
- **PRO:** desbloqueia o restante ("39 empresas restantes disponíveis no plano PRO")

> Implementado na Etapa 6. O que se cobra é o **contato revelado**, não o lead
> descoberto: a descoberta inteira aparece na tela, com ramo, bairro, porte,
> score e insight — só o contato fica atrás da cota.

---

## 3. Estado atual

### 3.1 O que está pronto e testado

Fases 0 a 7 concluídas (detalhe em [PROGRESS.md](PROGRESS.md)). Em resumo:

| Motor | O que faz | Estado |
|---|---|---|
| **Cérebro** (Motor 2) | serviço livre → ramos que CONSOMEM (CNAE), com peso e exclusão de concorrente | ✅ |
| **Descoberta** (Motor 1) | QueryBuilder → Places → Receita Federal → dedup | ✅ |
| **Abordagem** (Motor 3) | personalização + envio com limites, opt-out e autonomia | ✅ |
| **Conversa** (Motor 4) | receber, classificar intenção, responder ou se calar | ✅ |
| **Cadência** (Motor 5) | 2º e 3º toque com ângulo próprio, e onde a cadência para | ✅ |

Também prontos: compliance LGPD completo (LIA, opt-out de 1 clique, direitos do
titular, retenção, auditoria encadeada por hash), créditos e planos com teto e
bloqueio, custo em dois baldes que nunca se misturam (1 = dados, 2 = IA), painel
de margem, adaptadores reais dos provedores, execução ao vivo por SSE, revisão
por teclado, paleta de comandos (Ctrl+K), tema claro/escuro.

**290 testes verdes · lint limpo.**

### 3.2 O Motor 4, e a decisão que ele carrega

O sistema deixou de ser de mão única. Quando uma resposta chega, o motor
registra, **classifica a intenção** e decide — e a decisão mais importante é
**quando não responder**:

| Intenção | O que acontece |
|---|---|
| `pedido_opt_out` | registra a supressão e para. Para sempre. |
| `recusa` | respeita o não, descarta o lead, não insiste |
| `pedido_humano` | devolve para a pessoa, **mesmo em piloto automático** |
| `ausencia` | resposta de férias não é resposta; nada a fazer |
| `interesse` | responde e marca lead quente |
| `duvida` / `objecao` | responde, sem inventar preço |

A classificação é **lexical primeiro**, LLM só no ambíguo. Isso tira o caso
crítico das mãos do modelo: "me tire da lista" não pode depender de
interpretação. E "não quero receber, mas quanto custa?" é opt-out — em caso de
dúvida o direito do titular ganha do negócio.

---

## 4. Plano de execução

Uma etapa por vez, testando cada coisa feita. A ordem começou pela jornada do
usuário (etapas 1 a 3) e depois passou a seguir o que mais move resultado —
o argumento de cada uma está em [docs/IDEIAS.md](docs/IDEIAS.md) §11.

| # | Etapa | Estado |
|---|---|---|
| 0 | **Este handoff** | ✅ feito |
| 1 | **Navegação nova** — Busca / Descoberta / Conversas | ✅ feito |
| 2 | **Landing page + onboarding por chat** | ✅ feito |
| 3 | **Conversas / Motor 4** — o motor de conversa | ✅ feito |
| 4 | **Cadência (Motor 5) + supressão de bounce** | ✅ feito |
| 5 | **Resposta manual dentro do produto** | ✅ feito |
| 6 | **Paywall no servidor + cobrar por revelação** | ✅ feito |

As etapas seguintes, com o argumento de cada uma, estão em
[docs/IDEIAS.md](docs/IDEIAS.md).

### O que a Etapa 6 entregou

O corte das "3 melhores" era um `slice(0, 3)` na **tela**: a API devolvia as
42 empresas com CNPJ, e-mail e telefone. Qualquer pessoa com o devtools aberto
— ou um `curl` — via tudo que o plano PRO cobrava. Cortina, não porta.

- **O corte é do servidor** (`services/revelacao.py`). A lista **inteira**
  continua visível: ramo, bairro, porte, score e o insight de cada empresa. O
  que fica atrás da cota é o **contato** — razão social, CNPJ, e-mail,
  telefone, site. Ver que existem 39 hotéis com o perfil certo e não poder
  falar com eles é exatamente o que faz pagar; esconder que eles existem não
  vende nada.
- **O eixo da cobrança mudou.** Descobrir deixou de custar crédito; **contato
  revelado** passou a custar. Cobrar por lead descoberto punia o cliente
  quando o Cérebro errava a mira: ele pagava pelo nosso erro.
- **Duas travas, decididas com o Matheus em 31/08:** 3 contatos por busca e
  teto de 10 por mês no plano grátis. Só a mensal deixaria o usuário gastar
  tudo numa busca e ficar sem nada na seguinte; só a por-busca não protegeria
  o custo. Planos pagos não têm a trava por busca — quem paga já está
  limitado pelo teto do mês, e uma segunda regra viraria dúvida no suporte.
- **Abordar revela.** A mensagem cita o nome da empresa no corpo e o e-mail no
  destinatário: sem cobrar ali, o paywall cairia com um clique em "iniciar
  abordagem". E revela na **geração**, não no envio — no modo assistido o
  rascunho já mostra tudo enquanto espera aprovação.
- **Revelar é idempotente.** Um duplo clique não pode custar dois créditos.
- **A mensagem do bloqueio diz a regra que está valendo.** Quem esbarrou na
  trava da busca lê "3 por busca", não "créditos insuficientes" — a segunda
  mandaria comprar crédito que não destravaria nada.
- **Migration 0009** (`leads.revelado_em`), com backfill: todo lead que já tem
  mensagem nasce revelado.
- **18 testes.**

> **O que isso resolveu do plano:** as divergências 1 e 2 da seção 9.1 — o
> paywall de mentira e as duas tabelas de preço. "10 leads grátis" passou a
> significar **10 contatos revelados**, com a descoberta inteira visível.

### O que a Etapa 5 entregou

O botão "assumir a conversa" abria um `mailto:`. Parece equivalente e não é:
a resposta do lead voltava para a caixa pessoal do usuário, **fora do alcance
do Motor 4**, e a thread ficava com um buraco exatamente no trecho que decide
o negócio.

- **`ServicoDeConversa.responder_manualmente`** — a pessoa escreve, o
  `SendService` envia. Mesmo caminho de saída de sempre, mesmos guardrails.
- **Sem declaração de IA, com link de descadastro.** O Marco da IA manda
  declarar quando **é** IA; não manda mentir que é. Carimbar "escrita por um
  agente" no que a pessoa digitou seria declaração falsa. Já a LGPD não muda
  conforme quem digitou: continua sendo contato comercial não solicitado, e o
  descadastro continua.
- **O texto não passa por LLM.** Reescrever o que alguém digitou é colocar
  palavra na boca de quem assina. Há teste que falha se um LLM for chamado.
- **Opt-out não cede para humano nenhum.** O direito é do titular, não do
  remetente: enviar manualmente para um contato suprimido devolve 451.
- **`leads.assumido_em`** (migration 0008) — quando uma pessoa assume, o
  agente **cala**: nem toque de cadência, nem réplica do Motor 4. Sem isso o
  toque 2 sairia por cima da mensagem recém-escrita, dois remetentes falando
  ao mesmo tempo com o mesmo lead.
- **Assumir tem volta** — `POST /v1/leads/{id}/devolver-para-ia`. Sem isso um
  clique errado calaria aquele lead para sempre, e ausência de mensagem não
  aparece em tela nenhuma.
- **A thread diz quem escreveu.** O balão sai assinado "você" ou "Prospector
  AI", derivado do **mesmo campo** que carrega a declaração de IA: se a
  mensagem se declara escrita por um agente, foi o agente.
- **20 testes.**

### Detalhe de texto que valia consertar

O assunto da réplica cortava em contagem de caractere e saía
*"Re: manutencao predial preventiva: eletrica, hidraulica e climat"*. Agora
corta em palavra inteira e fecha com reticências — sem elas o corte cai no
meio de uma enumeração e parece erro de digitação, não texto cortado. É a
linha que a pessoa lê antes de decidir se abre.

### O que a Etapa 4 entregou

- **`services/cadencia.py`** — o Motor 5. Três toques (D0, D+3, D+7), cada um
  com **ângulo próprio**: o insight, a prova, e a saída ("encerro por aqui?").
  Nunca "seguindo minha mensagem anterior" — isso confessa que ninguém quis
  responder e transfere ao lead a culpa pelo silêncio.
- **Sem tabela nova.** Um toque é uma `messages` como qualquer outra, com o
  número do toque nos metadados e chave de idempotência por toque
  (`campanha:lead:email:t2`). O que decide o toque é o **estado da conversa
  lido na hora**, não um agendamento gravado — assim nenhuma linha velha de
  fila consegue disparar para quem já respondeu.
- **`services/entregabilidade.py`** — o retorno do provedor. Bounce permanente
  suprime e descarta; reclamação de spam suprime com origem própria e manda o
  lead para opt-out; retorno temporário **não suprime nada** (caixa cheia hoje
  não é cliente ruim para sempre). Acima de 2% de retorno a campanha **pausa
  sozinha**, com amostra mínima de 20 envios.
- **`POST /v1/inbound/retorno`** (webhook, 202 mesmo sem casar) e
  **`POST /v1/leads/{id}/simular-retorno`** (só em mock, igual ao Motor 4).
- **`GET /v1/cadencia`** e **`POST /v1/cadencia/executar`**; `forcar=true` pula
  **só a espera** e não existe com `EMAIL_MODE=real`.
- **Migration 0007** — `messages.retorno` (coluna, não chave em JSON: é dela
  que sai a taxa, e a conta tem que rodar igual nos dois dialetos) mais
  `origem_opt_out.reclamacao_spam` e `tipo_evento.bounce_registrado`.
- **A tela deixou de mentir por omissão.** O rodapé dizia "aguardando o lead
  responder" e dava a entender que o sistema tinha desistido. Agora diz
  "Toque 1 de 3 enviado. O próximo sai em 3 dias" — e, quando acaba, por que
  acabou.
- **27 testes** do Motor 5, a maioria sobre quando o toque **não** sai.

### O bug que só apareceu ao abrir a tela

**`concluida` não pode parar a cadência.** Eu tinha posto `concluida` junto de
`pausada` e `falhou` na lista de campanhas que não recebem toque. Parece
óbvio — e está errado: **toda** campanha termina em `concluida` assim que o
pipeline roda, e a rodada acaba em segundos enquanto o toque 2 sai três dias
depois. Com isso o Motor 5 nunca rodaria para ninguém: código morto com
cobertura verde, porque as fixtures do teste usavam `executando`. Só apareceu
ao abrir Conversas no navegador e ver a lista de cadência vazia. O que encerra
a cadência é o estado do **lead**, não o da rodada que o encontrou.


### O que a Etapa 3 entregou

- **`services/conversa.py`** — o Motor 4 (ver 3.2).
- **`POST /v1/inbound/email`** — webhook do provedor. Devolve 202 mesmo sem
  achar o lead: 404 diria a quem perguntasse quais e-mails estão na base.
- **`POST /v1/leads/{id}/simular-resposta`** — só em modo mock, e a rota se
  recusa a funcionar com `EMAIL_MODE=real`. Sem ela o Motor 4 só seria testável
  depois de ligar provedor pago.
- **Thread de duas pontas** na interface, com o balão do lead à esquerda, faixa
  de lead quente e simulador com um exemplo por caminho do motor — inclusive os
  três que fazem o agente se calar.
- **28 testes** do Motor 4, a maioria verificando **quando ele se cala**.

### Dois bugs reais encontrados na Etapa 3

- **Ordem da thread saía invertida.** A ordem vinha de `created_at`, e relógio
  não serve como chave aqui: `datetime.now()` no Windows tem granularidade de
  ~15 ms, então a pergunta do lead e a réplica da IA — nascidas no mesmo turno —
  saíam com carimbo **idêntico**, e a resposta aparecia antes da pergunta.
  Corrigido com `messages.ordem` (migration 0006), mesma solução de
  `audit_logs.seq`. O backfill desempata por `direcao`, senão reproduziria o bug
  nos dados antigos.
- **Rodapé mentia depois da resposta.** Dizia "aguardando o lead responder"
  quando o lead já tinha respondido. Eram quatro situações tratadas como duas.

### O que a Etapa 1 entregou

- **Busca** (`pages/Busca.tsx`) — "Quem você quer atender hoje?": serviço + região,
  com exemplos clicáveis. Cria a campanha e leva direto para a Descoberta.
- **Descoberta** (`pages/Descoberta.tsx`) — "Encontramos N empresas precisando de
  X na sua região", as 3 melhores em cartões com score, **insight da IA** e
  "por quê?"; diz quantas ficaram para o plano PRO. Abre a execução ao vivo
  sozinha quando a campanha nunca rodou.
- **Conversas** (`pages/Conversas.tsx`) — lista com estado por conversa, thread à
  direita, revisão por teclado. Diz na cara que ainda é de mão única.
- **Menu da conta** — Painel, Créditos e Conformidade saíram do topo. A barra
  principal tem só os três passos da jornada.
- **`scripts/limpar_demo.py`** — devolve o banco ao estado de seed preservando
  usuário, CNAEs e **opt-outs** (apagar opt-out para limpar demo seria voltar a
  contatar quem pediu para não ser contatado).

### O que a Etapa 2 entregou

- **Landing** (`pages/Landing.tsx`) — herói, "como funciona" em 3 passos, quatro
  provas concretas e chamada final. Dois botões: "Usar de forma gratuita" e
  "Suporte". Nenhum número inventado: prova social falsa em produto novo é o
  jeito mais rápido de perder o cliente na primeira tela.
- **Onboarding por chat** (`pages/OnboardingChat.tsx`) — o roteiro combinado:
  autônomo/empresa → nome → "o que a {empresa} faz?" → região → **a IA mostra os
  ramos que vai procurar** (vindos de `/v1/cerebro/expandir`, não de texto
  ensaiado) → escolha da autonomia. Se o entendimento estiver errado, o usuário
  corrige antes de gastar consulta paga.
- **Painel de suporte** — diz que o WhatsApp com IA **ainda não está no ar**.
  Botão de suporte que abre vazio queima confiança exatamente quando a pessoa
  precisou de ajuda.
- **Entrada em `localStorage`** (`prospector:entrou`) — não é autenticação, é
  memória de navegação. "Ver a página inicial" no menu da conta volta para a
  landing.

### Achado da Etapa 2

`onboarding_completo` é **derivado** no backend (`empresa AND servico_padrao`),
não um campo gravável. O chat chegou a enviá-lo no `PATCH /v1/me` — código morto
com cara de funcional. Removido: o que conclui o onboarding é preencher os dois
campos.

### Dois defeitos reais corrigidos no caminho

- **Dedup bem-sucedido parecia falha.** Quando a busca encontrava empresas mas
  todas já estavam na base, a tela dizia "Nenhuma empresa ainda" — idêntico a
  não ter achado nada. São resultados opostos. Agora a tela distingue os dois e
  aponta para Conversas.
- **Insight da IA repetia em todo cartão.** Ele escolhia o fator de maior
  pontuação, e "tem contato comercial" (20 pts) ganhava sempre — mas todo lead
  que chega ali tem contato: é pré-requisito, não insight. Agora a ordem é por
  poder de distinção, com o ramo na frente ("Hotéis — ramo que consome esse
  serviço de forma recorrente").

**Ordem escolhida e por quê:** vai do mais barato e visível ao mais complexo.
A casca primeiro dá lugar para o Motor 4 morar e deixa o app parecido com o
protótipo cedo. O Motor 4 é o mais pesado e vem por último, com o resto estável.

### Regras de trabalho combinadas
- **Uma etapa por vez**, com teste a cada coisa feita.
- **Este arquivo é atualizado ao fim de cada etapa** — é o que permite continuar
  numa conversa nova sem perder contexto.
- **Etapa fechada = commit *e* push, juntos** (combinado em 31/08/2026). O push
  virou o passo esquecido: as Etapas 1, 2 e 3 ficaram só nesta máquina e só
  foram para o GitHub junto com a 4. Commit sem push não é backup de nada — se
  o disco morre, morrem quatro etapas junto. Quem fechar uma etapa pergunta no
  fim e envia.
- Nada de chave de API: tudo continua rodando em mock.

---

## 5. Como rodar

O backend serve a interface compilada — **um processo só**.

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abrir: **http://localhost:8000**

Se mexer no frontend, recompile:

```bash
cd frontend && npm run build
```

Testes e lint:

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests -q && .venv/Scripts/ruff.exe check app tests scripts alembic
```

> **Esta máquina não tem Docker** e vive apertada de memória. O `docker-compose.yml`
> está pronto e correto, mas não dá para validar aqui. O servidor de
> desenvolvimento do Vite (porta 5173) consome centenas de MB e morre quando a
> RAM aperta — por isso o backend serve o `dist/`.

---

## 6. Guardrails que não se negociam

Valem para qualquer etapa, sempre:

1. **Nunca** fazer scraping de Google Maps/Earth. Descoberta só via Places API oficial.
2. **Nunca** disparar WhatsApp frio para pessoa física. Canal padrão é e-mail;
   WhatsApp preferencialmente inbound.
3. **MVP é B2B.** Sem prospecção ativa a PF desconhecida.
4. **Compliance é arquitetura, não item opcional.** Toda mensagem declara ser IA
   e leva link de descadastro. Opt-out é consultado antes de todo envio.
5. **Todo custo externo vira `cost_event`** em dois baldes que nunca se misturam:
   balde 1 = dados (Places, Receita, e-mail), balde 2 = IA (LLM, busca).
6. **Fases 0–6 rodam sem nenhuma chave.** Provedor externo só entra atrás de
   porta com mock; um flag `*_MODE=real` por provedor faz a virada.
7. **Acrescentar valor a enum exige migration.** Já quebrou uma vez: a Fase 4
   adicionou eventos ao `TipoEvento` e só ensinou o PostgreSQL; o SQLite quebrou
   na hora de gerar a LIA. Há teste fixando isso.

---

## 7. Armadilhas já pagas (não repetir)

- **SSE que reexecuta a campanha.** O `EventSource` reconecta sozinho quando o
  servidor fecha o fluxo. Como abrir a rota EXECUTA a campanha, cada reconexão
  virava uma execução nova — um clique gerou **256 execuções e 1020 consultas ao
  Places**. Defesas: o servidor recusa execução concorrente (409), manda
  `retry: 24h`, e o cliente fecha explicitamente.
- **Callback em dependência de efeito.** `aoTerminar` no array de dependências
  fazia o efeito reexecutar a cada renderização — e reabrir o fluxo custa
  execução paga. Vive numa `ref`.
- **Hook dentro de `useState`.** `useState(useAbertura)` faz o hook rodar só na
  primeira renderização e quebra a ordem dos hooks depois.
- **Coringa de SPA engolindo rota de API.** `/v1/` com erro de digitação
  devolveria HTML com status 200 — falha silenciosa. Há lista de prefixos
  reservados e teste.
- **`--reload` do uvicorn** dobra o consumo de memória e já deixou o processo
  em estado onde toda requisição virava 500.
- **Tela em branco com 500 em todo módulo** = falta de RAM. O Vite perde o
  processo filho do esbuild e responde `The service is no longer running`.
- **Teste que monta o próprio estado não vê o estado que a aplicação produz.**
  A Etapa 4 tratou `concluida` como "campanha parada" e a cadência nunca
  rodaria para ninguém — mas as fixtures usavam `executando`, então a
  cobertura ficou verde em cima de código morto. Só apareceu ao **abrir a
  tela**. Vale abrir a interface uma vez antes de dar qualquer etapa por
  fechada.
- **Cobrar no lugar errado do fluxo vaza o produto.** A Etapa 6 quase cobrou a
  revelação só no envio — só que no modo assistido o rascunho fica esperando
  aprovação com o nome da empresa no corpo e o e-mail no destinatário. O
  contato já estava à vista de graça. Cobra-se na **geração**.
- **A interface parece travada no preview quando o painel do navegador está
  oculto.** As animações do framer-motion dependem de `requestAnimationFrame`,
  que fica estrangulado em aba oculta: a transição de página trava por 20s e
  só anda a cada screenshot. Não é bug do app.

---

## 8. Onde as coisas moram

```
backend/app/
  services/cerebro.py       Motor 2 — serviço → ramos que consomem
  services/descoberta.py    Motor 1 — QueryBuilder + Places + Receita + dedup
  services/envio.py         Motor 3 — personalização + SendService
  services/cadencia.py      Motor 5 — 2º e 3º toque, e onde a cadência para
  services/entregabilidade.py  bounce, reclamação e pausa por reputação
  services/conversa.py      Motor 4 + a resposta manual (assumir/devolver)
  services/revelacao.py     o paywall: mascara de contato e cota de revelação
  services/scoring.py       score explicável, com pesos aprendidos
  services/compliance.py    LIA, opt-out, direitos do titular, retenção
  services/observador.py    eventos da execução ao vivo
  domain/lead_state.py      máquina de estados do lead
  adapters/mock/            todos os provedores em mock (sem chave)
  adapters/real/            adaptadores reais (Fase 7)
  api/estatico.py           serve a interface compilada

frontend/src/
  App.tsx                   navegação, tema, paleta
  pages/Landing.tsx         a primeira tela, antes de entrar
  pages/OnboardingChat.tsx  o onboarding por conversa
  pages/Busca.tsx           "quem você quer atender hoje?"
  pages/Descoberta.tsx      o resultado, com o contato atrás da cota
  pages/Conversas.tsx       thread, cadência, resposta manual
  pages/                    Painel, Créditos, Conformidade (menu da conta)
  components/ExecucaoAoVivo.tsx   o SSE narrando o pipeline
  components/Revisao.tsx          triagem por teclado (A/R/E)
  components/Paleta.tsx           Ctrl+K
```

Documentos: [README.md](README.md) · [PROGRESS.md](PROGRESS.md) ·
[docs/IDEIAS.md](docs/IDEIAS.md) ·
[docs/ARQUITETURA.md](docs/ARQUITETURA.md) · [docs/RUNBOOK-FASE7.md](docs/RUNBOOK-FASE7.md)

---

## 9. Pendências conhecidas

### 9.1 Divergências entre este documento e o código

Achadas na leitura de 31/08/2026. Não são bugs: são lugares onde a visão e o
repositório contam histórias diferentes. Argumento completo e proposta de
decisão em [docs/IDEIAS.md](docs/IDEIAS.md).

| # | Divergência | Onde | Status |
|---|---|---|---|
| 1 | ~~**Paywall só no cliente**~~ — resolvida na Etapa 6 | `services/revelacao.py` | ✅ |
| 2 | ~~**Duas tabelas de preço**~~ — resolvida na Etapa 6: grátis = 10 contatos/mês, 3 por busca | `services/creditos.py` | ✅ |
| 3 | ~~**"Assumir a conversa" sai do produto**~~ — resolvida na Etapa 5 | `services/conversa.py` | ✅ |
| 4 | ~~**Não existia segundo toque**~~ — resolvida na Etapa 4 | `services/cadencia.py` | ✅ |
| 5 | **`X-User-Email` ainda é a autenticação** | `backend/app/api/deps.py:33` | Etapa 8 |

A número 4 era a mais cara das cinco, e a única que não aparecia em nenhuma
tela: o produto parece completo até o dia em que ninguém responde.

### 9.2 Outras pendências

- **Ofício adjacente na expansão.** Para "manutenção de ar-condicionado", o
  Cérebro trouxe "Instalação e manutenção elétrica" (peso 11) como alvo.
  Eletricista não consome esse serviço — é ofício vizinho, quase concorrente.
  O peso é baixo e não polui o topo, mas **falta decidir**: adjacente entra como
  alvo ou é descartado junto com o concorrente? Precisa de julgamento de domínio.
- **`pages/Campanhas.tsx` ficou órfão.** A tela antiga foi substituída por
  Busca + Descoberta + Conversas e não é importada desde a Etapa 1. A
  condição que a nota original pedia ("apagar quando a Etapa 3 estabilizar")
  já passou faz três etapas — o arquivo pode ser apagado com
  `git rm frontend/src/pages/Campanhas.tsx`. Ficou por decidir, não por
  necessidade.
- **Chaves de API.** Nenhum provedor real ligado. O roteiro da virada está em
  [docs/RUNBOOK-FASE7.md](docs/RUNBOOK-FASE7.md): um provedor por vez.
- **`limpar_demo.py` preserva supressão de bounce.** O script preserva todos os
  opt-outs de propósito — apagar seria voltar a contatar quem pediu para sair.
  Só que agora existe supressão vinda de **bounce**, que não é vontade de
  titular nenhum: é endereço que não existe. Num banco de demo isso gruda para
  sempre numa empresa fictícia. **Falta decidir** se o script passa a limpar as
  supressões de origem `bounce_permanente` (mantendo intactas as humanas).
- **"3 com automação gratuita" sumiu do plano.** A visão (§2.6) tinha dois
  eixos: 10 leads por mês **e** 3 deles com automação. A Etapa 6 implementou o
  primeiro (10 contatos revelados, 3 por busca) e o segundo continua sendo só
  os limites diários genéricos de envio, iguais para todo mundo. **Falta
  decidir** se automação é um eixo próprio de cota ou se some de vez — hoje
  ela não aparece em lugar nenhum da tela, o que é pior que qualquer uma das
  duas respostas.
- **Autenticação.** Não existe login: o usuário vem do header `X-User-Email` com
  fallback no usuário de seed. É dev-only e precisa virar JWT antes de qualquer
  exposição pública. É a **Etapa 8** e a última divergência aberta da §9.1.
