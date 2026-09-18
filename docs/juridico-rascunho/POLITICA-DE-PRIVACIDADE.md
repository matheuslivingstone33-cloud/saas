# Política de Privacidade — Prospector AI

<!-- REVISAR (antes de publicar): este arquivo é servido COMO TEXTO CRU pela rota
pública /legal/privacidade. Estes comentários NÃO ficam escondidos: aparecem para
o visitante. Antes de publicar: (1) preencher todos os marcadores entre colchetes;
(2) apagar TODOS os comentários REVISAR; (3) conferir a lista de pendências em
docs/REVISAO-JURIDICA.md, porque alguns trechos só serão verdade depois de
ajustes no sistema. -->

**Versão 2.0 — rascunho para revisão jurídica**
**Última atualização: 18/09/2026**

Esta política explica, em linguagem direta, que dados pessoais o Prospector AI
trata, por quê, com quem compartilha, por quanto tempo guarda e como você exerce
seus direitos. Ela segue a Lei Geral de Proteção de Dados (Lei nº 13.709/2018,
"LGPD") e o Marco Civil da Internet (Lei nº 12.965/2014).

---

## Resumo

- O Prospector AI é uma plataforma que ajuda **prestadores de serviço** (nossos
  clientes) a encontrar **empresas** que costumam precisar daquele serviço e a
  iniciar uma conversa comercial por **e-mail**, com ajuda de inteligência
  artificial.
- Esta política fala com **dois públicos**:
  - **Parte A — clientes:** quem cria uma conta e usa o Prospector AI.
  - **Parte B — pessoas ligadas a empresas prospectadas:** quem trabalha numa
    empresa encontrada pela plataforma, ou quem responde pelo e-mail ou telefone
    comercial dela.
- **Não vendemos dados.** Não compramos listas. Não prospectamos pessoas como
  consumidoras (pessoa física): a prospecção é só entre empresas.
- Toda mensagem de prospecção diz que foi escrita por inteligência artificial e
  traz um link para parar de receber.
- Para sair da lista ou exercer um direito: use o link no e-mail, responda
  pedindo, ou escreva para **[E-MAIL DO ENCARREGADO]**.

---

## 1. Quem somos e quem decide sobre cada dado

O Prospector AI é operado por **[RAZÃO SOCIAL]**, CNPJ **[CNPJ]**, com endereço
em **[ENDEREÇO]**.

A LGPD separa quem **decide** sobre um dado (o **controlador**) de quem apenas
**trata o dado em nome de outro** (o **operador**). No Prospector AI esses papéis
mudam conforme a situação:

| Situação | Quem é o controlador | Papel do Prospector AI |
|---|---|---|
| Dados da conta do cliente (cadastro, uso, pagamentos) | Prospector AI | controlador |
| Dados de empresas e contatos prospectados numa campanha | o **cliente** que criou a campanha | **operador** (trata por conta e ordem do cliente) |
| Lista global de bloqueio e pedidos de titulares recebidos pelos nossos canais | Prospector AI | controlador |
| Registros de segurança e trilha de auditoria | Prospector AI | controlador |

**Por que o cliente é o controlador das campanhas.** É o cliente quem decide
prospectar, qual serviço oferecer, em que região buscar, se as mensagens saem só
com a aprovação dele (modo assistido) ou automaticamente (modo automático), e
quem assina a oferta. A avaliação de legítimo interesse (seção 3.4) é gerada em
nome de cada cliente, com os dados das campanhas dele. O Prospector AI executa
essas escolhas seguindo o contrato com o cliente e o Acordo de Tratamento de
Dados (anexo dos Termos de Uso).

**Por que a lista global é nossa.** Quando uma pessoa nos pede diretamente para
não ser mais contatada, ou para apagar seus dados, aplicamos esse pedido **a
todos os clientes** da plataforma. Essa decisão é do Prospector AI, para proteger
quem pediu — por isso, nesse ponto, somos controladores.

**Na prática, para você:** qualquer que seja a campanha, você pode falar
diretamente conosco. Nós atendemos o pedido e o registro fica disponível para o
cliente responsável pela campanha.

