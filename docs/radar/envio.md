> **ESTADO INTEGRADO NA VERSÃO PRINCIPAL — 15/09/2026**
>
> De 12 a 15/09 as rotinas trabalharam em cópias separadas e não enxergavam o
> trabalho umas das outras — a mesma correção chegou a ser feita quatro vezes.
> As correções abaixo foram escolhidas, testadas juntas e integradas no `main`.
> **Leia esta lista antes de agir: o que coincidir com ela já está resolvido e
> não deve ser refeito.** Os hashes citados são dos commits originais; no `main`
> eles têm hash novo, com a mesma mensagem.
>
> - **Tradutor do retorno SES/SNS** (versão de 13/09, `988ceed`): `classificar_retorno_ses()` e `url_de_confirmacao_sns()` em `adapters/real/ses_email.py`. Escolhida por ser a única que extrai o endereço de `"Nome <email>"` — as outras gravariam o texto inteiro na supressão, e o bloqueio não bateria com o e-mail do lead. Descartadas: 12/09 (`236f30e`), 14/09 (`ebabc92`), 15/09 (`0050b2d`).
> - **Ainda não existe rota que receba o SNS.** `/v1/inbound/retorno` exige a nossa assinatura HMAC, e o SNS assina com certificado próprio da AWS. O tradutor está pronto e não tem porta de entrada — depende de rota nova, fora do escopo desta rotina.
> - **A verificar com Privacidade:** hoje o link de descadastro vai só no cabeçalho `List-Unsubscribe`; o texto do e-mail não o contém.
>
> O que vem abaixo é o diário da execução de 13/09, mantido como estava.

---

# Radar — Envio (Motor 3 + entregabilidade + SES)

> Área de risco: **o envio é o ponto mais frágil do produto porque o ativo é a
> reputação do domínio.** Em mock nada sai e nada quebra; com SES real entram
> SPF/DKIM/DMARC, warmup, limites de conta e — o mais perigoso — os retornos
> assíncronos de bounce e reclamação via SNS.
>
> Arquivos desta área: `backend/app/services/envio.py`,
> `personalizacao.py`, `entregabilidade.py`,
> `backend/app/adapters/real/ses_email.py` e os testes correspondentes.

**Última execução:** 2026-09-20 · a taxa de RECLAMAÇÃO de spam ganhou teto
próprio, bem mais baixo que o de bounce — a campanha pausa por spam antes de a
conta ser suspensa, e não depois.

---

## 2026-09-20 (2) — reclamação de spam ganhou teto próprio (não divide mais o de bounce)

### O que corrigi (com teste)

**A taxa de reclamação de spam deixou de dividir o mesmo teto do bounce
(`bounce_taxa_maxima`, 2%) e passou a ter freio próprio, muito mais baixo
(`RECLAMACAO_TAXA_MAXIMA` = 0,3%).** A campanha agora pausa se a taxa **combinada**
estourar (como antes) **ou** se a de **reclamação**, sozinha, passar do teto de
spam.

Por que este é o maior risco de envio que fechava inteiro no meu escopo: a pausa
automática por reputação (`_pausar_se_preciso`) é a principal defesa do domínio —
o ativo mais frágil do produto — com SES real. Só que ela media bounce e
reclamação na **mesma régua de 2%**, e os provedores **não** os tratam assim: o
SES põe a conta em revisão perto de **0,1%** e a suspende perto de **0,5%** de
reclamação, contra ~5–10% de bounce; a regra de remetente em massa do Gmail
(02/2024) manda ficar abaixo de **0,3%**. Com o teto único de 2%, uma conta a
0,5% de reclamação (bem abaixo dos 2% combinados se o bounce for baixo) seria
**suspensa pela AWS antes de a campanha pausar** — o domínio morre exatamente
pelo sinal que este módulo existe para vigiar. A defesa disparava tarde demais
justamente no retorno mais perigoso.

