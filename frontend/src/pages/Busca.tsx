import { motion } from "framer-motion";
import { useState } from "react";
import { api } from "../lib/api";
import { EXPO } from "../components/movimento";
import { Aviso, Botao } from "../components/ui";

/**
 * Busca — a porta de entrada do produto.
 *
 * Uma pergunta, duas caixas, um botao. O usuario diz o que FAZ e onde atua; o
 * Cerebro se encarrega de descobrir quem CONSOME isso.
 *
 * A tela e proposital: um formulario com dez campos comunicaria "trabalho";
 * uma pergunta comunica "me diga e eu resolvo". O trabalho pesado acontece
 * depois, e o usuario assiste na tela de Descoberta.
 */

const EXEMPLOS = [
  { servico: "Manutenção de ar-condicionado", regiao: "Fortaleza, CE" },
  { servico: "Manutenção predial: elétrica e hidráulica", regiao: "Foz do Iguaçu, PR" },
  { servico: "Limpeza e conservação para empresas", regiao: "Curitiba, PR" },
];

export default function Busca({ aoDescobrir }: { aoDescobrir: (campanhaId: string) => void }) {
  const [servico, setServico] = useState("");
  const [regiao, setRegiao] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const podeBuscar = servico.trim().length >= 5 && regiao.trim().length >= 2;

  async function descobrir() {
    if (!podeBuscar || ocupado) return;
    setOcupado(true);
    setErro(null);
    try {
      // O nome da campanha sai do proprio pedido — ninguem quer batizar
      // campanha antes de ver se o produto funciona.
      const campanha = await api.criarCampanha({
        nome: `${servico.trim().slice(0, 60)} — ${regiao.trim()}`,
        servico: servico.trim(),
        regiao: regiao.trim(),
        meta_leads: 25,
      });
      aoDescobrir(campanha.id);
    } catch (e) {
      setErro(String(e));
      setOcupado(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-2xl flex-col items-center justify-center py-10 text-center">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EXPO }}
        className="w-full"
      >
        <span className="inline-flex items-center gap-2 rounded-full border border-borda bg-superficie-2 px-3 py-1 text-xs text-texto-medio">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-marca" fill="none" aria-hidden>
            <path
              d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
          Sua próxima obra começa com uma busca
        </span>

        <h1 className="mt-6 text-4xl font-semibold tracking-tight text-texto sm:text-5xl">
          Quem você quer atender hoje?
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm text-texto-medio">
          Diga o serviço que você faz e onde você atua. A gente encontra as empresas
          que precisam disso agora.
        </p>

        <div className="mt-8 flex flex-col gap-2 rounded-2xl border border-borda bg-superficie p-2 shadow-2 sm:flex-row">
          <label className="flex flex-1 items-center gap-2.5 rounded-xl px-3 py-2.5 focus-within:bg-superficie-2">
            <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-texto-fraco" fill="none" aria-hidden>
              <path
                d="M14.7 6.3a4 4 0 0 0 5 5L15 16l-4-4 3.7-5.7zM11 12l-6.3 6.3a1.5 1.5 0 0 0 2.1 2.1L13 14"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <input
              value={servico}
              onChange={(e) => setServico(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && descobrir()}
              placeholder="O serviço que você faz"
              aria-label="Serviço que você faz"
              className="w-full bg-transparent text-sm text-texto outline-none placeholder:text-texto-fraco"
            />
          </label>

          <div className="hidden w-px bg-borda sm:block" />

          <label className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 focus-within:bg-superficie-2 sm:w-56">
            <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-texto-fraco" fill="none" aria-hidden>
              <path
                d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11z"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinejoin="round"
              />
              <circle cx="12" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.7" />
            </svg>
            <input
              value={regiao}
              onChange={(e) => setRegiao(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && descobrir()}
              placeholder="Cidade, UF"
              aria-label="Região onde você atua"
              className="w-full bg-transparent text-sm text-texto outline-none placeholder:text-texto-fraco"
            />
          </label>
        </div>

        <div className="mt-5">
          <Botao onClick={descobrir} disabled={!podeBuscar} carregando={ocupado}>
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
              <path
                d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
            </svg>
            Descobrir clientes
          </Botao>
        </div>

        {!podeBuscar && !ocupado && (
          <div className="mt-6">
            <p className="text-xs text-texto-fraco">ou comece por um exemplo</p>
            <div className="mt-2 flex flex-wrap justify-center gap-2">
              {EXEMPLOS.map((ex) => (
                <button
                  key={ex.servico}
                  onClick={() => {
                    setServico(ex.servico);
                    setRegiao(ex.regiao);
                  }}
                  className="rounded-full border border-borda bg-superficie-2 px-3 py-1.5 text-xs text-texto-medio transition-colors hover:border-borda-forte hover:text-texto"
                >
                  {ex.servico}
                </button>
              ))}
            </div>
          </div>
        )}

        {erro && (
          <div className="mt-6 text-left">
            <Aviso tom="erro">{erro}</Aviso>
          </div>
        )}

        <p className="mt-8 flex items-center justify-center gap-1.5 text-xs text-texto-fraco">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-positivo" fill="none" aria-hidden>
            <path
              d="M12 3l7 3v6c0 4.4-3 8.2-7 9-4-.8-7-4.6-7-9V6l7-3z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
            <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          Prospecção 100% B2B em conformidade com a LGPD
        </p>
      </motion.div>
    </div>
  );
}
