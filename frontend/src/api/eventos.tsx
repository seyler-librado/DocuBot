// Eventos en vivo por WebSocket (/api/eventos). Cada evento refresca las consultas afectadas.

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Evento = {
  tipo: string;
  corrida_id?: number | null;
  recibido: number;
  [clave: string]: unknown;
};

type Estado = { conectado: boolean; eventos: Evento[] };
const Contexto = createContext<Estado>({ conectado: false, eventos: [] });

function clavesDe(e: Evento): string[] {
  const base = ["corridas", "corrida", "resumen"];
  switch (e.tipo) {
    case "sitio":
      return [...base, "sitios"];
    case "descarga":
    case "ficha":
      return [...base, "documentos", "documento", "fichas", "candidatos"];
    case "lugar":
      return ["mapa", "documento", "dudosos", "documentos"];
    case "tarea":
      if (e.etapa === "indexar") return [...base, "busqueda"];
      return e.etapa === "descubrir" || e.etapa === "explorar" ? [...base, "candidatos"] : base;
    default:
      return base;
  }
}

export function ProveedorEventos({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [estado, setEstado] = useState<Estado>({ conectado: false, eventos: [] });

  useEffect(() => {
    let ws: WebSocket | undefined;
    let cerrado = false;
    let reintento: ReturnType<typeof setTimeout> | undefined;
    let lote: ReturnType<typeof setTimeout> | undefined;
    const pendientes = new Set<string>();

    // durante una corrida llegan muchos eventos: se refresca en lotes, no en cada uno
    const invalidar = (claves: string[]) => {
      claves.forEach((c) => pendientes.add(c));
      if (lote) return;
      lote = setTimeout(() => {
        pendientes.forEach((c) => qc.invalidateQueries({ queryKey: [c] }));
        pendientes.clear();
        lote = undefined;
      }, 1200);
    };

    const conectar = () => {
      const protocolo = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${protocolo}://${location.host}/api/eventos`);
      ws.onopen = () => setEstado((s) => ({ ...s, conectado: true }));
      ws.onclose = () => {
        setEstado((s) => ({ ...s, conectado: false }));
        if (!cerrado) reintento = setTimeout(conectar, 3000);
      };
      ws.onmessage = (mensaje) => {
        let e: Evento;
        try {
          e = { ...JSON.parse(mensaje.data), recibido: Date.now() };
        } catch {
          return;
        }
        if (e.tipo === "ping") return;
        setEstado((s) => ({ ...s, eventos: [e, ...s.eventos].slice(0, 200) }));
        invalidar(clavesDe(e));
      };
    };

    conectar();
    return () => {
      cerrado = true;
      clearTimeout(reintento);
      clearTimeout(lote);
      ws?.close();
    };
  }, [qc]);

  return <Contexto.Provider value={estado}>{children}</Contexto.Provider>;
}

export const useEventos = () => useContext(Contexto);
