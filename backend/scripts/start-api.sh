#!/bin/sh
set -e
echo "[start-api] aguardando banco e aplicando migrations..."
alembic upgrade head

# Catalogo de ramos (base do Cerebro): roda SEMPRE, com ou sem seed. Ele NAO e
# dado de demonstracao — e o que diz "quem consome o servico". Antes so vinha
# junto com o seed, e producao roda com SEED_ON_START=false: a API subia
# healthy, o cadastro funcionava, e toda busca expandia para ZERO ramos, sem
# erro em lugar nenhum. Idempotente: so acrescenta o que falta.
#
# Catalogo vazio derruba a subida de proposito (o container fica `restarting`
# e o log diz o motivo): e melhor parar no deploy do que abrir para cliente um
# produto que nao acha ninguem.
echo "[start-api] carregando o catalogo de ramos..."
python - <<'PY'
import sys

from sqlalchemy import func, select

from app.db.seed import carregar_catalogo
from app.db.session import session_scope
from app.models.lead import RamoCnae

with session_scope() as s:
    novos = carregar_catalogo(s)
    total = s.execute(select(func.count()).select_from(RamoCnae)).scalar_one()
print(f"[start-api] catalogo de ramos: {total} no banco ({novos} acrescentados agora)")
if total == 0:
    print(
        "[start-api] ERRO: catalogo de ramos vazio. Confira se data/cnae/cnaes_b2b.json "
        "existe no servidor (o compose monta ./data em /app/data).",
        file=sys.stderr,
    )
    sys.exit(1)
PY

if [ "${SEED_ON_START:-true}" = "true" ]; then
  echo "[start-api] populando seed..."
  python -m app.db.seed
fi
echo "[start-api] subindo API em 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
