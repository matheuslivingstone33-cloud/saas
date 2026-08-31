# IDEIAS — o que construir, em que ordem e por quê

> Documento de produto. Nasceu de uma leitura do repositório inteiro em
> 31/08/2026, confrontando a visão do [HANDOFF.md](../HANDOFF.md) com o que o
> código realmente faz.
>
> **Não é backlog.** Backlog lista tarefas; isto argumenta escolhas. Cada ideia
> aqui vem com o motivo — porque daqui a três meses o motivo é a única parte que
> ainda importa, e é a primeira que se perde.

---

## 0. O ponto de partida

O produto sabe **encontrar** (Motor 1 + Motor 2), sabe **abordar** (Motor 3) e
sabe **conversar** (Motor 4). O que ele não sabe é **insistir**.

Essa frase é o resumo de quase tudo que vem abaixo. Um prestador de serviço não
compra "42 empresas encontradas": ele compra reunião marcada. Entre uma coisa e
outra existe um trabalho chato, repetitivo e educado — voltar três vezes, em
ângulos diferentes, sem virar praga — que é exatamente o trabalho que ele não
faz sozinho e por isso está pagando alguém para fazer.

---

## 1. Divergências entre a visão e o código

Não são bugs. São lugares onde o documento e o repositório contam histórias
diferentes — e decidir qual das duas vale é pré-requisito para o resto.

| # | Divergência | Onde | Decisão necessária |
|---|---|---|---|
| 1 | **Paywall só no cliente**: a tela corta em 3, a API devolve as 42 | `frontend/src/pages/Descoberta.tsx:98` | virar corte de servidor (§4) |
| 2 | **Duas tabelas de preço**: visão diz "grátis 10 leads / 3 automações", código tem TRIAL 50 · STARTER R$197 · PRO R$597 · SCALE R$1.497 | `HANDOFF.md` §2.6 × `backend/app/services/creditos.py:68` | escolher uma (§4) |
| 3 | ~~**"Assumir a conversa" sai do produto**~~ | resolvida | ✅ Etapa 5 |
| 4 | ~~**Não existe segundo toque**~~ | resolvida | ✅ Etapa 4 |
| 5 | **`X-User-Email` ainda é a autenticação** | `backend/app/api/deps.py:33` | JWT antes de qualquer usuário real (§10) |

A divergência 4 era a mais cara das cinco, e a única que não aparecia em tela
nenhuma: o produto parecia completo até o dia em que ninguém respondia. Foi a
primeira a ser fechada, por isso.

---

## 2. Motor 5 — Cadência ✅ *(entregue na Etapa 4, 31/08/2026)*

**O problema.** Cada lead recebe **um** e-mail. Se ninguém responder, o sistema
não faz mais nada e o Motor 4 nunca acorda. Em prospecção B2B por e-mail, a
maior parte das respostas vem do segundo ao quinto toque — o primeiro é o que
menos responde. Com um toque só, o cliente vê o número bonito da Descoberta,
recebe silêncio por duas semanas e conclui que não funciona, **mesmo com todo o
resto perfeito**.

**A proposta.** Três toques por lead — D0, D+3, D+7 — cada um com um **ângulo
diferente**. Nunca "seguindo minha mensagem anterior": isso é confissão de que
ninguém quis responder e transfere para o lead a culpa pelo silêncio. Ângulos
que funcionam porque cada um é uma mensagem inteira, não um empurrão:

| Toque | Ângulo | O que ele traz de novo |
|---|---|---|
| **D0** | o insight | por que **esta** empresa, com o fato que o scoring encontrou |
| **D+3** | a prova | um caso parecido, no mesmo ramo, com número |
| **D+7** | a saída | "faz sentido eu parar por aqui?" — a pergunta que mais responde, porque responder custa uma palavra |

**Onde a cadência para** — e isso importa mais que onde ela continua:

- qualquer resposta do lead (o Motor 4 assume);
- opt-out, em qualquer toque;
- recusa já classificada;
- bounce permanente (§3);
- fim do toque 3 — o lead descansa, não vira lista eterna.

**Por que foi a próxima etapa.** Quase tudo já existia: `SendService` como único
caminho de saída revalidando opt-out no envio, worker com tarefa agendada, e a
máquina de estados do lead. Faltava o agendador e o registro de qual toque já
saiu — a melhor razão esforço/resultado do projeto.

> **Entregue** em `backend/app/services/cadencia.py`, com `GET /v1/cadencia`,
> `POST /v1/cadencia/executar`, a tarefa diária `executar_cadencia` e o estado
> da cadência na tela de Conversas. 27 testes.

**O risco a respeitar.** Cadência é a diferença entre insistência e perseguição,
e a linha é o volume. Teto por lead, teto por domínio de destino, e nenhum toque
novo enquanto houver toque pendente de aprovação no modo assistido.

---

## 3. Entregabilidade é risco existencial ✅ *(entregue na Etapa 4)*

