import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Aviso, Card, Carregando, Vazio } from "../components/ui";
import { dataHora } from "../lib/format";

type OptOuts = Awaited<ReturnType<typeof api.optOuts>>;
type Integridade = Awaited<ReturnType<typeof api.integridade>>;

/** Conformidade: LIA, lista de supressao e integridade da trilha de auditoria. */
export default function Conformidade() {
  const [lia, setLia] = useState<Record<string, unknown> | null>(null);
  const [optOuts, setOptOuts] = useState<OptOuts | null>(null);
  const [integridade, setIntegridade] = useState<Integridade | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.lia(), api.optOuts(), api.integridade()])
      .then(([l, o, i]) => {
        setLia(l);
        setOptOuts(o);
        setIntegridade(i);
      })
      .catch((e) => setErro(String(e)));
  }, []);

  if (erro) return <Aviso tom="erro">{erro}</Aviso>;
  if (!lia || !optOuts || !integridade) return <Carregando />;

  const salvaguardas = (lia.salvaguardas as string[]) ?? [];
  const direitos = (lia.direitos as string[]) ?? [];
  const fontes = (lia.fontes as string[]) ?? [];
  const balanceamento = (lia.balanceamento as Record<string, string>) ?? {};

  return (
    <div className="space-y-6">
      <Aviso tom={integridade.integra ? "sucesso" : "erro"}>
        Trilha de auditoria: <strong>{integridade.registros}</strong> registros ·{" "}
        {integridade.integra
          ? "cadeia de hash íntegra"
          : `ADULTERAÇÃO detectada no registro ${integridade.primeiro_erro_seq}`}
      </Aviso>

      <Card titulo="Avaliação de Legítimo Interesse (LIA)">
        <p className="text-sm text-texto-medio">{String(lia.finalidade)}</p>

        <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-texto-fraco">
          Balanceamento
        </h3>
        <dl className="space-y-2 text-sm">
          {Object.entries(balanceamento).map(([chave, valor]) => (
            <div key={chave}>
              <dt className="text-xs uppercase text-texto-fraco">{chave}</dt>
              <dd className="text-texto-medio">{valor}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-5 grid gap-5 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-texto-fraco">
              Salvaguardas ({salvaguardas.length})
            </h3>
            <ul className="space-y-1 text-sm text-texto-medio">
              {salvaguardas.map((s) => (
                <li key={s}>· {s}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-texto-fraco">
              Direitos do titular
            </h3>
            <ul className="space-y-1 text-sm text-texto-medio">
              {direitos.map((d) => (
                <li key={d}>· {d}</li>
              ))}
            </ul>
            <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-texto-fraco">
              Fontes de dados
            </h3>
            <ul className="space-y-1 text-sm text-texto-medio">
              {fontes.map((f) => (
                <li key={f}>· {f}</li>
              ))}
            </ul>
          </div>
        </div>

        <p className="mt-5 rounded-md bg-superficie-2 p-3 text-sm text-texto-medio">
          {String(lia.conclusao)}
        </p>
        <p className="mt-2 text-xs text-texto-fraco">
          Hash do documento: <code>{String(lia.hash)}</code>
        </p>
      </Card>

      <Card titulo={`Lista de supressão (${optOuts.total})`}>
        {optOuts.itens.length === 0 ? (
          <Vazio>Ninguém pediu descadastro ainda.</Vazio>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-texto-fraco">
              <tr className="border-b border-borda">
                <th className="py-2 pr-3">Contato</th>
                <th className="py-2 pr-3">Origem</th>
                <th className="py-2">Quando</th>
              </tr>
            </thead>
            <tbody>
              {optOuts.itens.map((o) => (
                <tr key={o.contato} className="border-b border-borda">
                  <td className="py-2 pr-3 text-texto-medio">{o.contato}</td>
                  <td className="py-2 pr-3 text-texto-fraco">{o.origem.replace(/_/g, " ")}</td>
                  <td className="py-2 text-xs text-texto-fraco">
                    {dataHora(o.registrado_em)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card titulo="Documentos públicos">
        <ul className="space-y-2 text-sm">
          <li>
            <a
              className="text-marca-forte underline"
              href={`${import.meta.env.VITE_API_URL ?? "http://localhost:8000"}/legal/privacidade`}
              target="_blank"
              rel="noreferrer"
            >
              Política de Privacidade
            </a>
          </li>
          <li>
            <a
              className="text-marca-forte underline"
              href={`${import.meta.env.VITE_API_URL ?? "http://localhost:8000"}/legal/ia`}
              target="_blank"
              rel="noreferrer"
            >
              Declaração de uso de IA
            </a>
          </li>
        </ul>
      </Card>
    </div>
  );
}
