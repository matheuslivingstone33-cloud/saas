# Colocar o Prospector AI no ar — passo a passo

> **Para quem é:** para o dono do produto, sem precisar saber programar. Cada
> passo diz o que fazer, onde clicar ou o que copiar, quanto custa, quanto tempo
> leva e como saber que deu certo.
>
> **Como ler os comandos:** o que está dentro das caixas cinzas é para **copiar
> e colar** na tela preta do servidor (o "terminal"). Onde aparecer
> `<seu-dominio>`, troque pelo domínio que você comprou (ex.: `meusite.com.br`).
> Onde aparecer `<IP-do-servidor>`, troque pelo número que o provedor mostrar.
>
> **Senhas e chaves:** nenhuma aparece escrita aqui, e nenhuma deve ir para
> conversa, e-mail ou documento. As senhas internas do sistema são **criadas
> pelo próprio servidor** com um comando (passo 3.3). As chaves das APIs você
> copia do site do fornecedor e cola **direto no arquivo de configuração dentro
> do servidor**.
>
> **Preços:** mudam com frequência. Onde está escrito "conferir no site", o
> valor não foi confirmado — abra o endereço indicado antes de contratar.
>
> Última conferência deste documento contra o código: **16/09/2026**.

---

## Onde estamos

### ✅ O que já está pronto

- ✅ O sistema inteiro funciona em **modo de teste** (sem gastar nada): busca,
  qualificação, mensagens, conversas, 2º e 3º contato, créditos e painel.
  415 testes automáticos passando (conferido em 16/09).
- ✅ Cadastro, login e sessão com senha.
- ✅ Os arquivos que montam o sistema num servidor **já foram usados de verdade**
  (09 a 11/09/2026). Os quatro defeitos que apareceram ali foram corrigidos.
- ✅ As ligações com as APIs pagas estão escritas e testadas com simulação:
  Google (busca de empresas), Anthropic (IA), OpenAI (comparação de textos),
  AWS (envio de e-mail), Stripe (pagamento) e WhatsApp.
- ✅ Cópia de segurança diária do banco de dados (roteiro pronto, passo 7.1).
- ✅ **16/09:** o link "descadastrar" dos e-mails passa a abrir a página certa no
  endereço do site. Antes ele abria a página inicial e **não descadastrava
  ninguém** — ver [radar de deploy](radar/deploy.md).
- ✅ **16/09:** um cliente não vê mais os pedidos de privacidade de outro cliente.

### ⬜ O que falta você fazer (em ordem)

