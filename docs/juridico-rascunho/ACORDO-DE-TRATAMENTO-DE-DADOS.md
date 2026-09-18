# Acordo de Tratamento de Dados — Anexo I dos Termos de Uso

<!-- REVISAR (antes de publicar): preencher os marcadores e apagar TODOS os
comentários REVISAR. Este acordo depende do modelo de papéis explicado na
Política de Privacidade, seção 1 — se o advogado concluir por controladoria
conjunta, este anexo muda de natureza. -->

**Versão 1.0 — rascunho para revisão jurídica**
**Última atualização: 18/09/2026**

Este acordo regula como **[RAZÃO SOCIAL]** ("Prospector AI", **operador**)
trata dados pessoais em nome do Cliente (**controlador**) nas campanhas do
Cliente, conforme os arts. 37 a 42 da LGPD. Ele faz parte dos Termos de Uso. Em
caso de conflito sobre proteção de dados, prevalece este acordo.

---

## 1. Escopo

| Item | Descrição |
|---|---|
| **Titulares** | pessoas ligadas a empresas prospectadas nas campanhas do Cliente (sócios, funcionários, responsáveis por e-mail ou telefone comercial) e quem responde às mensagens |
| **Dados** | identificação e localização da empresa, e-mail, telefone e site comerciais, informações públicas do Google (categorias, nota, número de avaliações), pontuação, mensagens enviadas e recebidas, classificação das respostas, descadastros |
| **Operações** | busca, enriquecimento com a base aberta de CNPJ, pontuação, redação por IA, envio por e-mail, recebimento e classificação de respostas, registro de descadastro, retenção e eliminação |
| **Finalidade** | prospecção comercial entre empresas (B2B) do serviço do Cliente |
| **Duração** | enquanto durar o contrato, mais o prazo de devolução e eliminação da seção 9 |

**Fora deste acordo** (o Prospector AI é controlador, conforme a Política de
Privacidade): dados da conta do Cliente, registros de acesso e de segurança,
trilha de auditoria, e a **lista global de bloqueio** formada por pedidos que os
titulares fazem diretamente ao Prospector AI.

---

## 2. Instruções do Cliente

2.1. O Prospector AI trata os dados **somente** conforme as instruções
documentadas do Cliente. São instruções: estes Termos e as configurações que o
Cliente escolhe na plataforma (serviço, região, filtros, modo assistido ou
automático, aprovação ou rejeição de mensagens, conversas assumidas).

2.2. Se uma instrução parecer contrária à LGPD, o Prospector AI avisará o
Cliente e poderá deixar de cumpri-la.

2.3. Algumas proteções são fixas e **não podem ser desligadas por instrução**:
declaração de IA nas mensagens escritas pela IA, link de descadastro, consulta à
lista de bloqueio antes de cada envio, bloqueio de prospecção a pessoa física,
limites diários de envio e pausa automática por taxa de devolução.

---

## 3. Confidencialidade

Só têm acesso aos dados as pessoas do Prospector AI que precisam deles para
prestar o serviço, todas sob dever de sigilo.

---

## 4. Suboperadores

4.1. O Cliente autoriza o uso dos suboperadores abaixo:

| Suboperador | Função | País |
|---|---|---|
| Vercel | hospedagem da aplicação | São Paulo (Brasil); empresa dos EUA |
| Neon | banco de dados | São Paulo (Brasil); empresa dos EUA |
| Anthropic | IA: redação, classificação, planejamento de busca e pesquisa de sinais públicos | EUA |
| OpenAI | comparação de semelhança entre textos | EUA |
| Google (Places API) | encontrar estabelecimentos | EUA |
| Amazon Web Services (SES) | envio de e-mails | região a definir |
| Provedor da caixa de e-mail do domínio | recebimento de respostas | a definir |

4.2. O Prospector AI exige de cada suboperador obrigações de proteção de dados
equivalentes às deste acordo e responde pelo cumprimento delas.

4.3. Antes de incluir ou trocar um suboperador, o Prospector AI avisará o
Cliente com [PRAZO] dias de antecedência. Se o Cliente se opuser por motivo
razoável ligado a proteção de dados, poderá encerrar o contrato sem multa.

<!-- REVISAR: (1) nenhum destes fornecedores está contratado; a tabela precisa
bater com os contratos reais. (2) Sugestão de prazo de aviso: 15 dias.
(3) Para cada um, guardar cópia do contrato de tratamento de dados dele. -->

---

## 5. Transferência internacional

O Cliente autoriza a transferência dos dados para os países indicados na seção
4. O Prospector AI só fará essa transferência com uma das garantias do art. 33
da LGPD, preferencialmente as cláusulas-padrão contratuais aprovadas pela ANPD.

<!-- REVISAR: confirmar se cada suboperador aceita as cláusulas-padrão da ANPD
(Resolução CD/ANPD nº 19/2024 — confirmar). Sem isso, esta cláusula promete o
que ainda não existe. -->

---

## 6. Segurança

