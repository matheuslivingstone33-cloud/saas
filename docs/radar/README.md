# docs/radar — como as rotinas conversam

Cada rotina agendada escreve **só no próprio arquivo** e **lê todos os outros**
antes de agir. Escrita isolada, leitura compartilhada: é o que deixa elas
conversarem sem uma desfazer a outra.

| Arquivo | Rotina dona |
|---|---|
| `descoberta.md` | Descoberta e Cérebro |
| `envio.md` | Envio e Entregabilidade |
| `conversa.md` | Conversa e Cadência |
| `custo.md` | Custo, Crédito e Margem |
| `compliance.md` | Compliance e Jurídico |
| `deploy.md` | Preparação para Colocar no Ar (mantém também `docs/COLOCAR-NO-AR.md`) |

A Consolidação não tem radar: ela lê todos e mantém o `HANDOFF.md`.

## Regra que custou caro

Estes arquivos só servem se estiverem **na versão principal**. De 12 a 15/09
cada execução rodou numa cópia separada, escreveu o radar ali, e a execução
seguinte partiu do `main` antigo sem ver nada — a mesma correção foi feita
quatro vezes. Toda rotina que muda arquivo precisa partir de `origin/main` e
integrar de volta no `main` ao terminar.

## Formato de cada entrada

Datada, com três partes: **o que corrigi** (com teste), **o que achei e não
corrigi**, e **o que depende de outra rotina ou de decisão humana**.
