import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import type { Corrida } from "../api/cliente";
import type { Evento } from "../api/eventos";
import { bytes, dominio, haceCuanto, numero } from "../util/formato";
import { Estado, Tarjeta, cx } from "./ui";

export const ETAPAS = [
  { clave: "descubrir", nombre: "Descubrir" },
  { clave: "explorar", nombre: "Explorar" },
  { clave: "descargar", nombre: "Descargar" },
  { clave: "extraer", nombre: "Extraer texto" },
  { clave: "fichar", nombre: "Ficha IA" },
  { clave: "ubicar", nombre: "Ubicar" },
  { clave: "indexar", nombre: "Indexar" },
];

export function cuentas(c: Corrida) {
  const sitios = Object.values(c.sitios).reduce((a, b) => a + b, 0);
  const e = c.candidatos_estado ?? {};
  return {
    sitios,
    explorados: sitios - (c.sitios.pendiente ?? 0),
    aceptados: (e.aceptado ?? 0) + (e.descargado ?? 0) + (e.fallido ?? 0),
    fallidos: e.fallido ?? 0,
    activas: Object.values(c.tareas).reduce((a, t) => a + (t.pendiente ?? 0) + (t.tomada ?? 0), 0),
    tareasFallidas: Object.values(c.tareas).reduce((a, t) => a + (t.fallida ?? 0), 0),
    fichas: Object.values(c.fichas ?? {}).reduce((a, b) => a + b, 0),
  };
}

/** Las etapas del pipeline con su avance. */
export function LineaPipeline({ c }: { c: Corrida }) {
  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      {ETAPAS.map(({ clave, nombre }) => {
        const t = c.tareas[clave] ?? {};
        const hechas = t.hecha ?? 0;
        const activas = (t.pendiente ?? 0) + (t.tomada ?? 0);
        const fallidas = t.fallida ?? 0;
        const total = hechas + activas + fallidas + (t.cancelada ?? 0);
        const enCurso = (t.tomada ?? 0) > 0;
        return (
          <li
            key={clave}
            className={cx(
              "rounded-xl border p-3",
              enCurso
                ? "border-sky-300 bg-sky-50 dark:border-sky-900 dark:bg-sky-950/50"
                : "border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900",
            )}
          >
            <div className="flex items-center justify-between gap-1 text-xs font-medium text-stone-500">
              {nombre}
              {enCurso ? (
                <Loader2 className="size-3.5 animate-spin text-sky-600" />
              ) : total > 0 && activas === 0 ? (
                <CheckCircle2 className="size-3.5 text-emerald-600" />
              ) : null}
            </div>
            <div className="mt-1 text-lg font-semibold tabular-nums">
              {numero(hechas)}
              {total > 0 && <span className="text-sm font-normal text-stone-400"> / {numero(total)}</span>}
            </div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-stone-100 dark:bg-stone-800">
              <div className="h-full bg-marca-500 transition-all" style={{ width: `${total ? (hechas / total) * 100 : 0}%` }} />
            </div>
            {fallidas > 0 && <div className="mt-1 text-xs text-rose-600 dark:text-rose-400">{fallidas} fallaron</div>}
          </li>
        );
      })}
    </ol>
  );
}

export function TarjetaCorrida({ c }: { c: Corrida }) {
  const n = cuentas(c);
  return (
    <Link to={`/corridas/${c.id}`} className="block">
      <Tarjeta className="p-4 transition-shadow hover:shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="font-mono text-xs text-stone-400">#{c.id}</span>
            <span className="truncate font-medium">{c.perfil}</span>
            <Estado valor={c.estado} />
          </div>
          <span className="text-xs text-stone-500">{haceCuanto(c.creada)}</span>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-3 text-sm sm:grid-cols-6">
          <Dato valor={`${numero(n.explorados)}/${numero(n.sitios)}`} nombre="sitios" />
          <Dato valor={numero(c.paginas)} nombre="páginas" />
          <Dato valor={numero(c.candidatos_total)} nombre="candidatos" />
          <Dato valor={numero(n.aceptados)} nombre="aceptados" />
          <Dato valor={numero(c.documentos)} nombre={`bajados · ${bytes(c.bytes)}`} />
          <Dato valor={numero(n.fichas)} nombre="fichas" />
        </div>
        {(c.error || n.tareasFallidas > 0) && (
          <p className="mt-2 flex items-center gap-1 text-xs text-rose-700 dark:text-rose-300">
            <AlertTriangle className="size-3.5" /> {c.error ?? `${n.tareasFallidas} tarea(s) fallaron`}
          </p>
        )}
      </Tarjeta>
    </Link>
  );
}

