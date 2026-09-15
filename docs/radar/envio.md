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

**Última execução:** 2026-09-13 · adicionado o tradutor de notificação SNS do SES.

---

## O que foi corrigido nesta execução

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

1. **`SendResult.detalhes["permanente"]` é calculado pelo SES e ninguém lê.**
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

2. **`MessageRejected` é sobrecarregado no SES** (endereço na lista de
   supressão da conta vs. conteúdo recusado por política). Se o caminho síncrono
   passar a consumir `permanente`, distinguir o sub-motivo importa — senão uma
   recusa por conteúdo (que atinge todos os destinatários) viraria supressão em
   massa.

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
