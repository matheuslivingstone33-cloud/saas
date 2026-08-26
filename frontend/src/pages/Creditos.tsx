import { useEffect, useState } from "react";
import { api, type PlanoCatalogo, type Saldo } from "../lib/api";
import { Aviso, Badge, Botao, Card, Carregando, Stat, Vazio } from "../components/ui";
import { dataHora, moeda, numero, tokens } from "../lib/format";

type Vitrine = Awaited<ReturnType<typeof api.vitrine>>;
type Extrato = Awaited<ReturnType<typeof api.extrato>>;

/**
 * Creditos e a vitrine de tokens.
 *
 * A equivalencia mostrada e MEDIDA no consumo real do tenant sempre que existe
 * historico. Antes disso, dizemos que e estimativa — nunca fingimos precisao.
 */
export default function Creditos({ aoMudar }: { aoMudar: () => void }) {
  const [saldo, setSaldo] = useState<Saldo | null>(null);
  const [vitrine, setVitrine] = useState<Vitrine | null>(null);
  const [extrato, setExtrato] = useState<Extrato | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function carregar() {
    const [s, v, e] = await Promise.all([api.saldo(), api.vitrine(), api.extrato()]);
    setSaldo(s);
    setVitrine(v);
    setExtrato(e);
  }

  useEffect(() => {
    carregar().catch((e) => setErro(String(e)));
  }, []);

  async function acao(fn: () => Promise<string>) {
    setOcupado(true);
    setErro(null);
    setOk(null);
    try {
      setOk(await fn());
      await carregar();
      aoMudar();
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  const comprar = (codigo: string) =>
    acao(async () => {
      const { checkout, pacote } = await api.comprar(codigo);
      const r = await api.confirmarCompra(checkout.id, codigo);
      return `+${pacote.creditos} créditos (saldo: ${r.saldo}). Checkout mock: ${checkout.id}`;
    });

  const trocarPlano = (codigo: string) =>
    acao(async () => {
      const r = await api.trocarPlano(codigo);
      return `plano alterado de ${r.de} para ${r.para}. Saldo: ${r.saldo}`;
    });

  if (!saldo || !vitrine) return <Carregando />;

  return (
    <div className="space-y-6">
      {erro && <Aviso tom="erro">{erro}</Aviso>}
      {ok && <Aviso tom="sucesso">{ok}</Aviso>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          rotulo="Créditos disponíveis"
          valor={saldo.creditos}
          destaque={saldo.bloqueado ? "atencao" : "positivo"}
        />
        <Stat rotulo="Plano" valor={saldo.plano} />
        <Stat
          rotulo="Leads no mês"
          valor={`${saldo.leads_consumidos_mes}/${saldo.teto_leads_mes}`}
          nota={`${saldo.restante_no_teto} restantes`}
        />
        <Stat rotulo="Overage" valor={saldo.overage_habilitado ? "ligado" : "desligado"} />
      </div>

      {saldo.bloqueado && <Aviso tom="erro">Consumo bloqueado: {saldo.motivo_bloqueio}</Aviso>}

      <Card titulo="Planos — quanto de token cada um entrega">
        <p className="mb-4 text-sm text-texto-medio">{vitrine.observacao}</p>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {vitrine.planos.map((p) => (
            <PlanoCard
              key={p.codigo}
              plano={p}
              atual={p.codigo === saldo.plano}
              ocupado={ocupado}
              aoTrocar={() => trocarPlano(p.codigo)}
            />
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-4 text-xs text-texto-fraco">
          {Object.entries(vitrine.custo_em_creditos).map(([op, custo]) => (
            <span key={op}>
              {op.replace(/_/g, " ")}: <strong>{custo} crédito(s)</strong>
            </span>
          ))}
        </div>
      </Card>

      <Card titulo="Recarga avulsa">
        <div className="grid gap-4 md:grid-cols-3">
          {vitrine.pacotes_avulsos.map((p) => (
            <div key={p.codigo} className="rounded-lg border border-borda p-4">
              <div className="font-medium text-texto">{p.nome}</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums text-texto">
                {p.creditos}
                <span className="ml-1 text-sm font-normal text-texto-fraco">créditos</span>
              </div>
              <div className="text-sm text-texto-fraco">
                {moeda(p.preco_reais)} · {moeda(p.centavos_por_credito / 100)}/crédito
              </div>
              <div className="mt-3">
                <Botao tamanho="sm" onClick={() => comprar(p.codigo)} disabled={ocupado}>
                  comprar (mock)
                </Botao>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card titulo="Extrato">
        {!extrato || extrato.itens.length === 0 ? (
          <Vazio>Sem movimentação ainda.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-texto-fraco">
                <tr className="border-b border-borda">
                  <th className="py-2 pr-3">Quando</th>
                  <th className="py-2 pr-3">Tipo</th>
                  <th className="py-2 pr-3">Descrição</th>
                  <th className="py-2 pr-3 text-right">Créditos</th>
                  <th className="py-2 text-right">Saldo</th>
                </tr>
              </thead>
              <tbody>
                {extrato.itens.map((i) => (
                  <tr key={i.id} className="border-b border-borda">
                    <td className="py-2 pr-3 text-xs text-texto-fraco">
                      {dataHora(i.created_at)}
                    </td>
                    <td className="py-2 pr-3">
                      <Badge>{i.tipo}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-texto-medio">{i.descricao ?? "—"}</td>
                    <td
                      className={`py-2 pr-3 text-right tabular-nums ${
                        i.quantidade < 0 ? "text-perigo" : "text-positivo"
                      }`}
                    >
                      {i.quantidade > 0 ? "+" : ""}
                      {i.quantidade}
                    </td>
                    <td className="py-2 text-right tabular-nums text-texto-medio">{i.saldo_apos}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function PlanoCard({
  plano,
  atual,
  ocupado,
  aoTrocar,
}: {
  plano: PlanoCatalogo;
  atual: boolean;
  ocupado: boolean;
  aoTrocar: () => void;
}) {
  const eq = plano.equivalencia;
  return (
    <div
      className={`rounded-lg border p-4 ${
        atual ? "border-marca ring-1 ring-marca" : "border-borda"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-texto">{plano.nome}</span>
        {atual && <Badge tom="convertido">atual</Badge>}
      </div>
      <div className="mt-1 text-2xl font-semibold text-texto">
        {moeda(plano.preco_reais)}
        <span className="text-sm font-normal text-texto-fraco">/mês</span>
      </div>

      {eq && (
        <div className="mt-3 rounded-md bg-superficie-2 p-3 text-xs">
          <div className="font-medium text-texto-medio">{tokens(eq.tokens_mes)} tokens/mês</div>
          <div className="mt-0.5 text-texto-fraco">
            ≈ {numero(eq.leads_estimados)} leads · {numero(eq.tokens_por_lead)} tokens por lead
          </div>
          <div className="mt-1 text-[11px] text-texto-fraco">{eq.aviso}</div>
        </div>
      )}

      <ul className="mt-3 space-y-1 text-xs text-texto-medio">
        {plano.destaques.map((d) => (
          <li key={d}>· {d}</li>
        ))}
      </ul>

      {!atual && (
        <div className="mt-4">
          <Botao tamanho="sm" variante="secundario" onClick={aoTrocar} disabled={ocupado}>
            escolher este
          </Botao>
        </div>
      )}
    </div>
  );
}
