import type { Lead } from "../lib/api";
import { Aviso, Botao } from "./ui";
import Portal from "./Portal";

/**
 * "Por que esta empresa apareceu?"
 *
 * E a pergunta mais importante que o produto precisa saber responder. Sem
 * resposta, o score e um numero magico e o cliente nao confia. Aqui abrimos a
 * conta inteira: cada fator, quanto pesou, e de onde veio cada dado.
 *
 * Extraido de Campanhas.tsx para ser reusado por Descoberta e Conversas.
 */

export default function ExplicacaoLead({ lead, aoFechar }: { lead: Lead; aoFechar: () => void }) {
  const b = lead.score_breakdown ?? {};
  const componentes = Object.entries(b.componentes ?? {});
  const contribuicoes = b.contribuicoes ?? {};
  const proveniencia = lead.provenance as Record<string, unknown>;

  return (
    <Portal>
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-fundo/70 p-4 backdrop-blur-sm"
      onClick={aoFechar}
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-borda bg-superficie p-6 shadow-3"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-texto">
              {lead.razao_social ?? lead.nome_fantasia ?? "Contato ainda nao revelado"}
            </h3>
            <p className="text-sm text-texto-fraco">
              Por que este lead apareceu e por que recebeu esta nota
            </p>
          </div>
          <Botao variante="fantasma" tamanho="sm" onClick={aoFechar}>
            fechar
          </Botao>
        </header>

        {b.explicacao && <Aviso tom="info">{b.explicacao}</Aviso>}

        <h4 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-texto-fraco">
          Composição do score
        </h4>
        <div className="space-y-1.5">
          {componentes.map(([nome, valor]) => (
            <div key={nome} className="flex items-center gap-3 text-sm">
              <span className="w-40 shrink-0 text-texto-medio">{nome.replace(/_/g, " ")}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-superficie-3">
                <div className="h-full bg-marca" style={{ width: `${valor * 100}%` }} />
              </div>
              <span className="w-24 text-right tabular-nums text-xs text-texto-fraco">
                {(valor * 100).toFixed(0)}% → {(contribuicoes[nome] ?? 0).toFixed(1)} pts
              </span>
            </div>
          ))}
        </div>

        <h4 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-texto-fraco">
          Origem do dado (LGPD)
        </h4>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          {Object.entries(proveniencia)
            .filter(([, v]) => typeof v === "string")
            .map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-texto-fraco">{k.replace(/_/g, " ")}</dt>
                <dd className="text-texto-medio">{String(v)}</dd>
              </div>
            ))}
        </dl>
      </div>
    </div>
    </Portal>
  );
}