**Decisão de desenho, resolvida:** o freio novo só **adiciona** pausa, nunca
remove. `acima_do_teto` = combinada acima de 2% **ou** reclamação acima de 0,3% —
então tudo que já pausava continua pausando, e o que muda é pausar **mais cedo**
quando o problema é spam. O teto de bounce continua em `bounce_taxa_maxima`
(configurável); a reclamação virou **constante do módulo** de propósito, porque
promovê-la a `Settings` tocaria `config.py`, que é de outro dono — quando alguém
mexer em `config.py`, é forte candidata a virar setting.

Como ficou, tudo em `entregabilidade.py` (só meu):

- `RECLAMACAO_TAXA_MAXIMA = 0.003` — teto separado, documentado com o porquê.
- `reputacao()` agora conta **bounce** e **reclamação** em separado (`_contar_retornos`),
  calcula `taxa_reclamacao` além da combinada, e liga `reclamacao_acima_do_teto`.
- `Reputacao` ganhou campos **aditivos** (`bounces`, `reclamacoes`,
  `taxa_reclamacao`, `reclamacao_acima_do_teto`); `to_dict()` mantém byte a byte
  as chaves antigas (`enviadas`, `retornos`, `taxa`, `amostra_suficiente`,
  `acima_do_teto`), então a rota `GET /campanhas/{id}/reputacao` e o painel não
  quebram — só recebem mais informação.
- `_pausar_se_preciso` registra na auditoria o motivo **específico** (reclamação
  vs. taxa combinada), para o humano que revisa a pausa saber o que aconteceu.

`SendService` segue o único caminho de saída e opt-out segue terminal: esta
mudança só **antecipa** um bloqueio automático, nunca abre exceção.

Testes: 2 novos em `test_motor5_cadencia.py` — 1 reclamação em 100 envios (1%,
abaixo do teto combinado de 2%, acima do de reclamação de 0,3%) **pausa** a
campanha (falha antes, passa depois); e o par que fixa a assimetria: 1 bounce em
100 (1%) **não** pausa, porque a régua estrita é só da reclamação. **466 passed,
3 skipped; `ruff` limpo.**

### O que achei e NÃO corrigi (uma coisa por execução)

1. **🔴 O "descadastro de 1 clique" NÃO é o one-click do RFC 8058** (herdado, segue
   aberto). Falta `List-Unsubscribe-Post: List-Unsubscribe=One-Click` **e** a rota
   `/descadastro/{token}` aceitar POST (arquivo de outro dono). Pôr só o header
   agora seria pior (POST one-click → 405). Continua candidato assim que a rota
   aceitar POST. Ver "O que depende de outros".
2. **`bounce_amostra_minima` (20) vale para os dois tetos.** Com 20 envios, 1
   reclamação já é 5% — bem acima de 0,3% —, então na prática, passada a amostra
   mínima, **qualquer** reclamação pausa a campanha. É conservador de propósito:
   uma conta suspensa por spam derruba o e-mail com que o cliente fatura, e a
   pausa é trivial de retomar por um humano. Se o volume mostrar que isso é
   sensível demais, a saída é uma amostra mínima **própria** para reclamação —
   mas isso mora em `config.py` (outro dono), então não fechava aqui.
3. **A supressão por endereço morto grava o e-mail cru** (herdado). Minimizar
   para hash exige a **consulta** de opt-out por hash (`repositories/misc.py`),
   fora do meu escopo. Registrado para casar com Compliance.
4. **Bounce `Undetermined` → `transitorio` (não suprime).** Escolha conservadora
   e reversível, herdada; confirmar com produto/ops se o volume for alto.

### O que depende de outros

- **Promover `RECLAMACAO_TAXA_MAXIMA` (e uma amostra mínima de reclamação) a
  `Settings`** — mora em `config.py`, de outro dono. Hoje são constante de módulo,
  o que resolve o risco; virar setting é conforto de operação, não pré-requisito.
- **One-click do RFC 8058** (Envio ↔ dono das rotas): o header é meu e trivial; o
  endpoint POST em `api/routes/compliance.py` não é. Sobem **juntos**, senão o
  descadastro quebra (405). Sem mudança nesta execução.
