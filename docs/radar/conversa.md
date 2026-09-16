> **ESTADO INTEGRADO NA VERSÃO PRINCIPAL — 15/09/2026**
>
> De 12 a 15/09 as rotinas trabalharam em cópias separadas e não enxergavam o
> trabalho umas das outras — a mesma correção chegou a ser feita quatro vezes.
> As correções abaixo foram escolhidas, testadas juntas e integradas no `main`.
> **Leia esta lista antes de agir: o que coincidir com ela já está resolvido e
> não deve ser refeito.** Os hashes citados são dos commits originais; no `main`
> eles têm hash novo, com a mesma mensagem.
>
> - **Corte do histórico citado** (versão de 14/09, `3043612`): intenção de negócio só na resposta nova; **opt-out no texto inteiro**. A de 15/09 (`50578e4`) foi descartada porque cortava o histórico também para o opt-out e perdia "me tire da lista" escrito embaixo da citação. As de 12/09 e 13/09 cortavam só dentro de `ServicoDeConversa.classificar`.
> - A mesma correção fecha um defeito que estava no `main` e nenhuma versão registrou: a nossa declaração termina com *"Responda a este e-mail para falar com uma pessoa"*, e lida inteira fazia **toda** resposta virar `pedido_humano`. Há teste agora.
> - **Proteção nova:** linha que contém o nosso link `/descadastro/` não entra na varredura de opt-out. Sem ela, no dia em que o link for para o corpo do e-mail, todo "tenho interesse" respondido por cima de uma mensagem nossa viraria opt-out. Rótulo e link devem ficar na mesma linha.
>
> - **Quoted-printable decodificado — integrado em 16/09** (versão de 15/09, `f8116f2`, adaptada ao `main`). `decodificar_quoted_printable()` roda no começo de `classificar_por_sinal` e antes do LLM, então `n=C3=A3o me envie` e `desca=
dastrar` viram opt-out. Teste novo: o **nosso link partido por soft break** também sai da varredura, porque a linha é remontada antes. **Falta ainda o corpo em HTML** (tags e entidades como `n&atilde;o`) — esse é o próximo do item 1 abaixo.
>
> O que vem abaixo é o diário das execuções, mantido como estava.

---

# Radar — Conversa / Cadência / Webhook (Motor 4 e Motor 5)

> Arquivos sob esta responsabilidade: `backend/app/services/conversa.py`,
> `cadencia.py`, `webhook.py` e os testes correspondentes.
>
> Objetivo permanente: preparar a classificação de intenção e o parsing da
> resposta para **texto de e-mail real**. No mock o corpo chega limpo; na vida
> real vem com histórico citado, assinatura, rodapé corporativo, HTML,
> quoted-printable e resposta automática de servidor. Uma coisa por execução,
> com teste que falha antes e passa depois.
>
> **Regra que não se negocia:** em caso de dúvida, o direito do titular ganha
> do negócio. Opt-out duvidoso é opt-out.

**Última execução:** 2026-09-16

---

## O que corrigiu nesta execução (2026-09-16)

**O bloco de cabeçalho do Outlook (`De:/Enviada em:/Para:/Assunto:`) passou a
fechar o histórico citado.** (`services/conversa.py`, commit `0c154da`)

Era o item 2 da fila de "achado e não corrigi" (abaixo), e o próximo fechável
inteiro dentro dos meus três arquivos — o item 1 (HTML/quoted-printable)
continua travado na definição do formato do payload da Fase 7.

O buraco: `remover_historico_citado` reconhecia `>`, atribuição `escreveu:`/
`wrote:`, `-----Mensagem original-----` e a régua de sublinhados do Outlook.
Mas o Outlook (e vários webmails) intercalam o histórico com um bloco de
cabeçalho **sem a régua e sem `>`**:

