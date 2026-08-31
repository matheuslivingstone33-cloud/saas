import { useEffect, useState } from "react";
import {
  api,
  type Dashboard,
  type EstadoAprendizado,
  type Provedores,
  type RamoAprendido,
} from "../lib/api";

type Margem = Awaited<ReturnType<typeof api.margem>>;
import { Aviso, Badge, Card, Carregando, Stat } from "../components/ui";
import { numero } from "../lib/format";

/** Painel de KPIs: funil, entregas, custo nos dois baldes e consumo por lead. */
export default function Painel() {
  const [dados, setDados] = useState<Dashboard | null>(null);
  const [provedores, setProvedores] = useState<Provedores>({});
  const [margem, setMargem] = useState<Margem | null>(null);
  const [aprendizado, setAprendizado] = useState<EstadoAprendizado | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.dashboard(), api.provedores(), api.margem(), api.pesos()])
      .then(([d, p, m, a]) => {
        setDados(d);
        setProvedores(p.provedores);
        setMargem(m);
        setAprendizado(a);
      })
      .catch((e) => setErro(String(e)));
  }, []);

  if (erro) return <Aviso tom="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  const f = dados.funil;
  const etapas = [
    { rotulo: "Descobertos", valor: f.descobertos },
    { rotulo: "Qualificados", valor: f.qualificados },
    { rotulo: "Abordados", valor: f.abordados },
    { rotulo: "Responderam", valor: f.respondidos },
    { rotulo: "Converteram", valor: f.convertidos },
  ];
  const maximo = Math.max(1, ...etapas.map((e) => e.valor));

  return (
    <div className="space-y-6">
      {dados.saldo.bloqueado && (
        <Aviso tom="erro">
          Consumo bloqueado: {dados.saldo.motivo_bloqueio}. Recarregue em{" "}
          <a className="underline" href="#/creditos">
            Créditos
          </a>
          .
        </Aviso>
      )}
      {dados.saldo.alertas.map((a) => (
        <Aviso key={a} tom="atencao">
          {a}
        </Aviso>
      ))}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat rotulo="Campanhas" valor={dados.campanhas} />
        <Stat rotulo="Leads descobertos" valor={f.descobertos} nota={`${f.opt_outs} opt-outs`} />
        <Stat
          rotulo="Abordados"
          valor={f.abordados}
          nota={`taxa de resposta ${dados.taxas.resposta}%`}
        />
        <Stat
          rotulo="Créditos"
          valor={dados.saldo.creditos}
          nota={`${dados.saldo.restante_no_teto} no teto do plano`}
          destaque={dados.saldo.bloqueado ? "atencao" : "positivo"}
        />
      </div>

      <Card titulo="Funil">
        <div className="space-y-2">
          {etapas.map((e) => (
            <div key={e.rotulo} className="flex items-center gap-3">
              <span className="w-28 shrink-0 text-sm text-texto-medio">{e.rotulo}</span>
              <div className="h-6 flex-1 overflow-hidden rounded bg-superficie-3">
                <div
                  className="flex h-full items-center justify-end bg-marca px-2 text-xs font-medium text-white"
                  style={{ width: `${Math.max(4, (e.valor / maximo) * 100)}%` }}
                >
                  {e.valor}
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3 text-center text-xs text-texto-fraco">
          <div>
            qualificação <strong className="text-texto">{dados.taxas.qualificacao}%</strong>
          </div>
          <div>
            resposta <strong className="text-texto">{dados.taxas.resposta}%</strong>
          </div>
          <div>
            conversão <strong className="text-texto">{dados.taxas.conversao}%</strong>
          </div>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card titulo="Custo — dois baldes que nunca se misturam">
          <div className="grid grid-cols-2 gap-3">
            <Stat
              rotulo="Balde 1 — Dados"
              valor={`US$ ${dados.custo.balde_1_dados.usd.toFixed(4)}`}
              nota={`${dados.custo.balde_1_dados.eventos} chamadas (Places, Receita, e-mail)`}
            />
            <Stat
              rotulo="Balde 2 — IA"
              valor={`US$ ${dados.custo.balde_2_ia.usd.toFixed(4)}`}
              nota={`${dados.custo.balde_2_ia.eventos} chamadas (LLM, busca)`}
            />
          </div>
          <p className="mt-3 text-xs text-texto-fraco">
            Custo médio por lead:{" "}
            <strong>
              US$ {(dados.consumo.custo_medio_lead_micros / 1_000_000).toFixed(5)}
            </strong>{" "}
            · {numero(dados.consumo.tokens_por_lead)} tokens/lead (
            {dados.consumo.base === "medido"
              ? `medido em ${dados.consumo.amostra_leads} leads`
              : "estimativa inicial"}
            )
          </p>
        </Card>

        <Card titulo="Mensagens">
          <div className="grid grid-cols-2 gap-3">
            <Stat rotulo="Aguardando aprovação" valor={dados.mensagens.aguardando_aprovacao} />
            <Stat rotulo="Enviadas" valor={dados.mensagens.enviadas} destaque="positivo" />
            <Stat rotulo="Bloqueadas" valor={dados.mensagens.bloqueadas} />
            <Stat rotulo="Falhas" valor={dados.mensagens.falhas} />
          </div>
        </Card>
      </div>

      {margem && (
        <Card titulo="Margem — receita menos os dois baldes">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat rotulo="Receita reconhecida" valor={`R$ ${margem.receita_brl.toFixed(2)}`} nota={`${margem.creditos_consumidos} creditos consumidos`} />
            <Stat rotulo="Custo total" valor={`R$ ${margem.custo.total_brl.toFixed(2)}`} nota={`US$ ${margem.custo.total_usd.toFixed(4)} @ ${margem.taxa_usd_brl}`} />
            <Stat
              rotulo="Margem"
              valor={`R$ ${margem.margem_brl.toFixed(2)}`}
              nota={`${margem.margem_pct.toFixed(1)}%`}
              destaque={margem.margem_brl >= 0 ? "positivo" : "atencao"}
            />
            <Stat
              rotulo="Por lead"
              valor={`R$ ${margem.por_lead.margem_brl.toFixed(3)}`}
              nota={`custo R$ ${margem.por_lead.custo_brl.toFixed(3)} · receita R$ ${margem.por_lead.receita_brl.toFixed(3)}`}
              destaque={margem.por_lead.margem_brl >= 0 ? "positivo" : "atencao"}
            />
          </div>
          {margem.receita_brl === 0 && (
            <p className="mt-3 text-xs text-texto-fraco">
              No plano de teste a receita e zero e o custo e real: essa margem negativa e o
              custo de aquisicao, nao prejuizo operacional.
            </p>
          )}
        </Card>
      )}

      {aprendizado && <Mira estado={aprendizado} />}

      <Card titulo="Provedores">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Object.entries(provedores).map(([nome, p]) => (
            <div key={nome} className="rounded-lg border border-borda p-3">
              <div className="text-sm font-medium text-texto">{nome}</div>
              <div className="mt-1 flex items-center gap-2">
                <Badge tom={p.modo}>{p.modo}</Badge>
                <span className="text-xs text-texto-fraco">
                  {p.rede_habilitada ? "rede on" : "rede off"}
                </span>
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-texto-fraco">
          Tudo em <strong>mock</strong>: nenhuma chave, nenhuma requisição real. A virada para
          produção é feita um provedor por vez na Fase 7.
        </p>
      </Card>
    </div>
  );
}


/**
 * A mira aprendida por ramo (Etapa 7).
 *
 * Esta tela existe por um motivo especifico: o sistema passou a inclinar a
 * busca com base nas respostas que cada cliente recebe. Se ele deixa de trazer
 * hoteis, a UNICA evidencia seria a ausencia de hoteis na lista — e ausencia
 * nao aparece em lugar nenhum. Aprendizado invisivel e indistinguivel de
 * supersticao, entao ele fica aqui, com o numero de respostas que o produziu.
 */
function Mira({ estado }: { estado: EstadoAprendizado }) {
  const ramos = estado.mira;

  return (
    <Card titulo="A mira — o que as respostas ensinaram">
      {ramos.length === 0 ? (
        <p className="text-sm text-texto-medio">
          Nenhuma resposta registrada ainda. Conforme os leads respondem, cada ramo ganha um
          fator próprio <strong>para a sua empresa</strong>: quem responde sobe, quem pede
          descadastro desce. Os ramos vêm do Cérebro e valem para todo mundo; isto é o que só o
          seu histórico sabe.
        </p>
      ) : (
        <>
          <div className="space-y-3">
            {ramos.map((r) => (
              <LinhaDoRamo key={r.cnae} ramo={r} />
            ))}
          </div>
          <p className="mt-4 text-xs text-texto-fraco">
            O fator multiplica o peso do Cérebro e anda entre 0,5 e 1,5 — ele inclina a busca,
            nunca apaga um ramo. São necessárias 20 respostas de um ramo antes do primeiro
            ajuste: com três, o que parece padrão ainda é acaso.
          </p>
        </>
      )}
    </Card>
  );
}

function LinhaDoRamo({ ramo }: { ramo: RamoAprendido }) {
  const acima = ramo.fator > 1.001;
  const abaixo = ramo.fator < 0.999;
  const rotulo = acima ? "mira reforçada" : abaixo ? "mira reduzida" : "sem ajuste ainda";
  const cor = acima ? "text-positivo" : abaixo ? "text-atencao" : "text-texto-fraco";
  // 0,5 -> 0% e 1,5 -> 100%: o centro da barra e o peso original do Cerebro.
  const posicao = Math.min(100, Math.max(0, ((ramo.fator - 0.5) / 1.0) * 100));

  return (
    <div className="rounded-xl border border-borda p-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-texto">
          {ramo.descricao || `CNAE ${ramo.cnae}`}
        </span>
        <span className={`shrink-0 text-sm font-semibold ${cor}`}>
          {ramo.fator.toFixed(2)}×
        </span>
      </div>
      <div className="relative mt-2 h-1.5 overflow-hidden rounded bg-superficie-3">
        <div className="absolute left-1/2 top-0 h-full w-px bg-borda-forte" />
        <div
          className={`h-full rounded ${acima ? "bg-positivo" : abaixo ? "bg-atencao" : "bg-borda-forte"}`}
          style={{ width: `${Math.max(2, posicao)}%` }}
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-texto-fraco">
        <span className={cor}>{rotulo}</span>
        <span>
          {ramo.amostras} {ramo.amostras === 1 ? "resposta" : "respostas"}
        </span>
        {ramo.faltam_amostras > 0 && (
          <span>faltam {ramo.faltam_amostras} para o próximo ajuste</span>
        )}
        {Object.entries(ramo.intencoes).map(([intencao, n]) => (
          <span key={intencao} className="rounded bg-superficie-3 px-1.5 py-0.5">
            {intencao.replace(/_/g, " ")} {n}
          </span>
        ))}
      </div>
    </div>
  );
}