- **Retorno assíncrono do SNS** (item 8) segue testado por contrato e sem rota que
  o chame (verificar assinatura X.509 do SNS + confirmar inscrição, em
  `api/routes/entregabilidade.py`) — sem mudança nesta execução.

---

## 2026-09-20 — a pausa por reputação agora PARA o envio (não só a leva)

### O que corrigi (com teste)

**Uma campanha `PAUSADA` ou `FALHOU` não despacha mais abordagem fria nova —
nem por `aprovar` humano, nem pelo worker (`processar_pendentes`).** Fecha o item
que estava aberto desde 16/09 e reapontado em 18/09 (“`aprovar()` numa conta
quebrada pausa a campanha, mas não freia o próximo clique”).

Por que isto é o maior risco de envio que fechava inteiro no meu escopo: com SES
real, a **pausa automática por reputação** (`_pausar_se_preciso`, acima de 2% de
retorno) é a principal defesa do domínio — o ativo mais frágil do produto —
contra a espiral que mata o domínio. Só que essa defesa era **porosa**:
`checar_bloqueios` nunca olhava `campanha.status`. A cadência já se recusava a
tocar campanha parada (`cadencia.CAMPANHA_PARADA`), mas assim que a campanha
pausava, um `aprovar` na fila de aprovação ou o worker drenando a fila
continuavam mandando cold mail **justamente para a campanha que estourou o
limite**. A pausa não parava o sangramento.

**A decisão de desenho (a que o radar dizia “não decido sozinho”), resolvida:**
a trava vale só para **abordagem fria** (primeiro contato + toques de cadência).
**Resposta dentro de uma conversa em andamento não é barrada** — a do Motor 4
(auto) e a manual. Uma resposta a quem já escreveu é *solicitada*: não ameaça a
reputação, e bloqueá-la só perderia negócio no pior momento (lead engajado). A
resposta manual (`conversa.py`, fora do meu escopo, não olha o status da
campanha) continua sendo a saída para conversar com um lead engajado de campanha
pausada. Ou seja: a automação de prospecção para; a conversa não.

Como ficou, em **um único ponto de estrangulamento** (`envio.py`, só meu):

- `CAMPANHA_PARADA = {PAUSADA, FALHOU}` — espelha a regra que a cadência já usa.
- `checar_bloqueios(..., abordagem_fria=False)` — ganhou a flag. Quando `True` e a
  campanha está parada, devolve `Bloqueio("campanha_parada", status)`. O padrão
  `False` preserva **byte a byte** todos os chamadores externos (as respostas do
  `conversa.py` e a cadência, que já barra antes).
- `despachar` — o único caminho de saída — calcula `_e_abordagem_fria(mensagem)`
  e passa a flag. Abordagem fria = a mensagem **não** é resposta de conversa
  (`metadados["intencao"]` ausente) nem manual (`gerado_por != "humano"`). Assim
  `aprovar`, `processar_pendentes` e o disparo automático do lote passam a
  respeitar a pausa sem eu tocar em `cadencia.py` nem em `conversa.py`.
- `preparar_lote` — porta da frente: campanha parada retorna lote vazio **sem
  redigir** (não queima geração de IA numa campanha que não vai despachar).

`SendService` segue o único caminho de saída e opt-out segue terminal: esta
mudança só **adiciona** bloqueio, nunca abre exceção.

Testes: 3 novos em `test_fase3_abordagem.py` — `aprovar` de abordagem fria em
campanha pausada é bloqueado e nada sai do outbox; `preparar_lote` em campanha
pausada não gera nada; e o teste que fixa a decisão de desenho (sem a flag, a
pausa **nunca** é o motivo do bloqueio; com a flag, é). Verificado que falham
antes e passam depois. **455 passed, 3 skipped; `ruff` limpo.**

### O que achei e NÃO corrigi (uma coisa por execução)

