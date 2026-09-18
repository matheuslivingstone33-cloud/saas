# Declaração de uso de Inteligência Artificial — Prospector AI

<!-- REVISAR (antes de publicar): este arquivo é servido COMO TEXTO CRU pela rota
pública /legal/ia — estes comentários aparecem para o visitante. Preencher os
marcadores e apagar TODOS os comentários REVISAR antes de publicar. -->

**Versão 2.0 — rascunho para revisão jurídica**
**Última atualização: 18/09/2026**

O Prospector AI usa inteligência artificial para encontrar empresas e iniciar
conversas comerciais em nome dos nossos clientes. Esta página explica, sem
rodeios, o que a IA faz, onde há uma pessoa no controle, como falar com uma
pessoa e como sair da lista.

---

## 1. O que a IA faz

| Tarefa | O que acontece | Quem faz |
|---|---|---|
| **Entender o serviço** | lê a frase do cliente ("faço manutenção de ar-condicionado") e escolhe os ramos de empresa que costumam contratar esse serviço, procurando descartar concorrentes | comparação de textos (OpenAI) e, com a IA real ligada, o modelo da Anthropic, que pode pesquisar na web e consultar o Google Places para validar os ramos |
| **Encontrar empresas** | busca estabelecimentos desses ramos na região escolhida e completa com a base aberta de CNPJ | API oficial do Google Places e base da Receita Federal — **não é IA e não há raspagem de dados** |
| **Pontuar empresas** | dá uma nota de 0 a 100 a cada empresa, com a explicação de cada fator | uma **fórmula explicável** de seis fatores; a IA entra só na medida de semelhança entre textos, e os pesos são ajustados pelo histórico de respostas de cada cliente |
| **Pesquisar sinais públicos** | para as empresas mais bem pontuadas, procura notícias públicas recentes (expansão, obra, vaga aberta) | busca na web por meio do serviço da Anthropic |
| **Escrever a primeira mensagem e os acompanhamentos** | redige uma apresentação e até dois acompanhamentos, cada um com um ângulo diferente | modelo de linguagem da Anthropic (Claude) |
| **Classificar as respostas** | identifica se a resposta é interesse, dúvida, objeção, recusa, pedido para sair, pedido para falar com uma pessoa ou ausência | **primeiro regras fixas de palavras**; a IA só é consultada quando o texto é ambíguo |
| **Responder** | redige uma resposta quando a pessoa demonstra interesse, tem dúvida ou faz uma objeção. É instruída a nunca inventar preço | modelo de linguagem da Anthropic |

## 2. O que a IA **não** faz

- Não responde a quem pediu para sair, recusou, pediu para falar com uma pessoa
  ou mandou resposta automática de ausência. Nesses casos ela **para**.
- Não decide sobre descadastro: "me tire da lista" é reconhecido por regras
  fixas, sem depender de interpretação do modelo. Na dúvida entre sair e
  continuar, vale o pedido de saída.
- Não fecha negócio, não negocia preço, não assina, não cobra e não agenda
  reuniões.
- Não prospecta pessoa física como consumidora e não envia prospecção por
  WhatsApp.
- Não toma decisão que produza efeito jurídico sobre uma pessoa, nem define
  perfil pessoal, de consumo ou de crédito.

## 3. Onde há uma pessoa no controle

| Momento | Controle humano |
|---|---|
| Antes de buscar | o cliente vê os ramos que a IA escolheu e pode corrigir |
| Antes de abordar | o cliente vê a pontuação de cada empresa e o porquê de cada fator |
| Antes de enviar | no **modo assistido** — o modo inicial de toda conta — cada mensagem e cada resposta da IA só sai depois que uma pessoa do cliente aprova. A pessoa pode aprovar ou rejeitar |
| Durante a conversa | o cliente pode **assumir a conversa** a qualquer momento. A partir daí a IA não envia mais acompanhamentos nem respostas àquele contato, até o cliente devolver a conversa |
| Modo automático | o cliente pode escolher que as mensagens saiam sem aprovação individual, dentro de limites diários, com a lista de bloqueio e a trilha de auditoria. A troca de modo é registrada |

<!-- REVISAR: (1) a tela de revisão tem botão "editar", mas o texto editado não
é salvo — ao aprovar, sai o original. Por isso a tabela diz "aprovar ou
rejeitar". (2) Os acompanhamentos (2º e 3º contato) só saem se a tarefa diária
estiver agendada; hoje nada a dispara sozinha. -->

## 4. O que vai em cada mensagem

Toda mensagem escrita pela IA traz, **no próprio texto** (não escondida em
rodapé técnico), a frase:

