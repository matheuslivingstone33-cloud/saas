/** Formatadores pt-BR. */

export function moeda(reais: number): string {
  return reais.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function numero(valor: number): string {
  return valor.toLocaleString("pt-BR");
}

/** Tokens em escala legivel: 850 mil, 2,4 mi. */
export function tokens(valor: number): string {
  if (valor >= 1_000_000) return `${(valor / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} mi`;
  if (valor >= 1_000) return `${(valor / 1_000).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} mil`;
  return numero(valor);
}

export function dataHora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
