> **ESTADO INTEGRADO NA VERSÃO PRINCIPAL — 15/09/2026**
>
> De 12 a 15/09 as rotinas trabalharam em cópias separadas e não enxergavam o
> trabalho umas das outras — a mesma correção chegou a ser feita quatro vezes.
> As correções abaixo foram escolhidas, testadas juntas e integradas no `main`.
> **Leia esta lista antes de agir: o que coincidir com ela já está resolvido e
> não deve ser refeito.** Os hashes citados são dos commits originais; no `main`
> eles têm hash novo, com a mesma mensagem.
>
> - Expurgo de mensagem entra na trilha e não reconta o que já saiu (`1a102e6`).
> - Expurgo mascara o `remetente` da resposta do lead (`fde1fa8`).
> - Retenção passa a expurgar as `privacy_requests` (`43cdec9`).
> - Expurgo do assunto da mensagem (`48456ca`).
> - **A verificar:** o link de descadastro vai só no cabeçalho `List-Unsubscribe`, não no texto do e-mail. O guardrail do projeto diz que toda mensagem leva o link — e a rotina de Conversa já está protegida para o dia em que ele for para o corpo.
>
> O que vem abaixo é o diário da execução de 15/09, mantido como estava.

---

# Radar — Compliance e Jurídico

> Diário da rotina que cuida **só** de `backend/app/services/compliance.py`,
> `docs/POLITICA-DE-PRIVACIDADE.md`, `docs/DECLARACAO-DE-IA.md` e dos testes
> correspondentes. Este radar é o único lugar onde a rotina escreve fora desses
> arquivos. Uma coisa nova por execução.
>
> **A régua:** enquanto tudo é mock, nenhum dado real de terceiro é tratado —
> nada aqui é violação hoje. O relógio começa a correr no dia em que a Fase 7
> ligar os provedores reais: aí o produto passa a coletar dados de empresas
> reais e a mandar mensagem para pessoas reais, e cada item abaixo vira risco de
> verdade. Cada achado é medido por esse dia.
>
> **Quem escreve aqui não é advogado.** O que exige parecer profissional está
> marcado **[revisão jurídica]**; o que é decisão de produto/negócio está
> marcado **[decisão de produto]**. Esses não devem ser tratados como resolvidos.

**Última execução:** 2026-09-21

---

## Execução 2026-09-21 — o acesso (art. 18, II) revela a supressão que guardamos

> Parti de `origin/main` (`85c9c03`). Reconferi o `HANDOFF` §0/§0.1/§0.3 e a fila
> deste radar. Já integrado no `main` e **não refeito**: as correções de retenção
> de setembro, o `relatorio` enxergar a resposta do titular (16/09), a
> anonimização dos reidentificadores (20/09, 1ª leva), a eliminação alcançar as
> mensagens do titular (20/09, 2ª leva) e o filtro de tenant em `/solicitacoes`
> (item 2 — o §0.3 do HANDOFF confirma resolvido e manda **não tratar como
> pendência**; mora fora do meu escopo de qualquer jeito). Uma coisa só nesta
> execução.

### O que corrigi (com teste)

**O relatório de acesso do titular era mudo sobre a lista de supressão — o
`opt_out` com o e-mail cru que guardamos em caráter PERMANENTE não aparecia.**
`services/compliance.py` · `PrivacyService.relatorio`

O acesso (art. 18, II; Política §8 "Saber o que temos") tem que devolver **todo**
dado pessoal que guardamos sobre o titular. `relatorio()` já devolvia os leads e
as mensagens dos dois lados, mas **não** a lista de supressão — e um `opt_out`
guarda o contato cru do titular, a origem, o motivo e a data, retido em caráter
**permanente** (Política §7: "Registro de descadastro: permanente"). O buraco
ficava gritante **depois de uma eliminação**: `eliminar()` anonimiza o lead e
expurga as mensagens, mas **mantém** o `opt_out` com o e-mail cru — então um novo
pedido de acesso devolvia `leads=[]`, `mensagens=[]`, como se não tivéssemos mais
nada, enquanto seguíamos guardando o endereço real do titular para sempre, sem
contar a ele. É a mesma simetria acesso↔eliminação que os leads e as mensagens já
seguem (16/09, 20/09): faltava fechá-la para a supressão.

Agora `relatorio()` traz também `opt_outs`, com a origem, o motivo, o escopo
(global ou do controlador — **sem** expor `user_id`) e desde quando o contato
está suprimido. É disclosure do que **já** guardamos, não coleta nova. A Política
§8 passou a dizer que "saber o que temos" inclui esse registro de supressão,
para o texto público não prometer menos do que o sistema faz.