```
Perfeito, tenho interesse! Podemos conversar esta semana.

De: Prospector AI <contato@exemplo.com>
Enviada em: terça-feira, 9 de setembro de 2026 10:15
Para: gerencia@brisamarhotel.com.br
Assunto: RE: manutenção de ar-condicionado

Olá, equipe. No mês passado vocês responderam: não tenho interesse, obrigado.
```

Sem fronteira reconhecida, o método devolvia o texto **inteiro** como "resposta
nova". Como `recusa` vem antes de `interesse` na ordem das regras, o
`"não tenho interesse"` citado lá embaixo ganhava do `"tenho interesse"`
recém-escrito no topo — e o lead quente ia para `descartado`. É o cenário 1 do
objetivo, agora no formato do Outlook, e o teste ponta a ponta confirmava o
dano (retornava `RECUSA`).

O que mudou:

- **`_RE_CABECALHO_ENCAMINHADO`** — casa uma linha que começa com um **rótulo de
  e-mail conhecido** seguido de `:` (`De`, `Para`, `Assunto`, `Enviada/Enviado
  em`, `Data`, `Cc`, `Cco`, `Responder para/a`, e os equivalentes EN `From`,
  `To`, `Subject`, `Sent`, `Date`, `Reply-To`). Só rótulos conhecidos entram —
  `Prazo:` / `Valor:` de uma resposta de verdade não contam.
- **`_abre_bloco_encaminhado(linhas, i)`** — o corte só acontece com **DUAS
  linhas de cabeçalho seguidas**. É o que torna o corte seguro nos dois flancos:
  `"De acordo, ..."` nem casa (não há `:` depois de `De`), e um `"Assunto: ..."`
  solto no meio de uma frase não engole a resposta. O corte continua
  **conservador** — na dúvida, deixa histórico passar, nunca descarta resposta.
- **Opt-out não muda em nada.** Ele continua varrendo o texto **inteiro** (menos
  a linha do nosso `/descadastro/`), independente do `remover_historico_citado`.
  Estreitar o que conta como "resposta nova" só afeta a intenção de negócio;
  o direito do titular segue no lado mais amplo. "Opt-out duvidoso é opt-out"
  permanece intacto.

Testes (em `test_motor4_conversa.py`), todos falhando antes e passando depois:
`test_remover_historico_citado_corta_bloco_encaminhado_sem_regua`,
`test_bloco_encaminhado_do_outlook_nao_descarta_lead_que_disse_sim` (ponta a
ponta lexical) e `test_bloco_encaminhado_exige_duas_linhas_e_nao_corta_resposta_comum`
(o lado conservador). **390 passed, 3 skipped; `ruff` limpo.**

`cadencia.py` e `webhook.py` não foram tocados — a correção foi toda no Motor 4.

---

## O que corrigiu na execução anterior (2026-09-14)

**A intenção de negócio passou a sair da resposta NOVA, não do histórico citado.**
(`services/conversa.py`, commit `3043612`)

O `classificar_por_sinal` varria o corpo **inteiro** com `any(marca in t)`. Como
a ordem das regras põe `recusa` antes de `interesse`, um `"não tenho interesse"`
copiado de uma troca antiga — que vem colado embaixo da resposta em qualquer
e-mail real — ganhava de um `"tenho interesse"` recém-escrito no topo. O lead
quente ia para `descartado`. É exatamente o cenário 1 do objetivo, e o teste
ponta a ponta confirmou o dano: o lead terminava `[descartado]`.

O que mudou:

- **`remover_historico_citado(texto)`** — separa a resposta nova do histórico,
  cortando na primeira fronteira inequívoca e preservando tudo o que está
  **acima** dela. Fronteiras reconhecidas: linha citada (`>`), linha de
  atribuição que termina em `"escreveu:"` / `"wrote:"`, separador
  `-----Mensagem original-----` (e variantes EN/encaminhada) e a régua de
  sublinhados do Outlook (`_____`). O corte é **conservador**: sem fronteira,
  devolve o texto inteiro; nunca engole a resposta nova. O lado seguro de errar
  é deixar histórico passar, não descartar resposta.
