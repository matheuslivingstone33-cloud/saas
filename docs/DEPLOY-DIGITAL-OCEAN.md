# Deploy — Digital Ocean

Guia do zero até o sistema no ar. Assume um droplet Ubuntu 24.04 (2 vCPU / 4 GB
é o mínimo confortável) e um domínio apontando para ele.

> O sistema sobe em **modo mock** e continua funcionando assim. As chaves entram
> depois, **uma por vez**, seguindo o [runbook da Fase 7](RUNBOOK-FASE7.md).

> **Desde a Etapa 8 há autenticação de verdade** (cadastro, login, sessão por
> JWT). Era o último bloqueio para o sistema poder ficar público: antes dela,
> `curl -H "X-User-Email: cliente@empresa.com"` devolvia os leads daquele
> cliente. Três variáveis novas de `.env` vieram junto — veja o passo 3.

> **Memória:** 4 GB é mínimo, não recomendação. O build do frontend acontece no
> servidor e morre por falta de RAM em droplets de 2 GB.

---

## 1. Droplet

```bash
ssh root@SEU_IP
```

```bash
adduser prospector && usermod -aG sudo prospector && rsync --archive --chown=prospector:prospector ~/.ssh /home/prospector
```

```bash
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

Depois entre como `prospector` (não use root para o dia a dia).

A imagem do provedor costuma vir com dezenas de atualizações de segurança
pendentes. Aplique antes de o servidor ficar público:

```bash
sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get upgrade -y
```

### Fechar o login por senha

O servidor nasce com a porta 22 aberta para a internet, e bots varrem faixas de
IP inteiras testando `123456`, `admin`, `senha`. Com um usuário no grupo `sudo`,
isso não é risco teórico.

**Antes de desligar a senha, confirme que a chave funciona** — de outra aba, a
partir da sua máquina:

```bash
ssh -o BatchMode=yes prospector@SEU_IP "echo ACESSO_OK"
```

`BatchMode` proíbe qualquer prompt: se imprimir `ACESSO_OK`, a chave está de
pé sozinha. Só então:

```bash
sudo tee /etc/ssh/sshd_config.d/99-prospector.conf > /dev/null <<'EOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
EOF
sudo sshd -t && sudo systemctl reload ssh && echo "CONFIG OK"
```

O `sshd -t` valida a sintaxe **antes** do reload: com erro, ele para e não
derruba o serviço. E se ainda assim algo der errado, o console pelo navegador
do provedor entra por teclado virtual, independente do SSH.

## 2. Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
```

Dê ao usuário do dia a dia o direito de usar o Docker sem `sudo`. Repare que o
nome vai **explícito**, não como `$USER`:

```bash
sudo usermod -aG docker prospector
```

> **Por que não `$USER`:** se você estiver numa sessão `root` — e é fácil estar,
> porque o passo 1 começa como root —, `$USER` vale `root` e o comando adiciona
> o usuário errado, sem erro nenhum. O sintoma aparece bem depois, como
> `permission denied` no `docker.sock`, e não parece ter relação com isto.

Grupo só é carregado no login. **Saia e entre de novo** — não basta `newgrp`, e
muito menos continuar na sessão atual:

```bash
exit
```

Reconecte e confirme (a lista tem que incluir `docker`, e o `docker ps` tem que
responder sem `sudo`):

```bash
id -nG && docker ps
```

> **Cuidado com sessões SSH aninhadas.** Se você deu `ssh` de dentro do
> servidor, o `exit` te devolve à sessão de fora em vez de encerrar — e você
> segue trabalhando com o grupo antigo achando que abriu sessão nova. Na dúvida,
> feche tudo e reconecte a partir da sua máquina.

## 3. Código e ambiente

O repositório é **privado**, então o servidor precisa de credencial para
cloná-lo. Use uma **deploy key**: um par de chaves que serve para *este*
repositório e só para leitura. É melhor que um token pessoal, que valeria para
todos os seus repositórios e ficaria no histórico do shell.