Teste novo `test_acesso_revela_a_supressao_que_guardamos_do_titular` — falha antes
(`KeyError: 'opt_outs'`) e passa depois; fixa também a simetria: mesmo com leads e
mensagens já vazios após a eliminação, o acesso ainda revela a supressão que
sobrevive. `pytest` (500 passed, 3 skipped) e `ruff` verdes.

### O que achei e NÃO corrigi

Nada novo fora da fila abaixo. Esta correção é sobre o que o acesso **revela**;
ela **não** resolve o item 5 (a supressão ainda guarda o e-mail **cru**, não o
hash — coisa diferente, é o que a lista **guarda**, e a consulta de opt-out mora
em `repositories/misc.py`/`services/envio.py`, fora do meu escopo). Herda o
mesmo ressalvo do item 1: como `POST /privacidade/solicitacao` atende sem
**verificar a identidade** do titular, o relatório inteiro (leads, CNPJ,
proveniência, mensagens — e agora a supressão) fica exposto a um impostor.
Revelar a supressão **não piora** isso — o impostor já recebia todo o resto —,
mas a trava de verdade continua sendo o item 1 (verificação de identidade,
`api/routes/compliance.py`, fora do meu escopo). **[revisão jurídica]** se o
acesso é obrigado a **listar** a supressão (revelá-la é o caminho transparente e
sem risco; a obrigatoriedade exata é parecer profissional).

### O que depende de outra rotina ou de decisão humana

Esta correção vive inteira em `compliance.py` (+ a linha da Política) — não cria
dependência nova. As pendências seguem as da tabela ao fim do radar (rotas,
worker, opt-out/envio, domínio real). O que **trava de verdade** para o dia da
Fase 7 continua sendo o 🔴 item 1 (verificação de identidade do titular em
`api/routes/compliance.py`, fora do meu escopo).

---

## Execução 2026-09-20 — eliminação (art. 18, IV) alcança as mensagens do titular

> Parti de `origin/main` (`bec3f86`). Reconferi o `HANDOFF` §0/§0.3 e a fila: as
> correções de retenção de setembro, a anonimização dos reidentificadores
> (execução anterior, já no `main`) e o filtro de tenant em `/solicitacoes`
> (§0.3, fora do meu escopo) já estão integrados. Não refiz nada disso.

### O que corrigi (com teste)

**A eliminação a pedido do titular anonimizava os leads mas deixava as mensagens
trocadas com ele de pé — o e-mail dele e o texto que ele mesmo escreveu
sobreviviam na tabela `messages` até o prazo de retenção (365 dias).**
`services/compliance.py` · `PrivacyService.eliminar`

O direito de eliminação (art. 18, IV) tem que alcançar **todo** o dado pessoal do
titular. E o relatório de **acesso** (art. 18, II) já reconhece as mensagens como
dado dele: desde 16/09, `relatorio()` devolve os dois lados (`destinatario` **ou**
`remetente`), porque numa mensagem de entrada o e-mail do titular está no
`remetente`. Mas `eliminar()` só chamava `_anonimizar` nos **leads** — as
mensagens ficavam intactas. Resultado: o acesso enxergava os dois lados, a
eliminação apagava só um. O endereço real do titular (nos dois lados) e o corpo
que ele escreveu ficavam vivos até o expurgo por prazo levá-los, 365 dias depois.
A própria Política §8 promete que, ao pedir eliminação, guardamos "apenas o
registro de descadastro" — o que o código antigo **contrariava**.