**O problema.** Uma campanha fria mal calibrada queima a reputação do domínio do
cliente. Não é um incidente: é irreversível na prática. Um domínio com
reputação destruída para de entregar e-mail **para os clientes atuais dele
também** — a nota fiscal, o orçamento, a resposta ao chamado. O produto que
prometia trazer cliente novo derrubou o faturamento antigo.

Hoje o SNS de bounce/complaint do SES está listado como pendência da Fase 7, no
mesmo nível de "papel de admin no painel de margem". Não é o mesmo nível.

**A proposta.** Promover a bloqueante, e entrar junto com a cadência — porque é
a cadência que multiplica o volume e, com ele, o dano:

- **bounce permanente → supressão automática**, pela mesma porta do opt-out;
- **reclamação de spam → supressão + sinal negativo forte** no aprendizado;
- **teto por reputação**: taxa de bounce acima de 2% pausa a campanha e avisa,
  em vez de continuar e torcer;
- **warm-up**: domínio novo começa com volume baixo e sobe por dia.

**O argumento comercial que sai disso.** *"A gente protege o seu domínio"* é uma
promessa mais forte para um refrigerista do que *"a gente manda muito e-mail"* —
e é uma que quase nenhum concorrente pode fazer com a cara limpa, porque exige
justamente a arquitetura de supressão que já existe aqui.

> **Entregue** em `backend/app/services/entregabilidade.py`: supressão por
> bounce permanente, origem própria para reclamação de spam, retorno temporário
> que não suprime nada, e pausa automática da campanha acima de 2%.
>
> **NÃO entregue:** o **warm-up** de domínio novo, e o adaptador que traduz o
> SNS do SES para `POST /v1/inbound/retorno`. O motor está pronto e testado; o
> que falta é a tradução do formato do provedor, que é trabalho da virada de
> chave (Fase 7), e a rampa de volume — que só faz sentido com envio real.

---

## 4. Cobrar por revelação, não por descoberta

**O problema, em duas partes.** O corte das 3 melhores é um `slice` no cliente;
e o preço tem duas versões incompatíveis (§1).

**A proposta.** Mudar o eixo do que é cobrado. Descoberta custa balde 1 e é
barata por lead; **revelação de contato** é o que tem valor. Então:

- a API devolve **3 leads completos + N leads com o valor visível e o contato
  oculto**: ramo, bairro, faixa de funcionários, score e o insight — sem CNPJ,
  sem e-mail, sem telefone;
- o corte é feito no servidor, não na tela;
- o contador conta **contato revelado**, não lead descoberto.

**Por que é melhor, e não só mais seguro.** Ver que existem 39 hotéis com câmara
frigorífica na sua cidade e não poder falar com eles é exatamente o que faz
pagar. Um `slice` no cliente não vende nada — só engana quem não sabe abrir o
devtools, que é o mesmo público que não ia pagar. E cobrar por lead descoberto
pune o cliente quando o Cérebro erra a mira: ele paga pelo nosso erro.

Isso também resolve a divergência de preço sem escolher um dos dois lados: o
"10 leads grátis" passa a significar **10 contatos revelados**, com a descoberta
inteira visível. É mais generoso, mais honesto e mais fácil de explicar em uma
frase.

---

## 5. A resposta manual dentro do produto ✅ *(entregue na Etapa 5, 31/08/2026)*

**O problema.** No momento mais valioso da jornada — o lead esquentou —
`Conversas.tsx` abre um `mailto:`. A conversa sai do sistema. A resposta do lead
volta para a caixa pessoal do usuário, o Motor 4 fica cego justamente no lead
que estava dando certo, e a auditoria perde o trecho mais importante da conversa.
Não existe hoje rota para enviar mensagem manual: `api/routes/messages.py` só
aprova, rejeita e despacha.

**A proposta.** Caixa de resposta na thread, enviando pelo `SendService` com a
identidade do usuário. É pequena, e destrava quatro coisas de uma vez: a thread
continua de duas pontas, o Motor 4 continua enxergando, a auditoria fica íntegra,
e o "Abordagem IA / Manual" da visão (§2.4 do handoff) finalmente existe.

> **Entregue** em `ServicoDeConversa.responder_manualmente`, com
> `POST /v1/leads/{id}/responder`, `POST /v1/leads/{id}/devolver-para-ia` e a
> caixa de escrever na tela de Conversas. 20 testes.
>
> Uma decisão que só apareceu ao construir: a mensagem escrita por gente **não
> leva a declaração de IA**. O Marco da IA manda declarar quando é IA; não
> manda mentir que é. O link de descadastro fica, porque a LGPD não muda
> conforme quem digitou. E `leads.assumido_em` cala o agente — sem isso o
> toque 2 sairia por cima do que a pessoa acabou de escrever.

---

## 6. O insight deve virar a primeira linha do e-mail

O trabalho da Etapa 2 — ordenar o insight por poder de distinção, em vez de por
pontuação — parou no cartão da Descoberta. O mesmo fato que justifica o score
deveria **abrir a abordagem**, e o usuário deveria poder editar o insight e ver
a mensagem mudar.