O Prospector AI mantém medidas técnicas e administrativas adequadas (LGPD,
art. 46), entre elas: conexão cifrada; senhas guardadas só como resumo
criptográfico; sessões de curta duração; separação entre contas de clientes
verificada por testes automáticos; trilha de auditoria imutável e encadeada;
chaves de sistema fora do código; assinatura digital nos links de descadastro e
nos avisos de fornecedores; acesso mínimo às contas dos fornecedores.

<!-- REVISAR: não acrescentar "criptografia em repouso", "backup" ou "teste de
invasão" sem confirmar com o provedor escolhido. Lacunas conhecidas hoje (não
listar publicamente): sem revogação de sessão, sem segundo fator, backup ainda
sem cópia fora do servidor. Limite de tentativas de login e registro de IP de
acesso existem desde 18/09. -->

---

## 7. Incidentes de segurança

7.1. O Prospector AI avisará o Cliente, **em até [48] horas** após tomar
conhecimento, de qualquer incidente que afete dados das campanhas dele e possa
causar risco ou dano relevante aos titulares.

7.2. O aviso informará, no que já se souber: o que aconteceu, que dados e
titulares foram afetados, os riscos, as medidas tomadas e o contato para
acompanhamento. As informações que faltarem serão enviadas assim que obtidas.

7.3. O Prospector AI apoiará o Cliente na comunicação à ANPD e aos titulares
(LGPD, art. 48).

<!-- REVISAR: prazo de aviso. A ANPD exige que o controlador comunique o
incidente em 3 dias úteis (Resolução CD/ANPD nº 15/2024 — confirmar). O
operador precisa avisar bem antes disso: 24 ou 48 horas são o usual. -->

---

## 8. Apoio aos direitos dos titulares

8.1. A plataforma oferece ao Cliente: a lista de descadastros das campanhas
dele, a Avaliação de Legítimo Interesse e o registro dos pedidos de titulares
ligados aos contatos das campanhas dele.

8.2. Quando um titular fizer um pedido diretamente ao Prospector AI, o
Prospector AI poderá atendê-lo diretamente. O Cliente concorda que:

- pedidos de **oposição** e de **eliminação** são aplicados a **todas** as
  contas de clientes em que aquele contato aparece, com bloqueio global do
  endereço;
- o registro do pedido fica disponível ao Cliente cujas campanhas contêm aquele
  contato.

8.3. Quando o Cliente receber um pedido, o Prospector AI ajudará a atendê-lo no
prazo legal.

<!-- REVISAR: (1) o registro dos pedidos está na API (GET
/v1/compliance/solicitacoes), sem tela; e ninguém avisa o Cliente quando chega
um pedido. (2) Pedidos públicos hoje são atendidos sem verificar a identidade de
quem pede — pendência 🔴 antes do lançamento. -->

---

## 9. Fim do contrato: devolução e eliminação

9.1. Encerrado o contrato, o Cliente poderá pedir, em até [30] dias, a
devolução dos dados das campanhas em formato estruturado.

9.2. Após esse prazo, o Prospector AI eliminará os dados das campanhas, exceto:

- o endereço na lista de bloqueio, que continua valendo para impedir novo
  contato com quem pediu para sair;
- os registros da trilha de auditoria e o que a lei exigir guardar.

<!-- REVISAR: PENDÊNCIA TÉCNICA — não existe exportação dos dados das campanhas
nem rotina de eliminação ao fim do contrato. Hoje seria tudo manual. E apagar a
conta direto no banco apaga em cascata a lista de bloqueio do Cliente; o fluxo
precisa mover esses bloqueios para a lista global antes de apagar. -->

---

## 10. Auditoria e prestação de contas

10.1. O Prospector AI manterá registro das operações de tratamento (LGPD,
art. 37) e fornecerá ao Cliente, mediante pedido, as informações necessárias
para demonstrar o cumprimento deste acordo — incluindo a verificação de
integridade da trilha de auditoria da conta dele.

10.2. O Cliente pode pedir, no máximo uma vez por ano e com aviso de 30 dias,
uma auditoria documental. Auditorias presenciais ou técnicas dependem de acordo
prévio sobre escopo, confidencialidade e custos, e não podem expor dados de
outros clientes.

---

## 11. Responsabilidade

Cada parte responde pelos danos que causar ao descumprir a LGPD ou este acordo,
nos termos dos arts. 42 a 45 da LGPD. Os limites de responsabilidade dos Termos
de Uso se aplicam na medida permitida pela lei.

<!-- REVISAR: pela LGPD (art. 42, § 1º, I) o operador responde solidariamente
quando descumpre a lei ou as instruções lícitas do controlador. O limite de
responsabilidade dos Termos pode não valer perante o titular; entre as partes,
confirmar a redação com o advogado. -->

---

**[RAZÃO SOCIAL]** — CNPJ [CNPJ] — Encarregado: [NOME DO ENCARREGADO],
**[E-MAIL DO ENCARREGADO]**
