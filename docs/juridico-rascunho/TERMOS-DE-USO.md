# Termos de Uso — Prospector AI

<!-- REVISAR (antes de publicar): (1) preencher os marcadores entre colchetes;
(2) apagar TODOS os comentários REVISAR; (3) PENDÊNCIA TÉCNICA: hoje não existe
rota pública para estes Termos (só há /legal/privacidade e /legal/ia), o
cadastro não mostra link para os Termos e NÃO registra o aceite (data, hora e
versão aceita). Sem esse registro fica difícil provar que o cliente aceitou.
Criar antes do lançamento. -->

**Versão 1.0 — rascunho para revisão jurídica**
**Última atualização: 18/09/2026**

Estes Termos são o contrato entre **[RAZÃO SOCIAL]**, CNPJ **[CNPJ]**, com
endereço em **[ENDEREÇO]** ("Prospector AI", "nós"), e a pessoa ou empresa que
cria uma conta na plataforma ("Cliente", "você").

Fazem parte destes Termos:

- a [Política de Privacidade](POLITICA-DE-PRIVACIDADE.md);
- o [Acordo de Tratamento de Dados](ACORDO-DE-TRATAMENTO-DE-DADOS.md) (Anexo I);
- a [Declaração de uso de Inteligência Artificial](DECLARACAO-DE-IA.md);
- a página de planos e a tela de Créditos, vigentes no momento da contratação.

Ao criar a conta você declara que leu e aceita estes Termos. Se não concordar,
não use a plataforma.

---

## 1. Definições

- **Plataforma:** o software Prospector AI, acessado pelo navegador.
- **Campanha:** uma busca criada por você, com o serviço que você presta e a
  região onde quer clientes.
- **Empresa prospectada (lead):** empresa encontrada pela plataforma numa
  campanha sua.
- **Contato revelado:** empresa cujos dados de contato (razão social, CNPJ,
  e-mail, telefone, site, endereço) foram liberados para você.
- **Crédito:** unidade que você compra e que é consumida pelo uso.
- **Modo assistido:** cada mensagem só sai depois que você a aprova. É o modo
  inicial de toda conta.
- **Modo automático:** as mensagens saem sem aprovação individual, dentro dos
  limites da plataforma.
- **Descadastro (opt-out):** pedido de uma pessoa ou empresa para não receber
  mais mensagens.
- **Lista de bloqueio:** lista de endereços que não podem receber mensagens —
  as suas e a lista global do Prospector AI.

---

## 2. O que a plataforma faz

A partir da descrição do serviço que você presta e de uma região, a plataforma:

1. escolhe os ramos de atividade que costumam contratar esse serviço, procurando
   excluir os que prestam o mesmo serviço que você;
2. encontra empresas desses ramos por meio da API oficial do Google Places e da
   base aberta de CNPJ da Receita Federal;
3. pontua cada empresa, com a explicação de cada fator;
4. mostra a lista encontrada e libera o contato conforme o seu plano e os seus
   créditos;
5. redige com inteligência artificial uma mensagem de apresentação e até dois
   acompanhamentos, e os envia por e-mail — com a sua aprovação (modo assistido)
   ou sem ela (modo automático);
6. classifica as respostas recebidas e, conforme o caso, redige uma resposta,
   para de escrever ou devolve a conversa para você;
7. permite que você assuma a conversa e escreva suas próprias mensagens.

**O que a plataforma não faz:** não prospecta pessoas físicas como consumidoras;
não envia prospecção por WhatsApp; não permite importar listas de contatos; não
fecha negócios, não negocia preço, não assina nem agenda reuniões em seu nome; e
não garante resultado comercial.

**Remetente das mensagens:** as mensagens saem de um endereço e de um domínio
operados pelo Prospector AI e informam que são enviadas **a serviço da sua
empresa**. Esse domínio é compartilhado por todos os clientes — por isso existem
os limites e as regras de uso aceitável destes Termos.

<!-- REVISAR: (1) o plano Starter anuncia "e-mail com domínio próprio" e isso
NÃO existe no código — todas as mensagens saem do mesmo remetente
(SES_FROM_EMAIL). Tirar a frase da vitrine ou construir a função antes de
vender. (2) As respostas dos destinatários chegam à caixa desse remetente; hoje
não existe a peça que as traz para dentro da plataforma. Definir como elas
chegam ao Cliente antes do lançamento — até lá, o item 6 acima não funciona com
e-mail real. -->

---

## 3. Cadastro e segurança da conta