1. **🔴 O “descadastro de 1 clique” NÃO é o one-click do RFC 8058 — e o docstring
   do SES afirma que é.** `ses_email.py` (linha 11) e os comentários dizem “1
   clique … já implementado”, mas o e-mail leva só o header `List-Unsubscribe:
   <https…>` — **falta `List-Unsubscribe-Post: List-Unsubscribe=One-Click`** — e a
   rota `/descadastro/{token}` (`api/routes/compliance.py`) é **só GET**. Gmail e
   Yahoo exigem one-click de verdade de quem manda em volume desde 02/2024: sem
   ele, o botão de descadastro pode não aparecer, e quem não acha como sair marca
   como spam — a reclamação é o que suspende a conta e queima o domínio. **Não
   corrigi de propósito porque não fecha inteiro no meu escopo:** o one-click real
   precisa que a rota **aceite POST** (arquivo de outro dono). Pôr só o header
   agora seria **pior** — o provedor faria o POST one-click e levaria 405, um
   descadastro quebrado que o Google detecta. Deixei como dependência cruzada (ver
   abaixo); é forte candidato à próxima execução assim que a rota aceitar POST.
2. **A supressão por endereço morto grava o e-mail cru** (herdado). Minimizar para
   hash exige que a **consulta** de opt-out antes do envio (`repositories/misc.py`)
   compare por hash — fora do meu escopo. Registrado para casar com Compliance.
3. **Bounce `Undetermined` → `transitorio` (não suprime).** Escolha conservadora e
   reversível, herdada; confirmar com produto/ops se o volume for alto.

### O que depende de outros

- **One-click do RFC 8058 (novo, dependência cruzada Envio ↔ dono das rotas).** A
  peça de e-mail (o header `List-Unsubscribe-Post`) é minha e é trivial; a peça
  que falta — `/descadastro/{token}` aceitar **POST** com corpo
  `List-Unsubscribe=One-Click` e efetivar a supressão sem página — mora em
  `api/routes/compliance.py`. As duas têm que subir **juntas**: header sem
  endpoint POST = descadastro quebrado. Quando a rota aceitar POST, eu adiciono o
  header no mesmo `headers=` onde já vai o `List-Unsubscribe` (`envio.py`,
  `cadencia.py`, `conversa.py` — os três montam o mesmo header) e ajusto o
  docstring do SES, que hoje afirma algo que ainda não é verdade.
- **Retorno assíncrono do SNS** (item 8) segue testado por contrato e sem rota que
  o chame (verificar assinatura X.509 do SNS + confirmar inscrição, em
  `api/routes/entregabilidade.py`) — sem mudança nesta execução.

---

## 2026-09-18 — o link de descadastro saiu do cabeçalho e foi para o CORPO

### O que corrigi (com teste)

**Toda abordagem gerada pela IA agora traz o link de descadastro visível no
corpo do e-mail, e não só no cabeçalho `List-Unsubscribe`.** Fecha o item 7 da
fila autônoma.

Por que isto é risco de envio, não de tela: com SES real, o que suspende a conta
e queima a reputação do domínio — o ativo mais frágil do produto — é a **taxa de
reclamação de spam**. Quem não acha como sair marca como spam. O cabeçalho
`List-Unsubscribe` sozinho não basta: muitos clientes de e-mail não o exibem.
Dar o link na cara do destinatário é a mitigação que mais mexe no risco que mais
importa antes de ligar `EMAIL_MODE=real`.

**A regra invisível que só a Consolidação via (radar 0.3, dependência 2):**
rótulo e link ficam na **mesma linha**, de propósito. O Motor 4 remove a linha
inteira que contém `/descadastro/` antes de varrer opt-out
(`conversa.py::_RE_LINHA_DO_NOSSO_LINK`, já no `main`). Se o rótulo
("descadastre-se") caísse numa linha separada da URL, ele voltaria citado em toda
resposta e um "tenho interesse" que citasse nosso rodapé viraria opt-out — que é
**terminal**. Por isso o rodapé é uma linha só, e o teste prova que, removida a
linha do `/descadastro/`, não sobra nenhuma marca de opt-out no corpo.

Onde:

- `personalizacao.py` — nova `LINHA_DESCADASTRO` (rótulo + `{link}` na mesma
  linha) anexada ao corpo logo abaixo da declaração de IA. O link é o
  `OptOutService.link_para(lead, url_publica)`, **determinístico** (HMAC de
  `lead.id` + `app_secret`): sai idêntico ao que o `SendService` e a cadência já
  põem no header `List-Unsubscribe`, então o destinatário não vê dois endereços
  de saída diferentes.
