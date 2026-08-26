/** @type {import('tailwindcss').Config} */

/* Cada cor aponta para um token CSS. O `<alpha-value>` deixa o Tailwind
   aplicar opacidade normalmente (ex.: bg-superficie/60). */
const token = (nome) => `rgb(var(--cor-${nome}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        fundo: token("fundo"),
        superficie: token("superficie"),
        "superficie-2": token("superficie-2"),
        "superficie-3": token("superficie-3"),
        borda: token("borda"),
        "borda-forte": token("borda-forte"),

        texto: token("texto"),
        "texto-medio": token("texto-medio"),
        "texto-fraco": token("texto-fraco"),

        marca: {
          DEFAULT: token("marca"),
          forte: token("marca-forte"),
          fraca: token("marca-fraca"),
        },
        acento: token("acento"),

        positivo: token("positivo"),
        "positivo-fraco": token("positivo-fraco"),
        atencao: token("atencao"),
        "atencao-fraco": token("atencao-fraco"),
        perigo: token("perigo"),
        "perigo-fraco": token("perigo-fraco"),
        "neutro-fraco": token("neutro-fraco"),
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        marca: ["'Instrument Serif'", "ui-serif", "Georgia", "serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        1: "var(--sombra-1)",
        2: "var(--sombra-2)",
        3: "var(--sombra-3)",
        marca: "var(--brilho-marca)",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      transitionTimingFunction: {
        // "Expo out": rapido no inicio, assentamento longo. E o que da
        // sensacao de peso e qualidade no movimento.
        expo: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      letterSpacing: {
        rotulo: "0.08em",
      },
      keyframes: {
        surgir: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "none" },
        },
      },
      animation: {
        surgir: "surgir 400ms cubic-bezier(0.16, 1, 0.3, 1) both",
      },
    },
  },
  plugins: [],
};
