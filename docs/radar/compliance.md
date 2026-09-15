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

**Última execução:** 2026-09-15

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

6. **`_mascarar` descarta destinatário sem `@`.** No expurgo, `_mascarar`
   devolve `None` para qualquer contato sem `@` — um destinatário de **telefone**
   seria anulado, não mascarado, e a auditoria perderia o registro de que
   existiu um destinatário. Hoje o canal é e-mail-first, impacto nulo; quando o
   WhatsApp/telefone entrar (§9 do IDEIAS), vira perda silenciosa de registro.
   Pequeno e dentro do escopo — candidato a uma execução futura (precisa decidir
   o formato de máscara de telefone).

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
- **Direitos do titular:** acesso, eliminação (anonimiza + mantém supressão),
  oposição e portabilidade atendidos; correção vai para análise humana. Prazo
  gravado por pedido (ressalva: ninguém vigia o vencimento — item 4).
- **LIA** gerada dos dados reais do controlador (fontes e campos vêm do banco),
  com hash, evento de auditoria e as nove seções. Ressalva: a salvaguarda de
  retenção depende do expurgo rodar (item 7).
- **Retenção:** cobre leads sem interação, corpo **e assunto** das mensagens,
  ambos os endereços, e as solicitações de direitos concluídas; idempotente e
  auditada em cada eixo.
- **Trilha de auditoria** encadeada por hash; `verificar_cadeia()` fecha verde
  depois de rodar pipeline + LIA + expurgo.
- **Declaração de IA** presente no corpo de toda mensagem, com resposta a humano
  e direito à explicação.
