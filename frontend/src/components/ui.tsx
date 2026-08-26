import type { ReactNode } from "react";

/** Primitivas visuais. Nada de biblioteca de componentes: o app e pequeno. */

export function Card({
  titulo,
  acao,
  children,
  className = "",
}: {
  titulo?: string;
  acao?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}
    >
      {(titulo || acao) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
          {titulo && (
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
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

export function Stat({
  rotulo,
  valor,
  nota,
  destaque,
}: {
  rotulo: string;
  valor: string | number;
  nota?: string;
  destaque?: "positivo" | "atencao" | "neutro";
}) {
  const cor =
    destaque === "positivo"
      ? "text-emerald-700"
      : destaque === "atencao"
        ? "text-amber-700"
        : "text-slate-900";
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{rotulo}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${cor}`}>{valor}</div>
      {nota && <div className="mt-0.5 text-xs text-slate-400">{nota}</div>}
    </div>
  );
}

const CORES_BADGE: Record<string, string> = {
  descoberto: "bg-slate-100 text-slate-700",
  qualificado: "bg-sky-100 text-sky-800",
  enfileirado: "bg-indigo-100 text-indigo-800",
  abordado: "bg-violet-100 text-violet-800",
  respondido: "bg-emerald-100 text-emerald-800",
  convertido: "bg-emerald-600 text-white",
  opt_out: "bg-rose-100 text-rose-800",
  descartado: "bg-slate-100 text-slate-500",
  aguardando_aprovacao: "bg-amber-100 text-amber-900",
  aprovada: "bg-sky-100 text-sky-800",
  enviada: "bg-emerald-100 text-emerald-800",
  bloqueada: "bg-rose-100 text-rose-800",
  rejeitada: "bg-slate-200 text-slate-600",
  falhou: "bg-rose-100 text-rose-800",
  rascunho: "bg-slate-100 text-slate-600",
  descobrindo: "bg-sky-100 text-sky-800",
  qualificando: "bg-indigo-100 text-indigo-800",
  pronta: "bg-amber-100 text-amber-900",
  executando: "bg-violet-100 text-violet-800",
  concluida: "bg-emerald-100 text-emerald-800",
  pausada: "bg-amber-100 text-amber-900",
  mock: "bg-slate-100 text-slate-600",
  real: "bg-emerald-100 text-emerald-800",
};

export function Badge({ children, tom }: { children: string; tom?: string }) {
  const classe = CORES_BADGE[tom ?? children] ?? "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${classe}`}>
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
}: {
  children: ReactNode;
  onClick?: () => void;
  variante?: "primario" | "secundario" | "perigo" | "fantasma";
  disabled?: boolean;
  tamanho?: "sm" | "md";
  type?: "button" | "submit";
}) {
  const base =
    "inline-flex items-center justify-center rounded-md font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
  const dimensao = tamanho === "sm" ? "px-3 py-1 text-xs" : "px-4 py-2 text-sm";
  const estilos = {
    primario: "bg-marca-500 text-white hover:bg-marca-600",
    secundario: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
    perigo: "border border-rose-300 bg-white text-rose-700 hover:bg-rose-50",
    fantasma: "text-slate-500 hover:text-slate-800",
  }[variante];
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${dimensao} ${estilos}`}>
      {children}
    </button>
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
    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-marca-500 focus:ring-1 focus:ring-marca-500";
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{rotulo}</span>
      {multiline ? (
        <textarea
          className={`${classe} min-h-[5rem]`}
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
      {ajuda && <span className="mt-1 block text-xs text-slate-400">{ajuda}</span>}
    </label>
  );
}

export function BarraScore({ valor }: { valor: number }) {
  const pct = Math.max(0, Math.min(100, valor));
  const cor = pct >= 60 ? "bg-emerald-500" : pct >= 35 ? "bg-amber-500" : "bg-slate-300";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full ${cor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums text-xs text-slate-600">{pct.toFixed(0)}</span>
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
    info: "border-sky-200 bg-sky-50 text-sky-900",
    erro: "border-rose-200 bg-rose-50 text-rose-900",
    sucesso: "border-emerald-200 bg-emerald-50 text-emerald-900",
    atencao: "border-amber-200 bg-amber-50 text-amber-900",
  }[tom];
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${estilos}`}>{children}</div>
  );
}

export function Vazio({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-slate-400">{children}</p>;
}

export function Carregando() {
  return <p className="py-8 text-center text-sm text-slate-400">carregando...</p>;
}
