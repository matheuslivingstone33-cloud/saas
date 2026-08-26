import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { EXPO } from "./movimento";

/**
 * Abertura do aplicativo.
 *
 * O traco do logo se desenha, a marca aparece letra a letra e a cortina sobe
 * revelando o app. Roda UMA VEZ por aba (sessionStorage): abertura bonita que
 * se repete a cada clique vira pedagio.
 *
 * Com "reduzir movimento" ligado, nao ha abertura — o app entra direto.
 */

const CHAVE = "prospector:abertura-vista";
const NOME = "Prospector";

export function useAbertura(): boolean {
  const reduzido = useReducedMotion();
  const [mostrar, setMostrar] = useState(() => {
    if (typeof sessionStorage === "undefined") return false;
    return sessionStorage.getItem(CHAVE) !== "1";
  });

  useEffect(() => {
    if (reduzido && mostrar) {
      sessionStorage.setItem(CHAVE, "1");
      setMostrar(false);
    }
  }, [reduzido, mostrar]);

  return mostrar && !reduzido;
}

export function marcarAberturaVista(): void {
  try {
    sessionStorage.setItem(CHAVE, "1");
  } catch {
    /* sessionStorage indisponivel: a abertura simplesmente repete */
  }
}

export default function Abertura({ aoTerminar }: { aoTerminar: () => void }) {
  const [saindo, setSaindo] = useState(false);

  useEffect(() => {
    const t1 = setTimeout(() => setSaindo(true), 1650);
    const t2 = setTimeout(() => {
      marcarAberturaVista();
      aoTerminar();
    }, 2300);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [aoTerminar]);

  return (
    <AnimatePresence>
      {!saindo && (
        <motion.div
          key="abertura"
          className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-fundo"
          exit={{ y: "-100%", transition: { duration: 0.75, ease: EXPO } }}
        >
          {/* Aura que respira atras do logo */}
          <motion.div
            className="aura h-[28rem] w-[28rem]"
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 0.3, scale: 1 }}
            transition={{ duration: 1.4, ease: EXPO }}
          />

          <div className="relative flex flex-col items-center gap-6">
            <motion.svg
              viewBox="0 0 64 64"
              className="h-16 w-16"
              initial={{ opacity: 0, scale: 0.85, rotate: -8 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              transition={{ duration: 0.8, ease: EXPO }}
            >
              {/* A lente do prospector: circulo que se desenha + cabo */}
              <motion.circle
                cx="27"
                cy="27"
                r="15"
                fill="none"
                stroke="rgb(var(--cor-marca))"
                strokeWidth="4.5"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1, ease: EXPO, delay: 0.15 }}
              />
              <motion.line
                x1="38"
                y1="38"
                x2="53"
                y2="53"
                stroke="rgb(var(--cor-acento))"
                strokeWidth="5"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.5, ease: EXPO, delay: 0.85 }}
              />
              {/* Ponto que pulsa dentro da lente: o lead encontrado */}
              <motion.circle
                cx="27"
                cy="27"
                r="4"
                fill="rgb(var(--cor-acento))"
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: [0, 1.5, 1], opacity: [0, 1, 1] }}
                transition={{ duration: 0.7, ease: EXPO, delay: 1.05 }}
              />
            </motion.svg>

            <div className="flex overflow-hidden">
              {NOME.split("").map((letra, i) => (
                <motion.span
                  key={i}
                  className="font-marca text-3xl tracking-tight text-texto"
                  initial={{ y: "110%", opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ duration: 0.6, ease: EXPO, delay: 0.5 + i * 0.035 }}
                >
                  {letra}
                </motion.span>
              ))}
              <motion.span
                className="ml-2 self-center rounded-full border border-marca/40 px-2 py-0.5 text-[10px] font-medium uppercase tracking-rotulo text-marca"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5, ease: EXPO, delay: 1.05 }}
              >
                AI
              </motion.span>
            </div>

            <motion.div
              className="h-px w-40 origin-left bg-gradient-to-r from-transparent via-borda-forte to-transparent"
              initial={{ scaleX: 0, opacity: 0 }}
              animate={{ scaleX: 1, opacity: 1 }}
              transition={{ duration: 0.8, ease: EXPO, delay: 1.15 }}
            />

            <motion.p
              className="text-xs text-texto-fraco"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 1.3 }}
            >
              descobrindo quem precisa do seu serviço
            </motion.p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
