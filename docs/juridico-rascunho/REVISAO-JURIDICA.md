# Revisão jurídica — o que falta para os textos valerem

**Versão 1.0 · Última atualização: 18/09/2026**

Documento interno, não publicar. Os rascunhos ficam nesta pasta,
`docs/juridico-rascunho/`, **que não vai para o site**:
[Política de Privacidade](POLITICA-DE-PRIVACIDADE.md) ·
[Termos de Uso](TERMOS-DE-USO.md) ·
[Acordo de Tratamento de Dados](ACORDO-DE-TRATAMENTO-DE-DADOS.md) ·
[Declaração de IA](DECLARACAO-DE-IA.md). Quem escreveu não é advogado: os
pontos em dúvida estão marcados no próprio texto com `REVISAR`.

> **Como publicar:** depois de aprovados, a política e a declaração de IA
> substituem os arquivos de mesmo nome em `docs/` (é de lá que o site lê), e os
> Termos ganham página própria. Desde 18/09 o site esconde sozinho os
> comentários `<!-- ... -->`, mas apague os `REVISAR` mesmo assim: alguns
> descrevem falhas ainda abertas.

## (a) O que você precisa preencher

| Marcador | O que é |
|---|---|
| `[RAZÃO SOCIAL]`, `[CNPJ]`, `[ENDEREÇO]` | a empresa que opera o Prospector AI (a lei exige identificar o controlador) |
| `[NOME DO ENCARREGADO]`, `[E-MAIL DO ENCARREGADO]` | quem responde por privacidade. O e-mail precisa existir e ser lido (ex.: `privacidade@<seu-dominio>`). Pôr o mesmo em `ENCARREGADO_EMAIL` no `.env` |
| `[E-MAIL DE CONTATO]` | atendimento a clientes |
| `[CIDADE/UF DO FORO]` | cidade para eventual processo |
| `<seu-dominio>` | o domínio que ainda vai ser comprado |
| `[PRAZO]`, `[PRAZO DE AVISO]`, `[TETO…]`, `[REDAÇÃO CONFORME…]` | saem das decisões abaixo |
| `[OS TRIBUTOS APLICÁVEIS…]` | ver com o contador |

## (b) Decisões que são suas

| Decisão | Recomendação curta |
|---|---|
| Crédito expira? (hoje nunca expira e acumula) | crédito do plano vale no mês; avulso vale 12 meses. Exige ajuste no código |
| Reembolso | 7 dias de arrependimento na primeira compra + cancelamento sem devolução do mês corrente |
| Teto de responsabilidade | valor pago pelo cliente nos últimos 12 meses |
| Foro | cidade da sede, ressalvado o direito do consumidor |
| Link de descadastro vale só para o cliente que enviou (hoje) ou para todos? | para todos — protege mais e evita reclamação |
| Quanto tempo guardar empresa abordada sem resposta e empresa descadastrada (hoje: para sempre) | 12 meses após o último contato; do descadastrado, guardar só o e-mail na lista de bloqueio |
| Quanto tempo guardar conta encerrada | 6 meses, fora o que a lei fiscal exige |
| Prazos de aviso (termos, preço, fornecedor novo) | 30 dias; 15 para fornecedor novo |
| Aviso de incidente ao cliente | até 48 horas |
| Como confirmar que quem pede os dados é o dono do e-mail | link de confirmação enviado ao próprio endereço antes de entregar ou apagar |
| "E-mail com domínio próprio" anunciado no plano Starter | tirar da vitrine: não existe |

## (c) Os 5 maiores riscos hoje

1. **Mandar e-mail para quem, na prática, é pessoa física.** O e-mail vem do
   cadastro de CNPJ, que muitas vezes é do dono, do contador ou de um MEI.
   *Os textos:* tratam tudo como dado pessoal, usam legítimo interesse com
   avaliação (LIA), proíbem prospecção de pessoa física, declaram a IA e dão
   descadastro de um clique. *Falta:* o filtro do sistema é só por palavras;
   avaliar excluir ou tratar à parte o MEI.