- **Cobre a cadência de graça:** `personalizacao.gerar` é o mesmo caminho dos
  toques 2 e 3 (Motor 5), então todos os toques passaram a levar o link no corpo
  **sem tocar em `cadencia.py`** (que não é meu).

`SendService` continua o único caminho de saída e opt-out continua terminal:
esta mudança só **adiciona** um link visível, não abre exceção a nada.

Teste: 1 novo em `test_fase3_abordagem.py`
(`test_corpo_traz_link_de_descadastro_com_rotulo_na_mesma_linha`) — verificado
que **falha antes** (corpo sem `/descadastro/`) e **passa depois**. **419 testes,
3 pulados; `ruff` limpo.**

### O que achei e NÃO corrigi (uma coisa por execução)

1. **A resposta manual (Etapa 5) leva o link só no cabeçalho.** O corpo digitado
   pela pessoa não recebe o link visível — o rodapé é montado em `conversa.py`
   (`responder_manualmente`), **fora do meu escopo**. Quando for para o corpo lá,
   vale a mesma regra: rótulo e link na mesma linha, senão a blindagem do Motor 4
   não pega. Registrado para o dono daquele arquivo.
2. **O link do corpo e o do header são calculados duas vezes** (uma na
   personalização, uma no `SendService`/cadência ao gravar a `Message`). São
   idênticos por serem determinísticos, então não há divergência possível; unir
   numa fonte só (campo `link_descadastro` na `Personalizacao`) seria limpeza,
   mas mexeria em `cadencia.py`, que não é meu. Deixei como está.
3. **`aprovar()` numa conta quebrada pausa a campanha, mas não freia o próximo
   clique** — herdado da execução de 16/09, segue aberto. A leva
   (`preparar_lote`/`processar_pendentes`) para na primeira falha de conta, mas
   um segundo `aprovar` manual ainda tentaria enviar, porque `checar_bloqueios`
   não olha `campanha.status`. Um guardrail "campanha pausada não despacha"
   fecharia isso, mas muda também o comportamento de campanhas pausadas por
   reputação — é decisão de desenho. Bom candidato para a próxima execução.

### O que depende de outros

- **Motor 4 já está pronto para receber este rodapé** (`conversa.py`, não é meu):
  a remoção da linha do `/descadastro/` roda **depois** da decodificação de
  quoted-printable, então mesmo que o SES quebre a linha longa do link com um
  soft break (`=\n`) na entrega, o QP é remontado antes da varredura e o
  `/descadastro/` volta inteiro numa linha só. Nada a fazer aqui; registro por
  ser a peça que torna a "mesma linha" segura ponta a ponta.
- **Retorno assíncrono do SNS** continua testado por contrato e sem rota que o
  chame (item 8 da fila, em `api/routes/entregabilidade.py`, não é meu) — sem
  mudança nesta execução.

---

## 2026-09-16 — a falha SÍNCRONA de envio deixou de ser um "FALHOU" mudo

### O que corrigi (com teste)

**Uma recusa síncrona do SES agora tem consequência — e a consequência certa
para cada tipo de recusa.**

Antes, quando o `send_email` do SES estourava, o `despachar` (em `envio.py`) só
marcava a mensagem `FALHOU`. O `SendResult.detalhes["permanente"]` que o
adaptador calculava não era lido por ninguém. Dois danos ficavam soltos:

- **endereço morto continuava na base**: o próximo toque de cadência tentava de
  novo, e o SES cobra caro por insistir num endereço morto;
- **e o "permanente" era uma armadilha**: `ERROS_PERMANENTES` misturava falha do
  **destinatário** (`MessageRejected`) com falha da **conta/remetente**
  (`AccountSuspendedException`, `MailFromDomainNotVerifiedException`). Agir
  cegamente sobre ele para suprimir o destinatário **apagaria a base inteira
  durante uma suspensão de conta**.

