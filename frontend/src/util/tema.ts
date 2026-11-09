import { useEffect, useState } from "react";

export type Tema = "claro" | "oscuro" | "sistema";

function leer(): Tema {
  try {
    const t = localStorage.getItem("tema");
    return t === "claro" || t === "oscuro" ? t : "sistema";
  } catch {
    return "sistema";
  }
}

export function aplicarTema(tema: Tema) {
  const oscuro = tema === "oscuro" || (tema === "sistema" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", oscuro);
}

export function useTema(): [Tema, (t: Tema) => void] {
  const [tema, setTema] = useState<Tema>(leer);
  useEffect(() => {
    aplicarTema(tema);
    try {
      localStorage.setItem("tema", tema);
    } catch {
      /* sin almacenamiento: el tema dura la sesión */
    }
    if (tema !== "sistema") return;
    const m = matchMedia("(prefers-color-scheme: dark)");
    const alCambiar = () => aplicarTema("sistema");
    m.addEventListener("change", alCambiar);
    return () => m.removeEventListener("change", alCambiar);
  }, [tema]);
  return [tema, setTema];
}