No servidor, gere a chave (sem passphrase, senão o `git pull` do deploy
travaria pedindo senha):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/deploy_prospector -N "" -C "deploy prospector" && cat ~/.ssh/deploy_prospector.pub
```

Copie a saída e cole em **GitHub → o repositório → Settings → Deploy keys →
Add deploy key**. Deixe "Allow write access" **desmarcado**: o servidor só lê.

Ensine o SSH a usar essa chave para o GitHub:

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/deploy_prospector\n  IdentitiesOnly yes\n' >> ~/.ssh/config
```

Confirme (a resposta esperada diz seu usuário e "does not provide shell
access" — isso é sucesso, não erro):

```bash
ssh -T git@github.com
```

Agora clone:

```bash
git clone git@github.com:matheuslivingstone33-cloud/saas.git prospector && cd prospector && cp .env.example .env
```

Edite o `.env`. Em produção, estas variáveis são **obrigatórias** (o compose de
produção recusa subir sem elas):

| Variável | O que é |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | credenciais do banco |
| `APP_SECRET` | assina o token de descadastro |
| `JWT_SECRET` | assina a sessão de login |
| `WEBHOOK_SECRET` | assina os webhooks de entrada (`/v1/inbound/*`) |
| `APP_ENV` | **`producao`** — é o que liga as travas abaixo |
| `URL_PUBLICA` | base do link de descadastro (`https://app.seudominio.com.br`) |
| `URL_API_PUBLICA` | base da API para o frontend (`https://api.seudominio.com.br`) |
| `ENCARREGADO_EMAIL` | contato do encarregado de dados (LGPD) |

Gere segredos fortes:

```bash
python3 -c "import secrets; [print(n + '=' + secrets.token_urlsafe(48)) for n in ('APP_SECRET','JWT_SECRET','WEBHOOK_SECRET')]"
```

> **Três travas que existem de propósito:**
>
> - com `APP_ENV=producao`, a aplicação **recusa subir** se o `JWT_SECRET`
>   estiver com o valor de desenvolvimento ou tiver menos de 32 caracteres.
>   Falhar no deploy é melhor do que subir deixando qualquer pessoa que leia
>   este repositório assinar um token válido para qualquer conta;
> - `WEBHOOK_SECRET` vazio **fecha** `/v1/inbound/*` em vez de abrir. Um webhook
>   que "funciona" porque ninguém configurou a chave aceitaria o mundo inteiro —
>   e desde a Etapa 7 uma resposta forjada não suja só a thread: ela move a mira
>   do aprendizado daquele cliente;
> - `SEED_ON_START=false` (já é o padrão do compose de produção) — **não rode o
>   seed em produção**: ele cria o usuário demo com senha publicada neste
>   repositório. A primeira conta nasce pelo cadastro, na própria tela.

## 4. Base de CNPJ da Receita (dado aberto, sem chave)

A amostra do repositório serve para desenvolvimento. Em produção, importe o
dump completo dos dados abertos da Receita Federal e aponte
`RECEITA_DATASET_PATH` para ele (`/app/data/receita/cnpj_full.csv`, no formato
`;` do `cnpj_sample.csv`).

Com o dump completo (dezenas de milhões de linhas), migre a busca para uma
tabela indexada no PostgreSQL em vez de carregar em memória — o `EnrichmentPort`
não muda, só a implementação por trás dele.

## 5. Subir

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

As migrations rodam sozinhas no start (`scripts/start-api.sh`). Se precisar
aplicá-las à mão:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

```bash
curl -s localhost:8000/health && curl -s localhost:8000/v1/providers
```

**Confira que a porta está fechada** — é o ponto inteiro da Etapa 8:

```bash
curl -s -o /dev/null -w "sem token: %{http_code}\n" localhost:8000/v1/leads
```

Tem que responder **401**. Se responder 200, pare o deploy e investigue antes
de apontar o domínio.

Backend e frontend só escutam em `127.0.0.1` — o acesso externo passa pelo proxy.

## 6. TLS e proxy reverso (Caddy)

```bash
sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```
app.seudominio.com.br {
    reverse_proxy 127.0.0.1:8080
}

api.seudominio.com.br {
    reverse_proxy 127.0.0.1:8000
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
    }
}
```

```bash
sudo systemctl reload caddy
```

O Caddy emite e renova o certificado sozinho. O link de descadastro precisa
funcionar em HTTPS público — é ele que sustenta o legítimo interesse.

> **Atenção ao SSE.** A execução ao vivo (`/v1/campaigns/{id}/run/stream`) é um
> fluxo que fica aberto. O Caddy não bufferiza e funciona direto; se você trocar
> por nginx, `proxy_buffering off;` é obrigatório — senão a tela fica parada até
> o fim da execução e parece travada.

## 7. Backup do banco

`/etc/cron.daily/prospector-backup`:

```bash
#!/bin/sh
cd /home/prospector/prospector
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U "$POSTGRES_USER" prospector | gzip > "backups/prospector-$(date +%F).sql.gz"
find backups -name 'prospector-*.sql.gz' -mtime +14 -delete
```

**Teste o restore.** Backup que nunca foi restaurado não é backup.

## 8. Tarefas agendadas

O expurgo por retenção (LGPD) precisa rodar diariamente:

```bash
docker compose -f docker-compose.prod.yml exec backend python -c "from app.workers.tasks import executar_retencao; print(executar_retencao())"
```

Coloque no cron diário, ou agende via RQ Scheduler no worker.

## 9. Operação

| Ação | Comando |
|---|---|
| Logs da API | `docker compose -f docker-compose.prod.yml logs -f backend` |
| Logs do worker | `docker compose -f docker-compose.prod.yml logs -f worker` |
| Estado dos provedores | `curl -s localhost:8000/v1/providers` |
| Margem consolidada | `curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/v1/margem/consolidado` |
| Integridade da auditoria | `curl -s localhost:8000/v1/audit/integridade` |
| Deploy de nova versão | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |

O `$TOKEN` sai do login:

```bash
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/entrar -H 'Content-Type: application/json' -d '{"email":"voce@dominio.com.br","senha":"SUA_SENHA"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["acesso"])')
```

Ele vale 30 minutos.

### O que monitorar

- `http_esgotou_tentativas` e circuito aberto nos logs → provedor instável;
- taxa de bounce/complaint do SES → risco de reputação de domínio;
- `margem_pct` por cliente → se cair, o preço do plano está errado;
- `/v1/audit/integridade` retornando `integra: false` → **incidente de segurança**;
- fila do RQ crescendo → worker travado ou volume acima do teto;
- 401 em massa nos logs → alguém tentando adivinhar senha, ou o relógio do
  servidor fora de hora (o JWT valida `exp` contra o relógio local).

## 10. Antes de abrir para clientes reais

- [x] ~~Autenticação real (JWT) no lugar do header `X-User-Email`~~ — Etapa 8.
- [x] ~~Webhook de entrada assinado~~ — Etapa 8 (HMAC-SHA256 + timestamp).
- [ ] **Recuperação de senha.** Não existe: quem esquecer só volta com um
      `UPDATE` no banco. Depende de e-mail real, então vem depois da Fase 7.
- [ ] **Limite de tentativas de login.** O bcrypt de custo 12 encarece a força
      bruta (~250 ms por tentativa), mas isso é mitigação, não defesa. O lugar
      mais simples é o `rate_limit` do Caddy.
- [ ] Papel de admin protegendo `/v1/margem/consolidado`.
- [ ] Webhook assinado do Stripe creditando (em vez de `/billing/confirmar`).
- [ ] SNS de bounce/complaint do SES alimentando `opt_outs`.
- [ ] Política de privacidade publicada na URL pública.
- [ ] Restore de backup testado.
- [ ] Limites de envio calibrados pelo warmup do domínio.