<!-- REVISAR: modelo de papéis. Há três fatos que puxam o Prospector AI para o
papel de controlador (ou controlador conjunto) também nas campanhas:
(1) é o sistema que escolhe as fontes (Google Places, base da Receita, busca na
web), os campos coletados e os prazos de guarda;
(2) a descoberta das empresas e a escolha dos ramos-alvo são feitas pelo próprio
sistema (o "Cérebro"), a partir de uma frase do cliente;
(3) hoje TODAS as mensagens saem de um único endereço do domínio do Prospector AI
(SES_FROM_EMAIL, ex.: contato@<seu-dominio>), e as respostas chegam a essa caixa.
Quem recebe o e-mail enxerga o Prospector AI como remetente.
A escolha adotada aqui (cliente = controlador; Prospector AI = operador das
campanhas e controlador da lista global) é a que o código já reflete (a LIA sai
em nome do cliente). Pedir ao advogado para confirmar se ela se sustenta ou se é
melhor assumir controladoria conjunta, com divisão de responsabilidades por
escrito. Isso muda a exposição do Prospector AI a responder junto com o cliente
(LGPD art. 42). -->

**Encarregado pelo tratamento de dados (DPO):** [NOME DO ENCARREGADO] —
**[E-MAIL DO ENCARREGADO]**.

---

## 2. Parte A — Clientes que usam o Prospector AI

### 2.1 Que dados tratamos

| Tipo | Exemplos |
|---|---|
| Cadastro | nome, e-mail, nome da empresa, CNPJ (opcional) |
| Senha | guardada **apenas como resumo criptográfico** (bcrypt); ninguém da equipe vê a senha |
| Configuração do negócio | descrição do serviço que você presta, regiões de busca, filtros das campanhas |
| Assinatura e créditos | plano, situação da assinatura, modo de autonomia (assistido/automático), saldo e extrato de créditos |
| Uso da plataforma | campanhas criadas, mensagens aprovadas ou rejeitadas, mensagens que você mesmo escreve, histórico de ações registrado na trilha de auditoria |
| Custos por operação | registro interno do custo de cada chamada a fornecedores (usado para cobrança e controle de margem) |
| Pagamento | processado pelo Stripe. **Não recebemos nem guardamos o número do seu cartão** |
| Navegação | a sessão de acesso fica guardada no armazenamento local do seu navegador. **Não usamos cookies de rastreamento, nem ferramentas de análise ou de publicidade.** As fontes de texto do site são carregadas do Google Fonts, o que envia ao Google o endereço IP de quem abre o site |
| Registros técnicos | data e hora, página ou rota acessada, resultado e tempo de resposta de cada requisição |
| Registros de acesso | data, hora e endereço IP de cada entrada na conta, de cada tentativa de entrada e de cada cadastro |

<!-- REVISAR: desde 18/09 o sistema grava data, hora e IP de cada login (certo
ou errado) e de cada cadastro, e apaga depois de 6 meses. Confirmar com o
advogado se isso cumpre o art. 15 do Marco Civil ou se a renovação automática
da sessão (a cada 30 minutos) também precisa ser registrada. -->

### 2.2 De onde vêm

De você (cadastro, configuração, mensagens que escreve), do próprio uso da
plataforma e do Stripe (confirmação de pagamento).

### 2.3 Para que usamos e com que base legal

| Finalidade | Base legal (LGPD) |
|---|---|
| Criar e manter sua conta, prestar o serviço contratado, cobrar | execução de contrato (art. 7º, V) |
| Enviar avisos sobre o serviço (mudanças, cobrança, segurança) | execução de contrato (art. 7º, V) |
| Segurança da conta, prevenção de fraude e de uso abusivo, trilha de auditoria | legítimo interesse (art. 7º, IX) |
| Guardar registros de acesso à aplicação (Marco Civil, art. 15) | obrigação legal (art. 7º, II) |
| Guardar registros fiscais e financeiros | obrigação legal (art. 7º, II) |
| Defender direitos em processos | exercício regular de direitos (art. 7º, VI) |

Não usamos seus dados para publicidade de terceiros. Hoje o aprendizado da
plataforma (os pesos que ajustam a pontuação das empresas) é feito **por conta**
e não é compartilhado entre clientes.

### 2.4 Por quanto tempo guardamos

| Dado | Prazo |
|---|---|
| Dados da conta | enquanto a conta estiver ativa |
| Após o encerramento da conta | [PRAZO] |
| Registros financeiros e fiscais | pelo prazo exigido pela legislação fiscal |
| Registros de acesso (Marco Civil) | 6 meses |
| Trilha de auditoria | permanente (é imutável, ver seção 5) |

