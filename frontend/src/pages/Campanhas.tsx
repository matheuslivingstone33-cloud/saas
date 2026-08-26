import { useEffect, useState } from "react";
import {
  api,
  type Campanha,
  type Lead,
  type Limites,
  type Mensagem,
  type ResultadoExecucao,
} from "../lib/api";
import { Aviso, Badge, BarraScore, Botao, Campo, Card, Vazio } from "../components/ui";

/**
 * Campanhas: criar, rodar, revisar leads com score explicavel e
 * aprovar/disparar mensagens (modo assistido) ou apenas acompanhar (automatico).
 */
export default function Campanhas({ nivel }: { nivel: string }) {
  const [campanhas, setCampanhas] = useState<Campanha[]>([]);
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [limites, setLimites] = useState<Limites | null>(null);
  const [resultado, setResultado] = useState<ResultadoExecucao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [criando, setCriando] = useState(false);
  const [detalhe, setDetalhe] = useState<Lead | null>(null);

  const [nome, setNome] = useState("");
  const [servico, setServico] = useState("");
  const [regiao, setRegiao] = useState("Fortaleza, CE");

  async function carregarLista() {
    const lista = await api.campanhas();
    setCampanhas(lista.itens);
    if (!selecionada && lista.itens[0]) setSelecionada(lista.itens[0].id);
  }

  async function carregarDetalhe(id: string) {
    const [l, m, lim] = await Promise.all([api.leads(id), api.mensagens(id), api.limites(id)]);
    setLeads(l.itens);
    setMensagens(m.itens);
    setLimites(lim);
  }

  useEffect(() => {
    carregarLista().catch((e) => setErro(String(e)));
  }, []);

  useEffect(() => {
    if (selecionada) carregarDetalhe(selecionada).catch((e) => setErro(String(e)));
  }, [selecionada]);

  async function executar() {
    if (!selecionada) return;
    setOcupado(true);
    setErro(null);
    try {
      const campanha = campanhas.find((c) => c.id === selecionada);
      if (campanha && ["concluida", "executando"].includes(campanha.status)) {
        await api.reabrir(selecionada).catch(() => undefined);
      }
      setResultado(await api.executar(selecionada, 5));
      await Promise.all([carregarLista(), carregarDetalhe(selecionada)]);
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  async function acao(fn: () => Promise<unknown>) {
    setOcupado(true);
    setErro(null);
    try {
      await fn();
      if (selecionada) await carregarDetalhe(selecionada);
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  async function criar() {
    await acao(async () => {
      const nova = await api.criarCampanha({ nome, servico, regiao, meta_leads: 25 });
      setNome("");
      setServico("");
      setCriando(false);
      await carregarLista();
      setSelecionada(nova.id);
    });
  }

  const pendentes = mensagens.filter((m) => m.status === "aguardando_aprovacao");
  const campanha = campanhas.find((c) => c.id === selecionada);

  return (
    <div className="space-y-6">
      {erro && <Aviso tom="erro">{erro}</Aviso>}

      <Card
        titulo="Campanhas"
        acao={
          <Botao tamanho="sm" variante="secundario" onClick={() => setCriando(!criando)}>
            {criando ? "cancelar" : "+ nova campanha"}
          </Botao>
        }
      >
        {criando && (
          <div className="mb-5 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <Campo rotulo="Nome" valor={nome} onChange={setNome} placeholder="Climatização — hotéis" />
            <Campo
              rotulo="Serviço"
              valor={servico}
              onChange={setServico}
              multiline
              placeholder="manutenção preventiva de ar condicionado para empresas"
            />
            <Campo rotulo="Região" valor={regiao} onChange={setRegiao} />
            <Botao onClick={criar} disabled={ocupado || nome.length < 3 || servico.length < 10}>
              criar
            </Botao>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <select
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
            value={selecionada ?? ""}
            onChange={(e) => {
              setSelecionada(e.target.value);
              setResultado(null);
            }}
          >
            {campanhas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
          {campanha && <Badge tom={campanha.status}>{campanha.status}</Badge>}
          <Botao onClick={executar} disabled={ocupado || !selecionada}>
            {ocupado ? "executando..." : "rodar campanha"}
          </Botao>
          {nivel === "assistido" && pendentes.length > 0 && (
            <Botao
              variante="secundario"
              onClick={() => acao(() => api.disparar(selecionada!))}
              disabled={ocupado}
            >
              disparar aprovadas
            </Botao>
          )}
          {limites && (
            <span className="ml-auto text-xs text-slate-500">
              limite diário: {limites.restante_campanha} nesta campanha ·{" "}
              {limites.restante_usuario} na conta
            </span>
          )}
        </div>

        {resultado && (
          <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-4 text-sm md:grid-cols-4">
            <Metric rotulo="descobertos" valor={resultado.descobertos} />
            <Metric rotulo="duplicados" valor={resultado.duplicados} />
            <Metric rotulo="mensagens" valor={resultado.mensagens_geradas} />
            <Metric
              rotulo={nivel === "assistido" ? "aguardando você" : "enviadas"}
              valor={
                nivel === "assistido"
                  ? resultado.mensagens_aguardando_aprovacao
                  : resultado.mensagens_enviadas
              }
            />
            {resultado.interrompido_por_saldo && (
              <div className="col-span-full">
                <Aviso tom="atencao">A leva parou: acabaram os créditos no meio da execução.</Aviso>
              </div>
            )}
            {Object.keys(resultado.motivos_bloqueio).length > 0 && (
              <div className="col-span-full text-xs text-slate-500">
                bloqueios:{" "}
                {Object.entries(resultado.motivos_bloqueio)
                  .map(([k, v]) => `${k.replace(/_/g, " ")} (${v})`)
                  .join(" · ")}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card titulo={`Leads (${leads.length})`}>
        {leads.length === 0 ? (
          <Vazio>Nenhum lead ainda. Rode a campanha.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr className="border-b border-slate-100">
                  <th className="py-2 pr-3">Empresa</th>
                  <th className="py-2 pr-3">CNPJ</th>
                  <th className="py-2 pr-3">Cidade</th>
                  <th className="py-2 pr-3">Contato</th>
                  <th className="py-2 pr-3">Score</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {leads.map((l) => (
                  <tr key={l.id} className="border-b border-slate-50">
                    <td className="py-2 pr-3 font-medium text-slate-900">
                      {l.razao_social ?? l.nome_fantasia}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs text-slate-500">{l.cnpj ?? "—"}</td>
                    <td className="py-2 pr-3 text-slate-500">
                      {l.municipio ?? "—"}/{l.uf ?? "—"}
                    </td>
                    <td className="py-2 pr-3 text-slate-500">{l.email ?? "—"}</td>
                    <td className="py-2 pr-3">
                      <BarraScore valor={Number(l.score)} />
                    </td>
                    <td className="py-2 pr-3">
                      <Badge tom={l.status}>{l.status}</Badge>
                    </td>
                    <td className="py-2 text-right">
                      <Botao variante="fantasma" tamanho="sm" onClick={() => setDetalhe(l)}>
                        por quê?
                      </Botao>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {detalhe && <ExplicacaoLead lead={detalhe} aoFechar={() => setDetalhe(null)} />}

      <Card titulo={`Mensagens (${mensagens.length})`}>
        {mensagens.length === 0 ? (
          <Vazio>Nenhuma mensagem gerada ainda.</Vazio>
        ) : (
          <div className="space-y-3">
            {mensagens.map((m) => (
              <article key={m.id} className="rounded-lg border border-slate-200 p-4">
                <div className="mb-2 flex flex-wrap items-center gap-3">
                  <span className="text-sm font-medium text-slate-900">{m.destinatario}</span>
                  <Badge tom={m.status}>{m.status}</Badge>
                  <span className="text-xs text-slate-400">
                    {m.tokens_entrada + m.tokens_saida} tokens
                  </span>
                  {m.status === "aguardando_aprovacao" && (
                    <span className="ml-auto flex gap-2">
                      <Botao tamanho="sm" onClick={() => acao(() => api.aprovar(m.id))} disabled={ocupado}>
                        aprovar e enviar
                      </Botao>
                      <Botao
                        tamanho="sm"
                        variante="perigo"
                        onClick={() => acao(() => api.rejeitar(m.id))}
                        disabled={ocupado}
                      >
                        rejeitar
                      </Botao>
                    </span>
                  )}
                </div>
                <p className="mb-1 text-xs font-medium text-slate-500">{m.assunto}</p>
                <p className="whitespace-pre-line text-sm text-slate-600">{m.corpo}</p>
              </article>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function Metric({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500">{rotulo}</div>
      <div className="text-xl font-semibold tabular-nums text-slate-900">{valor}</div>
    </div>
  );
}

function ExplicacaoLead({ lead, aoFechar }: { lead: Lead; aoFechar: () => void }) {
  const b = lead.score_breakdown ?? {};
  const componentes = Object.entries(b.componentes ?? {});
  const contribuicoes = b.contribuicoes ?? {};
  const proveniencia = lead.provenance as Record<string, unknown>;

  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={aoFechar}
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-900">
              {lead.razao_social ?? lead.nome_fantasia}
            </h3>
            <p className="text-sm text-slate-500">
              Por que este lead apareceu e por que recebeu esta nota
            </p>
          </div>
          <Botao variante="fantasma" tamanho="sm" onClick={aoFechar}>
            fechar
          </Botao>
        </header>

        {b.explicacao && <Aviso tom="info">{b.explicacao}</Aviso>}

        <h4 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Composição do score
        </h4>
        <div className="space-y-1.5">
          {componentes.map(([nome, valor]) => (
            <div key={nome} className="flex items-center gap-3 text-sm">
              <span className="w-40 shrink-0 text-slate-600">{nome.replace(/_/g, " ")}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full bg-marca-500" style={{ width: `${valor * 100}%` }} />
              </div>
              <span className="w-24 text-right tabular-nums text-xs text-slate-500">
                {(valor * 100).toFixed(0)}% → {(contribuicoes[nome] ?? 0).toFixed(1)} pts
              </span>
            </div>
          ))}
        </div>

        <h4 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Origem do dado (LGPD)
        </h4>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          {Object.entries(proveniencia)
            .filter(([, v]) => typeof v === "string")
            .map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-slate-400">{k.replace(/_/g, " ")}</dt>
                <dd className="text-slate-700">{String(v)}</dd>
              </div>
            ))}
        </dl>
      </div>
    </div>
  );
}