3.1. Para usar a plataforma você precisa ser maior de 18 anos e capaz, ou agir
em nome de uma empresa com poderes para isso.

3.2. Você deve informar dados verdadeiros e mantê-los atualizados —
principalmente o **nome da sua empresa**, que aparece em todas as mensagens
enviadas em seu nome. É proibido usar nome de outra empresa ou pessoa.

<!-- REVISAR: PENDÊNCIA TÉCNICA — hoje, se o Cliente não preencher o nome da
empresa, a mensagem sai "a serviço de nossa equipe", sem identificar quem
oferta. O sistema deveria impedir o envio sem nome de empresa preenchido. -->

3.3. Você é responsável por guardar sua senha e por tudo o que for feito com a
sua conta. Se suspeitar de uso indevido, troque a senha e avise-nos em
**[E-MAIL DE CONTATO]**.

<!-- REVISAR: PENDÊNCIA TÉCNICA — hoje não há recuperação de senha, nem como
encerrar a sessão em outros aparelhos (HANDOFF §0.1 itens 3 e 6). O limite de
tentativas de login existe desde 18/09. O item 3.3 pressupõe que o cliente
consiga trocar a senha. -->

3.4. A conta é pessoal da empresa ou profissional que a criou. Não revenda nem
ceda o acesso a terceiros.

---

## 4. Planos, créditos e cobrança

4.1. **Planos.** Os planos, seus preços, limites e o que cada um inclui são os
exibidos na página de planos no momento da contratação. O plano gratuito tem
limite de contatos revelados por mês e por busca.

4.2. **O que consome créditos.** A plataforma cobra pelo que tem valor para
você, não pela busca: ver a lista de empresas encontradas (ramo, bairro, porte,
pontuação) não consome crédito. Hoje consomem créditos:

| Operação | Créditos |
|---|---|
| Revelar o contato de uma empresa | 1 |
| Cada mensagem enviada pela plataforma | 1 |
| Pesquisa de sinais públicos na web sobre uma empresa (quando usada) | 2 |

Revelar o mesmo contato duas vezes não cobra de novo. Preparar a primeira
mensagem para uma empresa revela o contato dela (o rascunho já mostra nome e
e-mail), mesmo que a mensagem ainda aguarde a sua aprovação. A tabela vigente
fica na tela de Créditos e prevalece sobre esta.

4.3. **Limites.** Cada plano tem um limite mensal de contatos revelados. Ao
atingir o limite ou zerar os créditos, a plataforma bloqueia novas operações
pagas até a renovação, a compra de créditos ou a ativação do consumo excedente
(quando o plano permitir).

4.4. **Pagamento.** Os pagamentos são processados pelo Stripe. Não recebemos nem
guardamos o número do seu cartão. Os preços incluem [OS TRIBUTOS APLICÁVEIS /
NÃO INCLUEM TRIBUTOS — definir].

4.5. **Validade dos créditos.**

<!-- REVISAR — DECISÃO DO DONO. Hoje o código NÃO expira crédito e SOMA os
créditos de cada renovação ao saldo anterior. Opções:
(A) Créditos não expiram (é o que o código faz hoje). Simples, sem risco de
    reclamação; custo: passivo que cresce.
(B) Créditos do plano valem até o fim do ciclo mensal (não acumulam); créditos
    comprados avulsos valem 12 meses. Padrão de mercado. Exige mudança no código.
(C) Todos os créditos valem 12 meses a partir da compra.
Recomendação: (B), com aviso claro na tela de compra e no extrato. Evitar prazo
muito curto para avulsos (pode ser visto como abusivo pelo CDC, se o cliente for
consumidor). Apagar as opções não escolhidas. -->

[REDAÇÃO CONFORME A OPÇÃO ESCOLHIDA]

4.6. **Cancelamento e reembolso.**

<!-- REVISAR — DECISÃO DO DONO. Opções:
(A) Arrependimento em 7 dias: na primeira contratação (plano ou pacote), o
    Cliente pode desistir em até 7 dias e recebe o valor integral de volta,
    descontados os créditos já usados. Cobre o art. 49 do CDC (compra pela
    internet) caso o Cliente seja considerado consumidor.
(B) Sem reembolso de créditos usados; créditos não usados de pacote avulso
    reembolsáveis em até [X] dias da compra.
(C) Cancelamento do plano interrompe a próxima cobrança, sem devolução
    proporcional do mês em curso.