> *"Esta mensagem foi redigida por um agente de inteligência artificial a
> serviço de [empresa do cliente]. Responda a este e-mail para falar com uma
> pessoa."*

A primeira mensagem e os acompanhamentos trazem também, logo abaixo, o **link
de descadastro**:

> *"Para não receber mais estas mensagens, descadastre-se: [link]"*

Quando uma pessoa do cliente escreve a mensagem ela mesma, a frase de IA **não**
é incluída — dizer que foi a IA seria falso —, mas as regras de descadastro
continuam valendo.

<!-- REVISAR — PENDÊNCIAS TÉCNICAS (corrigir antes do e-mail real):
(1) A RESPOSTA ESCRITA PELA IA a um lead (services/conversa.py, _responder) sai
com a declaração de IA, mas SEM o link de descadastro no texto, e com um link no
cabeçalho que não funciona (endereço fixo app.prospector.local e token sem
assinatura). Viola o guardrail "toda mensagem leva link de descadastro".
(2) A mensagem escrita à mão leva o link só no cabeçalho, não no texto.
(3) Se o cliente não preencheu o nome da empresa, a frase sai "a serviço de
nossa equipe" — não identifica quem oferta. Exigir o nome antes de enviar.
(4) A frase original da mensagem é sem acentos no código ("redigida por um
agente de inteligencia artificial"); a citação acima está acentuada. Alinhar. -->

## 5. Como falar com uma pessoa

- **Responda à mensagem** dizendo que quer falar com uma pessoa (por exemplo,
  "quero falar com uma pessoa" ou "isso é um robô?"). A IA deixa de responder e a
  conversa passa para atendimento humano do cliente que enviou a mensagem.
- Ou escreva para **[E-MAIL DO ENCARREGADO]**.

<!-- REVISAR: hoje não existe a peça que traz as respostas do e-mail para dentro
da plataforma. As respostas caem na caixa do remetente, que é do Prospector AI
(contato@<seu-dominio>), e não chegam ao cliente nem à classificação
automática. Até isso existir, quem "fala como pessoa" é quem lê essa caixa.
Definir o encaminhamento antes do lançamento. -->

## 6. Como sair da lista

- **Clique no link de descadastro** da mensagem: um clique, sem login e sem
  confirmação. Vale na hora, é permanente e bloqueia novas mensagens do cliente
  que enviou.
- Ou **responda** pedindo para sair ("me tire da lista", "não quero receber").
- Para bloquear mensagens de **todos** os clientes do Prospector AI, peça
  oposição a **[E-MAIL DO ENCARREGADO]**.

Detalhes na [Política de Privacidade](POLITICA-DE-PRIVACIDADE.md), seções 3.6 e
3.7.

## 7. Direito à explicação e à revisão

Toda decisão da IA fica registrada e pode ser explicada:

- **por que um ramo foi escolhido:** os ramos, os pesos e a justificativa ficam
  visíveis para o cliente;
- **por que uma empresa foi priorizada:** cada empresa guarda a pontuação de cada
  fator e quanto ele contribuiu;
- **de onde veio cada dado:** cada empresa guarda a origem de cada campo e a data
  da coleta;
- **o que a IA fez e quando:** a trilha de auditoria registra as decisões da IA
  em sequência encadeada e imutável.

Se você foi contatado e quer entender ou contestar uma decisão — por exemplo,
acha que sua resposta foi mal interpretada —, escreva para
**[E-MAIL DO ENCARREGADO]**. Uma pessoa revisa o caso (LGPD, art. 20).

## 8. Limites que assumimos

- A IA pode errar ao escolher um ramo, ao escrever ou ao classificar uma
  resposta. Por isso a pontuação é explicável, o modo assistido é o padrão e
  pedidos de saída não dependem da IA.
- O texto gerado é uma apresentação comercial, não uma promessa contratual.
- Sinais encontrados na web são indícios públicos, não fatos confirmados.

## 9. Fornecedores de IA

| Fornecedor | Uso |
|---|---|
| Anthropic (modelo Claude) | redação, classificação de respostas ambíguas, planejamento de busca e pesquisa na web |
| OpenAI | comparação de semelhança entre textos |

Os dois tratam dados nos Estados Unidos. Ver a Política de Privacidade, seções 4
e 6.

<!-- REVISAR: (1) hoje o sistema roda em modo de teste, sem IA real ligada;
esta tabela vale a partir da Fase 7. (2) Referência legal: além da LGPD
(art. 20), o projeto de lei de IA (PL 2338/2023) exigia transparência sobre
interação com IA — verificar se já virou lei e se pede algo a mais. -->

## 10. Contato

Dúvidas sobre o uso de inteligência artificial: **[E-MAIL DO ENCARREGADO]**.
