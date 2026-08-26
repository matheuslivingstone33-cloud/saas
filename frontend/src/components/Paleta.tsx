import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { EXPO } from "./movimento";
import { useTema } from "./tema";
import Portal from "./Portal";

/**
 * Paleta de comandos (Ctrl+K / Cmd+K).
 *
 * Navegar por menu custa tres cliques e obriga a saber onde a coisa mora.
 * Aqui o usuario descreve o que quer e executa: "rodar", "revisar", "escuro",
 * "conformidade". Quem usa a ferramenta todo dia para de usar o mouse.
 *
 * A busca e por subsequencia, nao por prefixo: "rvs" encontra "revisar".
 */

export type Comando = {
  id: string;
  titulo: string;
  descricao?: string;
  grupo: string;
  atalho?: string;
  executar: () => void;
};

/** Busca fuzzy: as letras precisam aparecer na ordem, nao coladas. */
function combina(texto: string, busca: string): number {
  const t = texto.toLowerCase();
  const b = busca.toLowerCase().trim();
  if (!b) return 1;
  if (t.includes(b)) return 3; // acerto direto pesa mais

  let i = 0;
  for (const letra of b) {
    i = t.indexOf(letra, i);
    if (i === -1) return 0;
    i += 1;
  }
  return 1;
}

export function usePaleta() {
  const [aberta, setAberta] = useState(false);

  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAberta((v) => !v);
      }
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, []);

  return { aberta, abrir: () => setAberta(true), fechar: () => setAberta(false) };
}

export default function Paleta({
  aberta,
  fechar,
  comandos,
}: {
  aberta: boolean;
  fechar: () => void;
  comandos: Comando[];
}) {
  const { tema, definir } = useTema();
  const [busca, setBusca] = useState("");
  const [selecionado, setSelecionado] = useState(0);
  const entrada = useRef<HTMLInputElement>(null);

  const todos = useMemo<Comando[]>(
    () => [
      ...comandos,
      {
        id: "tema-escuro",
        titulo: "Tema escuro",
        grupo: "Aparência",
        descricao: tema === "escuro" ? "em uso" : undefined,
        executar: () => definir("escuro"),
      },
      {
        id: "tema-claro",
        titulo: "Tema claro",
        grupo: "Aparência",
        descricao: tema === "claro" ? "em uso" : undefined,
        executar: () => definir("claro"),
      },
      {
        id: "tema-sistema",
        titulo: "Seguir o tema do sistema",
        grupo: "Aparência",
        descricao: tema === "sistema" ? "em uso" : undefined,
        executar: () => definir("sistema"),
      },
    ],
    [comandos, tema, definir],
  );

  const filtrados = useMemo(() => {
    return todos
      .map((c) => ({
        c,
        p: Math.max(combina(c.titulo, busca), combina(c.grupo, busca) * 0.5),
      }))
      .filter((x) => x.p > 0)
      .sort((a, b) => b.p - a.p)
      .map((x) => x.c);
  }, [todos, busca]);

  useEffect(() => {
    if (aberta) {
      setBusca("");
      setSelecionado(0);
      setTimeout(() => entrada.current?.focus(), 40);
    }
  }, [aberta]);

  useEffect(() => setSelecionado(0), [busca]);

  function aoTeclar(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelecionado((i) => (i + 1) % Math.max(1, filtrados.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelecionado((i) => (i - 1 + filtrados.length) % Math.max(1, filtrados.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const alvo = filtrados[selecionado];
      if (alvo) {
        alvo.executar();
        fechar();
      }
    } else if (e.key === "Escape") {
      fechar();
    }
  }

  // Agrupa preservando a ordem de relevancia.
  const grupos = filtrados.reduce<Record<string, Comando[]>>((acc, c) => {
    (acc[c.grupo] ??= []).push(c);
    return acc;
  }, {});

  return (
    <Portal>
    <AnimatePresence>
      {aberta && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-fundo/60 p-4 pt-[12vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={fechar}
        >
          <motion.div
            role="dialog"
            aria-label="Paleta de comandos"
            onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.99 }}
            transition={{ duration: 0.24, ease: EXPO }}
            className="realce-topo w-full max-w-xl overflow-hidden rounded-2xl border border-borda bg-superficie shadow-3"
          >
            <div className="flex items-center gap-3 border-b border-borda px-4">
              <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-texto-fraco" fill="none">
                <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
                <path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <input
                ref={entrada}
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                onKeyDown={aoTeclar}
                placeholder="O que você quer fazer?"
                className="w-full bg-transparent py-3.5 text-sm text-texto outline-none placeholder:text-texto-fraco"
              />
              <kbd className="shrink-0 rounded border border-borda px-1.5 py-0.5 text-[10px] text-texto-fraco">
                esc
              </kbd>
            </div>

            <div className="max-h-[22rem] overflow-y-auto p-2">
              {filtrados.length === 0 ? (
                <p className="px-3 py-8 text-center text-sm text-texto-fraco">
                  Nada encontrado para “{busca}”.
                </p>
              ) : (
                Object.entries(grupos).map(([grupo, itens]) => (
                  <div key={grupo} className="mb-1">
                    <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-rotulo text-texto-fraco">
                      {grupo}
                    </div>
                    {itens.map((c) => {
                      const i = filtrados.indexOf(c);
                      const ativo = i === selecionado;
                      return (
                        <button
                          key={c.id}
                          onMouseEnter={() => setSelecionado(i)}
                          onClick={() => {
                            c.executar();
                            fechar();
                          }}
                          className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors duration-100 ${
                            ativo ? "bg-marca-fraca text-texto" : "text-texto-medio hover:bg-superficie-2"
                          }`}
                        >
                          <span className="flex-1 truncate text-sm">{c.titulo}</span>
                          {c.descricao && (
                            <span className="shrink-0 text-xs text-texto-fraco">{c.descricao}</span>
                          )}
                          {c.atalho && (
                            <kbd className="shrink-0 rounded border border-borda px-1.5 py-0.5 text-[10px] text-texto-fraco">
                              {c.atalho}
                            </kbd>
                          )}
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>

            <div className="flex items-center gap-3 border-t border-borda px-4 py-2 text-[11px] text-texto-fraco">
              <span>
                <kbd className="rounded border border-borda px-1">↑</kbd>{" "}
                <kbd className="rounded border border-borda px-1">↓</kbd> navegar
              </span>
              <span>
                <kbd className="rounded border border-borda px-1">↵</kbd> executar
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
    </Portal>
  );
}
