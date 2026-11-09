import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, FileText, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/cliente";
import { useCandidatos } from "../api/consultas";
import { useDiferido } from "../util/diferido";
import { dominio, numero } from "../util/formato";
import { Boton, Cargando, Entrada, Estado, Insignia, Paginacion, Selector, Tarjeta, Vacio, cx } from "./ui";

const LIMITE = 50;

function Puntaje({ valor }: { valor: number | null }) {
  if (valor == null) return <span className="text-stone-400">—</span>;
  const color = valor >= 80 ? "bg-emerald-500" : valor >= 60 ? "bg-marca-500" : valor >= 40 ? "bg-amber-500" : "bg-stone-300 dark:bg-stone-600";
  return (
    <span className="flex items-center gap-2">
      <span className="w-7 text-right tabular-nums">{valor}</span>
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-stone-100 dark:bg-stone-800">
        <span className={cx("block h-full", color)} style={{ width: `${valor}%` }} />
      </span>
    </span>
  );
}

/** Candidatos con filtros y acciones manuales. `fijos` se aplican siempre (p. ej. la corrida). */
export default function TablaCandidatos({ fijos = {}, perfiles }: { fijos?: Record<string, string | number>; perfiles?: string[] }) {
  const [estado, setEstado] = useState("");
  const [perfil, setPerfil] = useState("");
  const [texto, setTexto] = useState("");
  const [desde, setDesde] = useState(0);
  const q = useDiferido(texto);
  const filtros = { ...fijos, estado, perfil, q, limite: LIMITE, desde };
  const { data, isLoading, isFetching } = useCandidatos(filtros);
  const qc = useQueryClient();
  const cambiar = useMutation({
    mutationFn: ({ id, nuevo }: { id: number; nuevo: "aceptado" | "rechazado" }) => api.cambiarCandidato(id, nuevo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidatos"] });
      qc.invalidateQueries({ queryKey: ["corrida"] });
    },
  });
  const filtrar = (f: () => void) => {
    f();
    setDesde(0);
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2">
        <Entrada className="max-w-xs" placeholder="Buscar en URL o texto del enlace…" value={texto} onChange={(e) => filtrar(() => setTexto(e.target.value))} />
        <Selector className="w-auto" value={estado} onChange={(e) => filtrar(() => setEstado(e.target.value))} aria-label="Estado">
          <option value="">Todos los estados</option>
          <option value="aceptado">Aceptados (por bajar)</option>
          <option value="descargado">Descargados</option>
          <option value="rechazado">Rechazados</option>
          <option value="fallido">Fallidos</option>
        </Selector>
        {perfiles && perfiles.length > 1 && (
          <Selector className="w-auto" value={perfil} onChange={(e) => filtrar(() => setPerfil(e.target.value))} aria-label="Perfil">
            <option value="">Todos los perfiles</option>
            {perfiles.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </Selector>
        )}
        {isFetching && !isLoading && <span className="self-center text-xs text-stone-400">actualizando…</span>}
      </div>

      {isLoading ? (
        <Cargando />
      ) : !data?.elementos.length ? (
        <Vacio titulo="No hay candidatos con esos filtros" />
      ) : (
        <Tarjeta className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-stone-200 bg-stone-50 text-left text-xs text-stone-500 dark:border-stone-800 dark:bg-stone-900/60">
                <tr>
                  <th className="px-3 py-2 font-medium">Puntaje</th>
                  <th className="px-3 py-2 font-medium">Documento</th>
                  <th className="px-3 py-2 font-medium">Estado</th>
                  <th className="px-3 py-2 font-medium">Fuente</th>
                  <th className="px-3 py-2 text-right font-medium">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
                {data.elementos.map((c) => (
                  <tr key={c.id} className="align-top">
                    <td className="px-3 py-2.5">
                      <Puntaje valor={c.puntaje} />
                    </td>
                    <td className="max-w-md px-3 py-2.5">
                      <div className="line-clamp-2 font-medium">{c.ancla || decodeURIComponent(c.url.split("/").pop() || c.url)}</div>
                      <a href={c.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 truncate text-xs text-stone-500 hover:text-marca-700">
                        {dominio(c.url)} <ExternalLink className="size-3 shrink-0" />
                      </a>
                      {c.motivo && <div className="mt-0.5 text-xs text-stone-400">{c.motivo}</div>}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        <Estado valor={c.estado} />
                        {c.tipo && <Insignia tono="marca">{c.tipo}</Insignia>}
                        {c.nuevo && <Insignia tono="info">nuevo</Insignia>}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-stone-500">{c.fuente}</td>
                    <td className="px-3 py-2.5">
                      <div className="flex justify-end gap-1">
                        {c.documento_id ? (
                          <Link to={`/documentos/${c.documento_id}`}>
                            <Boton tamano="sm" icono={<FileText className="size-3.5" />}>
                              Ver
                            </Boton>
                          </Link>
                        ) : (
                          <>
                            {c.estado !== "aceptado" && (
                              <Boton tamano="sm" title="Aceptar y descargar" icono={<Check className="size-3.5" />} onClick={() => cambiar.mutate({ id: c.id, nuevo: "aceptado" })}>
                                Aceptar
                              </Boton>
                            )}
                            {c.estado !== "rechazado" && (
                              <Boton tamano="sm" variante="fantasma" title="Rechazar" icono={<X className="size-3.5" />} onClick={() => cambiar.mutate({ id: c.id, nuevo: "rechazado" })}>
                                <span className="sr-only">Rechazar</span>
                              </Boton>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Tarjeta>
      )}
      {data && (
        <>
          <Paginacion total={data.total} limite={LIMITE} desde={desde} alCambiar={setDesde} />
          {data.total <= LIMITE && data.total > 0 && <p className="mt-3 text-xs text-stone-400">{numero(data.total)} candidato(s)</p>}
        </>
      )}
    </div>
  );
}