- **Escopo dividido por intenção** (`_SOBRE_TEXTO_INTEIRO`). `recusa`,
  `interesse`, `objeção`, `ausência` e `pedido_humano` são classificados **só
  sobre a resposta nova**. **`pedido_opt_out` continua varrendo o texto
  inteiro** — de propósito: um pedido de saída escrito abaixo da citação não
  pode se perder. Para o opt-out a varredura é a mais ampla possível; para os
  outros, a mais estreita. Isso cobre os dois lados do objetivo de uma vez.
- O **LLM de desempate** (`classificar`) também passou a receber só a resposta
  nova. Como o opt-out lexical já rodou sobre o texto inteiro antes, estreitar
  o escopo do modelo não arrisca perder pedido de saída.

Testes (em `test_motor4_conversa.py`): `test_recusa_citada_nao_descarta_lead_que_disse_sim`
e o par ponta a ponta falhavam antes (retornavam `RECUSA`) e passam agora;
`test_opt_out_apos_citacao_nao_se_perde` fixa que o opt-out abaixo da citação
continua pego; três casos parametrizados fixam o corte de Gmail, Outlook e
"Mensagem original". **347 passed, 3 skipped; ruff limpo.**

---

## O que achou e não corrigiu (fila de "uma coisa por execução")

Em ordem sugerida — do que mais protege titular/negócio ao mais cosmético.

1. **HTML e quoted-printable ainda não são decodificados.** Se o provedor
   entregar o corpo em HTML (`<br>`, `<div>`, `&nbsp;`, entidades) ou em
   quoted-printable (`=E3`, `=0D=0A`, soft breaks `=\n`), tanto o casamento
   lexical quanto a detecção de fronteira de citação degradam: `"não tenho
   interesse"` pode chegar como `n=C3=A3o tenho interesse` e escapar de toda
   marca. **Depende de decidir onde decodificar** (ver seção seguinte) — mas a
   decodificação para texto puro, uma vez definida a origem, mora aqui, antes de
   classificar. É o maior buraco: sem isso, o resto do parsing trabalha sobre
   lixo.

2. ✅ **RESOLVIDO em 2026-09-16 — rodapé de citação do Outlook sem `>` e sem
   régua.** O bloco `De:/Enviada:/Para:/Assunto:` que aparecia sozinho, sem a
   régua de sublinhados e sem prefixo de citação, agora é reconhecido como
   fronteira (ver "O que corrigiu nesta execução (2026-09-16)" acima). Casa duas
   linhas de rótulo de e-mail conhecido seguidas, o que não corta uma resposta
   que só comece com `"De acordo, ..."`.

3. **Resposta automática de servidor além de palavra-chave.** `ausência` hoje é
   puramente lexical ("estou de férias", "out of office"). Auto-resposta real
   costuma trazer sinais de cabeçalho — `Auto-Submitted: auto-replied`,
   `X-Autoreply`, `Precedence: bulk` — que não chegam ao `corpo`. Enquanto o
   webhook não repassar cabeçalhos, uma férias em outro idioma ou um "delivery
   status notification" passam como resposta de verdade e podem virar `dúvida`
   (o motor responde para um robô). Ver dependência no item de payload.

4. **Assinatura e rodapé corporativo não são removidos.** Bloco de assinatura
   ("Atenciosamente, Fulano | Cargo | Telefone | site") continua no texto que
   vai ao LLM. Não muda a classificação lexical (não tem marca), mas polui o
   contexto do modelo e pode carregar termos que confundem
   (`"não responda este e-mail automático"`). Baixo risco; fazer depois de HTML.

