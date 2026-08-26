import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Renderiza o conteudo direto no <body>.
 *
 * Necessario para qualquer sobreposicao (modal, gaveta, dica flutuante).
 *
 * O motivo e uma armadilha do CSS: um elemento com `transform` cria um novo
 * containing block, e `position: fixed` dentro dele passa a se posicionar em
 * relacao a esse elemento, NAO a janela. Como a transicao de pagina anima
 * `y` (que vira transform), todo modal dentro dela era empurrado para fora da
 * tela — media-se `top: 802px` com a janela de 798px de altura: invisivel,
 * mas presente e bloqueando a interacao.
 *
 * Portal resolve na raiz: fora da arvore transformada, `fixed` volta a ser
 * relativo a janela.
 */
export default function Portal({ children }: { children: ReactNode }) {
  const [montado, setMontado] = useState(false);

  // So renderiza depois da montagem: no primeiro passo o document pode nao
  // estar disponivel (renderizacao no servidor, testes).
  useEffect(() => {
    setMontado(true);
  }, []);

  if (!montado) return null;
  return createPortal(children, document.body);
}
