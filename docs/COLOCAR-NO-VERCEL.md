# Colocar o Prospector AI no ar pelo Vercel — passo a passo

> **Para quem é:** para o dono do produto, sem precisar programar. Leva uns
> 30 minutos. Nada aqui custa dinheiro: Vercel e Neon têm plano gratuito.
>
> **Como fica:** dois projetos no Vercel, os dois lendo o mesmo repositório do
> GitHub. Cada vez que algo novo é salvo na versão principal, os dois se
> atualizam sozinhos.
>
> | Projeto | O que é | Endereço |
> |---|---|---|
> | `prospector-ai-app-api` | o servidor (a parte que pensa) | `https://prospector-ai-app-api.vercel.app` |
> | `prospector-ai-app` | as telas (o que o cliente vê) | `https://prospector-ai-app.vercel.app` |
>
> Os nomes `prospector-ai` e `prospector-ai-api` já pertencem a outras pessoas no
> Vercel (conferido em 22/09): por isso `prospector-ai-app` e `prospector-ai-app-api`.
>
> O banco de dados fica no **Neon**, em São Paulo, e o servidor do Vercel
> também roda em São Paulo: os dados ficam no Brasil e as respostas são rápidas.
>
> **Tudo continua em modo de teste.** Nenhum e-mail real sai, nenhuma busca
> real é feita, nenhuma API paga é chamada. Ligar as APIs reais é outro passo,
> em [COLOCAR-NO-AR.md](COLOCAR-NO-AR.md), fase 5.
>
> Última conferência deste documento contra o código: **22/09/2026**.

---

## ✅ NO AR desde 22/09/2026

| O quê | Endereço |
|---|---|
| Telas | https://prospector-ai-app.vercel.app |
| Servidor | https://prospector-ai-app-api.vercel.app |
| Saúde do servidor | https://prospector-ai-app-api.vercel.app/v1/health/ready |

Conferido em 22/09: banco Neon respondendo (`"banco":"ok"`), ambiente
`producao`, **tudo em modo de teste** (`"tudo_mock":true`), página de
privacidade abrindo, link de descadastro atendido pelo servidor e a origem das
telas autorizada. O passo a passo abaixo fica como registro de como foi feito.

---

## Antes de começar: o plano gratuito do Vercel não é para venda