function Dato({ valor, nombre }: { valor: string; nombre: string }) {
  return (
    <div className="min-w-0">
      <div className="font-semibold tabular-nums">{valor}</div>
      <div className="truncate text-xs text-stone-500">{nombre}</div>
    </div>
  );
}

function describir(e: Evento): { texto: string; tono: "ok" | "error" | "info" | "neutro"; enlace?: string } {
  switch (e.tipo) {
    case "sitio":
      return {
        texto: `${e.dominio}: ${e.estado === "explorado" ? `${e.paginas} páginas, ${e.documentos} documentos` : String(e.estado).replace("_", " ")}`,
        tono: e.estado === "explorado" ? "info" : "neutro",
      };
    case "descarga":
      return e.estado === "descargado"
        ? { texto: `Bajado de ${dominio(e.url as string)} (${bytes(e.bytes as number)})${e.respaldo ? " · Internet Archive" : ""}`, tono: "ok", enlace: `/documentos/${e.documento_id}` }
        : { texto: `No se pudo bajar de ${dominio(e.url as string)}: ${e.motivo}`, tono: "error" };
    case "ficha":
      return {
        texto: `Ficha ${e.estado === "ok" ? "lista" : e.estado === "revision" ? "por revisar" : e.estado}: ${e.titulo ?? `documento ${e.documento_id}`}`,
        tono: e.estado === "ok" ? "ok" : e.estado === "revision" ? "neutro" : "error",
        enlace: `/documentos/${e.documento_id}`,
      };
    case "lugar":
      return {
        texto: e.lugar ? `Ubicado en ${e.lugar}` : e.estado === "ambiguo" ? "Lugar ambiguo: elige uno en Revisión" : "Sin lugar en el documento",
        tono: e.lugar ? "info" : "neutro",
        enlace: `/documentos/${e.documento_id}`,
      };
    case "corrida":
      return { texto: `Corrida #${e.corrida_id} ${e.estado === "corriendo" ? "en curso" : e.estado}`, tono: "info", enlace: `/corridas/${e.corrida_id}` };
    case "tarea":
      return e.estado === "fallida"
        ? { texto: `Falló una tarea de ${e.etapa}: ${e.error ?? ""}`, tono: "error" }
        : { texto: `${e.etapa}: tarea ${e.estado}`, tono: "neutro" };
    default:
      return { texto: e.tipo, tono: "neutro" };
  }
}

const PUNTO = { ok: "bg-emerald-500", error: "bg-rose-500", info: "bg-sky-500", neutro: "bg-stone-400" };

/** Lo último que pasó (eventos en vivo). Las tareas terminadas sin novedad no se muestran. */
export function Actividad({ eventos, limite = 15 }: { eventos: Evento[]; limite?: number }) {
  const visibles = eventos.filter((e) => !(e.tipo === "tarea" && e.estado !== "fallida")).slice(0, limite);
  if (!visibles.length) return <p className="py-6 text-center text-sm text-stone-500">Aquí aparece lo que va pasando mientras corre algo.</p>;
  return (
    <ul className="divide-y divide-stone-100 dark:divide-stone-800">
      {visibles.map((e, i) => {
        const { texto, tono, enlace } = describir(e);
        const contenido = (
          <span className="flex items-start gap-2 py-2 text-sm">
            <span className={cx("mt-1.5 size-1.5 shrink-0 rounded-full", PUNTO[tono])} />
            <span className="min-w-0 flex-1 break-words">{texto}</span>
            <span className="shrink-0 text-xs text-stone-400">{haceCuanto(e.recibido)}</span>
          </span>
        );
        return <li key={`${e.recibido}-${i}`}>{enlace ? <Link to={enlace} className="block hover:text-marca-700 dark:hover:text-marca-100">{contenido}</Link> : contenido}</li>;
      })}
    </ul>
  );
}