Recomendação: (A) + (C). É o mínimo para não perder uma discussão de CDC e é
simples de operar. Apagar as opções não escolhidas. -->

[REDAÇÃO CONFORME A OPÇÃO ESCOLHIDA]

4.7. **Reajuste.** Podemos alterar preços com aviso prévio de [PRAZO DE AVISO].
A mudança não afeta créditos já comprados nem o ciclo já pago.

4.8. **Falta de pagamento.** Se um pagamento falhar ou for estornado, podemos
suspender as operações pagas até a regularização.

<!-- REVISAR: PENDÊNCIAS TÉCNICAS de cobrança (não publicar estas cláusulas como
se tudo funcionasse): (1) não existe cobrança recorrente mensal — o Stripe só
vende pacotes avulsos; (2) a troca de plano hoje NÃO cobra nada e recarrega
créditos (bug conhecido, travar antes do Stripe real); (3) a confirmação de
compra pode creditar duas vezes; (4) o limite mensal não zera sozinho a cada
mês; (5) conta nova nasce com 500 créditos e limite de 100 contatos/mês, mas a
vitrine do plano gratuito promete 10 contatos/mês e 50 créditos — alinhar a tela,
o código e este texto. -->

---

## 5. Uso aceitável

5.1. **Só entre empresas.** A plataforma serve exclusivamente para oferecer o
**seu** serviço a **empresas**. É proibido usá-la para contatar pessoas físicas
como consumidoras.

5.2. **É proibido:**

- enviar spam, correntes, mensagens em massa sem relação com o ramo da empresa
  contatada ou qualquer conteúdo que não seja oferta do seu próprio serviço;
- usar listas compradas, alugadas, obtidas de vazamento ou de raspagem de dados,
  ou tentar inserir contatos de fora na plataforma;
- enviar conteúdo falso, enganoso ou que prometa resultado que você não pode
  entregar;
- se passar por outra empresa ou pessoa, ou esconder quem está fazendo a oferta;
- ofertar produtos ou serviços ilegais, ou que exijam autorização que você não
  tem;
- remover ou tentar contornar a declaração de IA, o link de descadastro, a lista
  de bloqueio, os limites de envio ou as travas de plano;
- revender, ceder, publicar ou usar os dados obtidos na plataforma para outra
  finalidade que não a prospecção do seu próprio serviço;
- raspar, copiar em massa, fazer engenharia reversa, testar vulnerabilidades ou
  sobrecarregar a plataforma;
- usar a plataforma para desenvolver produto concorrente.

5.3. **Descadastro é definitivo.** Quando alguém se descadastra ou pede para não
ser contatado, a plataforma bloqueia o endereço **de forma permanente**. Você
não pode remover esse bloqueio, nem usar outro meio (outra ferramenta, outro
e-mail, telefone) para insistir na mesma oferta com quem pediu para sair. Alguns
bloqueios valem só para as suas campanhas (quando a pessoa se descadastra de uma
mensagem sua); outros valem para todos os clientes (quando a pessoa pede
diretamente ao Prospector AI). Ferramentas automáticas de segurança do
destinatário podem abrir o link de descadastro e acionar o bloqueio; ele não é
revertido.

5.4. **Pedidos recebidos fora da plataforma.** Se alguém pedir para sair por
outro meio (telefone, outro e-mail), registre o pedido na plataforma ou envie-o
para **[E-MAIL DE CONTATO]** em até 1 dia útil.

<!-- REVISAR: PENDÊNCIA TÉCNICA — o registro manual de descadastro existe só na
API (POST /v1/compliance/opt-outs); a tela de Conformidade mostra a lista mas
não tem campo para registrar. Criar o campo ou manter só o e-mail. -->



5.5. **Limites de envio.** A plataforma aplica limites diários de envio e pausa
automaticamente campanhas com taxa de e-mails devolvidos acima de 2%. Essas
travas protegem o domínio de envio de todos os clientes e não são negociáveis.

---

## 6. Suas responsabilidades pelos dados das campanhas

Nas suas campanhas **você é o controlador dos dados** das empresas prospectadas,
e o Prospector AI atua como operador, conforme o Anexo I. Por isso você se
compromete a:

- ter um interesse legítimo real em oferecer seu serviço às empresas
  contatadas, e descrever seu serviço com veracidade;
- manter a Avaliação de Legítimo Interesse gerada para a sua conta (tela de
  Conformidade) e revisá-la se mudar o uso;
- responder, com o nosso apoio, aos pedidos de titulares relacionados às suas
  campanhas;