Fecha o loop entre scoring explicável e personalização, e transforma o "por quê?"
de justificativa em ferramenta: o usuário conhece o próprio mercado melhor que o
Cérebro, e hoje não tem onde colocar isso.

---

## 7. O Motor 4 é o melhor professor que o Cérebro poderia ter

**O que existe.** `LoopAprendizado` realimenta os pesos do scoring a partir do
**desfecho do lead** — sinal raro, lento e que só chega quando já gastamos tudo.

**O que passou a existir com o Motor 4.** A **intenção da resposta**: um sinal
mais barato, mais cedo e muito mais denso. Vinte `recusa` no mesmo CNAE não é
azar — é o Cérebro tendo errado o ramo. Taxa de resposta por ramo, por tenant,
realimentando o peso daquele ramo.

**Por que isso é o fosso.** Cada cliente afina a própria mira, e o ativo é o
histórico dele. É a única parte do produto que fica **mais difícil de copiar com
o tempo** em vez de mais fácil: um concorrente copia a tela em uma semana e o
prompt em uma tarde, mas não copia dois anos de resposta de hotel em Foz do
Iguaçu.

Depende de volume de respostas — ou seja, depende do §2. Por isso vem depois.

---

## 8. Adjacente: decidir por "parceiro", não por peso

**A pendência aberta.** Para "manutenção de ar-condicionado", o Cérebro trouxe
"Instalação e manutenção elétrica" (peso 11). Eletricista não consome o serviço;
é ofício vizinho, quase concorrente. Falta decidir se entra ou sai.

**A decisão proposta: entra, em balde separado, e nunca no topo** — rotulado como
*"pode indicar, não compra"*.

O eletricista não compra manutenção de ar-condicionado, mas está no mesmo prédio
que quem compra, e indica o tempo todo. Tratado como alvo, ele é ruído no score.
Tratado como parceria, vira um canal — e um canal que quase ninguém está
olhando, porque a indústria inteira modela adjacência como erro de matching.

Custo de errar é baixo: se o balde não converter, ele some sem ter contaminado
nenhuma métrica do balde principal.

---

## 9. WhatsApp não é o suporte — é o canal do produto

**A visão atual** (§2.5 do handoff) põe o WhatsApp com IA como diferencial de
atendimento: o cliente vê a qualidade da nossa IA na prática. Está certo, e é
pouco.

**A ideia maior.** O refrigerista **vive no WhatsApp e não abre dashboard**. Um
lead esquenta às 14h de uma terça — ele está em cima de um telhado, não no
navegador. Toda a promessa do produto depende de alguém lembrar de abrir o site.

Então: notificação de lead quente no WhatsApp, com resposta pelo próprio
WhatsApp — o texto entra pelo `SendService` e vai por e-mail para o lead. Mesmo
motor do suporte, e continua **inbound** (o cliente falou com a gente primeiro),
sem esbarrar no guardrail de WhatsApp frio.

Vem depois porque é a maior das ideias e a que mais depende do resto estar
estável.

---

## 10. Antes de qualquer usuário real

JWT, papel de admin em `/v1/margem/consolidado`, webhook do Stripe assinado.

Não é ideia, é porta de entrada: enquanto `X-User-Email` for a autenticação,
"multiusuário" significa "todo mundo vê tudo", inclusive o consolidado de margem
de todos os clientes.

---

## 11. Ordem proposta

Do que faz o produto **produzir resultado** para o que o faz **poder ser
vendido**:

| # | Etapa | Por que nesta posição |
|---|---|---|
| ~~4~~ | ~~**Cadência (Motor 5) + supressão de bounce**~~ | ✅ **entregue em 31/08/2026** |
| ~~5~~ | ~~**Resposta manual dentro do produto**~~ | ✅ **entregue em 31/08/2026** |
| **6** | **Paywall no servidor + alinhar planos** | só faz sentido cobrar depois que o produto produz resposta |
| **7** | **Aprendizado por intenção** | precisa do volume de respostas que a Etapa 4 gera |
| **8** | **JWT + admin + webhook assinado** | último momento possível antes de qualquer pessoa de fora |
| **9** | **WhatsApp como canal** | a maior, e a que mais depende do resto estável |

**Etapa 4 primeiro** porque o produto sabia encontrar e sabia conversar, mas não
sabia insistir — e insistir com educação é literalmente o trabalho que o cliente
está comprando. A 5 veio logo atrás, e era pequena. **A próxima é a 6**: cobrar
por revelação em vez de por descoberta (§4) — que resolve de uma vez o paywall
de mentira e as duas tabelas de preço.

### O que a Etapa 4 ensinou

O bug mais caro da etapa não apareceu em nenhum teste: `concluida` é o estado
normal em que **toda** campanha termina, e tratá-lo como "campanha parada"
fazia a cadência nunca rodar para ninguém. Cobertura verde, motor morto — as
fixtures usavam `executando`. Só apareceu ao abrir a tela e ver a lista vazia.

A lição serve para as próximas etapas: **teste que monta o próprio estado não
vê o estado que a aplicação produz sozinha.** Vale abrir a tela uma vez antes
de dar a etapa por fechada.