2. **Responder junto pelo que o cliente fizer.** O sistema escolhe as fontes e
   envia tudo do domínio do Prospector AI, o que pode fazer de você controlador
   junto com o cliente. *Os textos:* cliente declarado controlador, uso aceitável
   rígido, indenização, suspensão imediata e acordo de tratamento com proteções
   que o cliente não pode desligar.
3. **Pedido falso de titular.** Hoje qualquer pessoa pede, pelo formulário, os
   dados de outra ou o bloqueio de qualquer empresa, e o sistema atende na hora.
   *Os textos:* reservam o direito de confirmar identidade. *Falta:* construir a
   confirmação antes de lançar.
4. **Dados indo para os EUA sem contrato adequado** (Anthropic, OpenAI, Google,
   AWS, Stripe). O servidor e o banco (Vercel e Neon) ficam em São Paulo desde
   18/09, mas as duas empresas são americanas. *Os textos:* declaram a
   transferência e a garantia (cláusulas-padrão da ANPD). *Falta:* conferir e
   assinar com cada fornecedor.
5. **Texto público prometendo o que o sistema não faz** — é propaganda
   enganosa e quebra a transparência que a LGPD exige. *Os textos:* descrevem só
   o que existe; o resto está marcado como pendente (lista abaixo).

## (d) O que o sistema ainda não faz (os textos não podem prometer)

**Antes de ligar e-mail real e abrir para clientes:**

- ~~A resposta que a IA escreve ao lead saía sem link de descadastro no texto
  e com um link quebrado no cabeçalho.~~ **Corrigido em 18/09.** Falta a mesma
  linha na mensagem que o cliente escreve à mão.
- Formulário de privacidade atende sem conferir identidade, e só existe como
  rota da API (não há página).
- Expurgo por prazo existe, mas nada o dispara sozinho.
- ~~Não grava IP de acesso.~~ **Desde 18/09 grava data, hora e IP de cada
  login e cadastro, por 6 meses.** Confirmar com o advogado se basta.
- Cadastro não mostra os Termos nem registra o aceite; não há rota para os Termos.
- Respostas dos leads e avisos de spam/devolução não chegam ao sistema: sem
  isso, a IA não lê respostas, "me tire da lista" por resposta e a pausa por
  devolução não funcionam.
- Cobrança: não há mensalidade recorrente (subir para plano pago fica
  bloqueado até existir); o limite do mês não zera sozinho; a conta nova ganha
  mais do que a vitrine promete. **Desde 18/09** a compra credita uma vez só e
  só o pacote que foi pago.
- A LIA diz que a mensagem informa a origem do dado — não informa.
- Sem nome de empresa no cadastro, a mensagem sai "a serviço de nossa equipe".

**Depois, mas antes de crescer:** eliminação não apaga o texto das mensagens;
não há encerramento de conta, exportação nem eliminação ao fim do contrato
(e apagar a conta no banco apagaria a lista de bloqueio do cliente); lista de
bloqueio guarda o e-mail aberto; ninguém vigia prazo de pedido de titular;
"editar" na revisão não salva o texto; registro manual de descadastro só pela
API; sem recuperação de senha e encerramento de sessão (o limite de tentativas
de login existe desde 18/09).

## (e) O que obrigatoriamente precisa de advogado

- Papéis: você é operador ou controlador junto com o cliente? Isso define o
  Acordo de Tratamento de Dados.
- Se o legítimo interesse sustenta e-mail de cadastro de CNPJ que é, na prática,
  de pessoa física (MEI, e-mail pessoal), e se a LIA gerada pelo sistema serve.
- Transferência internacional: contrato com cada fornecedor.
- Se o cliente autônomo é consumidor (CDC): reembolso, teto de
  responsabilidade, indenização e foro mudam.
- Termos do Google Maps Platform: eles restringem guardar dados do Places, e o
  sistema guarda nome, endereço, telefone, site e nota por 180 dias ou mais.
  Risco de o Google cortar a chave.
- Prazos de guarda por situação; base para guardar o descadastro e a trilha de
  auditoria para sempre; prazos de resposta por tipo de direito.
- Se o Prospector AI pode usar as regras de agente de pequeno porte da ANPD
  (provavelmente não, por usar IA) — nomear encarregado de qualquer forma.
- Situação atual da lei de IA (PL 2338/2023) e boas práticas de e-mail comercial.
