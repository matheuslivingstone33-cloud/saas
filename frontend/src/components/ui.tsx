import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { EXPO, Esqueleto, NumeroAnimado, RAPIDO } from "./movimento";

/**
 * Primitivas visuais. Nenhuma cor literal aqui: tudo sai dos tokens em
 * index.css, o que faz claro e escuro funcionarem sem componente duplicado.
 */

export function Card({
  titulo,
  acao,
  children,
  className = "",
  destaque,
}: {
  titulo?: string;
  acao?: ReactNode;
  children: ReactNode;
  className?: string;
  destaque?: boolean;
}) {
  return (
    <section
      className={`realce-topo overflow-hidden rounded-2xl border bg-superficie shadow-1 transition-shadow duration-300 ease-expo hover:shadow-2 ${
        destaque ? "border-marca/30 shadow-marca" : "border-borda"
      } ${className}`}
    >
      {(titulo || acao) && (
        <header className="flex items-center justify-between gap-3 border-b border-borda px-5 py-3.5">
          {titulo && (
            <h2 className="text-[11px] font-semibold uppercase tracking-rotulo text-texto-fraco">
              {titulo}
            </h2>
          )}
          {acao}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/**
 * KPI. Aceita numero (conta ate o valor) ou string ja formatada.
 * `prefixo`/`sufixo` existem para o numero animar sem perder "US$" ou "%".
 */
export function Stat({
  rotulo,
  valor,
  nota,
  destaque,
  casas = 0,
  prefixo,
  sufixo,
  icone,
}: {
  rotulo: string;
  valor: string | number;
  nota?: ReactNode;
  destaque?: "positivo" | "atencao" | "negativo" | "marca" | "neutro";
  casas?: number;
  prefixo?: string;
  sufixo?: string;
  icone?: ReactNode;
}) {
  const cor = {
    positivo: "text-positivo",
    atencao: "text-atencao",
    negativo: "text-perigo",
    marca: "text-marca",
    neutro: "text-texto",
  }[destaque ?? "neutro"];

  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={RAPIDO}
      className="realce-topo group rounded-xl border border-borda bg-superficie p-4 shadow-1 transition-colors duration-300 hover:border-borda-forte"
    >
      <div className="flex items-center gap-1.5">
        {icone && <span className="text-texto-fraco">{icone}</span>}
        <div className="text-[10px] font-medium uppercase tracking-rotulo text-texto-fraco">
          {rotulo}
        </div>
      </div>
      <div className={`mt-1.5 text-[26px] font-semibold leading-none tracking-tight ${cor}`}>
        {typeof valor === "number" ? (
          <NumeroAnimado valor={valor} casas={casas} prefixo={prefixo} sufixo={sufixo} />
        ) : (
          <span className="num">{valor}</span>
        )}
      </div>
      {nota && <div className="mt-1.5 text-xs text-texto-fraco">{nota}</div>}
    </motion.div>
  );
}

/* Cada estado tem cor propria; o fundo usa o token fraco correspondente. */
type Tom = "neutro" | "marca" | "acento" | "positivo" | "atencao" | "perigo";

const TOM_DE_ESTADO: Record<string, Tom> = {
  descoberto: "neutro",
  qualificado: "acento",
  enfileirado: "marca",
  abordado: "marca",
  respondido: "positivo",
  convertido: "positivo",
  opt_out: "perigo",
  descartado: "neutro",
  aguardando_aprovacao: "atencao",
  aprovada: "acento",
  enviada: "positivo",
  entregue: "positivo",
  bloqueada: "perigo",
  rejeitada: "neutro",
  falhou: "perigo",
  rascunho: "neutro",
  descobrindo: "acento",
  qualificando: "marca",
  pronta: "atencao",
  executando: "marca",
  concluida: "positivo",
  pausada: "atencao",
  mock: "neutro",
  real: "positivo",
  assistido: "acento",
  automatico: "marca",
};

const CLASSES_TOM: Record<Tom, string> = {
  neutro: "bg-neutro-fraco text-texto-medio ring-borda",
  marca: "bg-marca-fraca text-marca ring-marca/25",
  acento: "bg-acento/10 text-acento ring-acento/25",
  positivo: "bg-positivo-fraco text-positivo ring-positivo/25",
  atencao: "bg-atencao-fraco text-atencao ring-atencao/25",
  perigo: "bg-perigo-fraco text-perigo ring-perigo/25",
};

export function Badge({ children, tom, ponto }: { children: string; tom?: string; ponto?: boolean }) {
  const chave = tom ?? children;
  const escolhido = (["neutro", "marca", "acento", "positivo", "atencao", "perigo"] as Tom[]).includes(
    chave as Tom,
  )
    ? (chave as Tom)
    : (TOM_DE_ESTADO[chave] ?? "neutro");
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset ${CLASSES_TOM[escolhido]}`}
    >
      {ponto && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children.replace(/_/g, " ")}
    </span>
  );
}

export function Botao({
  children,
  onClick,
  variante = "primario",
  disabled,
  tamanho = "md",
  type = "button",
  carregando,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variante?: "primario" | "secundario" | "perigo" | "fantasma";
  disabled?: boolean;
  tamanho?: "sm" | "md";
  type?: "button" | "submit";
  carregando?: boolean;
  className?: string;
}) {
  const reduzido = useReducedMotion();
  const base =
    "relative inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-200 ease-expo disabled:cursor-not-allowed disabled:opacity-45";
  const dimensao = tamanho === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm";
  const estilos = {
    primario:
      "bg-marca text-white shadow-1 hover:bg-marca-forte hover:shadow-2 active:shadow-1",
    secundario:
      "border border-borda bg-superficie text-texto-medio hover:border-borda-forte hover:bg-superficie-2 hover:text-texto",
    perigo:
      "border border-perigo/30 bg-perigo-fraco text-perigo hover:border-perigo/50 hover:bg-perigo/10",
    fantasma: "text-texto-fraco hover:bg-superficie-2 hover:text-texto",
  }[variante];

  return (
    <motion.button
      type={type}
      onClick={onClick}
      disabled={disabled || carregando}
      whileHover={reduzido || disabled ? undefined : { y: -1 }}
      whileTap={reduzido || disabled ? undefined : { scale: 0.97, y: 0 }}
      transition={{ duration: 0.15, ease: EXPO }}
      className={`${base} ${dimensao} ${estilos} ${className}`}
    >
      {carregando && (
        <span
          className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-current border-t-transparent"
          aria-hidden
        />
      )}
      {children}
    </motion.button>
  );
}

export function Campo({
  rotulo,
  valor,
  onChange,
  placeholder,
  ajuda,
  multiline,
}: {
  rotulo: string;
  valor: string;
  onChange: (v: string) => void;
  placeholder?: string;
  ajuda?: string;
  multiline?: boolean;
}) {
  const classe =
    "mt-1.5 w-full rounded-lg border border-borda bg-superficie-2 px-3 py-2 text-sm text-texto outline-none transition-all duration-200 ease-expo placeholder:text-texto-fraco focus:border-marca focus:bg-superficie focus:ring-4 focus:ring-marca/12";
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase tracking-rotulo text-texto-fraco">{rotulo}</span>
      {multiline ? (
        <textarea
          className={`${classe} min-h-[5.5rem] resize-y`}
          value={valor}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className={classe}
          value={valor}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {ajuda && <span className="mt-1.5 block text-xs text-texto-fraco">{ajuda}</span>}
    </label>
  );
}

export function BarraScore({ valor }: { valor: number }) {
  const reduzido = useReducedMotion();
  const pct = Math.max(0, Math.min(100, valor));
  const cor = pct >= 60 ? "bg-positivo" : pct >= 35 ? "bg-atencao" : "bg-texto-fraco";
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-superficie-3">
        <motion.div
          className={`h-full rounded-full ${cor}`}
          initial={reduzido ? false : { width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.9, ease: EXPO }}
        />
      </div>
      <span className="num text-xs font-medium text-texto-medio">{pct.toFixed(0)}</span>
    </div>
  );
}

export function Aviso({
  tom = "info",
  children,
}: {
  tom?: "info" | "erro" | "sucesso" | "atencao";
  children: ReactNode;
}) {
  const estilos = {
    info: "border-acento/25 bg-acento/8 text-texto",
    erro: "border-perigo/30 bg-perigo-fraco text-perigo",
    sucesso: "border-positivo/30 bg-positivo-fraco text-positivo",
    atencao: "border-atencao/30 bg-atencao-fraco text-atencao",
  }[tom];
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={RAPIDO}
      className={`rounded-xl border px-4 py-3 text-sm ${estilos}`}
    >
      {children}
    </motion.div>
  );
}

export function Vazio({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col items-center gap-3 py-10 text-center"
    >
      <svg viewBox="0 0 48 48" className="h-9 w-9 text-texto-fraco/40" fill="none" aria-hidden>
        <circle cx="21" cy="21" r="12" stroke="currentColor" strokeWidth="2.5" />
        <path d="M30 30l9 9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <p className="max-w-sm text-sm text-texto-fraco">{children}</p>
    </motion.div>
  );
}

export function Carregando({ linhas = 3 }: { linhas?: number }) {
  return (
    <div className="space-y-3 py-6" role="status" aria-label="Carregando">
      <Esqueleto className="h-8 w-40" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Esqueleto key={i} className="h-20" arredondado="rounded-xl" />
        ))}
      </div>
      {Array.from({ length: linhas }).map((_, i) => (
        <Esqueleto key={i} className="h-4 w-full" />
      ))}
    </div>
  );
}
