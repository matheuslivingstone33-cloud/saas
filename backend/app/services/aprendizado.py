"""Loop de aprendizado do Cerebro.

Ideia, sem misticismo: quando um lead chega a `respondido`/`convertido`, os
componentes que ele tinha altos eram bons preditores. Quando vira
`descartado`/`opt_out`, o contrario. Acumulamos a media de cada componente nos
dois grupos e deslocamos os pesos na direcao da diferenca — com amortecimento,
piso e teto, e sempre renormalizando.

Propriedades que importam para um produto:
  * **explicavel** — as estatisticas que geraram cada versao ficam gravadas;
  * **conservador** — precisa de um minimo de amostras e move pouco por vez;
  * **por tenant** — o que funciona para climatizacao nao vale para advocacia;
  * **reversivel** — `restaurar_padrao()` volta aos pesos globais.

O gancho de observacao e chamado pelo LeadService a cada transicao, entao o
loop funciona igual em mock e em producao.

Existem DOIS eixos de aprendizado, e eles aprendem coisas diferentes:

  * **componentes** (`ScoreWeights`) — quanto vale cada um dos seis componentes
    do score. Sinal: o desfecho do lead;
  * **ramo** (`RamoWeights`) — quanto vale cada CNAE para ESTE cliente. Sinal:
    a **intencao** da resposta, que chega semanas antes de qualquer desfecho.

O segundo e o fosso do produto: o peso do CNAE vem do Cerebro e e igual para
todo mundo. Se hotel nao responde para este prestador, so o historico dele
sabe disso — e historico nao se copia.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import StatusLead
from app.models.lead import RamoCnae
from app.models.learning import RamoWeights, ScoreWeights
from app.services.scoring import COMPONENTES, PESOS_PADRAO, Pesos

log = get_logger("aprendizado")

#: Resultados que contam como sinal positivo / negativo.
#:
#: `RESPONDIDO` esta FORA de proposito. Responder nao e sucesso: depende do que
#: a resposta diz. Como o lead passa por `respondido` a caminho de `opt_out`, um
#: "me tire da lista" gerava duas amostras contraditorias — primeiro ensinava
#: que a mira estava certa, logo depois que estava errada. Quem responde agora
#: ensina pela INTENCAO (`observar_intencao`), que sabe a diferenca.
SUCESSO = frozenset({StatusLead.CONVERTIDO})
FRACASSO = frozenset({StatusLead.DESCARTADO, StatusLead.OPT_OUT})

#: Guardas para o ajuste nao sair do controle.
MINIMO_AMOSTRAS = 20
MINIMO_POR_GRUPO = 5
TAXA_APRENDIZADO = 0.15
PESO_MINIMO = 0.02
PESO_MAXIMO = 0.60

#: Quanto cada intencao vale como sinal, em [-1, 1]. Nao e uma escala de
#: educacao — e de MIRA: o que se pergunta a cada resposta e "o ramo estava
#: certo?", nao "o lead gostou?".
#:
#:   * `objecao` e POSITIVA de proposito. "Esta caro" e "agora nao e o momento"
#:     dizem que o ramo compra esse servico e o momento estava errado; ensinar
#:     o Cerebro a fugir desse ramo seria trocar a mira certa por silencio.
#:   * `recusa` e so levemente negativa pelo mesmo motivo — "ja temos
#:     fornecedor" e a frase de quem consome o servico, nao de quem nao precisa.
#:   * `pedido_opt_out` e o unico -1: irritar a ponto de a pessoa pedir para
#:     sair da lista e o sinal mais forte de que o alvo estava errado.
#:   * `ausencia` vale 0 — resposta de ferias nao e resposta, e ja e tratada
#:     assim pelo Motor 4.
VALOR_POR_INTENCAO: dict[str, float] = {
    "interesse": 1.0,
    "duvida": 0.5,
    "pedido_humano": 0.5,
    "objecao": 0.3,
    "recusa": -0.3,
    "pedido_opt_out": -1.0,
    "ausencia": 0.0,
    "indefinida": 0.0,
}

#: Guardas do eixo de ramo. O fator e MULTIPLICADOR do peso do Cerebro.
MINIMO_AMOSTRAS_RAMO = 20
FATOR_MINIMO = 0.5
FATOR_MAXIMO = 1.5
FATOR_PADRAO = 1.0


@dataclass(slots=True)
class Ajuste:
    aplicado: bool
    motivo: str
    versao: int
    pesos: dict[str, float]
    amostras: int
    delta: dict[str, float] | None = None

    def to_dict(self) -> dict:
        return {
            "aplicado": self.aplicado,
            "motivo": self.motivo,
            "versao": self.versao,
            "pesos": self.pesos,
            "amostras": self.amostras,
            "delta": self.delta,
        }


@dataclass(slots=True)
class AjusteRamos:
    """Resultado de um passo do aprendizado por ramo."""

    aplicado: bool
    motivo: str
    ramos: list[dict]

    def to_dict(self) -> dict:
        return {"aplicado": self.aplicado, "motivo": self.motivo, "ramos": self.ramos}


def _acumulador() -> dict:
    return {c: {"sucesso": {"n": 0, "soma": 0.0}, "fracasso": {"n": 0, "soma": 0.0}}
            for c in COMPONENTES}


class LoopAprendizado:
    """Interface do loop. A Fase 1 entrega o ciclo completo em modo offline."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- leitura --------------------------------------------------------------
    def pesos_de(self, user_id: uuid.UUID | None) -> Pesos:
        registro = self._registro(user_id)
        if registro is None and user_id is not None:
            registro = self._registro(None)  # cai nos pesos globais
        return Pesos.from_dict(registro.pesos) if registro else PESOS_PADRAO

    def estado(self, user_id: uuid.UUID | None) -> dict:
        registro = self._registro(user_id)
        if registro is None:
            # `estatisticas` vazio, e nao ausente: a forma da resposta nao pode
            # mudar conforme o tenant ja ter aprendido alguma coisa ou nao —
            # quem consome quebraria exatamente no cliente novo.
            return {
                "versao": 0,
                "amostras": 0,
                "pesos": PESOS_PADRAO.to_dict(),
                "origem": "padrao_global",
                "estatisticas": _acumulador(),
                "mira": self.mira(user_id),
            }
        return {
            "versao": registro.versao,
            "amostras": registro.amostras,
            "pesos": registro.pesos,
            "origem": "tenant" if registro.user_id else "global",
            "estatisticas": registro.estatisticas,
            "mira": self.mira(user_id),
        }

    # -- escrita --------------------------------------------------------------
    def observar(
        self,
        *,
        user_id: uuid.UUID,
        resultado: StatusLead,
        componentes: dict[str, float] | None,
    ) -> bool:
        """Registra o desfecho de um lead. Devolve True se o sinal foi contado."""
        if resultado in SUCESSO:
            grupo = "sucesso"
        elif resultado in FRACASSO:
            grupo = "fracasso"
        else:
            return False
        return self._creditar(user_id, grupo, componentes)

    def _creditar(
        self, user_id: uuid.UUID, grupo: str, componentes: dict[str, float] | None
    ) -> bool:
        """Soma um lead ao balde de sucesso ou de fracasso deste tenant."""
        if not componentes:
            return False
        registro = self._ou_cria(user_id)
        # deepcopy proposital: colunas JSON nao rastreiam mutacao aninhada. Se
        # mutassemos o dict carregado, o SQLAlchemy compararia o valor antigo
        # com ele mesmo, concluiria "nada mudou" e nao gravaria o UPDATE.
        stats = {**_acumulador(), **copy.deepcopy(registro.estatisticas or {})}
        for componente in COMPONENTES:
            valor = componentes.get(componente)
            if valor is None:
                continue
            bucket = stats.setdefault(
                componente, {"sucesso": {"n": 0, "soma": 0.0}, "fracasso": {"n": 0, "soma": 0.0}}
            )[grupo]
            bucket["n"] = int(bucket.get("n", 0)) + 1
            bucket["soma"] = float(bucket.get("soma", 0.0)) + float(valor)

        registro.estatisticas = stats
        registro.amostras += 1
        self.session.flush()
        return True

    def recalcular(self, user_id: uuid.UUID) -> Ajuste:
        """Aplica um passo de ajuste, se houver amostra suficiente."""
        registro = self._ou_cria(user_id)
        stats = registro.estatisticas or {}
        atuais = Pesos.from_dict(registro.pesos)

        n_sucesso = max(
            (stats.get(c, {}).get("sucesso", {}).get("n", 0) for c in COMPONENTES), default=0
        )
        n_fracasso = max(
            (stats.get(c, {}).get("fracasso", {}).get("n", 0) for c in COMPONENTES), default=0
        )
        if registro.amostras < MINIMO_AMOSTRAS:
            return Ajuste(
                False,
                f"amostras insuficientes ({registro.amostras}/{MINIMO_AMOSTRAS})",
                registro.versao,
                atuais.to_dict(),
                registro.amostras,
            )
        if n_sucesso < MINIMO_POR_GRUPO or n_fracasso < MINIMO_POR_GRUPO:
            return Ajuste(
                False,
                f"grupos desbalanceados (sucesso={n_sucesso}, fracasso={n_fracasso})",
                registro.versao,
                atuais.to_dict(),
                registro.amostras,
            )

        brutos: dict[str, float] = {}
        delta: dict[str, float] = {}
        for componente in COMPONENTES:
            s = stats.get(componente, {}).get("sucesso", {})
            f = stats.get(componente, {}).get("fracasso", {})
            media_s = (s.get("soma", 0.0) / s["n"]) if s.get("n") else 0.0
            media_f = (f.get("soma", 0.0) / f["n"]) if f.get("n") else 0.0
            diferenca = media_s - media_f  # em [-1, 1]
            atual = getattr(atuais, componente)
            novo = atual * (1 + TAXA_APRENDIZADO * diferenca)
            novo = min(PESO_MAXIMO, max(PESO_MINIMO, novo))
            brutos[componente] = novo
            delta[componente] = round(novo - atual, 6)

        novos = Pesos(**brutos).normalizados()
        registro.pesos = novos.to_dict()
        registro.versao += 1
        self.session.flush()
        log.info(
            "pesos_ajustados",
            user_id=str(user_id),
            versao=registro.versao,
            amostras=registro.amostras,
            pesos=registro.pesos,
        )
        return Ajuste(
            True,
            "ajuste aplicado",
            registro.versao,
            registro.pesos,
            registro.amostras,
            delta,
        )

    def restaurar_padrao(self, user_id: uuid.UUID) -> Ajuste:
        """Volta os DOIS eixos ao ponto de partida.

        Restaurar so os componentes deixaria a mira por ramo de pe e daria a
        impressao de que o aprendizado foi desfeito quando nao foi — o pior dos
        dois mundos para quem clicou justamente por desconfiar do resultado.
        """
        registro = self._ou_cria(user_id)
        registro.pesos = PESOS_PADRAO.to_dict()
        registro.estatisticas = _acumulador()
        registro.amostras = 0
        registro.versao += 1
        for ramo in self.session.execute(
            select(RamoWeights).where(RamoWeights.user_id == user_id)
        ).scalars():
            self.session.delete(ramo)
        self.session.flush()
        return Ajuste(True, "restaurado para o padrao", registro.versao, registro.pesos, 0)

    # -- aprendizado por ramo (sinal de intencao) -----------------------------
    def observar_intencao(
        self,
        *,
        user_id: uuid.UUID,
        intencao: str,
        cnae: str | None,
        componentes: dict[str, float] | None = None,
    ) -> bool:
        """Registra o que a resposta de um lead ensinou. True se contou.

        Alimenta os DOIS eixos com o mesmo evento: o ramo (sempre) e os
        componentes do score (quando o sinal tem direcao). E o unico lugar que
        credita o sinal daquela resposta — as transicoes que o Motor 4 dispara
        em seguida passam `aprender=False` para nao contar o mesmo fato duas
        vezes.
        """
        valor = VALOR_POR_INTENCAO.get(str(intencao), 0.0)
        contou = False

        if cnae:
            registro = self._ramo(user_id, str(cnae))
            registro.amostras += 1
            registro.soma += valor
            contagem = dict(registro.intencoes or {})
            contagem[str(intencao)] = int(contagem.get(str(intencao), 0)) + 1
            registro.intencoes = contagem
            self.session.flush()
            contou = True

        # `ausencia` e `indefinida` valem 0: nao dizem nada sobre a mira e nao
        # podem empurrar peso nenhum. Contam como amostra do ramo (a pessoa
        # existe e o e-mail chegou), mas nao votam.
        if valor > 0:
            contou = self._creditar(user_id, "sucesso", componentes) or contou
        elif valor < 0:
            contou = self._creditar(user_id, "fracasso", componentes) or contou
        return contou

    def fatores_de_ramo(self, user_id: uuid.UUID | None) -> dict[str, float]:
        """Multiplicadores vigentes por CNAE. Ausente = 1.0 (o padrao)."""
        if user_id is None:
            return {}
        linhas = self.session.execute(
            select(RamoWeights).where(RamoWeights.user_id == user_id)
        ).scalars()
        return {r.cnae: float(r.fator) for r in linhas}

    def mira(self, user_id: uuid.UUID | None) -> list[dict]:
        """O que o cliente aprendeu sobre cada ramo — para a tela.

        Aprendizado invisivel e o mesmo que superticao: se o sistema para de
        mostrar hoteis, alguem tem que conseguir ver que foi decisao, e por que.
        """
        if user_id is None:
            return []
        linhas = list(
            self.session.execute(
                select(RamoWeights).where(RamoWeights.user_id == user_id)
            ).scalars()
        )
        # O codigo cru nao diz nada a ninguem: "5510801" nao e "Hoteis". Sem a
        # descricao a tela mostraria numeros que o usuario nao consegue julgar —
        # que e o mesmo que nao mostrar.
        descricoes: dict[str, str] = {}
        if linhas:
            descricoes = dict(
                self.session.execute(
                    select(RamoCnae.codigo, RamoCnae.descricao).where(
                        RamoCnae.codigo.in_([r.cnae for r in linhas])
                    )
                ).all()
            )
        ramos = [
            {
                "cnae": r.cnae,
                "descricao": descricoes.get(r.cnae, ""),
                "fator": round(float(r.fator), 4),
                "amostras": r.amostras,
                "media_sinal": round(r.soma / r.amostras, 4) if r.amostras else 0.0,
                "versao": r.versao,
                "intencoes": dict(r.intencoes or {}),
                "faltam_amostras": max(0, MINIMO_AMOSTRAS_RAMO - r.amostras),
            }
            for r in linhas
        ]
        ramos.sort(key=lambda r: (-r["fator"], r["cnae"]))
        return ramos

    def recalcular_ramos(self, user_id: uuid.UUID) -> AjusteRamos:
        """Um passo do ajuste por ramo. Mesmas guardas do eixo de componentes."""
        linhas = list(
            self.session.execute(
                select(RamoWeights).where(RamoWeights.user_id == user_id)
            ).scalars()
        )
        if not linhas:
            return AjusteRamos(False, "nenhuma resposta registrada por ramo ainda", [])

        movidos: list[dict] = []
        for registro in linhas:
            if registro.amostras < MINIMO_AMOSTRAS_RAMO:
                continue
            media = registro.soma / registro.amostras  # em [-1, 1]
            anterior = float(registro.fator)
            novo = anterior * (1 + TAXA_APRENDIZADO * media)
            novo = min(FATOR_MAXIMO, max(FATOR_MINIMO, novo))
            if abs(novo - anterior) < 1e-9:
                continue
            registro.fator = novo
            registro.versao += 1
            movidos.append(
                {
                    "cnae": registro.cnae,
                    "de": round(anterior, 4),
                    "para": round(novo, 4),
                    "amostras": registro.amostras,
                    "media_sinal": round(media, 4),
                }
            )
        self.session.flush()
        if not movidos:
            return AjusteRamos(
                False,
                f"nenhum ramo com {MINIMO_AMOSTRAS_RAMO} respostas ainda",
                [],
            )
        log.info("ramos_ajustados", user_id=str(user_id), ramos=movidos)
        return AjusteRamos(True, "mira ajustada por ramo", movidos)

    # -- internos -------------------------------------------------------------
    def _ramo(self, user_id: uuid.UUID, cnae: str) -> RamoWeights:
        registro = self.session.execute(
            select(RamoWeights).where(
                RamoWeights.user_id == user_id, RamoWeights.cnae == cnae
            )
        ).scalar_one_or_none()
        if registro is None:
            registro = RamoWeights(
                user_id=user_id,
                cnae=cnae,
                fator=FATOR_PADRAO,
                amostras=0,
                soma=0.0,
                versao=1,
                intencoes={},
            )
            self.session.add(registro)
            self.session.flush()
        return registro

    def _registro(self, user_id: uuid.UUID | None) -> ScoreWeights | None:
        return self.session.execute(
            select(ScoreWeights).where(ScoreWeights.user_id == user_id)
        ).scalar_one_or_none()

    def _ou_cria(self, user_id: uuid.UUID | None) -> ScoreWeights:
        registro = self._registro(user_id)
        if registro is None:
            registro = ScoreWeights(
                user_id=user_id,
                pesos=PESOS_PADRAO.to_dict(),
                versao=1,
                amostras=0,
                estatisticas=_acumulador(),
            )
            self.session.add(registro)
            self.session.flush()
        return registro