A recusa síncrona passou a ser classificada por **escopo do dano**
(`EscopoFalhaEnvio`, em `entregabilidade.py`), e cada escopo tem a ação oposta:

- **`conta`** (conta suspensa, envio pausado, MAIL FROM não verificado) →
  **pausa a campanha** e **interrompe a leva** (para não redigir com IA os
  próximos leads só para falhar igual). **Não** suprime nem descarta ninguém: o
  problema é do remetente, os leads seguem válidos para quando a conta voltar.
- **`destinatario`** (endereço na lista de supressão da conta — morto de um
  bounce anterior) → **suprime aquele contato** (origem `bounce_permanente`) e
  **descarta o lead**, pelo mesmo efeito de um bounce permanente assíncrono, mas
  **sem** contar na taxa de reputação: a mensagem nunca foi aceita, não é
  "retorno" de nada enviado, e contá-la inflaria a taxa sobre um denominador que
  não existe.
- **`transitoria`** (throttle, 5xx, ou `MessageRejected` ambíguo por
  conteúdo/identidade) → só `FALHOU`, como antes.

Isso fecha os itens **1 e 2** da fila "não corrigi" desta área, juntos e de
propósito: o item 2 (o `MessageRejected` sobrecarregado) **não é opcional** ao
fazer o item 1. Tratar todo `MessageRejected` como endereço morto viraria
**supressão em massa** por uma recusa de conteúdo (que atinge todos os
destinatários) ou pela identidade não verificada do **sandbox** (que atinge todo
alvo durante o warmup). Por isso um `MessageRejected` só vira `destinatario`
quando o texto do erro diz explicitamente que veio da **lista de supressão**; na
dúvida cai em `transitoria`, que não suprime ninguém. O sinal definitivo de
endereço morto continua sendo o **bounce assíncrono via SNS**, tratado à parte.

`SendService` continua o único caminho de saída, e opt-out continua terminal: a
supressão por endereço morto **adiciona** bloqueio (nunca abre exceção), e
`_descartar_por_endereco_morto` se recusa a mexer em lead já `opt_out` ou
`descartado`.

Onde:

- `adapters/real/ses_email.py` — `classificar_falha_ses`, `ERROS_DE_CONTA`,
  `_MARCAS_SUPRESSAO`; `detalhes` agora carrega `escopo_falha` (vocabulário
  neutro de provedor, não o código cru do SES).
- `entregabilidade.py` — `EscopoFalhaEnvio`, `suprimir_destinatario_morto`,
  `pausar_por_falha_de_conta`, e o helper `_descartar_por_endereco_morto`
  extraído e **reusado pelo bounce assíncrono** (uma fonte só para o descarte).
- `envio.py` — `despachar` chama `_tratar_falha_sincrona`; a leva para em
  `interrompido_por_conta` (em `preparar_lote` e `processar_pendentes`).

Testes: 8 em `test_fase7_adaptadores_reais.py` (matriz de classificação por
escopo, incluindo os dois casos-armadilha — conteúdo e sandbox não-verificado —
e o wiring do `escopo_falha`) e 3 ponta a ponta com banco em
`test_fase3_abordagem.py` (destinatário morto suprime+descarta; conta
pausa+interrompe a leva e não toca em lead nem em opt-out; transitório só marca
FALHOU). Substituído o antigo `test_ses_marca_erro_permanente`, que fixava o
booleano removido. **397 passed, 3 skipped; `ruff` limpo.**

### O que achei e não corrigi (uma coisa por execução)

1. **`aprovar()` numa conta quebrada pausa a campanha, mas não tem freio para o
   próximo clique.** A leva (`preparar_lote`/`processar_pendentes`) para na
   primeira falha de conta, mas `aprovar` (lote=None) só pausa a campanha —
   `checar_bloqueios` não olha `campanha.status`, então um segundo `aprovar`
   manual ainda tentaria enviar. Um guardrail "campanha pausada não despacha"
   fecharia isso, mas muda também o comportamento para campanhas pausadas por
   **reputação**, então é decisão de desenho. Bom candidato para a próxima
   execução, com teste.
