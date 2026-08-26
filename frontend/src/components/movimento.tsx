import { animate, useReducedMotion, type Easing, type Transition, type Variants } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Vocabulario de movimento do produto.
 *
 * Duas regras que valem para tudo aqui:
 *  1. movimento curto e com assentamento longo (a curva "expo out") — e o que
 *     da sensacao de peso; animacao linear parece brinquedo;
 *  2. quem liga "reduzir movimento" no sistema operacional nao recebe
 *     transform nenhum, so opacidade. Isso nao e opcional: movimento grande
 *     causa enjoo em quem tem sensibilidade vestibular.
 */

export const EXPO: Easing = [0.16, 1, 0.3, 1];

export const RAPIDO: Transition = { duration: 0.22, ease: EXPO };
export const NORMAL: Transition = { duration: 0.36, ease: EXPO };
export const LENTO: Transition = { duration: 0.6, ease: EXPO };

/** Container que escalona a entrada dos filhos. */
export const listaVariantes: Variants = {
  oculto: {},
  visivel: { transition: { staggerChildren: 0.045, delayChildren: 0.04 } },
  saida: { transition: { staggerChildren: 0.015, staggerDirection: -1 } },
};

/** Item que sobe e aparece. */
export const itemVariantes: Variants = {
  oculto: { opacity: 0, y: 10 },
  visivel: { opacity: 1, y: 0, transition: NORMAL },
  saida: { opacity: 0, y: -6, transition: RAPIDO },
};

/** Pagina inteira entrando/saindo. */
export const paginaVariantes: Variants = {
  oculto: { opacity: 0, y: 8, filter: "blur(2px)" },
  visivel: { opacity: 1, y: 0, filter: "blur(0px)", transition: NORMAL },
  saida: { opacity: 0, y: -8, filter: "blur(2px)", transition: RAPIDO },
};

/** Versoes sem deslocamento, para quem pediu menos movimento. */
export const semMovimento: Variants = {
  oculto: { opacity: 0 },
  visivel: { opacity: 1, transition: { duration: 0.15 } },
  saida: { opacity: 0, transition: { duration: 0.1 } },
};

export function useVariantes(padrao: Variants): Variants {
  return useReducedMotion() ? semMovimento : padrao;
}

/**
 * Numero que conta ate o valor. Usado nos KPIs.
 *
 * Conta so quando o valor MUDA de verdade e a diferenca justifica: animar
 * 0 -> 0 em toda re-renderizacao seria ruido visual.
 */
export function NumeroAnimado({
  valor,
  casas = 0,
  prefixo = "",
  sufixo = "",
  duracao = 0.9,
  className = "",
}: {
  valor: number;
  casas?: number;
  prefixo?: string;
  sufixo?: string;
  duracao?: number;
  className?: string;
}) {
  const reduzido = useReducedMotion();
  const [mostrado, setMostrado] = useState(valor);
  const anterior = useRef(valor);

  useEffect(() => {
    const de = anterior.current;
    anterior.current = valor;
    if (reduzido || de === valor) {
      setMostrado(valor);
      return;
    }
    const controle = animate(de, valor, {
      duration: duracao,
      ease: EXPO,
      onUpdate: (v) => setMostrado(v),
    });
    return () => controle.stop();
  }, [valor, duracao, reduzido]);

  const texto = mostrado.toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });
  return (
    <span className={`num ${className}`}>
      {prefixo}
      {texto}
      {sufixo}
    </span>
  );
}

/** Barra que cresce ate a porcentagem, com atraso opcional para escalonar. */
export function BarraAnimada({
  pct,
  cor = "bg-marca",
  atraso = 0,
  altura = "h-1.5",
  className = "",
}: {
  pct: number;
  cor?: string;
  atraso?: number;
  altura?: string;
  className?: string;
}) {
  const reduzido = useReducedMotion();
  const alvo = Math.max(0, Math.min(100, pct));
  const [largura, setLargura] = useState(reduzido ? alvo : 0);

  useEffect(() => {
    if (reduzido) {
      setLargura(alvo);
      return;
    }
    const t = setTimeout(() => setLargura(alvo), atraso * 1000);
    return () => clearTimeout(t);
  }, [alvo, atraso, reduzido]);

  return (
    <div className={`${altura} overflow-hidden rounded-full bg-superficie-3 ${className}`}>
      <div
        className={`${altura} rounded-full ${cor}`}
        style={{
          width: `${largura}%`,
          transition: reduzido ? "none" : "width 900ms cubic-bezier(0.16,1,0.3,1)",
        }}
      />
    </div>
  );
}

/** Esqueleto de carregamento — melhor que "carregando..." em texto. */
export function Esqueleto({
  className = "h-4 w-full",
  arredondado = "rounded-md",
}: {
  className?: string;
  arredondado?: string;
}) {
  return <div className={`cintilar ${arredondado} ${className}`} aria-hidden />;
}

export function LinhasEsqueleto({ linhas = 3 }: { linhas?: number }) {
  return (
    <div className="space-y-2.5" role="status" aria-label="Carregando">
      {Array.from({ length: linhas }).map((_, i) => (
        <Esqueleto key={i} className={`h-4 ${i === linhas - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

/** Envolve conteudo que deve aparecer quando entra na tela. */
export function Revelar({
  children,
  atraso = 0,
  className = "",
}: {
  children: ReactNode;
  atraso?: number;
  className?: string;
}) {
  const reduzido = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [visivel, setVisivel] = useState(false);

  useEffect(() => {
    if (reduzido) {
      setVisivel(true);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entrada]) => {
        if (entrada.isIntersecting) {
          setVisivel(true);
          obs.disconnect();
        }
      },
      { threshold: 0.12 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [reduzido]);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: visivel ? 1 : 0,
        transform: visivel || reduzido ? "none" : "translateY(14px)",
        transition: reduzido
          ? "none"
          : `opacity 600ms cubic-bezier(0.16,1,0.3,1) ${atraso}s, transform 600ms cubic-bezier(0.16,1,0.3,1) ${atraso}s`,
      }}
    >
      {children}
    </div>
  );
}