Agora `eliminar()` também expurga as mensagens do contato, com o **mesmo
tratamento da retenção**, só que imediato e restrito ao titular: corpo vira
`CORPO_EXPURGADO`, assunto some, e os **dois** endereços são mascarados. A busca
cobre os dois lados (igual ao acesso) e pula o que já saiu (`corpo != CORPO_EXPURGADO`,
idempotente). Entra na trilha um evento `DADO_ANONIMIZADO` de resumo
(`entidade_tipo="mensagens"`), cumprindo a Política §7 ("cada remoção é
registrada"). Extraí o tratamento de campo para `_expurgar_conteudo_mensagem`,
usado agora **pela retenção e pela eliminação** — um só lugar, para nunca
divergirem (a retenção seguiu idêntica; os testes dela continuam verdes).

Teste novo `test_eliminacao_expurga_as_mensagens_trocadas_com_o_titular` — falha
antes (`KeyError: 'mensagens_expurgadas'`; as mensagens sobreviviam) e passa
depois; fixa também que o acesso, **após** a eliminação, não acha mais mensagem
pelo contato (a simetria acesso↔eliminação). `pytest` (473 passed, 3 skipped) e
`ruff` verdes.

### O que achei e NÃO corrigi

Nada novo fora da fila abaixo. Esta correção fecha a assimetria **acesso↔eliminação**
para as mensagens; ela **não** resolve o item 5 (a supressão ainda grava o e-mail
cru, não o hash — coisa diferente: é o que a lista de supressão **guarda**, não o
que a eliminação **apaga**). Fica uma dúvida de **margem** para a caneta jurídica:
mascarar os dois endereços apaga também o **nosso** endereço na linha da mensagem
— escolhi manter idêntico ao expurgo por prazo (que já faz isso e nenhum é dado de
terceiro: cada mensagem é 1:1 entre nós e um lead), mas confirmar o limite exato é
**[revisão jurídica]**. Não mexi nos itens 1–4 e 6–10; nenhum coincide com esta
correção.

### O que depende de outra rotina ou de decisão humana

Esta correção vive inteira em `compliance.py` — não cria dependência nova. As
pendências seguem as da tabela ao fim do radar (rotas, worker, opt-out/envio,
domínio real). O que **trava de verdade** para o dia da Fase 7 continua sendo os
🔴 itens 1 e 2 (verificação de identidade do titular e — já resolvido no `main` —
filtro de tenant em `/solicitacoes`), ambos em `api/routes/compliance.py`, fora do
meu escopo.

---

## Execução 2026-09-20

> Parti de `origin/main` (`e81f530`). Reconferi o `HANDOFF` §0/§0.3 e a fila
> deste radar: as correções de retenção de setembro (audita e não reconta,
> mascara remetente, alcança `privacy_requests`, expurga assunto, `[expurgado]`
> no contato sem `@`) e o buraco do `relatorio` (acesso enxerga a resposta do
> titular) já estão no `main`. Não refiz nada disso. O item 2 (🔴 `/solicitacoes`
> sem filtro de tenant) o `HANDOFF` §0.3 confirma **já corrigido** no `main` — e
> mora fora do meu escopo de qualquer jeito.

### O que corrigi (com teste)

**A anonimização apagava o texto do endereço mas deixava a empresa
reidentificável — sobreviviam CNPJ, `place_id`, lat/long exata, CEP e bairro.**
`services/compliance.py` · `_anonimizar`

Anonimizar (LGPD art. 5º, XI) é deixar o dado sem poder ser reassociado à empresa
por meios razoáveis. `_anonimizar` zerava e-mail, telefone, site, `endereco` (em
texto), `embedding`, `contexto` e `resumo`, e trocava a razão social por
`[anonimizado]` — mas mantinha de pé **todos os reidentificadores estruturados**:

- **`place_id`** — a chave estável do Google Places. Um `GET /places/{id}`
  recompõe nome, endereço e telefone do estabelecimento: o dado "anonimizado"
  volta inteiro. E ele sobrevivia em **dois** lugares — a coluna `place_id` **e**
  a `provenance` (que guarda `{"place_id": ...}`, ver `services/leads.py`).
  Zerar só a coluna deixaria a cópia na proveniência.
- **`cnpj`** — identifica a pessoa jurídica direto na base da Receita.
- **`latitude`/`longitude`** — `Numeric(9,6)`, precisão de ~0,1 m: reverse geocode
  devolve o endereço exato.
- **`cep`** (8 dígitos) e **`bairro`** — localização de precisão; incoerente
  apagar o `endereco` em texto e manter a versão estruturada da mesma coisa.

Agora `_anonimizar` também zera `cnpj`, `place_id`, `cep`, `bairro`, `latitude`,
`longitude` e remove `place_id` da `provenance` (via constante
`_PROVENANCE_REIDENTIFICADORAS`, preservando fonte/base legal/campos/coletado_em
para a auditoria e a LIA). Ficam só as **dimensões agregadas** — `municipio`,
`uf`, CNAE, porte e score —, que alimentam o aprendizado sem apontar para uma
empresa. Vale para os **dois** caminhos que chamam `_anonimizar`: a retenção por
prazo (`RetencaoService`) e a eliminação a pedido do titular (`PrivacyService.eliminar`, art. 18, IV).
Teste novo `test_anonimizar_apaga_os_reidentificadores_da_empresa` — falha antes
(`cnpj`/`place_id`/… sobreviviam) e passa depois; também fixa que `municipio`/`uf`
**permanecem**, para uma próxima execução não anonimizar demais. `pytest`
(461 passed, 3 skipped) e `ruff` verdes. Seguro por construção: o dedup já ignora
lead com `deleted_at` (`repositories/leads.py`), então zerar `place_id`/`cnpj` de
lead anonimizado não afeta descoberta; nenhum teste esperava esses campos vivos.

### O que achei e NÃO corrigi

Nada novo fora da fila abaixo. A correção de hoje resolve a **reidentificação**
por campo estruturado; ela **não** resolve o item 5 (eliminação guarda e-mail
cru na supressão, não hash) — são coisas diferentes: uma é o dado que o lead
guarda, a outra é o que a lista de supressão grava. Fica uma dúvida de **margem**
para quem tiver a caneta jurídica: se as geografias grossas (`municipio`/`uf`) ou
outros metadados da `provenance` também deveriam sair. Escolhi a linha padrão de
anonimização — apagar identificadores diretos e localização de precisão, manter
o agregado estatístico —, mas confirmar o limite exato é **[revisão jurídica]**.
Não mexi nos itens 1–10 restantes; nenhum coincide com esta correção.

### O que depende de outra rotina ou de decisão humana

Esta correção vive inteira em `compliance.py` — não cria dependência nova. As
pendências seguem as da tabela ao fim do radar (rotas, worker, opt-out/envio,
domínio real). O que **trava de verdade** para o dia da Fase 7 continua sendo os
🔴 itens 1 e 2 (verificação de identidade do titular e — já resolvido no `main` —
filtro de tenant em `/solicitacoes`), ambos em `api/routes/compliance.py`, fora
do meu escopo.

---

## Execução 2026-09-18

> Parti de `origin/main` (`186f018`). Reconferi o `HANDOFF` §0 e a fila: as
> correções de retenção de setembro (audita e não reconta, mascara remetente,
> alcança `privacy_requests`, expurga assunto) e o buraco do `relatorio` (acesso
> agora enxerga a resposta do titular) já estão no `main`. Não refiz nada disso.

### O que corrigi (com teste)

**O expurgo anulava — em vez de mascarar — o destinatário/remetente que não é
e-mail, e a auditoria perdia a evidência de que houve um contato.**
`services/compliance.py` · `_mascarar`

`_mascarar` devolvia `None` para **qualquer** contato sem `@`. No expurgo de
mensagem (`RetencaoService.executar`), um destinatário de **telefone/WhatsApp**
virava `NULL` — e uma linha sem destinatário é indistinguível de uma que nunca
teve um. O dado pessoal precisa sair, mas o **registro de que existiu um
destinatário** é parte da trilha de auditoria e não podia sumir em silêncio.
Hoje o canal é e-mail-first (impacto real nulo), mas o §9 do IDEIAS coloca o
WhatsApp no mapa, e era uma perda silenciosa esperando o canal.

Agora um contato sem `@` vira a marca `CONTATO_EXPURGADO = "[expurgado]"` — a
mesma já usada no expurgo de solicitação (antes embutida como literal na linha,
agora constante reaproveitada). Contato vazio continua devolvendo `None` (não há
o que registrar); e-mail continua virando `us***@dominio`. **Não inventei
máscara parcial de telefone** — essa é a metade que ainda depende de decisão
(abaixo). Teste novo `test_retencao_preserva_registro_de_destinatario_sem_arroba`
— falha antes (`destinatario` virava `None`) e passa depois. `pytest`
(419 passed, 3 skipped) e `ruff` verdes. Fecha a **metade sem decisão** do item 6
da fila.

### O que achei e NÃO corrigi

Nada novo fora do que já está na fila abaixo. A correção de hoje resolve só a
**perda de registro** do item 6; a **máscara parcial de telefone** (quantos
dígitos mostrar, se algum) continua aberta e depende de decidir o formato — não
inventei um para não fingir uma decisão de produto. Os itens 1–5 e 7–10 seguem
como estavam; nenhum coincide com esta correção.

### O que depende de outra rotina ou de decisão humana

Esta correção vive inteira em `compliance.py` — não cria dependência nova. As
pendências continuam as da tabela ao fim do radar (rotas, worker, opt-out/envio,
domínio real). O que **trava de verdade** para o dia da Fase 7 segue sendo os
🔴 itens 1 e 2 (verificação de identidade do titular e filtro de tenant em
`/solicitacoes`), ambos em `api/routes/compliance.py`, fora do meu escopo.

---

## Execução 2026-09-16

> Parti de `origin/main` (`9ee521e`). O risco de processo que abria este radar
> — trabalho parado em branches órfãs — **está resolvido**: o `HANDOFF` §0
> confirma que a consolidação de 15/09 foi integrada e o `main` já carrega as
> quatro correções de retenção (expurgo audita e não reconta, mascara o
> remetente, alcança as `privacy_requests`, expurga o assunto). Não refiz nada
> disso. A seção "⚠️ ANTES DE TUDO" abaixo fica como registro histórico.

### O que corrigi (com teste)

**O relatório de acesso do titular não trazia as respostas que o próprio titular
enviou.** `services/compliance.py` · `PrivacyService.relatorio`

O direito de acesso (art. 18, II) tem que devolver **todo** dado pessoal que
guardamos sobre o titular. Mas `relatorio()` buscava mensagens só por
`Message.destinatario == contato` — e numa mensagem de **entrada** (a resposta
do lead) o titular está no `remetente`, não no `destinatario`, que ali somos nós
(confirmado em `models/message.py:52-56`). Resultado: o relatório mostrava o que
**enviamos ao** titular, mas escondia a resposta que o titular **enviou a nós** —
o texto que ele escreveu e o endereço de onde respondeu, que são dado pessoal
dele. É a mesma assimetria que a retenção já reconheceu ao mascarar o
`remetente`; aqui era o direito de acesso que só enxergava um lado.

Agora a busca cobre os dois lados (`destinatario` **ou** `remetente`) e cada
mensagem do relatório passa a trazer o campo `direcao`, para a lista mista ficar
legível (o que saiu para o titular vs. o que veio dele). Teste novo
`test_acesso_inclui_a_resposta_enviada_pelo_titular` — falha antes (a resposta
de entrada não constava) e passa depois. `pytest` (396 passed, 3 skipped) e
`ruff` verdes.

### O que achei e NÃO corrigi

Nada novo além do que já está na fila abaixo. Reconferi a fila: os itens 1–10
seguem válidos e nenhum coincide com esta correção (o buraco do `relatorio` não
estava mapeado). A correção de hoje **não** resolve o item 5 (eliminação guarda
e-mail cru, não hash): são coisas diferentes — uma é o que o acesso **lê**, a
outra é o que a eliminação **grava**.

### O que depende de outra rotina ou de decisão humana

Sem novas dependências criadas por esta correção — ela vive inteira em
`compliance.py`. As dependências pendentes continuam as da tabela ao fim deste
radar (rotas, worker, opt-out/envio, domínio real). Destaque do que **trava de
verdade** para o dia da Fase 7: itens 🔴 1 e 2 (verificação de identidade do
titular e filtro de tenant em `/solicitacoes`), ambos em
`api/routes/compliance.py`, fora do meu escopo.

---

## ⚠️ ANTES DE TUDO: o trabalho de compliance está se repetindo em branches órfãs

Este é o maior risco desta área hoje, e não é jurídico — é de processo.

Cada execução desta rotina nasce de uma branch nova cortada do `main`, e **nenhuma
das correções anteriores foi integrada ao `main`**. Resultado: cada run começa
sem enxergar o que o anterior fez, e três correções reais de retenção ficaram
paradas, cada uma sozinha numa branch, sem se conhecerem:

| Correção | Branch órfã | Commit de origem |
|---|---|---|
| Expurgo de mensagem entra na trilha e para de recontar | `claude/frosty-hawking-95237b` | `1a102e6` |
| Expurgo mascarava só o destinatário e deixava o **remetente** (o e-mail do lead) sobreviver | `claude/frosty-varahamihira-91db3b` | `fde1fa8` |
| Retenção não alcançava as **solicitações de direitos** (guardava e-mail + relatório para sempre) | `claude/gifted-northcutt-28b406` | `43cdec9` |

**Nesta execução as três foram consolidadas nesta branch** (`cherry-pick -x`,
preservando autoria e histórico), verificadas juntas, e só então foi feita a
correção nova (abaixo). Agora existe **uma** branch com as quatro correções, em
vez de quatro branches com uma cada.

**Dependência que trava tudo:** enquanto esta branch (ou uma consolidação
equivalente) não for para o `main`, o próximo run vai repetir o problema. Isso é
exatamente o que o HANDOFF §0.1 e a lição "fechar = commit E push" tentam
evitar, mas o push sozinho não basta — as branches **estão** no `origin`, o que
falta é **integrar no `main`**. Essa é uma decisão fora do escopo da rotina
(mexe no `main`); precisa de alguém com essa alçada. **[decisão de produto]**

---

## Corrigido nesta execução

### O expurgo de retenção deixava o **assunto** da mensagem sobreviver ao prazo
`services/compliance.py` · `RetencaoService.executar` · commit `48456ca`

O expurgo zerava o corpo e mascarava os endereços, mas mantinha o `assunto` de
pé. E o assunto é conteúdo: na abordagem de saída ele carrega a identidade do
alvo — `_assunto` (em `services/personalizacao.py`) monta *"&lt;serviço&gt; para
&lt;nome da empresa&gt;"*. Passados os 365 dias, o corpo sumia mas o nome da
empresa-alvo e o serviço ofertado continuavam gravados na linha da mensagem —
justamente o dado que o expurgo existe para remover.

Agora o `assunto` some junto com o corpo (vira `NULL`; é nullable, então não
precisa de marca-sentinela — a detecção de "já expurgada" continua sendo pelo
`corpo`). Os metadados e o audit_log encadeado seguem intactos. A Política §7
passou a dizer *"Conteúdo das mensagens (assunto e corpo)"* no lugar de só
"Corpo", para o texto público não prometer menos do que o sistema faz.
`pytest` (345) e `ruff` verdes.

---

## Consolidado nesta execução (correções que já existiam, reunidas aqui)

Não são novas — vieram das branches órfãs acima. Ficam registradas para não
serem "redescobertas" de novo:

1. **Expurgo de mensagem audita e não reconta** (`1a102e6`). O expurgo do corpo
   passou a gerar evento `RETENCAO_EXPURGO` de resumo por rodada (a Política §7
   promete que "cada remoção é registrada na auditoria") e a pular a mensagem já
   expurgada (filtro `corpo != CORPO_EXPURGADO`), que antes recontava a cada
   rodada e inflava `mensagens_expurgadas`.
2. **Expurgo mascara o remetente também** (`fde1fa8`). Em mensagem de entrada
   (a resposta do lead) o e-mail real de quem escreveu está no `remetente`, não
   no `destinatario` — mascarar só o destinatário deixava esse dado pessoal
   sobreviver ao prazo. Agora mascara os dois.
3. **Retenção alcança as solicitações de direitos** (`43cdec9`). Solicitação
   concluída há mais que o prazo tem o dado pessoal expurgado (`contato`,
   `observacao`, e o relatório inteiro em `resultado`), preservando os metadados
   do atendimento para prestação de contas. Idempotente, com evento na trilha, e
   nunca toca em solicitação ainda em aberto. Inclui a linha correspondente na
   Política §7.

---

## Achado e NÃO corrigido (fila para as próximas execuções)

Ordenado por risco no dia em que a Fase 7 ligar. Sem repetir o que já está no
código depois da consolidação acima.

### 🔴 Alto

1. **Solicitação de direito do titular sem verificação de identidade.**
   `POST /privacidade/solicitacao` (público) chama `PrivacyService.atender()` na
   hora, para qualquer tipo, sem provar que quem pede controla aquele contato.
   Com dado real: `acesso` devolve ao solicitante tudo o que temos sobre o
   contato (vazamento para um impostor); `eliminacao` e `oposicao` gravam
   opt-out global e anonimizam leads **em todos os tenants** — qualquer um apaga
   o dado de qualquer empresa. O certo é confirmar a posse do contato antes de
   atender (ex.: link de confirmação enviado ao próprio endereço).
   - **Depende de outros:** a rota vive em `api/routes/compliance.py` e o envio
     de confirmação depende de e-mail real (Fase 7). O desenho do fluxo é
     **[decisão de produto]**; o nível de verificação por tipo de direito é
     **[revisão jurídica]**.

2. **`GET /v1/compliance/solicitacoes` não filtra por tenant.** Lista as últimas
   solicitações **de todos os controladores** (o `select` não tem `where
   user_id`). Como as solicitações públicas nascem com `user_id=None`, um
   controlador autenticado enxerga contato, tipo e status de titulares que
   escreveram sobre leads de outros controladores — fere o isolamento de tenant
   que a Etapa 8 fechou para o resto do sistema.
   - **Depende de outros:** `api/routes/compliance.py`, fora do meu escopo.

### 🟡 Médio

3. **A retenção não alcança lead `ABORDADO`-e-calado nem `OPT_OUT`.**
   `executar()` só anonimiza `DESCOBERTO`, `QUALIFICADO` e `DESCARTADO`. Um lead
   abordado que nunca respondeu, e um lead que fez opt-out, mantêm PII completa
   (e-mail, telefone, endereço, site, `embedding`, `contexto`, `resumo`) para
   sempre. A Política §7 promete "lead sem nenhuma interação: 180 dias" — e um
   abordado em silêncio é, do ponto de vista do titular, exatamente isso. Para o
   `OPT_OUT`, impedir o recontato exige só o contato na lista de supressão, não o
   dossiê inteiro.
   - **[decisão de produto]** o que conta como "interação" e se abordado entra no
     expurgo mexem no ciclo de cadência. **[revisão jurídica]** prazo por estado.
   - É o meu arquivo, mas a decisão vem antes do código. Não implementei porque
     escolher o critério errado apaga dado que a cadência ainda usaria.

4. **Prazo do titular é gravado, mas ninguém vigia o vencimento.**
   `prazo_resposta` é gravado (`now + 15 dias`, art. 19), e **nenhum código lê
   esse campo** para saber se um pedido venceu. A maioria dos direitos é atendida
   na hora, mas `CORRECAO` cai em `EM_ANALISE` e envelhece calada. Falta um
   `pendentes()`/`vencidas()` no `PrivacyService`.
   - **Cuidado com código morto:** um método de serviço sem quem o chame é o
     vício que o HANDOFF cobra (o `executar_retencao` que "existe e nada chama").
     Surfaçar isso exige rota ou tarefa de worker — **fora do meu escopo**.
     Recomendo casar o método com o dono das rotas na mesma leva, senão nasce
     inerte. Por isso não fiz sozinho.

5. **Eliminação guarda o e-mail cru, não o hash.** O comentário em
   `PrivacyService.eliminar` diz "guardamos só o hash do contato", mas o código
   grava o **e-mail cru** na lista de supressão (`opt_outs`), retido em caráter
   permanente. Pedir eliminação deixa o endereço real do titular guardado para
   sempre. Minimizar (guardar hash) exige que a **consulta** de opt-out antes do
   envio também compare por hash — vive em `repositories/misc.py` e
   `services/envio.py`.
   - **Depende de outros** (opt-out/envio). Quando for feito, corrigir também o
     comentário enganoso. **[revisão jurídica]**: confirmar que supressão por
     hash ainda cumpre o dever de impedir o recontato.

### 🟢 Baixo

6. **Máscara parcial de telefone no expurgo — a decidir.** ✅ **Metade resolvida
   em 18/09:** `_mascarar` não anula mais um contato sem `@`; ele vira a marca
   `[expurgado]`, então a auditoria não perde mais o registro de que existiu um
   destinatário/remetente de telefone (era perda silenciosa esperando o WhatsApp,
   §9 do IDEIAS). **Falta:** decidir se, e como, mostrar uma **máscara parcial**
   do telefone (ex.: últimos dígitos) em vez da marca genérica. Não inventei um
   formato para não fingir uma decisão de produto. Enquanto o canal for
   e-mail-first o impacto é nulo; a decisão pode esperar o WhatsApp entrar.

---

## Textos públicos — achado e a decidir

7. **A Política promete expurgo automático que ainda não roda.** A Política §7
   diz "o expurgo roda automaticamente"; o docstring do módulo diz "roda como
   tarefa agendada do worker". **Não roda** — é o item 5 da fila autônoma do
   HANDOFF (`executar_retencao()` existe e nada o chama). Texto público que
   promete o que o sistema não faz é risco por si só. O certo é **fazer rodar**,
   não enfraquecer o texto. Agendar no worker (RQ) é **dependência de outro
   agente** — não toco no worker. Enquanto isso, a mesma afirmação sustenta uma
   salvaguarda da LIA (retenção) — que fica parcialmente aspiracional.

8. **Placeholders e operadores presumidos.**
   - **Domínios reservados.** `privacidade@prospector.local` e
     `app.prospector.local` são placeholders (também em `config.py`:
     `encarregado_email`, `url_publica`). No dia da virada, o descadastro e o
     contato do encarregado precisam de e-mail e domínio reais. A LGPD art. 41
     §1º exige contato do encarregado divulgado de forma clara e objetiva — um
     `.local` (TLD reservado, RFC 6762) não recebe mensagem. **[decisão de
     produto]** o domínio ainda não foi escolhido (HANDOFF §0.2). O texto é meu;
     o `settings.encarregado_email` não.
   - **Operadores nomeados como se já estivessem em produção.** A Política §6
     lista AWS SES, Anthropic e Google Places como operadores. Tudo é mock hoje;
     quando as APIs entrarem, os operadores reais têm que bater com os
     contratados, senão o texto mente.
   - **Controlador sem identificação.** A LIA sai com "CNPJ: não informado" e a
     Política não traz razão social/endereço do controlador nem vigência real.
     **[decisão de produto / revisão jurídica]** quem é o controlador.

9. **Transferência internacional não declarada.** A Política §6 nomeia operadores
   que tratam dado **fora do Brasil** (Anthropic, Google) e não diz uma palavra
   sobre transferência internacional (LGPD art. 33) nem sobre a base que a
   autoriza. É divulgação exigível. Além disso, **nenhum contrato de operador
   (art. 39/DPA)** existe ainda; cada provedor real precisará do seu. Não escrevi
   porque nomear provedor e fixar base enquanto tudo é mock é adiantado — fica
   para quando a Fase 7 fixar quem de fato entra. **[revisão jurídica]**

10. **Prazo único de 15 dias para todo direito.** `PRAZO_RESPOSTA_DIAS = 15`
    (art. 19, II) é o prazo do **acesso** em formato completo. Eliminação,
    oposição e correção têm regime próprio (Resolução CD/ANPD nº 15/2024).
    Aplicar 15 dias a tudo pode estar certo ou ser generoso, mas não conferi caso
    a caso. **[revisão jurídica]**

---

## Depende de outros agentes / fora do meu escopo

| Item | Onde mora | Dono provável |
|---|---|---|
| **Integrar estas correções no `main`** (o risco nº 1 deste radar) | `main` | quem tem alçada de merge / produto |
| Agendar `RetencaoService.executar` periodicamente (7) | `workers/tasks.py` + scheduler | worker/RQ (fila autônoma, item 5) |
| Verificação de identidade do titular (1) | `api/routes/compliance.py` + e-mail real | rotas / produto |
| Filtro de tenant em `/solicitacoes` (2) | `api/routes/compliance.py` | rotas |
| Surfaçar `pendentes()`/`vencidas()` (4) | `api/routes/compliance.py` ou worker | rotas / worker |
| Supressão por hash (5) | `repositories/misc.py`, `services/envio.py` | opt-out/envio |
| Domínio/e-mail reais (8) e prazo de retenção como setting | `app/core/config.py` + DNS | produto (HANDOFF §0.2) |

---

## O que está sólido (para não reabrir à toa)

Conferido nesta leitura, após a consolidação:

- **Opt-out de 1 clique:** token assinado por HMAC (não expõe o id, não se
  forja), idempotente, imediato, terminal para o lead, auditado; a supressão
  sobrevive à eliminação.
- **Direitos do titular:** acesso, eliminação e oposição e portabilidade
  atendidos; correção vai para análise humana. Prazo gravado por pedido
  (ressalva: ninguém vigia o vencimento — item 4). **Eliminação simétrica ao
  acesso (20/09):** o que o acesso devolve como dado do titular — leads **e**
  mensagens (os dois lados) — a eliminação agora remove. Anonimiza os leads,
  expurga corpo/assunto e mascara os dois endereços das mensagens (mesmo
  tratamento da retenção, via `_expurgar_conteudo_mensagem`), imediato, e mantém
  a supressão. Antes as mensagens ficavam vivas até o expurgo por prazo (365 d).
  **Acesso revela a supressão (21/09):** o `relatorio` agora traz também os
  `opt_outs` do contato — o registro de descadastro que guardamos em caráter
  permanente é dado pessoal do titular, e o acesso o revela (origem, motivo,
  escopo, data), sem expor `user_id`. Fecha a simetria acesso↔supressão: depois
  de eliminar, o acesso não devolve mais "nada" enquanto o e-mail segue guardado.
- **LIA** gerada dos dados reais do controlador (fontes e campos vêm do banco),
  com hash, evento de auditoria e as nove seções. Ressalva: a salvaguarda de
  retenção depende do expurgo rodar (item 7).
- **Retenção:** cobre leads sem interação, corpo **e assunto** das mensagens,
  ambos os endereços, e as solicitações de direitos concluídas; idempotente e
  auditada em cada eixo. Endereço sem `@` (telefone) vira `[expurgado]`, não
  `NULL` — o registro de que houve um contato sobrevive ao expurgo (18/09).
- **Anonimização impede a reidentificação (20/09):** `_anonimizar` apaga não só
  o contato mas os reidentificadores estruturados — `cnpj`, `place_id` (na coluna
  **e** na `provenance`), lat/long, CEP e bairro. Ficam só as dimensões agregadas
  (município/UF, CNAE, porte, score). Vale para a retenção por prazo e para a
  eliminação a pedido (art. 18, IV). Ressalva de margem em aberto: se geografia
  grossa/outros metadados também deveriam sair — **[revisão jurídica]**.
- **Trilha de auditoria** encadeada por hash; `verificar_cadeia()` fecha verde
  depois de rodar pipeline + LIA + expurgo.
- **Declaração de IA** presente no corpo de toda mensagem, com resposta a humano
  e direito à explicação.