O plano gratuito (Hobby) do Vercel **só pode ser usado para projeto pessoal,
sem fins comerciais**. Serve para colocar no ar, testar e mostrar. **No dia em
que o primeiro cliente pagar**, o projeto precisa estar no plano Pro
(US$ 20 por mês por pessoa da equipe — conferir em https://vercel.com/pricing).

---

## Parte 1 — As três senhas internas

O servidor precisa de três senhas longas e aleatórias. **Ninguém precisa
saber quais são**, nem você: elas só ficam guardadas no Vercel.

No terminal do seu computador, rode este comando **três vezes**. Cada vez sai
uma senha diferente:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Deixe o terminal aberto: você vai copiar cada uma **direto para o Vercel** na
parte 2. **Não cole essas senhas em conversa, e-mail ou documento.**

---

## Parte 2 — O servidor (`prospector-ai-app-api`)

1. Entre em https://vercel.com e clique em **Add New… → Project**.
2. Em **Import Git Repository**, escolha o repositório **`saas`**.
   - Se ele não aparecer: clique em **Adjust GitHub App Permissions** e dê
     acesso ao repositório `saas`.
3. Na tela de configuração:
   - **Project Name:** `prospector-ai-app-api`
   - **Root Directory:** clique em **Edit** e escolha a pasta **`backend`**.
     Deixe **marcada** a opção de incluir arquivos de fora dessa pasta no build
     (vem marcada). Sem ela, a busca fica sem a lista de ramos.
   - **Framework Preset:** deve aparecer **FastAPI** sozinho.
4. Abra **Environment Variables**. O Vercel lê o `.env.example` do repositório e
   já cria ~44 linhas **vazias**. **Apague todas** (botão `−` de cada uma) e
   cadastre só estas 8 — linha vazia como `DATABASE_URL` atrapalha o banco, e as
   numéricas vazias derrubam o servidor:

   | Nome | Valor |
   |---|---|
   | `APP_ENV` | `producao` |
   | `JWT_SECRET` | a 1ª senha da parte 1 |
   | `APP_SECRET` | a 2ª senha da parte 1 |
   | `WEBHOOK_SECRET` | a 3ª senha da parte 1 |
   | `ADMIN_EMAILS` | o e-mail com que **você** vai criar sua conta no sistema |
   | `URL_PUBLICA` | `https://prospector-ai-app.vercel.app` |
   | `CORS_ORIGINS` | `https://prospector-ai-app.vercel.app` |
   | `ENCARREGADO_EMAIL` | um e-mail seu para assuntos de privacidade |

5. Clique em **Deploy**.
   - **O primeiro vai falhar**, com a mensagem *"sem banco Postgres
     configurado"*. É esperado: o banco vem no próximo passo.
6. **Crie o banco.** Dentro do projeto `prospector-ai-app-api`, abra a aba
   **Storage** → **Create Database** → **Neon** → **Continue**.
   - **Região:** **São Paulo** (`sa-east-1`).
   - **Plano:** **Free**.
   - Na hora de conectar ao projeto, deixe marcados todos os ambientes
     (Production, Preview e Development).
   - O Vercel pode pedir para você aceitar os termos do Neon: isso é com você.
7. Volte para a aba **Deployments**, abra o último, clique nos **três
   pontinhos** → **Redeploy**.
8. **Como saber que deu certo:** o deploy termina como **Ready**, e este
   endereço mostra `"status": "ok"` e `"banco": "ok"`:

   https://prospector-ai-app-api.vercel.app/v1/health/ready

> Se o Vercel der outro nome ao endereço (quando `prospector-ai-app-api` já está
> em uso por outra pessoa), anote o endereço que ele mostrar: as telas precisam
> apontar para ele, e o arquivo `frontend/vercel.json` também.

---

## Parte 3 — As telas (`prospector-ai-app`)

1. De novo **Add New… → Project** e o mesmo repositório **`saas`**.
2. Na tela de configuração:
   - **Project Name:** `prospector-ai-app`
   - **Root Directory:** **`frontend`**
   - **Framework Preset:** **Vite** (aparece sozinho).
3. Em **Environment Variables**:

   | Nome | Valor |
   |---|---|
   | `VITE_API_URL` | `https://prospector-ai-app-api.vercel.app` |

4. **Deploy**.
5. **Como saber que deu certo:** https://prospector-ai-app.vercel.app abre a tela
   de entrada. Crie sua conta com o **mesmo e-mail** que você pôs em
   `ADMIN_EMAILS`.
6. Teste o link de descadastro:
   https://prospector-ai-app.vercel.app/descadastro/teste — tem que aparecer uma
   página de **link inválido** (é o servidor respondendo). Se aparecer a tela
   inicial do sistema, o repasse para o servidor não está funcionando.

---

## O que ainda não roda sozinho no Vercel

- **2º e 3º contato e a limpeza de dados antigos (LGPD).** No servidor próprio
  eles eram agendados no próprio servidor. No Vercel isso vira um "Cron Job",
  que ainda não foi configurado. Enquanto tudo estiver em modo de teste, não
  faz falta; **antes de ligar o e-mail real, faz.**
- **Domínio próprio.** Por enquanto os endereços são `.vercel.app`. Quando
  comprar o domínio, ele é ligado em **Settings → Domains** de cada projeto, e
  `URL_PUBLICA`, `CORS_ORIGINS`, `VITE_API_URL` e o `frontend/vercel.json`
  mudam junto.

## Dois tropeços que já aconteceram (22/09)

- **"Deployment Blocked — the commit author did not have contributing access".**
  O Vercel do plano gratuito só aceita deploy de commit assinado pelo dono da
  conta. Os commits saíam com o e-mail de outra conta do GitHub. Corrigido: o
  repositório passou a assinar com
  `281270410+matheuslivingstone33-cloud@users.noreply.github.com`. **Commits
  antigos continuam bloqueados** — o deploy tem que partir de um commit novo.
- **"The pattern app/main.py defined in `functions` doesn't match any Serverless
  Functions inside the `api` directory".** O `backend/vercel.json` tinha um bloco
  `functions`, que o Vercel só casa com arquivos dentro de `api/`. O bloco saiu;
  os padrões já dão 300 s de teto no plano gratuito.

## Se algo der errado

Abra o deploy que falhou, copie as **últimas linhas do log** (sem nenhuma
senha) e mande na conversa.
