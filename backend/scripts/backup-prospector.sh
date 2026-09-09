#!/bin/sh
# Backup diario do Postgres de producao.
#
# Roda pelo cron do usuario `prospector`, que esta no grupo `docker`. O cron
# nasce com um ambiente quase vazio (sem PATH util, sem as variaveis do .env),
# entao tudo o que o script precisa e resolvido aqui dentro.
set -eu

RAIZ="/home/prospector/prospector"
DESTINO="$RAIZ/backups"
COMPOSE="docker compose -f $RAIZ/docker-compose.prod.yml"
PATH="/usr/local/bin:/usr/bin:/bin"
export PATH

cd "$RAIZ"

# O usuario do banco vive no .env; ler de la evita duplicar a configuracao.
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2-)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2-)
: "${POSTGRES_USER:?POSTGRES_USER ausente no .env}"
: "${POSTGRES_DB:=prospector}"

mkdir -p "$DESTINO"
ARQUIVO="$DESTINO/prospector-$(date +%F-%H%M).sql.gz"

# Escreve num temporario e so entao renomeia: um dump interrompido no meio nao
# pode ocupar o lugar de um backup bom com nome de backup bom.
$COMPOSE exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$ARQUIVO.parcial"
mv "$ARQUIVO.parcial" "$ARQUIVO"

# Um dump vazio ou minusculo e sintoma de falha silenciosa, nao de banco pequeno:
# ate um banco recem-criado passa de 1 KB por causa do schema.
TAMANHO=$(stat -c%s "$ARQUIVO")
if [ "$TAMANHO" -lt 1024 ]; then
    echo "ERRO: backup de apenas $TAMANHO bytes em $ARQUIVO" >&2
    exit 1
fi

find "$DESTINO" -name 'prospector-*.sql.gz' -mtime +14 -delete
find "$DESTINO" -name '*.parcial' -mtime +1 -delete
echo "backup ok: $ARQUIVO ($TAMANHO bytes)"