<!-- REVISAR: (1) prazo após o encerramento da conta é decisão do dono (sugestão:
6 meses para dados da conta, mantendo só o necessário para obrigação legal e
defesa); (2) confirmar com o contador o prazo fiscal (em geral 5 anos);
(3) PENDÊNCIA TÉCNICA: não existe hoje fluxo de encerramento nem de exclusão de
conta — o pedido tem de ser feito por e-mail e executado à mão. O Marco Civil
(art. 7º, X) dá ao usuário o direito de pedir a exclusão definitiva ao fim da
relação. -->

Para encerrar a conta ou pedir a exclusão dos seus dados, escreva para
**[E-MAIL DE CONTATO]**.

---

## 3. Parte B — Pessoas ligadas a empresas prospectadas

### 3.1 Que dados tratamos

O Prospector AI trabalha com **dados comerciais de empresas**. Mesmo assim,
tratamos esses dados **como dados pessoais**, porque um e-mail ou telefone
comercial pode identificar uma pessoa (por exemplo, `joao@empresa.com.br`, ou o
telefone de um microempreendedor individual).

| Tipo | Exemplos |
|---|---|
| Identificação da empresa | razão social, nome fantasia, CNPJ, ramo de atividade (CNAE), porte |
| Localização comercial | endereço, bairro, cidade, UF, CEP, coordenadas do estabelecimento |
| Contato comercial | telefone comercial, e-mail do cadastro de CNPJ, site |
| Informações públicas do Google | categorias do estabelecimento, nota média e número de avaliações. **Não guardamos o texto das avaliações** |
| Informações calculadas | pontuação de aderência com a explicação de cada fator, representação numérica usada para comparar semelhança de textos, situação na campanha (encontrada, abordada, respondeu etc.) |
| Sinais públicos (opcional) | títulos de resultados de busca na web sobre a empresa (ex.: expansão, obra, vaga aberta) — só para as empresas mais bem pontuadas |
| Comunicação | mensagens enviadas, respostas recebidas (texto e endereço de quem respondeu) e a classificação da intenção de cada resposta |
| Controle | registros de descadastro (endereço, origem, data) e pedidos de direitos |

**O que não tratamos:** dados sensíveis (saúde, religião, biometria etc.), dados
de crianças e adolescentes, dados de sócios, nem dados obtidos de vazamentos ou
de listas compradas.

<!-- REVISAR: (1) microempreendedor individual (MEI) e empresário individual: o
nome empresarial costuma ser o nome da própria pessoa, e na base aberta da
Receita o nome de MEI pode vir com o CPF embutido. Confirmar no arquivo real da
Receita; se vier, o sistema precisa remover o CPF antes de gravar, senão a frase
"não tratamos CPF" fica falsa (por isso ela foi retirada desta versão).
(2) O e-mail que usamos vem do cadastro de CNPJ da Receita; muitas vezes é o
e-mail do contador ou um e-mail pessoal do dono. Ver risco 1 em
REVISAO-JURIDICA.md. -->

### 3.2 De onde vêm

| Fonte | O que traz | Natureza |
|---|---|---|
| Google Places API (New) | nome, endereço, telefone, site, categorias, nota e número de avaliações | serviço oficial do Google, acessado por API contratada |
| Base de CNPJ da Receita Federal | CNPJ, razão social, CNAE, porte, situação, endereço, telefone e e-mail cadastrais | **dados abertos** publicados pelo governo |
| Busca na web (opcional) | sinais públicos recentes sobre a empresa | conteúdo público indexado, pesquisado por meio do serviço de IA |
| Você mesmo | a resposta que você envia a uma mensagem | comunicação direta |

**Não fazemos raspagem de dados** ("scraping") do Google Maps, do Google Earth ou
de qualquer site em violação aos seus termos. Cada empresa registrada guarda a
**origem de cada dado**: qual fonte trouxe qual campo, com qual termo de busca e
em que data.

### 3.3 Para que usamos

1. Identificar empresas cujo ramo costuma contratar o serviço do nosso cliente,
   na região que ele escolheu. O sistema procura excluir empresas que prestam o
   mesmo serviço (concorrentes do cliente).