5. **Post embaixo da citação (bottom-posting) perde a intenção de negócio.**
   Quando a pessoa escreve **abaixo** do histórico, `remover_historico_citado`
   corta no primeiro `>` e a resposta nova fica de fora → a intenção de negócio
   cai para o LLM (que vê texto vazio e devolve `indefinida`/`dúvida`). **Não é
   regressão perigosa**: o opt-out ainda varre o texto inteiro, e `dúvida` gera
   resposta útil sem descartar o lead. Mas é impreciso. Um passo futuro poderia
   tratar o caso "resposta só existe abaixo da citação".

6. **Falso opt-out a partir do nosso próprio rodapé citado.** Nossa mensagem de
   saída leva o link `/descadastro/{id}` e a declaração
   `"Responda a este e-mail para falar com uma pessoa"`. Se o cliente do lead
   **cita a nossa mensagem** de volta, a varredura de opt-out sobre o texto
   inteiro pode casar `"descadastr"` do nosso próprio link e suprimir um lead
   que respondeu com entusiasmo. Pela regra, opt-out duvidoso é opt-out — então
   o comportamento **atual é o lado seguro** —, mas suprimir um interessado por
   causa do nosso rodapé é dano real. O conserto certo é **remover o nosso
   rodapé/declaração citados** antes da varredura de opt-out (não estreitar o
   escopo do opt-out). Deixado como decisão, ver seção seguinte.

7. **Atribuição limitada a `escreveu:`/`wrote:`.** "No dia 9/9, Fulano
   respondeu:" ou variantes de outros idiomas não são fronteira. Ampliar a
   regra é fácil, mas cada padrão novo é risco de cortar resposta legítima —
   por isso ficou de fora do corte conservador desta execução.

`cadencia.py` e `webhook.py` **não foram tocados** nesta execução — a correção
foi toda no Motor 4. Nada pendente identificado dentro deles além do que a
seção seguinte lista como dependência.

---

## O que depende de outros

- **Formato do `corpo` que o provedor real entrega (Fase 7, precisa de chave).**
  A rota `POST /v1/inbound/email` passa `payload.corpo` direto para
  `ServicoDeConversa.receber` (`api/routes/conversas.py:105`). Se HTML,
  quoted-printable e cabeçalhos (`Auto-Submitted`, etc.) chegam crus, semi
  normalizados, ou já em texto puro, é o que decide **quanto** dos itens 1 e 3
  acima é trabalho meu e quanto é do adaptador. Isso trava em ligar o provedor
  real — item da §0.2 do HANDOFF ("Fase 7 — ligar provedores reais", exige
  chaves e cartão). **Não dá para fechar 1 e 3 sem essa definição.**

- **Repasse de cabeçalhos no payload do webhook.** Para o item 3 (auto-resposta
  por cabeçalho) e para o item 6 (distinguir nosso rodapé citado), ajudaria o
  `RespostaRecebida` carregar cabeçalhos selecionados. Mexer no schema do
  payload e na assinatura do `receber` toca `api/routes/conversas.py` e o DTO —
  **fora dos meus três arquivos**. Precisa de combinação com quem cuida da rota.

- **Decisão de produto — falso opt-out pelo nosso rodapé citado (item 6).**
  Confirmar com o Matheus se o conserto é "remover nosso rodapé antes de varrer
  opt-out" (recomendado) ou manter o comportamento atual (suprime na dúvida).
  A regra do projeto favorece suprimir; o ajuste é para não suprimir **quando a
  única fonte do sinal é a nossa própria mensagem citada**. Não é decisão que a
  rotina toma sozinha.

- **Efeito colateral bom, sem dependência:** a correção também protege o
  Motor 5. A cadência para quando o lead vai a `respondido`/`descartado`
  (`cadencia.py:_motivo_de_parada`); um descarte indevido por citação encerrava
  a cadência de um lead quente. Com a classificação certa, a cadência para pela
  razão certa. Nenhuma mudança foi necessária em `cadencia.py` para isso.
