# Política de Privacidade — Prospector AI

*Versão 1.0 — vigente a partir da Fase 4. Escrita em português claro, como manda
o art. 6º, VI da LGPD (princípio da transparência).*

---

## Em uma frase

O Prospector AI procura **empresas** que precisam do serviço que você presta, e
inicia o contato por e-mail. Trabalhamos com dados **comerciais e públicos de
pessoa jurídica**, e qualquer empresa pode sair da nossa lista com **um clique**.

---

## 1. Quem é o controlador

Há dois papéis distintos, e isso importa juridicamente:

| Papel | Quem é | Sobre o quê |
|---|---|---|
| **Controlador** | O prestador de serviço (nosso cliente) | Os leads que ele prospecta |
| **Operador** | Prospector AI | Trata os dados por conta e ordem do controlador |
| **Controlador** | Prospector AI | Os dados de cadastro do próprio cliente |

Contato do encarregado (DPO): **privacidade@prospector.local**

## 2. Que dados tratamos

**De empresas prospectadas (leads):**

- razão social, nome fantasia, CNPJ e CNAE;
- endereço comercial;
- telefone comercial publicado;
- e-mail comercial publicado;
- site institucional;
- porte da empresa;
- avaliações públicas do estabelecimento.

**Não tratamos:** dados de sócios, CPF, dados sensíveis (art. 5º, II), dados de
crianças e adolescentes, nem dados obtidos de vazamentos ou listas compradas.

**Do nosso cliente:** nome, e-mail, empresa, CNPJ e dados de uso da plataforma.

## 3. De onde vêm os dados

| Fonte | O que traz | Natureza |
|---|---|---|
| Google Places API (New) | nome, endereço, telefone, site, avaliações | diretório comercial público, via API oficial |
| Base de CNPJ da Receita Federal | CNPJ, razão social, CNAE, porte, situação | **dado aberto**, publicado pelo governo |
| Busca web (opcional) | sinais públicos de contexto do negócio | conteúdo público indexado |

**Não fazemos scraping** de Google Maps, Google Earth ou de qualquer serviço em
violação aos seus termos. Cada lead guarda a **proveniência campo a campo**:
qual fonte trouxe qual dado e quando.

## 4. Por que podemos tratar (base legal)

**Legítimo interesse** (art. 7º, IX e art. 10 da LGPD) para a prospecção B2B.

A avaliação formal desse interesse — o LIA — é gerada pelo sistema a partir dos
dados reais de cada controlador e fica disponível em
`GET /v1/compliance/lia`. Ela documenta o teste de finalidade, o teste de
necessidade e o teste de balanceamento.

Para os dados de cadastro do nosso cliente, a base é a **execução de contrato**
(art. 7º, V).

## 5. O que fazemos com esses dados

1. Cruzamos o serviço prestado com os ramos (CNAE) que costumam consumi-lo.
2. Buscamos empresas desses ramos na região indicada.
3. Enriquecemos com a base pública de CNPJ.
4. Atribuímos um score de aderência — **explicável**, componente a componente.
5. Escrevemos uma mensagem de apresentação e a enviamos por e-mail.

**Uso de inteligência artificial:** a seleção e a redação são feitas por um
agente de IA. Toda mensagem enviada **declara isso explicitamente** e oferece
resposta a uma pessoa humana. Não há decisão automatizada que produza efeito
jurídico sobre pessoa natural (art. 20 da LGPD).

## 6. Com quem compartilhamos

Apenas com os operadores necessários para a entrega:

| Operador | Para quê |
|---|---|
| Provedor de e-mail transacional (AWS SES) | entregar a mensagem |
| Provedor de LLM (Anthropic) | redigir e classificar |
| Google (Places API) | descobrir estabelecimentos |
| Infraestrutura de nuvem | hospedar a aplicação |

Não vendemos, alugamos nem cedemos dados para terceiros. Não montamos listas
para revenda.

## 7. Por quanto tempo guardamos

| Dado | Prazo |
|---|---|
| Lead sem nenhuma interação | 180 dias, depois anonimizado |
| Conteúdo das mensagens (assunto e corpo) | 365 dias, depois expurgado |
| Metadados de envio (para auditoria) | mantidos |
| Solicitação de direitos (art. 18) | dado pessoal expurgado 365 dias após a conclusão; os metadados do atendimento (tipo, data, prazo) ficam para prestação de contas |
| Registro de descadastro | **permanente** — é ele que impede o recontato |
| Trilha de auditoria | mantida, imutável |

O expurgo roda automaticamente e cada remoção é registrada na auditoria. Ao
expurgar uma solicitação de direitos, apagamos o e-mail do titular e o conteúdo
da resposta que geramos; guardamos apenas o registro de que a solicitação
existiu e foi atendida no prazo, como a lei exige que possamos comprovar.

## 8. Seus direitos

Você pode, a qualquer momento:

- **Sair da lista** — clique no link de descadastro de qualquer mensagem. Um
  clique, efeito imediato, permanente.
- **Saber o que temos** sobre a sua empresa (art. 18, I e II) — o relatório de
  acesso inclui os leads, as mensagens trocadas e, se você estiver na lista de
  descadastro, o registro dessa supressão que mantemos.
- **Corrigir** dado incompleto ou desatualizado (art. 18, III).
- **Pedir a eliminação** dos dados (art. 18, IV).
- **Se opor** ao tratamento (art. 18, § 2º).
- **Reclamar à ANPD** (art. 18, VI).

Como exercer: use o link de descadastro, escreva para o encarregado, ou envie o
formulário em `POST /privacidade/solicitacao`.

**Prazo de resposta: 15 dias.**

Ao pedir eliminação, mantemos **apenas** o registro de que aquele contato não
deve ser abordado. Sem isso, a próxima campanha descobriria a mesma empresa de
novo — guardar esse mínimo é o que protege você.

## 9. Segurança

- Segredos apenas em variável de ambiente; nunca em código ou imagem.
- Isolamento por tenant em toda consulta.
- Trilha de auditoria imutável, encadeada por hash, com bloqueio de alteração no
  próprio banco.
- Lista de supressão consultada imediatamente antes de cada envio.
- Teto diário de envio por campanha e por cliente.

## 10. Mudanças nesta política

Alterações materiais são comunicadas aos clientes com antecedência e a versão
fica registrada. Versão atual: **1.0**.

---

*Dúvidas: privacidade@prospector.local*