- não nos dar instruções que violem a lei;
- no modo assistido, ler cada mensagem antes de aprovar;
- ao ativar o **modo automático**, assumir a responsabilidade pelas mensagens
  enviadas em seu nome sem aprovação individual.

Você responde perante terceiros e perante o Prospector AI pelos danos causados
por uso da plataforma em desacordo com estes Termos ou com a lei, inclusive
reclamações, multas e custos de defesa decorrentes desse uso.

<!-- REVISAR: cláusula de indenização. Útil para o Prospector AI, mas em
contrato de adesão pode ser questionada se o Cliente for consumidor (CDC) ou se
for desproporcional (Código Civil, art. 424). Pedir redação ao advogado. -->

---

## 7. Conteúdo gerado por inteligência artificial

7.1. A plataforma usa IA para escolher ramos, pontuar empresas, redigir
mensagens e classificar respostas. A IA **pode errar**: escolher um ramo
inadequado, escrever algo impreciso ou interpretar mal uma resposta.

7.2. Os textos são sugestões de apresentação comercial, não promessas
contratuais. Cabe a você revisá-los (modo assistido) ou aceitar o risco de não
revisá-los (modo automático).

<!-- REVISAR: PENDÊNCIA TÉCNICA — a tela de revisão tem um botão "editar", mas
o texto editado NÃO é salvo: ao aprovar, sai o texto original da IA. Por isso
esta cláusula fala em "aprovar ou rejeitar", não em "editar". Corrigir antes de
vender a função. -->

7.3. Toda mensagem escrita pela IA leva a declaração de que foi redigida por
inteligência artificial a serviço da sua empresa. Essa declaração **não pode ser
removida**. Mensagens que você mesmo escreve não levam a declaração, mas levam o
link de descadastro.

7.4. **Não garantimos resultado comercial**: número de respostas, reuniões,
vendas ou entrega em caixa de entrada (e não na pasta de spam).

---

## 8. Disponibilidade e manutenção

8.1. Trabalhamos para manter a plataforma disponível, mas **não garantimos
funcionamento ininterrupto ou livre de erros**. Pode haver paradas para
manutenção, atualização ou por falha de fornecedores (hospedagem, Google,
provedores de IA, envio de e-mail, pagamentos).

8.2. Podemos alterar, melhorar ou descontinuar funcionalidades. Mudanças que
reduzam de forma relevante o que você contratou serão avisadas com antecedência
de [PRAZO DE AVISO], com direito de cancelar sem multa.

---

## 9. Limitação de responsabilidade

<!-- REVISAR — DECISÃO DO DONO + ADVOGADO. Opções de teto:
(A) o valor pago pelo Cliente nos 12 meses anteriores ao fato;
(B) o valor pago nos 3 meses anteriores;
(C) um valor fixo de R$ [X].
Recomendação: (A) — é o padrão de SaaS e o mais defensável. Atenção: se o
Cliente for consumidor (ex.: autônomo vulnerável), o CDC (art. 51, I) anula
cláusula que limite a responsabilidade do fornecedor (para consumidor pessoa
jurídica, só em situação justificável), e o art. 25 proíbe exonerar. Em contrato
de adesão, o Código Civil (art. 424) também limita renúncias. Por isso o texto
abaixo ressalva a lei. -->

9.1. Na máxima extensão permitida pela lei, o Prospector AI não responde por
lucros cessantes, perda de oportunidade de negócio, perda de receita ou danos
indiretos.

9.2. A responsabilidade total do Prospector AI, por qualquer causa ligada a
estes Termos, fica limitada a [TETO CONFORME A OPÇÃO ESCOLHIDA].

9.3. Os limites acima não se aplicam a danos causados por dolo ou culpa grave do
Prospector AI, nem afastam direitos que a lei não permita limitar, inclusive os
do Código de Defesa do Consumidor, quando aplicável.

9.4. O Prospector AI não responde pelo conteúdo que você aprovar ou escrever,
nem por mensagens enviadas no modo automático conforme as configurações que você
escolheu.

---

## 10. Suspensão e encerramento

10.1. **Por você:** você pode encerrar a conta a qualquer momento escrevendo
para **[E-MAIL DE CONTATO]**.

10.2. **Por nós:** podemos suspender a conta **imediatamente**, com aviso quando
possível, se houver: violação da seção 5 (uso aceitável); reclamações de spam ou
taxa de devolução que ameacem o domínio de envio; indício de fraude ou de uso
por terceiro não autorizado; falta de pagamento; ou ordem de autoridade.
Podemos encerrar a conta se a violação for grave ou não for corrigida em
[PRAZO] dias após o aviso.