2. Pontuar cada empresa por aderência, com explicação fator a fator.
3. Escrever e enviar por **e-mail** uma mensagem de apresentação e, se não houver
   resposta, **até dois acompanhamentos** (em regra 3 e 7 dias depois da
   primeira). O sistema evita registrar a mesma empresa duas vezes para o mesmo
   cliente.
4. Ler e classificar as respostas para decidir o próximo passo — inclusive
   **parar** de escrever quando a pessoa recusa, pede para sair, pede para falar
   com uma pessoa ou está ausente.
5. Registrar descadastros e pedidos de direitos, e cumprir esses pedidos.

A sequência de mensagens para quando a empresa responde, pede para sair, recusa,
quando uma pessoa do cliente assume a conversa, ou quando o endereço de e-mail
não existe.

**Canal:** a prospecção é feita **só por e-mail**. O WhatsApp não é usado para
prospectar: o envio por esse canal fica bloqueado no sistema, e mensagens a
pessoa física desconhecida são proibidas.

**Remetente:** as mensagens saem de um endereço do Prospector AI e dizem em nome
de qual empresa (nosso cliente) estão sendo enviadas.

**Mais de um cliente:** cada cliente faz as próprias campanhas, e os dados de uma
campanha não são repassados a outros clientes. Por isso, a mesma empresa pode
receber mensagens de mais de um cliente do Prospector AI. Para bloquear o
contato de **todos** os clientes de uma vez, use o pedido de oposição (seção
3.7).

### 3.4 Base legal

**Legítimo interesse** do cliente que faz a prospecção (LGPD, art. 7º, IX, e
art. 10): oferecer seu serviço a empresas que costumam precisar dele, usando
canais comerciais que essas empresas tornaram públicos.

Como os dados vêm de fontes públicas, o tratamento também observa o art. 7º,
§§ 3º, 4º e 7º da LGPD: a finalidade (contato comercial entre empresas) é
compatível com o motivo pelo qual esses dados foram publicados, e os direitos do
titular continuam valendo.

Para cada cliente, o sistema gera uma **Avaliação de Legítimo Interesse (LIA)** a
partir dos dados reais das campanhas dele: finalidade, necessidade,
balanceamento, salvaguardas e direitos. Você pode pedir informações sobre essa
avaliação ao encarregado.

Os registros de descadastro e de pedidos de direitos são mantidos para cumprir a
própria LGPD e para comprovar que cumprimos (art. 7º, II e VI).

