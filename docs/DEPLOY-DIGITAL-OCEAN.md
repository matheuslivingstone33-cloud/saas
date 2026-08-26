# Deploy — Digital Ocean

Guia do zero até o sistema no ar. Assume um droplet Ubuntu 24.04 (2 vCPU / 4 GB
é o mínimo confortável) e um domínio apontando para ele.

> O sistema sobe em **modo mock** e continua funcionando assim. As chaves entram
> depois, **uma por vez**, seguindo o [runbook da Fase 7](RUNBOOK-FASE7.md).

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

## 2. Docker

```bash
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER && newgrp docker
```

## 3. Código e ambiente

```bash
git clone SEU_REPO prospector && cd prospector && cp .env.example .env
```

Edite o `.env`. Em produção, estas variáveis são **obrigatórias** (o compose de
produção recusa subir sem elas):

| Variável | O que é |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | credenciais do banco |
| `APP_SECRET` | assina o token de descadastro |
| `JWT_SECRET` | assina a sessão |
| `URL_PUBLICA` | base do link de descadastro (`https://app.seudominio.com.br`) |
| `URL_API_PUBLICA` | base da API para o frontend (`https://api.seudominio.com.br`) |
| `ENCARREGADO_EMAIL` | contato do encarregado de dados (LGPD) |

Gere segredos fortes:

```bash
python3 -c "import secrets; print('APP_SECRET=' + secrets.token_urlsafe(48)); print('JWT_SECRET=' + secrets.token_urlsafe(48))"
```

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

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

```bash
curl -s localhost:8000/health && curl -s localhost:8000/v1/providers
```

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
| Margem consolidada | `curl -s -H "X-User-Email: ..." localhost:8000/v1/margem/consolidado` |
| Integridade da auditoria | `curl -s localhost:8000/v1/audit/integridade` |
| Deploy de nova versão | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |

### O que monitorar

- `http_esgotou_tentativas` e circuito aberto nos logs → provedor instável;
- taxa de bounce/complaint do SES → risco de reputação de domínio;
- `margem_pct` por cliente → se cair, o preço do plano está errado;
- `/v1/audit/integridade` retornando `integra: false` → **incidente de segurança**;
- fila do RQ crescendo → worker travado ou volume acima do teto.

## 10. Antes de abrir para clientes reais

- [ ] Autenticação real (JWT) no lugar do header `X-User-Email` de desenvolvimento.
- [ ] Papel de admin protegendo `/v1/margem/consolidado`.
- [ ] Webhook assinado do Stripe creditando (em vez de `/billing/confirmar`).
- [ ] SNS de bounce/complaint do SES alimentando `opt_outs`.
- [ ] Política de privacidade publicada na URL pública.
- [ ] Restore de backup testado.
- [ ] Limites de envio calibrados pelo warmup do domínio.