10.3. **Efeitos:** encerrada a conta, o acesso termina, o envio para, e os dados
das campanhas são tratados conforme o Anexo I (devolução e eliminação). Os
bloqueios de descadastro continuam valendo, porque protegem quem pediu para sair.

<!-- REVISAR: PENDÊNCIA TÉCNICA — não existe hoje encerramento de conta pela
tela, exportação dos dados das campanhas, nem rotina de eliminação ao fim do
contrato; tudo seria manual. Atenção: apagar a conta direto no banco apaga em
cascata a lista de bloqueio própria do Cliente (opt_outs.user_id com
ON DELETE CASCADE). O fluxo de encerramento precisa preservar os bloqueios. -->

---

## 11. Propriedade intelectual

11.1. A plataforma, seu código, sua marca, o catálogo de ramos, os modelos de
pontuação e a documentação pertencem ao Prospector AI. Estes Termos dão a você
apenas o direito de uso, pessoal, não exclusivo e intransferível, enquanto a
conta estiver ativa.

11.2. Os dados que você fornece (descrição do serviço, mensagens que escreve) são
seus. Você nos autoriza a usá-los apenas para prestar o serviço.

11.3. Os textos gerados pela IA para as suas campanhas podem ser usados por você
livremente. Textos parecidos podem ser gerados para outros clientes.

11.4. Hoje o aprendizado da plataforma é feito por conta e não é compartilhado
entre clientes. Se no futuro quisermos usar estatísticas agregadas e
anonimizadas para melhorar o produto, avisaremos com antecedência, na forma da
seção 14.

---

## 12. Confidencialidade

Cada parte guarda sigilo sobre as informações não públicas da outra a que tiver
acesso (dados de campanhas, preços negociados, informações técnicas), e só as
usa para cumprir estes Termos. O dever continua por [PRAZO] anos após o fim do
contrato, exceto para informações que se tornem públicas sem culpa da parte ou
que devam ser reveladas por lei ou ordem judicial.

---

## 13. Registros de acesso

Como determina o art. 15 do Marco Civil da Internet (Lei nº 12.965/2014), o
Prospector AI mantém os registros de acesso à aplicação (data, hora e endereço
IP), sob sigilo e em ambiente seguro, pelo prazo de 6 meses, e só os fornece
mediante ordem judicial.

<!-- REVISAR: desde 18/09 o sistema grava data, hora e IP de cada login e de
cada cadastro, e apaga depois de 6 meses (tabela tentativas_acesso). Confirmar
com o advogado se isso basta para o art. 15 ou se a renovação automática da
sessão também precisa ser registrada. -->

---

## 14. Alterações destes Termos

Podemos alterar estes Termos. Mudanças relevantes serão avisadas por e-mail com
antecedência de [PRAZO DE AVISO]. Se não concordar, você pode cancelar antes da
data de vigência, com os direitos da seção 4.6. Continuar usando a plataforma
depois dessa data significa aceitar a nova versão. Mudanças exigidas por lei ou
por segurança podem valer de imediato.

---

## 15. Disposições gerais

15.1. Estes Termos são regidos pelas leis do Brasil.

15.2. Fica eleito o foro da comarca de **[CIDADE/UF DO FORO]** para resolver
questões ligadas a estes Termos, ressalvado o direito do consumidor de propor
ação no próprio domicílio.

<!-- REVISAR: em contrato de adesão com consumidor, a eleição de foro que
dificulte a defesa pode ser considerada abusiva (CDC, art. 101, I). A ressalva
acima reduz esse risco. Recomendação: foro da cidade da sede do Prospector AI. -->

15.3. Se alguma cláusula for considerada inválida, as demais continuam valendo.
Deixar de exigir um direito não significa renunciar a ele. Você não pode ceder
este contrato sem nossa concordância; nós podemos cedê-lo em caso de
reorganização societária, com aviso.

15.4. As comunicações entre as partes serão feitas por e-mail: para você, no
e-mail da conta; para nós, em **[E-MAIL DE CONTATO]**.

---

## Contato

**[RAZÃO SOCIAL]** — CNPJ [CNPJ] — [ENDEREÇO]
Atendimento: **[E-MAIL DE CONTATO]** · Privacidade: **[E-MAIL DO ENCARREGADO]**
