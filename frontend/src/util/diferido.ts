import { useEffect, useState } from "react";

/** El valor, pero solo después de que deja de cambiar (para no buscar en cada tecla). */
export function useDiferido<T>(valor: T, ms = 350): T {
  const [diferido, setDiferido] = useState(valor);
  useEffect(() => {
    const t = setTimeout(() => setDiferido(valor), ms);
    return () => clearTimeout(t);
  }, [valor, ms]);
  return diferido;
}