1. ⬜ Escolher e comprar o domínio — [passo 1.1](#11-domínio)
2. ⬜ Contratar o servidor — [passo 1.2](#12-servidor)
3. ⬜ Criar as contas das APIs — [passos 1.3 a 1.9](#13-anthropic-a-ia-que-escreve)
4. ⬜ Preparar o servidor com segurança — [fase 2](#fase-2--preparar-o-servidor-com-segurança)
5. ⬜ Subir o sistema — [fase 3](#fase-3--subir-o-sistema)
6. ⬜ Apontar o domínio e ligar o cadeado (HTTPS) — [fase 4](#fase-4--domínio-e-https)
7. ⬜ Autenticar o e-mail e pedir a saída do modo restrito da AWS — [fase 6](#fase-6--e-mail-spf-dkim-dmarc-e-aquecimento)
8. ⬜ Ligar as APIs reais, uma por vez — [fase 5](#fase-5--ligar-as-apis-reais-uma-por-vez)
9. ⬜ Cópia de segurança fora do servidor e tarefas diárias — [fase 7](#fase-7--backup-expurgo-e-o-dia-a-dia)

> A fase 6 aparece antes da 5 nesta lista de propósito: a autenticação do
> e-mail leva até alguns dias para ser aprovada, então vale começar cedo.

### ⬜ O que ainda precisa de programação antes de rodar 100%

Não é tarefa sua, mas **impede o lançamento para clientes reais**. Você pode
subir o sistema e testar sem isto; só não abra para clientes.

| | O que falta | O que acontece hoje |
|---|---|---|
| ⬜ 🔴 | **Base completa de empresas da Receita Federal** dentro do banco | O servidor não tem a base. Sem ela, as empresas encontradas **não têm e-mail** — e sem e-mail nenhuma mensagem sai. A base completa também não cabe na memória do jeito que o código lê hoje: precisa ir para o banco de dados |
| ⬜ 🔴 | **Catálogo de ramos carregado no servidor** | O catálogo que diz "quem consome o seu serviço" só é carregado junto com os dados de demonstração, que ficam desligados no servidor. Resultado: a busca roda com **0 ramos** (conferido em 16/09) |
| ⬜ 🔴 | **Catálogo de ramos compatível com a IA real** | Quando a IA real é ligada, o catálogo continua com a "impressão digital" do modo de teste, e a comparação entre os dois perde o sentido |
| ⬜ 🔴 | **Receber as respostas dos leads** | Não existe a peça que pega o e-mail de resposta e entrega ao sistema. As respostas vão para a caixa do remetente e a IA não as vê |
| ⬜ 🔴 | **Receber o aviso de e-mail devolvido ou marcado como spam** (fila, item 8) | O tradutor existe, mas nenhum endereço do sistema recebe o aviso da AWS. Sem isso o sistema não bloqueia quem reclamou |
| ⬜ 🔴 | **Cobrança segura antes do Stripe real** | Qualquer conta logada troca de plano sem pagar, e a confirmação de compra aceita um pacote diferente do pago e pode ser repetida |
| ⬜ | **Recuperação de senha** (fila, item 3) | Quem esquece a senha não volta pela tela |
| ⬜ | **Limite de tentativas no login** (fila, item 4) | Nada impede alguém de testar senhas sem parar |
| ⬜ | **Expurgo da LGPD e 2º/3º contato rodando sozinhos** (fila, item 5) | Nada dispara os dois. Enquanto não houver, o [passo 7.4](#74-tarefas-diárias-expurgo-da-lgpd-e-2º3º-contato) agenda os dois no servidor |
| ⬜ | **Link de descadastro no texto do e-mail** (fila, item 7) e no formato "1 clique" que Gmail e Yahoo pedem | Hoje o link vai só no cabeçalho da mensagem |
| ⬜ | **Encerrar sessão de verdade** (fila, item 6) | Sair apaga a sessão só no navegador |
| ⬜ | **Política de privacidade e declaração de IA no ar** | No servidor as duas páginas respondem "não encontrado", porque o texto não vai junto com o sistema. O texto também precisa de revisão jurídica antes (ver decisões) |
| ⬜ | **Painel de margem de todos os clientes** protegido | Qualquer conta logada consegue abrir |
| ⬜ | **Volta do pagamento do Stripe** | Depois de pagar, o cliente cai na página inicial em vez da tela de créditos |

### ⬜ O que precisa de decisão sua

- ⬜ **Nome do domínio** e onde comprar.
- ⬜ **Provedor do servidor e quando subir** — custa todo mês.
- ⬜ **Quais APIs ligar e em que ordem**, e quanto cada uma pode gastar por mês.
- ⬜ **Quantas páginas de resultado do Google cada busca pode ler** — cada
  página é cobrada.
- ⬜ **Velocidade do aquecimento do e-mail** (quantos envios por dia em cada
  semana) — sugestão no passo 6.6.
- ⬜ **Onde guardar a cópia de segurança fora do servidor** — passo 7.2.
- ⬜ **Textos jurídicos:** e-mail do encarregado de dados, quem é o controlador,
  transferência de dados para fora do Brasil, contratos com fornecedores e
  prazos — pedem **revisão de advogado**.
- ⬜ **Como confirmar que quem pede a exclusão de dados é mesmo o dono do e-mail.**
- ⬜ **Por quanto tempo guardar** leads que receberam mensagem e não
  responderam, e leads que pediram para sair.
- ⬜ Itens de produto já listados no HANDOFF (seção 0.2): ofício vizinho entra
  ou sai da busca, "3 com automação gratuita", recálculo do aprendizado manual
  ou automático, devolução de e-mail ensina ou não, o que mostrar quando a busca
  falha no meio, e o nosso rodapé citado sendo lido como pedido de saída.

---

## Fase 1 — O que contratar e criar

### 1.1 Domínio

**O que é:** o endereço do site. O sistema usa dois nomes dentro dele:
`app.<seu-dominio>` (o site) e `api.<seu-dominio>` (onde o site busca os dados).

- **Onde:** para `.com.br`, em https://registro.br (precisa de CPF ou CNPJ).
  Para outras terminações, qualquer registrador.
- **Quanto custa:** anuidade — conferir no site.
- **Quanto tempo:** cerca de 15 minutos; a liberação pode levar algumas horas.
- **Deu certo quando:** o domínio aparece como ativo no painel do registrador.
- **Decisão sua:** o nome.

Crie também, no provedor de e-mail que você preferir, duas caixas de entrada
**que você lê**: `contato@<seu-dominio>` (é quem envia as mensagens e recebe as
respostas) e `privacidade@<seu-dominio>` (contato do encarregado de dados, que
aparece na página de descadastro). Custo: conferir no site do provedor de
e-mail escolhido.

### 1.2 Servidor

**O que é:** o computador alugado onde o sistema roda o tempo todo.

- **O que pedir:** Ubuntu **24.04**, com **2 processadores e 4 GB de memória**
  no mínimo. Com 2 GB a montagem do site trava por falta de memória.
- **Onde:** qualquer provedor. Há guia técnico para a DigitalOcean
  ([DEPLOY-DIGITAL-OCEAN.md](DEPLOY-DIGITAL-OCEAN.md)). O teste de 09/09 usou
  um Hetzner CPX21 em Ashburn, a **US$ 37,49/mês** segundo o HANDOFF.
  DigitalOcean: https://www.digitalocean.com/pricing/droplets · Hetzner:
  https://www.hetzner.com/cloud — **conferir no site**.
- **Ao criar:** escolha **entrar por chave** (e não por senha). Para criar a
  chave no seu computador (no Windows, abra o PowerShell):

  ```bash
  ssh-keygen -t ed25519
  ```

  Aperte Enter nas perguntas. Depois mostre a parte pública para colar no painel
  do provedor:

  ```bash
  cat ~/.ssh/id_ed25519.pub
  ```

- **Vale ligar:** a cópia de segurança automática do provedor (opção paga —
  conferir no site). Ela protege contra o servidor sumir inteiro.
- **Quanto tempo:** cerca de 10 minutos.
- **Deu certo quando:** o painel mostra o servidor ligado e o **número de IP**
  dele. Anote: é o `<IP-do-servidor>`.
- **Decisão sua:** provedor, e quando começar a pagar.

### 1.3 Anthropic (a IA que escreve)

- **Onde:** https://console.anthropic.com → crie a conta, cadastre o cartão,
  compre crédito e **defina um limite de gasto mensal**. Depois crie uma chave de
  API. Caminho exato das telas: conferir no site.
- **Vai no arquivo de configuração como:** `ANTHROPIC_API_KEY`. A mesma chave
  serve para a IA e para a busca na web.
- **Quanto custa:** por uso. O sistema estima o Claude Opus 5 a US$ 5 por
  milhão de palavras-pedaço lidas e US$ 25 por milhão escritas, e a busca na web
  a cerca de US$ 10 por mil buscas. Conferir em https://www.anthropic.com/pricing.
- **Quanto tempo:** cerca de 15 minutos.
- **Deu certo quando:** a chave aparece listada no painel.

### 1.4 OpenAI (comparação de textos)

**Obrigatória sempre que a IA real estiver ligada.** A Anthropic não oferece o
serviço que transforma um texto em números para comparar parecidos; o sistema
usa o da OpenAI para isso. Sem esta chave, **toda busca falha** com a IA real
ligada.

- **Onde:** https://platform.openai.com → conta, crédito, limite de gasto e
  chave de API.
- **Vai como:** `OPENAI_API_KEY`.
- **Quanto custa:** o sistema estima US$ 0,02 por milhão de palavras-pedaço.
  Conferir em https://openai.com/api/pricing.
- **Quanto tempo:** cerca de 15 minutos.
- **Deu certo quando:** a chave aparece listada no painel.

### 1.5 Google (busca de empresas)

- **Onde:** https://console.cloud.google.com → crie um projeto, ative o
  faturamento (cartão) e ative a **"Places API (New)"**. Crie uma chave de API.
- **Proteja a chave:** restrinja a chave para usar **só a Places API (New)** e
  **só a partir do IP do servidor**. Crie um **alerta de orçamento** no
  faturamento. Caminho exato das telas: conferir no site.
- **Vai como:** `GOOGLE_MAPS_API_KEY`.
- **Quanto custa:** por consulta. O sistema estima cerca de US$ 0,032 por
  página de resultados. Conferir em
  https://developers.google.com/maps/billing-and-pricing/pricing.
- **Quanto tempo:** cerca de 30 minutos.
- **Deu certo quando:** a API aparece como "ativada" no projeto e a chave
  aparece com as restrições.

### 1.6 AWS (envio de e-mail)

- **Onde:** https://aws.amazon.com → crie a conta. Depois, no serviço **SES**,
  escolha uma região e anote o código dela (ex.: `us-east-1`; conferir no
  console se o SES existe na região escolhida).
- **Usuário só para enviar e-mail:** em **IAM**, crie um usuário com uma
  permissão que só deixa enviar e-mail. Na criação da permissão, na aba de
  texto, cole:

  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {"Effect": "Allow", "Action": ["ses:SendEmail", "ses:SendRawEmail"], "Resource": "*"}
    ]
  }
  ```

  Depois crie uma **chave de acesso** para esse usuário. **Nunca** use a chave
  da conta principal.
- **Vai como:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` (o
  código da região) e `SES_FROM_EMAIL` (ex.: `contato@<seu-dominio>`).
- **Quanto custa:** o sistema estima US$ 0,10 por mil e-mails. Conferir em
  https://aws.amazon.com/ses/pricing/.
- **Quanto tempo:** cerca de 30 minutos para a conta; a autenticação do domínio
  e a saída do modo restrito estão na [fase 6](#fase-6--e-mail-spf-dkim-dmarc-e-aquecimento).
- **Deu certo quando:** o usuário aparece no IAM com a chave de acesso criada.

### 1.7 Stripe (pagamentos)

- **Onde:** https://dashboard.stripe.com → crie a conta (para receber no
  Brasil pede dados da empresa e conta bancária).
- **Vai como:** `STRIPE_SECRET_KEY`. **Comece com a chave de teste** (começa
  com `sk_test_`). Não use a chave real antes de a programação da cobrança
  segura ficar pronta (ver tabela no topo).
- **Quanto custa:** taxa por venda. Conferir em https://stripe.com/br/pricing.
- **Quanto tempo:** cerca de 30 minutos; a verificação da conta pode levar dias.
- **Deu certo quando:** o painel mostra a chave de teste.

### 1.8 WhatsApp (opcional — deixe para o fim)

Hoje o sistema só manda WhatsApp para quem escreveu antes, dentro de 24 horas.
O suporte por WhatsApp com IA ainda não foi construído. Pode esperar.

- **Onde:** https://developers.facebook.com/docs/whatsapp/cloud-api — conta
  empresarial da Meta, um número de telefone e um token permanente.
- **Vai como:** `WHATSAPP_BSP_TOKEN`, `WHATSAPP_PHONE_ID` e
  `WHATSAPP_BUSINESS_ID`.
- **Quanto custa:** por conversa. Conferir em
  https://developers.facebook.com/docs/whatsapp/pricing.
- **Quanto tempo:** de uma hora a alguns dias (a Meta verifica a empresa).

### 1.9 GitHub (de onde o servidor baixa o sistema)

Nada a contratar: você já tem o repositório. No [passo 3.1](#31-baixar-o-sistema)
o servidor cria uma chave só de leitura e você a cadastra no GitHub.

---

## Fase 2 — Preparar o servidor com segurança

Tempo total: cerca de 30 minutos. Custo: nenhum além do servidor.

### 2.1 Entrar no servidor

No seu computador (PowerShell no Windows):

```bash
ssh root@<IP-do-servidor>
```

**Deu certo quando:** aparece uma linha terminando em `#`. Na primeira vez ele
pergunta se confia no servidor: responda `yes`.

### 2.2 Criar o usuário do dia a dia

Não se trabalha como administrador principal. Crie o usuário `prospector` (ele
vai pedir uma senha para esse usuário — guarde no seu gerenciador de senhas):

```bash
adduser prospector && usermod -aG sudo prospector && rsync --archive --chown=prospector:prospector ~/.ssh /home/prospector
```

### 2.3 Fechar as portas que não são usadas

Deixa aberto só a entrada de administração e o site:

```bash
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

**Deu certo quando:** aparece `Firewall is active and enabled on system startup`.

### 2.4 Aplicar as atualizações de segurança

```bash
DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get update -qq && DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get upgrade -y
```

Leva de 2 a 10 minutos. Confira se as atualizações automáticas de segurança
estão ligadas:

```bash
systemctl is-enabled unattended-upgrades
```

**Deu certo quando:** responde `enabled`. Se não responder, rode
`apt-get install -y unattended-upgrades` e confira de novo.

### 2.5 Memória de reserva (recomendado)

Evita que a montagem do site trave por falta de memória:

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab && free -h
```

**Deu certo quando:** a linha `Swap:` mostra `2.0Gi`.

### 2.6 Desligar a entrada por senha

Robôs testam senhas em todo servidor novo. **Antes** de desligar, confirme que
a chave funciona. Abra **outra janela** do PowerShell no seu computador:

```bash
ssh -o BatchMode=yes prospector@<IP-do-servidor> "echo ACESSO_OK"
```

Só se aparecer `ACESSO_OK`, volte à janela do servidor e rode:

```bash
tee /etc/ssh/sshd_config.d/99-prospector.conf > /dev/null <<'EOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t && systemctl reload ssh && echo "CONFIG OK"
```

**Deu certo quando:** aparece `CONFIG OK`. Se algo der errado, o painel do
provedor tem um "console" pelo navegador que entra mesmo sem esta porta.

### 2.7 Instalar o Docker (o programa que roda o sistema)

```bash
curl -fsSL https://get.docker.com | sh && usermod -aG docker prospector
```

Leva cerca de 3 minutos. Agora **saia** e entre de novo, já como `prospector`:

```bash
exit
```

```bash
ssh prospector@<IP-do-servidor>
```

Confira:

```bash
id -nG && docker ps
```

**Deu certo quando:** a primeira linha inclui `docker` e a segunda mostra um
cabeçalho `CONTAINER ID ...` sem erro de permissão. Daqui em diante, **sempre**
entre como `prospector`.

---

## Fase 3 — Subir o sistema

Tempo total: cerca de 40 minutos. Custo: nenhum além do servidor.

### 3.1 Baixar o sistema

Crie a chave só de leitura do servidor:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/deploy_prospector -N "" -C "deploy prospector" && cat ~/.ssh/deploy_prospector.pub
```

Copie a linha que apareceu. No GitHub: **o repositório → Settings → Deploy
keys → Add deploy key**, cole, e deixe **"Allow write access" desmarcado**.

Ensine o servidor a usar essa chave e teste:

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/deploy_prospector\n  IdentitiesOnly yes\n' >> ~/.ssh/config && ssh -T git@github.com
```

**Deu certo quando:** a resposta diz "successfully authenticated" e "does not
provide shell access" (isso é o esperado). Agora baixe:

```bash
cd ~ && git clone git@github.com:matheuslivingstone33-cloud/saas.git prospector && cd prospector && git log --oneline -1
```

**Deu certo quando:** aparece uma linha com o último registro do projeto. O
sistema fica em `/home/prospector/prospector` — os roteiros de backup contam
com esse lugar exato.

### 3.2 Criar o arquivo de configuração

```bash
cd ~/prospector && cp .env.example .env && chmod 600 .env
```

O `chmod 600` faz só o usuário `prospector` conseguir ler o arquivo.

### 3.3 Criar as senhas internas (o servidor cria, ninguém vê)

Este comando sorteia quatro senhas longas e já as grava no arquivo, **sem
mostrar na tela**:

```bash
cd ~/prospector && for v in APP_SECRET JWT_SECRET WEBHOOK_SECRET POSTGRES_PASSWORD; do sed -i "s|^$v=.*|$v=$(openssl rand -hex 32)|" .env; done && grep -cE '^(APP_SECRET|JWT_SECRET|WEBHOOK_SECRET|POSTGRES_PASSWORD)=[0-9a-f]{64}$' .env
```

**Deu certo quando:** o número no fim é `4`. **Rode uma vez só**: rodar de novo
depois que o banco existir troca a senha do banco e o sistema para de entrar
nele.

> Por que esse formato: senha com `/`, `@` ou `$` quebra o endereço do banco e
> a leitura do arquivo, e o sistema não sobe.

### 3.4 Preencher o resto da configuração

Na primeira linha, troque `<seu-dominio>` pelo seu domínio (sem `https://`,
sem `app.`). Rode os dois comandos **na mesma janela**:

```bash
DOMINIO=<seu-dominio>
```

```bash
cd ~/prospector && sed -i -e "s|^POSTGRES_USER=.*|POSTGRES_USER=prospector|" -e "s|^APP_ENV=.*|APP_ENV=producao|" -e "s|^URL_PUBLICA=.*|URL_PUBLICA=https://app.$DOMINIO|" -e "s|^URL_API_PUBLICA=.*|URL_API_PUBLICA=https://api.$DOMINIO|" -e "s|^ENCARREGADO_EMAIL=.*|ENCARREGADO_EMAIL=privacidade@$DOMINIO|" -e "s|^MAX_ENVIOS_POR_CAMPANHA_DIA=.*|MAX_ENVIOS_POR_CAMPANHA_DIA=20|" -e "s|^MAX_ENVIOS_POR_USUARIO_DIA=.*|MAX_ENVIOS_POR_USUARIO_DIA=20|" .env && grep -E '^(POSTGRES_USER|APP_ENV|URL_PUBLICA|URL_API_PUBLICA|ENCARREGADO_EMAIL|MAX_ENVIOS_POR_CAMPANHA_DIA|MAX_ENVIOS_POR_USUARIO_DIA|PROVIDER_MODE)=' .env
```

**Deu certo quando:** a lista mostra o seu domínio (e nada com `.local` ou
`localhost`), `POSTGRES_USER=prospector`, os dois limites de envio em `20` e
`PROVIDER_MODE=mock`.

> **Os limites de envio precisam deste passo.** O arquivo modelo vem com 200 e
> 500 envios por dia, que valem por cima da proteção de aquecimento do
> servidor. Um domínio novo mandando 500 e-mails no primeiro dia vai para o
> spam e não volta. O aumento gradual está no [passo 6.6](#66-aquecimento-do-domínio).

Todas as APIs continuam em **modo de teste** (`mock`) até a fase 5.

### 3.5 Ligar

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml up -d --build
```

Na primeira vez leva de 5 a 15 minutos. Depois confira:

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml ps
```

**Deu certo quando:** aparecem 5 linhas (`postgres`, `redis`, `backend`,
`worker`, `frontend`) e todas dizem `healthy`. Se alguma disser `starting`,
espere um minuto e rode de novo. Se disser `unhealthy` ou `restarting`, veja o
motivo com:

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml logs --tail 50 backend
```

### 3.6 Os três testes de porta

```bash
curl -s localhost:8000/health; echo; curl -s -o /dev/null -w "sem login: %{http_code}\n" localhost:8000/v1/leads; curl -s -o /dev/null -w "descadastro: %{http_code}\n" localhost:8080/descadastro/teste
```

**Deu certo quando:**

- a primeira linha mostra `"status":"ok"` e `"ambiente":"producao"`;
- `sem login: 401` — os dados estão trancados. **Se aparecer 200, pare** e não
  aponte o domínio;
- `descadastro: 400` — o link de descadastro chega à parte do sistema que
  descadastra e recusa um link falso, como deve. **Se aparecer 200**, o servidor
  está com a versão antiga do site: rode o passo 3.5 de novo.

### 3.7 Não rodar os dados de demonstração

O servidor sobe **sem** o usuário de demonstração, de propósito: a senha dele
está publicada no projeto. A primeira conta nasce pela tela de cadastro, no
passo 4.4.

---

## Fase 4 — Domínio e HTTPS

Tempo total: 20 minutos de trabalho, mais a espera da propagação (minutos a
algumas horas). Custo: nenhum (o certificado do cadeado é gratuito).

### 4.1 Apontar o domínio para o servidor

No painel do registrador (no Registro.br, na área de **DNS** do domínio), crie
dois registros do tipo **A**:

| Nome | Tipo | Valor |
|---|---|---|
| `app` | A | `<IP-do-servidor>` |
| `api` | A | `<IP-do-servidor>` |

**Deu certo quando:** no seu computador, os dois comandos abaixo mostram o
`<IP-do-servidor>`:

```bash
nslookup app.<seu-dominio>
```

```bash
nslookup api.<seu-dominio>
```

### 4.2 Instalar o Caddy (o programa que liga o cadeado)

No servidor:

```bash
sudo apt-get install -y caddy
```

Se a resposta disser que o pacote não foi encontrado, siga o guia oficial:
https://caddyserver.com/docs/install (seção Debian/Ubuntu).

### 4.3 Configurar os dois endereços

Troque `<seu-dominio>` na primeira linha. Rode os dois comandos **na mesma
janela** — a primeira linha só vale até a janela fechar:

```bash
DOMINIO=<seu-dominio>
```

```bash
sudo tee /etc/caddy/Caddyfile > /dev/null <<EOF
app.$DOMINIO {
    reverse_proxy 127.0.0.1:8080
    header {
        Strict-Transport-Security "max-age=31536000"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
    }
}

api.$DOMINIO {
    reverse_proxy 127.0.0.1:8000
    header {
        Strict-Transport-Security "max-age=31536000"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
    }
}
EOF
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo systemctl reload caddy && echo "CADDY OK"
```

**Deu certo quando:** aparece `CADDY OK`. O cadeado é emitido e renovado
sozinho; se o domínio ainda não apontar para o servidor (4.1), espere e rode
`sudo systemctl reload caddy` de novo.

### 4.4 Testar pelo domínio

```bash
curl -s https://api.<seu-dominio>/health; echo; curl -s -o /dev/null -w "descadastro: %{http_code}\n" https://app.<seu-dominio>/descadastro/teste
```

**Deu certo quando:** a primeira linha mostra `"status":"ok"` e a segunda
`descadastro: 400`.

Depois abra `https://app.<seu-dominio>` no navegador, clique em **"Usar de
forma gratuita"** e crie a sua conta.

**Deu certo quando:** o navegador mostra o cadeado, o cadastro termina e você
entra no sistema. Se o cadastro falhar com "Failed to fetch", confira no
passo 3.4 se `URL_PUBLICA` é exatamente o endereço aberto no navegador e se
`URL_API_PUBLICA` é o endereço `api.`; corrija e aplique com
`docker compose -f docker-compose.prod.yml up -d --build` (o endereço da API
fica gravado dentro do site na montagem).

---

## Fase 5 — Ligar as APIs reais, uma por vez

**Regra:** uma API por vez. Liga, testa, confere o gasto no painel do
fornecedor no dia seguinte, e só então passa para a próxima. **Qual ligar e
quando é decisão sua.** A ordem abaixo vai da mais barata e fácil de desfazer
para a mais delicada.

### Como ligar qualquer uma (o mesmo roteiro para todas)

1. Abra o arquivo de configuração:

   ```bash
   cd ~/prospector && nano .env
   ```

2. Cole a chave na linha certa (ex.: `ANTHROPIC_API_KEY=` + a chave) e troque a
   linha do modo de `mock` para `real` (ex.: `LLM_MODE=real`). **Troque a linha
   da própria API**: mexer só em `PROVIDER_MODE` não adianta, porque cada API tem
   a sua linha.
3. Salve com **Ctrl+O**, Enter, e saia com **Ctrl+X**.
4. Aplique:

   ```bash
   cd ~/prospector && docker compose -f docker-compose.prod.yml up -d --build
   ```

5. Rode o teste daquela API (abaixo). O teste **recusa rodar** se a API ainda
   estiver em modo de teste, então ele não "passa" por engano.

**Para desligar** uma API: volte a linha para `mock` e repita o item 4.

**Onde ver o que está ligado:**

```bash
curl -s localhost:8000/v1/providers
```

### 5.1 IA (Anthropic + OpenAI)

Linhas: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LLM_MODE=real`.

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml exec backend python scripts/smoke.py llm
```

**Deu certo quando:** aparece a resposta da IA e o custo estimado. Este teste
**não** confere a OpenAI; confira com:

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml exec backend python -c "from app.adapters.registry import ProviderRegistry as R; print(len(R().llm.embutir(['teste']).vetores[0]))"
```

**Deu certo quando:** aparece `384`. Custo dos dois testes: frações de centavo.
Tempo: 5 minutos.

### 5.2 Busca na web (Anthropic)

Linha: `SEARCH_MODE=real` (usa a mesma chave da Anthropic).

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml exec backend python scripts/smoke.py search --termo "Hotel Gran Marquise Fortaleza"
```

**Deu certo quando:** aparece `buscas=` com um número maior que zero. Custo: cerca
de 1 centavo de dólar por busca, mais a IA. Tempo: 5 minutos.

### 5.3 Busca de empresas (Google)

Linhas: `GOOGLE_MAPS_API_KEY`, `PLACES_MODE=real`.

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml exec backend python scripts/smoke.py places --termo "supermercado" --regiao "Fortaleza, CE"
```

**Deu certo quando:** aparece `5 resultados` (ou um número parecido) com o nome
de uma empresa real. Custo: alguns centavos de dólar. Tempo: 5 minutos.

> Lembrete da tabela do topo: sem a base completa da Receita, as empresas
> encontradas chegam **sem e-mail**. Confira quantas empresas a base tem:
>
> ```bash
> cd ~/prospector && docker compose -f docker-compose.prod.yml exec backend python scripts/smoke.py enrichment
> ```
>
> Hoje o resultado esperado no servidor é **0** — é o item 🔴 da tabela. **Nunca**
> aponte a configuração para a amostra de 20 empresas do projeto: os e-mails
> dela parecem reais e as mensagens iriam para quem não tem nada a ver.

### 5.4 E-mail (AWS SES)

**Só depois da fase 6 inteira** (domínio autenticado e saída do modo restrito
aprovada).

Linhas: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`,
`SES_FROM_EMAIL`, `EMAIL_MODE=real`.

Troque pelo **seu** e-mail — nunca o de um lead:

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml exec backend python scripts/smoke.py email --para <seu-email-pessoal>
```

**Deu certo quando:** o e-mail chega na caixa de entrada (não no spam). No
Gmail, abra a mensagem → **⋮ → Mostrar original** e confira
`SPF: PASS`, `DKIM: PASS` e `DMARC: PASS`. O link de descadastro deste e-mail
de teste é fictício; o teste do link de verdade é o `descadastro: 400` do
passo 4.4. Custo: frações de centavo. Tempo: 10 minutos.

### 5.5 Pagamentos (Stripe) — só com a chave de teste

Linhas: `STRIPE_SECRET_KEY` (a que começa com `sk_test_`), `BILLING_MODE=real`.

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml exec backend python scripts/smoke.py billing
```

**Deu certo quando:** aparece `url=https://checkout.stripe.com/...`. Abra esse
endereço e pague com o cartão de teste do Stripe (`4242 4242 4242 4242`,
qualquer data futura e qualquer código). Custo: zero no modo de teste.
**Não troque para a chave real** antes de a cobrança segura ficar pronta.

### 5.6 WhatsApp (opcional)

Linhas: `WHATSAPP_BSP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_BUSINESS_ID`,
`WHATSAPP_MODE=real`. Antes, mande uma mensagem do seu celular para o número
da empresa (abre a janela de 24 horas).

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml exec backend python scripts/smoke.py whatsapp --para +55<seu-numero>
```

**Deu certo quando:** a mensagem de teste chega no seu celular.

---

## Fase 6 — E-mail: SPF, DKIM, DMARC e aquecimento

**Por que importa:** sem estas três "assinaturas" no domínio, Gmail e Outlook
mandam as mensagens para o spam. E um domínio queimado não se recupera rápido —
leva junto o e-mail que a empresa usa para trabalhar.

Tempo: 1 hora de trabalho, mais até 72 horas de espera da AWS. Custo: nenhum
além do envio.

### 6.1 Cadastrar o domínio na AWS (DKIM)

No console da AWS → **SES** → **Identities** → **Create identity** → tipo
**Domain** → `<seu-dominio>`, com a opção **Easy DKIM** ligada. A AWS mostra
**3 registros do tipo CNAME**. Crie os três no painel de DNS do registrador,
copiando nome e valor exatamente como aparecem.

**Deu certo quando:** a identidade aparece como **Verified** no SES (pode levar
até 72 horas).

### 6.2 Endereço de devolução (SPF)

Na mesma identidade, configure o **Custom MAIL FROM domain** com um subdomínio
(ex.: `envio.<seu-dominio>`). A AWS mostra **um registro MX e um TXT**. Crie os
dois no DNS, exatamente como aparecem.

**Deu certo quando:** o status do MAIL FROM aparece como verificado. É isto que
faz o `SPF: PASS` do passo 5.4 contar a favor do seu domínio.

### 6.3 Política do domínio (DMARC)

No DNS, crie um registro **TXT** com o nome `_dmarc` e o valor:

```text
v=DMARC1; p=none; rua=mailto:contato@<seu-dominio>
```

O endereço depois de `mailto:` recebe relatórios automáticos (arquivos
técnicos); pode ser outra caixa sua. Comece com `p=none` (só observa). Depois de 2 a 4 semanas com tudo passando,
troque para `p=quarantine`.

**Deu certo quando:** no seu computador,

```bash
nslookup -type=TXT _dmarc.<seu-dominio>
```

mostra o texto acima.

### 6.4 Sair do modo restrito da AWS

Conta nova no SES só envia para endereços verificados, com limite baixo. No
console do SES → **Account dashboard** → **Request production access**. Descreva
o uso com honestidade: prospecção **B2B** para empresas, descadastro de 1
clique em toda mensagem, lista de bloqueio consultada antes de cada envio,
pausa automática com devolução acima de 2%, volume inicial baixo.

> A AWS costuma perguntar como as devoluções e reclamações são tratadas. O
> aviso automático delas ainda não chega ao sistema (tabela do topo, item 🔴).

**Deu certo quando:** o painel mostra a conta fora do "sandbox". A resposta
costuma sair em cerca de um dia — conferir no site.

### 6.5 Painel de reputação do Google

Cadastre o domínio em https://postmaster.google.com (gratuito). Ele mostra se o
Gmail está recebendo as mensagens como spam.

### 6.6 Aquecimento do domínio

O domínio novo precisa começar devagar. O passo 3.4 já deixou **20 envios por
dia**. Sugestão de subida (a velocidade é **decisão sua**):

| Semana | `MAX_ENVIOS_POR_USUARIO_DIA` e `MAX_ENVIOS_POR_CAMPANHA_DIA` |
|---|---|
| 1 | 20 |
| 2 | 50 |
| 3 | 100 |
| 4 em diante | subir aos poucos, só se a semana anterior esteve limpa |

"Limpa" quer dizer: devolução abaixo de 2% (acima disso o sistema **pausa a
campanha sozinho**) e reclamação de spam bem abaixo de 0,1% no Postmaster
(conferir o limite atual na ajuda do Google).

Para mudar o limite, edite as duas linhas com `nano .env` e aplique com o item 4
do [roteiro da fase 5](#como-ligar-qualquer-uma-o-mesmo-roteiro-para-todas).

---

## Fase 7 — Backup, expurgo e o dia a dia

### 7.1 Cópia de segurança diária do banco

A pasta das cópias nasce com o dono errado; conserte e faça a primeira cópia
na hora:

```bash
cd ~/prospector && mkdir -p backups && sudo chown -R prospector:prospector backups && sh backend/scripts/backup-prospector.sh
```

**Deu certo quando:** aparece `backup ok: ... (NNNN bytes)`.

Agende para todo dia às 06:00 do servidor. Servidores novos usam o horário
universal (UTC), três horas à frente de Brasília: 06:00 no servidor = 03:00 em
Brasília. Confira com `timedatectl` (linha `Time zone`).

```bash
crontab -l 2>/dev/null | grep -q backup-prospector || (crontab -l 2>/dev/null; echo "0 6 * * * sh /home/prospector/prospector/backend/scripts/backup-prospector.sh >> /home/prospector/backup.log 2>&1") | crontab -
```

**Deu certo quando:** no dia seguinte, `tail -3 ~/backup.log` mostra
`backup ok`. As cópias ficam 14 dias e depois são apagadas sozinhas.

### 7.2 Cópia fora do servidor

A cópia do passo 7.1 mora **no mesmo disco** do servidor. Em 11/09 o servidor
de teste foi apagado e o backup foi junto. Escolha pelo menos um (decisão sua):

- **Backup automático do provedor** (passo 1.2) — pago, conferir no site.
- **Baixar para o seu computador uma vez por semana** — gratuito. No
  PowerShell do seu computador:

  ```bash
  scp "prospector@<IP-do-servidor>:~/prospector/backups/*.sql.gz" .
  ```

  **Deu certo quando:** os arquivos `prospector-AAAA-MM-DD-HHMM.sql.gz`
  aparecem na pasta onde você rodou o comando.

### 7.3 Testar a restauração (uma vez, de verdade)

Cópia que nunca foi restaurada não é cópia. Isto restaura num banco de teste,
sem tocar no de verdade:

```bash
cd ~/prospector && ARQ=$(ls -t backups/*.sql.gz | head -1) && docker compose -f docker-compose.prod.yml exec -T postgres psql -U prospector -d postgres -c "create database teste_restore" && gunzip -c "$ARQ" | docker compose -f docker-compose.prod.yml exec -T postgres psql -q -U prospector -d teste_restore > /dev/null && docker compose -f docker-compose.prod.yml exec -T postgres psql -U prospector -d teste_restore -c "select (select count(*) from users) as contas, (select count(*) from pg_tables where schemaname = current_schema()) as tabelas"
```

**Deu certo quando:** a tabela final mostra `contas` igual ao número de contas
criadas e `tabelas` igual a 14 (as 13 do sistema mais o controle de versão do
banco). Depois apague o banco de teste:

```bash
cd ~/prospector && docker compose -f docker-compose.prod.yml exec -T postgres psql -U prospector -d postgres -c "drop database teste_restore"
```

### 7.4 Tarefas diárias: expurgo da LGPD e 2º/3º contato

Duas tarefas do sistema precisam rodar todo dia e **nada as dispara sozinho
ainda** (tabela do topo). Até isso ser programado, o servidor agenda as duas:

- **expurgo da LGPD** — apaga os dados que passaram do prazo de guarda. A
  Política de Privacidade promete que isso roda;
- **2º e 3º contato** — sem isto a tela diz "o próximo sai em 3 dias" e ele
  nunca sai. Em modo assistido, o contato espera a sua aprovação, como sempre.

Sugestão: expurgo às 06:30 (logo depois da cópia de segurança) e contatos às
12:00 do servidor (09:00 em Brasília). O horário é decisão sua.

```bash
crontab -l 2>/dev/null | grep -q executar_retencao || (crontab -l 2>/dev/null; echo "30 6 * * * cd /home/prospector/prospector && docker compose -f docker-compose.prod.yml exec -T backend python -c 'from app.workers.tasks import executar_retencao as f; print(f())' >> /home/prospector/tarefas.log 2>&1") | crontab -
```

```bash
crontab -l 2>/dev/null | grep -q executar_cadencia || (crontab -l 2>/dev/null; echo "0 12 * * * cd /home/prospector/prospector && docker compose -f docker-compose.prod.yml exec -T backend python -c 'from app.workers.tasks import executar_cadencia as f; print(f())' >> /home/prospector/tarefas.log 2>&1") | crontab -
```

Confira que as três tarefas estão agendadas:

```bash
crontab -l
```

**Deu certo quando:** aparecem três linhas (backup, `executar_retencao`,
`executar_cadencia`). No dia seguinte, confira o registro das tarefas:

```bash
grep -c "'leads_anonimizados'" ~/tarefas.log; grep -c "'avaliados'" ~/tarefas.log; grep -c Traceback ~/tarefas.log
```

Os dois primeiros números devem ser `1` ou mais (um por dia que rodou), e o
último, `0`.

> Quando o item 5 da fila for programado, estas duas linhas passam a ser
> repetidas — sem dano (as duas tarefas não fazem nada duas vezes), mas vale
> removê-las com `crontab -e`.

### 7.5 Atualizar o sistema quando houver versão nova

```bash
cd ~/prospector && git pull && docker compose -f docker-compose.prod.yml up -d --build
```

**Sempre com `--build`.** Sem ele, o sistema reinicia com a versão antiga e
parece atualizado. Depois de atualizar, repita os testes do passo 3.6.

### 7.6 O que olhar toda semana (5 minutos)

| O que | Comando ou lugar | Está bem quando |
|---|---|---|
| Tudo ligado | `cd ~/prospector && docker compose -f docker-compose.prod.yml ps` | 5 linhas `healthy` |
| Cópia de segurança | `tail -3 ~/backup.log` | `backup ok` com a data de hoje |
| Tarefas diárias | `grep -c Traceback ~/tarefas.log` | `0` |
| Espaço em disco | `df -h /` | uso abaixo de 80% |
| Trilha de auditoria intacta | `curl -s localhost:8000/v1/audit/integridade` | `"integra":true` — se `false`, **trate como incidente de segurança** |
| Erros com as APIs | `cd ~/prospector && docker compose -f docker-compose.prod.yml logs --since 24h backend worker \| grep -c esgotou` | `0` ou perto disso |
| Devolução e spam | console do SES e https://postmaster.google.com | devolução < 2%, spam bem abaixo de 0,1% |
| Gasto | painéis da Google, Anthropic, OpenAI e AWS | dentro do orçamento que você definiu |
| Margem | tela **Painel** do sistema | margem por lead positiva — se ficar negativa, o problema é preço ou consumo |

### 7.7 Se algo der errado

- **Uma API deu problema:** volte a linha dela para `mock` e aplique (roteiro da
  fase 5). O resto continua funcionando.
- **O sistema não sobe:** `docker compose -f docker-compose.prod.yml logs --tail 100 backend`
  mostra o motivo. Mensagem sobre `JWT_SECRET` = o passo 3.3 não rodou.
- **Muitos "401" nos registros:** alguém tentando adivinhar senha, ou o relógio
  do servidor errado (`timedatectl` mostra a hora).

---

## Documentos técnicos de apoio

- [DEPLOY-DIGITAL-OCEAN.md](DEPLOY-DIGITAL-OCEAN.md) — o mesmo caminho, com o
  porquê técnico de cada passo.
- [RUNBOOK-FASE7.md](RUNBOOK-FASE7.md) — a virada das APIs reais, com os
  comandos para rodar no computador de desenvolvimento.
- [radar/deploy.md](radar/deploy.md) — o que a rotina de preparação corrigiu,
  o que achou e o que depende de outras rotinas.