<!-- REVISAR: (1) a LIA gerada pelo sistema (services/compliance.py) afirma que
"o primeiro contato já informa a origem do dado". HOJE A MENSAGEM NÃO INFORMA A
ORIGEM: ela traz o texto da IA, a declaração de IA e o link de descadastro.
Ou se acrescenta uma linha na mensagem ("Encontramos sua empresa em dados
públicos do Google e da Receita Federal"), ou se corrige a LIA. A transparência
é exigida para o legítimo interesse (art. 10, § 2º).
(2) Validar com o advogado se o legítimo interesse sustenta o envio quando o
e-mail do cadastro de CNPJ é, na prática, de uma pessoa física (MEI, e-mail
pessoal do dono ou do contador). -->

### 3.5 Por quanto tempo guardamos

| Dado | Prazo |
|---|---|
| Empresa que não chegou a ser abordada, ou que foi descartada (recusou, e-mail inexistente etc.) | **180 dias** após a coleta; depois o nome e os contatos são apagados e fica só o registro estatístico (ramo, cidade, porte, pontuação) |
| Empresa abordada (com ou sem resposta), que virou negócio ou que se descadastrou | enquanto a conta do cliente estiver ativa |
| Conteúdo das mensagens enviadas e recebidas (assunto e texto) | **365 dias**; depois o texto é apagado e os endereços ficam mascarados (ex.: `jo***@empresa.com.br`). Ficam data, canal e situação da mensagem |
| Pedidos de direitos (seção 3.7) | o dado pessoal é apagado **365 dias** após a conclusão; fica o registro de que o pedido existiu, o tipo, o prazo e quando foi atendido |
| Registro de descadastro e de bloqueio | **permanente** — é ele que impede um novo contato |
| Trilha de auditoria | permanente (ver seção 5) |

Uma rotina de expurgo aplica esses prazos e registra cada remoção na trilha de
auditoria.

<!-- REVISAR — pendências que tornam esta tabela parcialmente verdadeira hoje:
(1) A rotina de expurgo EXISTE, mas NADA a dispara sozinha (HANDOFF §0.1 item
5). Num servidor próprio ela é agendada à mão (COLOCAR-NO-AR 7.4); na Vercel não
há agendamento. Não publicar esta tabela antes de a rotina rodar sozinha.
(2) Empresa abordada que nunca respondeu e empresa que se descadastrou ficam com
todos os dados "para sempre" hoje. Prazo por situação é decisão do dono + revisão
jurídica (HANDOFF §0.2). Sugestão: 12 meses após o último contato para abordada
sem resposta; para descadastro, guardar só o endereço na lista de bloqueio e
apagar o resto.
(3) A lista de bloqueio guarda o endereço de e-mail em texto, não em forma
cifrada (hash). Minimizar exige mudança técnica (HANDOFF §0.3 item 3).
(4) Registros técnicos (logs) do provedor de hospedagem seguem o prazo do
provedor — a confirmar quando a hospedagem for definida. -->

### 3.6 Como parar de receber mensagens

| Como | O que acontece |
|---|---|
| **Clicar no link de descadastro** que vai no texto de cada mensagem de prospecção | Um clique, sem login e sem confirmação. O bloqueio vale na hora e é permanente para o **cliente que enviou** a mensagem |
| **Responder** pedindo para sair ("me tire da lista", "não quero receber" etc.) | O pedido é reconhecido por regras fixas de palavras, **sem depender da IA**. Nenhuma resposta é enviada e o contato é bloqueado para aquele cliente |
| **Marcar a mensagem como spam** | O aviso do provedor de e-mail também bloqueia o contato |
| **Pedir oposição ao encarregado** ([E-MAIL DO ENCARREGADO]) | O endereço é bloqueado para **todos os clientes** do Prospector AI |

Nenhum cliente consegue desfazer um descadastro pela plataforma. A lista de
bloqueio é consultada imediatamente antes de cada envio, inclusive das mensagens
escritas à mão por uma pessoa do cliente.

<!-- REVISAR — pontos de verdade técnica:
(1) ESCOPO: o link e a resposta "me tire da lista" bloqueiam o contato SÓ para o
cliente que enviou (opt_outs com user_id do cliente). Só o pedido de
oposição/eliminação feito ao Prospector AI é global. A página que aparece depois
do clique diz "não receberá mais mensagens nossas", o que pode ser lido como
"de ninguém". Decisão do dono: manter por cliente (padrão de mercado, mais
preciso) ou tornar o link global (mais protetor, menos reclamação). Sugestão:
global — "evitar processos" pesa mais que perder um lead para outros clientes.
Se mudar, ajustar esta tabela.
(2) Desde 18/09 a resposta que a IA escreve a um lead também leva o link no
texto e no cabeçalho. Falta a mensagem escrita à mão por uma pessoa do cliente,
que leva o link só no cabeçalho. Quando ela ganhar a linha no texto, a tabela
pode dizer "toda mensagem".
(3) Responder pedindo para sair só funciona quando as respostas chegarem ao
sistema — hoje não existe a peça que traz o e-mail de resposta para dentro da
plataforma (COLOCAR-NO-AR, tabela do topo). Até lá, quem lê a caixa do remetente
precisa registrar o pedido à mão.
(4) Aviso de spam: depende da rota de retorno do provedor (HANDOFF §0.1 item 8),
ainda não ligada. -->

### 3.7 Seus direitos e como exercê-los

Você pode, a qualquer momento:

| Direito (LGPD) | Como atendemos |
|---|---|
| Confirmar se tratamos seus dados e **acessá-los** (art. 18, I e II) | enviamos um relatório com os registros da empresa ligados ao contato informado, a origem de cada dado e a lista das mensagens (data, canal, direção e situação) |
| **Corrigir** dados incompletos ou desatualizados (art. 18, III) | uma pessoa analisa o pedido |
| **Eliminar** dados, ou pedir anonimização ou bloqueio (art. 18, IV e VI) | apagamos nome e contatos da empresa ligados àquele endereço **em todas as contas de clientes** e bloqueamos o endereço para todos os clientes |
| **Portabilidade** (art. 18, V) | o mesmo relatório do acesso, em formato estruturado |
| Saber com quem **compartilhamos** (art. 18, VII) | ver seção 4 |
| **Opor-se** ao tratamento (art. 18, § 2º) | bloqueio imediato do endereço para todos os clientes |
| Pedir **revisão** de decisão automatizada (art. 20) | ver seção 3.8 |
| **Reclamar à ANPD** (art. 18, § 1º) | pelo site da Autoridade Nacional de Proteção de Dados |

**Como pedir:**

- escreva para **[E-MAIL DO ENCARREGADO]**; ou
- use o formulário de privacidade em `https://app.<seu-dominio>/privacidade`
  (aceita pedidos feitos a partir de um endereço de e-mail; para telefone,
  escreva ao encarregado).

**O que fica guardado mesmo depois da eliminação:** apenas o endereço na lista
de bloqueio — sem ele, uma próxima busca encontraria sua empresa de novo e o
contato recomeçaria — e os registros da trilha de auditoria (seção 5).

**Confirmação de identidade:** para proteger você, podemos pedir que confirme que
controla o endereço informado antes de entregar dados ou apagá-los. Assim ninguém
consegue ver ou apagar os dados de outra pessoa se passando por ela.

**Prazo:** respondemos em até **15 dias**.

<!-- REVISAR — pendências e decisões:
(1) VERIFICAÇÃO DE IDENTIDADE: hoje o formulário público atende NA HORA, sem
confirmar nada. Um impostor recebe o relatório de outra pessoa (acesso) ou
apaga/bloqueia o contato de qualquer empresa em todas as contas (eliminação e
oposição). É o 🔴 aberto do radar de Compliance. O parágrafo acima reserva o
direito de verificar; o fluxo (ex.: link de confirmação enviado ao próprio
endereço) precisa existir antes do lançamento. Decisão de produto + revisão
jurídica do nível de verificação por tipo de pedido.
(2) FORMULÁRIO: só existe a rota da API (POST /privacidade/solicitacao). Não há
página com formulário no site. Até existir, o único canal real é o e-mail do
encarregado. Ajustar o endereço acima quando a página for criada.
(3) ELIMINAÇÃO: hoje apaga os dados da EMPRESA (lead), mas NÃO apaga o texto das
mensagens já trocadas nem o endereço gravado nelas — eles só somem no expurgo de
365 dias. Ou o sistema passa a apagar também as mensagens, ou o texto precisa
dizer isso. Pendência técnica.
(4) ACESSO: o relatório traz registros e origem, mas não o texto das mensagens,
nem os critérios da pontuação. Avaliar com o advogado se atende à "declaração
clara e completa" do art. 19, II.
(5) PRAZO: 15 dias é o prazo legal do acesso completo (art. 19, II). Para os
demais direitos a lei remete a regulamento da ANPD; confirmar. Hoje nenhum
código vigia prazo vencido (pedido de correção fica parado sem alerta).
(6) Um pedido público de eliminação afeta dados de TODOS os clientes que
prospectaram aquele contato. Confirmar que isso é aceitável contratualmente
(está previsto no Acordo de Tratamento de Dados). -->

### 3.8 Decisões automatizadas (LGPD, art. 20)

A inteligência artificial e regras automáticas participam de quatro decisões:

| Decisão | Como funciona | Onde há uma pessoa |
|---|---|---|
| **Quais ramos procurar** | a partir da frase do cliente sobre o serviço dele, o sistema escolhe os ramos de atividade que costumam contratá-lo e descarta concorrentes | o cliente vê os ramos escolhidos e pode corrigir antes de buscar |
| **Pontuar as empresas** | uma fórmula de 0 a 100 com seis fatores: ramo compatível (35%), semelhança entre a atividade da empresa e o serviço (20%), existência de canal comercial (20%), porte (10%), sinais públicos recentes (10%) e reputação pública (5%). Os pesos são ajustados pelo histórico de respostas **de cada cliente** | o cliente vê a explicação de cada fator e decide quem abordar |
| **Classificar respostas** | regras fixas de palavras reconhecem primeiro os pedidos de saída, de falar com uma pessoa, as recusas e as ausências; a IA só é usada quando o texto é ambíguo | em caso de dúvida entre sair e continuar, o sistema considera pedido de saída |
| **Escrever e responder** | a IA redige a primeira mensagem, os acompanhamentos e respostas a interesse, dúvida ou objeção | no **modo assistido** (o padrão) uma pessoa aprova cada mensagem antes do envio |

Essas decisões dizem respeito a **empresas** e a oportunidades comerciais. Nenhuma
delas produz efeito jurídico sobre uma pessoa, define perfil pessoal, de consumo
ou de crédito. Mesmo assim, você pode pedir que **uma pessoa revise** qualquer
uma delas — por exemplo, se acha que sua resposta foi mal interpretada:

- responda à mensagem dizendo que quer falar com uma pessoa — a IA deixa de
  responder e a conversa passa para atendimento humano; ou
- escreva para **[E-MAIL DO ENCARREGADO]** explicando o que quer revisar.

Mais detalhes na [Declaração de uso de Inteligência Artificial](DECLARACAO-DE-IA.md).

<!-- REVISAR: no modo AUTOMÁTICO a mensagem e as respostas da IA saem sem
aprovação individual. O cliente escolhe o modo; a troca é registrada na trilha.
Confirmar com o advogado se "revisão por pessoa mediante pedido" é suficiente
para o art. 20. Lembrete: "responder pedindo uma pessoa" depende de as respostas
chegarem ao sistema (pendência do item 3.6). -->

---

## 4. Com quem compartilhamos

Compartilhamos dados **apenas** com os fornecedores necessários para o serviço
funcionar, que agem como operadores (ou suboperadores) e só podem usar os dados
para nos atender:

| Fornecedor | Para quê | Que dados recebe | Onde trata |
|---|---|---|---|
| Vercel | hospedagem da aplicação | todos os dados em trânsito e registros técnicos | servidores em São Paulo (Brasil); empresa sediada nos EUA |
| Neon | banco de dados (PostgreSQL gerenciado) | todos os dados armazenados | servidores em São Paulo (Brasil); empresa sediada nos EUA |
| Anthropic | IA que redige, classifica respostas, planeja a busca e pesquisa sinais públicos na web | dados da empresa prospectada, descrição do serviço do cliente, texto das mensagens e respostas | EUA |
| OpenAI | comparação de semelhança entre textos | nome, categorias, ramo e cidade da empresa; descrição do serviço do cliente | EUA |
| Google (Places API) | encontrar estabelecimentos | termo de busca e região | EUA |
| Google (Fonts) | fontes do site | endereço IP de quem abre o site | EUA |
| Amazon Web Services (SES) | enviar os e-mails | endereço do destinatário, assunto e texto da mensagem | região a definir |
| Provedor da caixa de e-mail do domínio | receber respostas e mensagens ao encarregado | respostas e pedidos recebidos por e-mail | a definir |
| Stripe | pagamentos dos clientes | dados de pagamento do cliente (o cartão vai direto ao Stripe) | a confirmar |

Também podem ter acesso aos dados:

- **o cliente responsável pela campanha**, quanto às empresas encontradas e às
  mensagens trocadas nas campanhas dele;
- **autoridades**, quando houver obrigação legal ou ordem judicial.

**Não vendemos, não alugamos e não cedemos dados.** Não montamos listas para
revenda. Os dados de uma campanha não são repassados a outros clientes.

<!-- REVISAR: (1) nenhum destes fornecedores está contratado ainda (o sistema
roda em modo de teste). A lista precisa bater com os contratos reais no dia em
que cada um for ligado. (2) Conferir em cada contrato se o fornecedor usa os
dados para treinar modelos ou para fins próprios (em regra as APIs pagas de IA
não usam, mas confirmar por escrito) e por quanto tempo guarda. (3) O WhatsApp
(Meta) tem integração pronta mas desligada; se for ligado, entra nesta tabela.
(4) Se houver fila/cache (Redis ou similar) na hospedagem nova, entra aqui. -->

---

## 5. Trilha de auditoria

O Prospector AI mantém uma trilha de auditoria **imutável**: cada evento
relevante (coleta de dado, envio, descadastro, decisão da IA, pedido de
direitos, movimentação de créditos) é registrado em sequência, e cada registro é
encadeado ao anterior por um resumo criptográfico, de modo que qualquer alteração
é detectável. No banco de dados de produção, alterar ou apagar esses registros é
bloqueado.

A trilha serve para provar que as regras foram cumpridas. Alguns registros
contêm o endereço de contato envolvido (por exemplo, no evento de descadastro).
Por isso ela **não é apagada** quando alguém pede eliminação.

<!-- REVISAR: base legal para manter endereço de contato na trilha para sempre
(prestação de contas — art. 6º, X e art. 37; exercício regular de direitos —
art. 7º, VI; ou art. 16, I). Avaliar se basta guardar o endereço mascarado ou
cifrado nesses eventos. -->

---

## 6. Transferência internacional de dados

Vários fornecedores da seção 4 tratam dados **fora do Brasil**, principalmente
nos Estados Unidos. A LGPD só permite isso em hipóteses específicas (art. 33).
Usamos:

- para dados da conta do cliente: a transferência necessária para executar o
  contrato (art. 33, IX, combinado com o art. 7º, V);
- para os dados das empresas prospectadas: contratos com os fornecedores que
  contenham as **cláusulas-padrão contratuais aprovadas pela ANPD** ou outra
  garantia prevista no art. 33, II.

<!-- REVISAR: (1) Hoje NENHUM destes contratos existe. Para cada fornecedor,
confirmar se o contrato de tratamento de dados dele já traz as cláusulas-padrão
da ANPD (Resolução CD/ANPD nº 19/2024 — confirmar número e prazos) ou se é
preciso firmar um aditivo. Legítimo interesse NÃO é hipótese de transferência
internacional: para os dados prospectados a garantia do art. 33, II é
necessária.
(2) Hospedagem: desde 18/09 o servidor (Vercel, região gru1) e o banco (Neon,
aws-sa-east-1) ficam em São Paulo. Os dados guardados ficam no Brasil, mas as
duas empresas são americanas, e Anthropic e OpenAI tratam nos EUA: a
transferência continua existindo para o que vai à IA. -->

---

## 7. Segurança

Adotamos medidas técnicas e administrativas para proteger os dados, entre elas:

- conexão cifrada (HTTPS) entre o navegador e a plataforma;
- senhas guardadas só como resumo criptográfico (bcrypt);
- sessões com prazo curto (30 minutos, renovadas automaticamente por até 14
  dias);
- limite de tentativas de senha e de cadastros a partir do mesmo endereço;
- separação entre contas de clientes em todas as consultas, verificada por testes
  automáticos;
- trilha de auditoria imutável (seção 5);
- chaves e senhas de sistema fora do código;
- links de descadastro e avisos de fornecedores protegidos por assinatura
  digital, para não serem falsificados;
- acesso mínimo aos fornecedores (a chave de e-mail, por exemplo, só permite
  enviar);
- lista de bloqueio consultada antes de cada envio, limites diários de envio e
  pausa automática de campanha quando a taxa de e-mails devolvidos passa de 2%.

Nenhum sistema é 100% seguro. Se ocorrer um incidente de segurança que possa
causar risco ou dano relevante, comunicaremos a ANPD e as pessoas afetadas, como
manda a LGPD (art. 48).

---

## 8. Crianças e adolescentes

O Prospector AI é um serviço entre empresas. Não é dirigido a menores de 18
anos, contas só podem ser criadas por maiores de idade, e não tratamos
intencionalmente dados de crianças ou adolescentes.

---

## 9. Mudanças nesta política

Quando mudarmos algo relevante, avisaremos os clientes por e-mail com
antecedência de [PRAZO DE AVISO] e publicaremos a nova versão com a data de
atualização. As versões anteriores ficam guardadas.

<!-- REVISAR: prazo de aviso é decisão do dono (sugestão: 30 dias; para mudanças
exigidas por lei ou por segurança, imediato). -->

---

## 10. Contato

- Encarregado de dados: [NOME DO ENCARREGADO] — **[E-MAIL DO ENCARREGADO]**
- Atendimento a clientes: **[E-MAIL DE CONTATO]**
- [RAZÃO SOCIAL] — CNPJ [CNPJ] — [ENDEREÇO]

Documentos relacionados: [Termos de Uso](TERMOS-DE-USO.md) ·
[Acordo de Tratamento de Dados](ACORDO-DE-TRATAMENTO-DE-DADOS.md) ·
[Declaração de uso de Inteligência Artificial](DECLARACAO-DE-IA.md)
