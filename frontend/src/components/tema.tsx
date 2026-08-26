import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

/**
 * Tema claro/escuro.
 *
 * Tres estados, nao dois: "sistema" e o padrao e respeita o SO em tempo real
 * (se voce trocar o tema do Windows com o app aberto, ele acompanha). "claro"
 * e "escuro" sao escolhas explicitas e ficam salvas.
 *
 * O atributo vive no <html>: trocar de tema nao re-renderiza componente nenhum,
 * so troca quais variaveis CSS valem.
 */

export type Tema = "sistema" | "claro" | "escuro";

const CHAVE = "prospector:tema";

type Contexto = {
  tema: Tema;
  efetivo: "claro" | "escuro";
  definir: (t: Tema) => void;
};

const TemaContexto = createContext<Contexto | null>(null);

function lerSalvo(): Tema {
  if (typeof localStorage === "undefined") return "sistema";
  const v = localStorage.getItem(CHAVE);
  return v === "claro" || v === "escuro" ? v : "sistema";
}

function sistemaEscuro(): boolean {
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches;
}

function aplicar(tema: Tema): void {
  const html = document.documentElement;
  // Congela transicoes durante o swap: sem isto, o body anima a cor enquanto
  // os cartoes trocam na hora, e por ~400ms ha texto invisivel sobre fundo
  // da cor errada.
  html.setAttribute("data-trocando-tema", "");
  if (tema === "sistema") html.removeAttribute("data-tema");
  else html.setAttribute("data-tema", tema);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => html.removeAttribute("data-trocando-tema"));
  });
}

export function ProvedorTema({ children }: { children: ReactNode }) {
  const [tema, setTema] = useState<Tema>(lerSalvo);
  const [efetivo, setEfetivo] = useState<"claro" | "escuro">(() =>
    lerSalvo() === "sistema" ? (sistemaEscuro() ? "escuro" : "claro") : (lerSalvo() as "claro" | "escuro"),
  );

  useEffect(() => {
    aplicar(tema);
    setEfetivo(tema === "sistema" ? (sistemaEscuro() ? "escuro" : "claro") : tema);
  }, [tema]);

  // Em modo "sistema", acompanha a troca do SO sem precisar recarregar.
  useEffect(() => {
    if (tema !== "sistema" || typeof matchMedia === "undefined") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const aoMudar = () => setEfetivo(mq.matches ? "escuro" : "claro");
    mq.addEventListener("change", aoMudar);
    return () => mq.removeEventListener("change", aoMudar);
  }, [tema]);

  const definir = useCallback((t: Tema) => {
    setTema(t);
    if (t === "sistema") localStorage.removeItem(CHAVE);
    else localStorage.setItem(CHAVE, t);
  }, []);

  return <TemaContexto.Provider value={{ tema, efetivo, definir }}>{children}</TemaContexto.Provider>;
}

export function useTema(): Contexto {
  const ctx = useContext(TemaContexto);
  if (!ctx) throw new Error("useTema precisa estar dentro de <ProvedorTema>");
  return ctx;
}

const OPCOES: { valor: Tema; rotulo: string; icone: ReactNode }[] = [
  {
    valor: "claro",
    rotulo: "Tema claro",
    icone: (
      <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5" aria-hidden>
        <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
        <path
          d="M12 3v1.8M12 19.2V21M21 12h-1.8M4.8 12H3M18.4 5.6l-1.3 1.3M6.9 17.1l-1.3 1.3M18.4 18.4l-1.3-1.3M6.9 6.9L5.6 5.6"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    valor: "sistema",
    rotulo: "Seguir o sistema",
    icone: (
      <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5" aria-hidden>
        <rect x="3" y="4.5" width="18" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
        <path d="M9 20h6M12 16.5V20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    valor: "escuro",
    rotulo: "Tema escuro",
    icone: (
      <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5" aria-hidden>
        <path
          d="M20 13.4A8.2 8.2 0 1 1 10.6 4a6.6 6.6 0 0 0 9.4 9.4Z"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
];

/** Seletor de tres estados. O indicador desliza entre as opcoes. */
export function TrocaTema() {
  const { tema, definir } = useTema();
  return (
    <div
      role="radiogroup"
      aria-label="Tema"
      className="relative flex items-center gap-0.5 rounded-full border border-borda bg-superficie-2 p-0.5"
    >
      {OPCOES.map((o) => {
        const ativo = tema === o.valor;
        return (
          <button
            key={o.valor}
            role="radio"
            aria-checked={ativo}
            aria-label={o.rotulo}
            title={o.rotulo}
            onClick={() => definir(o.valor)}
            className={`relative flex h-7 w-7 items-center justify-center rounded-full transition-colors duration-200 ${
              ativo ? "text-marca" : "text-texto-fraco hover:text-texto-medio"
            }`}
          >
            {ativo && (
              <span className="absolute inset-0 rounded-full bg-superficie shadow-1 ring-1 ring-borda" />
            )}
            <span className="relative">{o.icone}</span>
          </button>
        );
      })}
    </div>
  );
}