2. **A supressão por endereço morto grava o e-mail cru** (igual ao bounce
   assíncrono). O radar de Compliance (item 5, "eliminação guarda o e-mail cru,
   não o hash") aponta o mesmo: minimizar para hash exige que a **consulta** de
   opt-out antes do envio também compare por hash — vive em
   `repositories/misc.py`, fora do meu escopo. Registrado para casar com aquela
   mudança quando vier.
3. **Bounce `Undetermined` → `transitorio` (não suprime).** Escolha conservadora
   e reversível, herdada da execução anterior; ainda vale confirmar com
   produto/ops se o volume for alto. Documentado no código.

### O que depende de outros

- **A classificação síncrona já roda em runtime** (`despachar` age sobre
  `escopo_falha`), diferente do tradutor **assíncrono** de SNS, que continua
  **testado por contrato mas sem rota que o chame**. Falta, em
  `api/routes/entregabilidade.py` (não é meu arquivo): aceitar o envelope cru do
  SNS, verificar a assinatura X.509 do SNS e percorrer `classificar_retorno_ses`.
  Tudo o que a execução de 2026-09-13 listou embaixo continua valendo.
- **`checar_bloqueios` ignorar campanha `PAUSADA`** (item 1 acima) tocaria só
  `envio.py` (meu), mas é decisão de comportamento — anotado, não decido sozinho.

---

_As seções abaixo são o diário da execução de **2026-09-13** (tradutor SNS),
mantidas como estavam. **Os itens 1 e 2 daquela lista "não corrigi" foram
resolvidos nesta execução** — ver o topo._

## O que foi corrigido nesta execução (2026-09-13)

**O tradutor de retorno assíncrono do SES (bounce/complaint via SNS) não existia.**

Era o maior risco que fechava inteiro dentro do escopo. A rota
`/v1/inbound/retorno` só aceita um payload **já normalizado** (`RetornoRecebido`
→ `TipoRetorno`), e o comentário da própria rota diz "o adaptador da Fase 7
traduz para este" — mas **esse adaptador não estava escrito**. Consequência ao
ligar `EMAIL_MODE=real`: a reclamação de spam e o bounce permanente chegam do
SES no formato SNS e **não têm caminho até `opt_outs`**. A taxa de reclamação
sobe sem freio, o SES suspende a conta, e o domínio do cliente morre junto —
levando o e-mail com que ele fatura.

Adicionado em `adapters/real/ses_email.py` (função pura, sem rede, sem boto3):

- `classificar_retorno_ses(payload) -> list[RetornoSES]` — traduz uma
  notificação do SES para a lista de retornos normalizados. Os campos de
  `RetornoSES` batem **1:1** com os kwargs de
  `ServicoDeEntregabilidade.registrar`, de propósito: quem consome só percorre
  a lista e repassa. Cobre:
  - envelope do SNS (evento serializado em `Message`), evento já
    desembrulhado, e o formato de *event publishing* (`eventType`);
  - `Bounce` → `Permanent` vira `PERMANENTE`; `Transient`/`Undetermined` viram
    `TRANSITORIO` (não suprimem);
  - `Complaint` → `RECLAMACAO`, com o `complaintFeedbackType` no diagnóstico;
  - bounce de lote → **um retorno por destinatário**;
  - `Delivery`/`Send`/etc. → `[]`;
  - `Nome <e-mail>` → extrai o endereço puro (senão a supressão ficaria sob uma
    chave que não casa com o e-mail do lead);
  - payload malformado → `[]`, **nunca levanta** (um webhook que estoura vira
    500 e o SNS reenvia em laço).
- `url_de_confirmacao_sns(payload)` — devolve o `SubscribeURL` do handshake de
  inscrição, para a rota confirmar (sem isso o SNS nunca começa a entregar).

Testes: 12 de contrato em `test_fase7_adaptadores_reais.py` (seção "SES —
retorno assíncrono") + 2 ponta a ponta com banco em `test_motor5_cadencia.py`
que provam que a notificação crua do SES suprime de fato (reclamação →
`OPT_OUT` com origem `RECLAMACAO_SPAM`; bounce permanente → `DESCARTADO` com
origem `BOUNCE_PERMANENTE`). **Suíte inteira e `ruff` verdes.**

`entregabilidade.py` não precisou mudar: seu `registrar` já consome exatamente
esses campos. O tradutor mora no adaptador (SES-específico) e não cria ciclo de
import (`TipoRetorno` é importado sob demanda; anotação via `TYPE_CHECKING`).

---

## O que achei e NÃO corrigi (uma coisa por execução)

> **Itens 1 e 2 abaixo foram RESOLVIDOS em 2026-09-16** — ver a seção do topo.
> Ficam aqui pelo argumento; não refazer.

1. ✅ **[RESOLVIDO 2026-09-16] `SendResult.detalhes["permanente"]` é calculado pelo SES e ninguém lê.**
   Em `envio.py::despachar`, uma falha **síncrona** de envio só marca a
   mensagem `FALHOU`: não suprime nem descarta. Um endereço morto continua na
   base e o próximo toque de cadência tenta de novo — o SES cobra caro por
   insistir em endereço morto.
   **Cuidado que torna isto não-trivial:** `ERROS_PERMANENTES` em `ses_email.py`
   mistura falha **do destinatário** (`MessageRejected`) com falha **da
   conta/remetente** (`AccountSuspendedException`,
   `MailFromDomainNotVerifiedException`). Agir cegamente sobre `permanente` para
   suprimir o destinatário **apagaria a base inteira durante uma suspensão de
   conta**. O certo é separar os dois: destinatário-permanente suprime aquele
   contato; conta/remetente deve **PAUSAR tudo**, não descartar leads. Bom
   candidato para a próxima execução.

2. ✅ **[RESOLVIDO 2026-09-16] `MessageRejected` é sobrecarregado no SES** (endereço na lista de
   supressão da conta vs. conteúdo recusado por política). Se o caminho síncrono
   passar a consumir `permanente`, distinguir o sub-motivo importa — senão uma
   recusa por conteúdo (que atinge todos os destinatários) viraria supressão em
   massa. *(Feito junto com o item 1: só a marca de "lista de supressão" vira
   `destinatario`; o resto cai em `transitoria`.)*

3. **Bounce `Undetermined` → tratado como `TRANSITORIO` (não suprime).** É uma
   escolha conservadora e reversível (perde um lead possivelmente bom, mas não
   machuca ninguém). Pode merecer confirmação de produto/ops se o volume de
   `Undetermined` for alto. Está documentado no código.

---

## O que depende de outros (fora do meu escopo de arquivos)

O tradutor está **testado por contrato, mas ainda não é chamado em runtime** —
como todos os adaptadores da Fase 7 neste repo, que existem prontos antes da
primeira chave. Para ligar ponta a ponta falta, em
`app/api/routes/entregabilidade.py` (dono da rota, **não é meu arquivo**):

- Aceitar o **envelope cru do SNS** em `/v1/inbound/retorno`, além do formato
  normalizado atual.
- **Verificar a assinatura do SNS** (X.509 via `SigningCertURL`/`Signature`) —
  é um esquema **diferente** do HMAC do `webhook_autenticado` que hoje protege a
  rota. Decisão de desenho do dono da rota: o SES não assina com o segredo do
  app. Sem verificação, um bounce forjado suprime contato e descarta lead — dá
  para apagar a base de um concorrente com um laço de `curl`.
- Tratar `SubscriptionConfirmation` fazendo `GET` em
  `url_de_confirmacao_sns(payload)`.
- Percorrer `classificar_retorno_ses(payload)` chamando
  `ServicoDeEntregabilidade.registrar(...)` para cada item.

Infra/ops (RUNBOOK-FASE7 §5): configuration set do SES com tópico SNS de
bounce/complaint apontando para esse endpoint; domínio verificado com
SPF/DKIM/DMARC; saída do sandbox; warmup via `MAX_ENVIOS_POR_USUARIO_DIA`.

Nada aqui liga chave nenhuma nem toca em opt-out como exceção: opt-out continua
terminal, e a reclamação de spam continua indo para `OPT_OUT`.
