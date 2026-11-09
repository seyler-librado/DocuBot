import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, MapPin, Pause, Play, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/cliente";
import { useCorrida, useDocumentos, useFallas, useSitios } from "../api/consultas";
import { useEventos } from "../api/eventos";
import { Actividad, LineaPipeline, cuentas } from "../componentes/corridas";
import { CuadriculaDocumentos } from "../componentes/documentos";
import TablaCandidatos from "../componentes/TablaCandidatos";
import { Aviso, Boton, Cargando, Cifra, Encabezado, Estado, Insignia, Paginacion, Pestanas, Tarjeta, Vacio } from "../componentes/ui";
import { bytes, duracion, fecha, numero } from "../util/formato";

type Vista = "actividad" | "sitios" | "candidatos" | "documentos" | "fallas";

function Sitios({ id }: { id: number }) {
  const { data, isLoading } = useSitios(id);
  if (isLoading) return <Cargando />;
  if (!data?.length) return <Vacio titulo="Esta corrida no ha registrado sitios" />;
  return (
    <Tarjeta className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-left text-xs text-stone-500 dark:border-stone-800 dark:bg-stone-900/60">
            <tr>
              <th className="px-3 py-2 font-medium">Sitio</th>
              <th className="px-3 py-2 font-medium">Estado</th>
              <th className="px-3 py-2 text-right font-medium">Páginas</th>
              <th className="px-3 py-2 text-right font-medium">Documentos</th>
              <th className="px-3 py-2 font-medium">Origen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
            {data.map((s) => (
              <tr key={s.sitio_id}>
                <td className="px-3 py-2">
                  <a href={`https://${s.dominio}`} target="_blank" rel="noreferrer" className="font-medium hover:text-marca-700">
                    {s.dominio}
                  </a>
                  {s.error && <div className="max-w-sm truncate text-xs text-stone-400" title={s.error}>{s.error}</div>}
                </td>
                <td className="px-3 py-2">
                  <Estado valor={s.estado} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{numero(s.paginas)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{numero(s.documentos)}</td>
                <td className="px-3 py-2 text-xs text-stone-500">
                  {s.origen}
                  {s.lugar && <Insignia className="ml-1">{s.lugar}</Insignia>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Tarjeta>
  );
}

function Documentos({ id }: { id: number }) {
  const [desde, setDesde] = useState(0);
  const { data, isLoading } = useDocumentos({ corrida: id, limite: 20, desde });
  if (isLoading) return <Cargando />;
  if (!data?.elementos.length) return <Vacio titulo="Esta corrida no ha descargado documentos" />;
  return (
    <>
      <CuadriculaDocumentos documentos={data.elementos} />
      <Paginacion total={data.total} limite={20} desde={desde} alCambiar={setDesde} />
    </>
  );
}

function Fallas({ id }: { id: number }) {
  const { data, isLoading } = useFallas(id);
  if (isLoading) return <Cargando />;
  if (!data?.length) return <Vacio titulo="Ninguna tarea falló" />;
  return (
    <Tarjeta className="divide-y divide-stone-100 dark:divide-stone-800">
      {data.map((f) => (
        <div key={f.id} className="px-4 py-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Insignia tono="error">{f.etapa}</Insignia>
            <span className="text-xs text-stone-500">{f.intentos} intento(s) · {fecha(f.terminada)}</span>
          </div>
          <p className="mt-1 break-words font-mono text-xs text-stone-600 dark:text-stone-300">{f.error}</p>
        </div>
      ))}
    </Tarjeta>
  );
}

export default function CorridaDetalle() {
  const id = Number(useParams().id);
  const { data: c, isLoading, error } = useCorrida(id);
  const { eventos } = useEventos();
  const [vista, setVista] = useState<Vista>("actividad");
  const qc = useQueryClient();
  const accion = useMutation({
    mutationFn: (f: () => Promise<unknown>) => f(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["corrida", id] }),
  });

  if (isLoading) return <Cargando />;
  if (error || !c) return <Aviso>No existe la corrida #{id}.</Aviso>;
  const n = cuentas(c);
  const porBajar = c.candidatos_estado?.aceptado ?? 0;
  const propias = eventos.filter((e) => e.corrida_id === id);
  const cambios = Object.entries(c.cambios ?? {});

  return (
    <div>
      <Link to="/corridas" className="mb-3 inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-800 dark:hover:text-stone-200">
        <ArrowLeft className="size-4" /> Corridas
      </Link>
      <Encabezado
        titulo={
          <span className="flex flex-wrap items-center gap-2">
            Corrida #{c.id} <Estado valor={c.estado} />
          </span>
        }
        subtitulo={
          <>
            Perfil <Link className="text-marca-700 hover:underline dark:text-marca-100" to={`/perfiles/${encodeURIComponent(c.perfil)}`}>{c.perfil}</Link> ·{" "}
            empezó {fecha(c.iniciada)} · {c.estado === "corriendo" ? "lleva" : "duró"} {duracion(c.iniciada, c.terminada)}
          </>
        }
        acciones={
          <>
            {c.estado === "corriendo" && (
              <Boton icono={<Pause className="size-4" />} cargando={accion.isPending} onClick={() => accion.mutate(() => api.detener(id))}>
                Detener
              </Boton>
            )}
            {c.estado === "detenida" && (
              <Boton icono={<Play className="size-4" />} cargando={accion.isPending} onClick={() => accion.mutate(() => api.reanudar(id))}>
                Reanudar
              </Boton>
            )}
            {porBajar > 0 && c.estado !== "corriendo" && (
              <Boton icono={<Download className="size-4" />} onClick={() => accion.mutate(() => api.descargarCorrida(id))}>
                Bajar {numero(porBajar)} aceptados
              </Boton>
            )}
            {c.documentos > 0 && c.estado !== "corriendo" && (
              <Boton icono={<Sparkles className="size-4" />} onClick={() => accion.mutate(() => api.fichasCorrida(id))}>
                Fichas faltantes
              </Boton>
            )}
            {c.documentos > 0 && c.estado !== "corriendo" && (
              <Boton variante="fantasma" icono={<MapPin className="size-4" />} onClick={() => accion.mutate(() => api.ubicarCorrida(id))}>
                Ubicar de nuevo
              </Boton>
            )}
          </>
        }
      />
      {accion.isError && (
        <div className="mt-4">
          <Aviso>{(accion.error as Error).message}</Aviso>
        </div>
      )}
      {(c.error || cambios.length > 0 || !c.descargar) && (
        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          {c.error && <Insignia tono="error">{c.error}</Insignia>}
          {!c.descargar && <Insignia>sin descarga</Insignia>}
          {cambios.map(([k, v]) => (
            <Insignia key={k} tono="aviso">
              {k.replace(/_/g, " ")}: {String(v)}
            </Insignia>
          ))}
        </div>
      )}

      <div className="mt-6">
        <LineaPipeline c={c} />
      </div>

      <Tarjeta className="mt-4 grid grid-cols-3 gap-5 p-5 sm:grid-cols-6">
        <Cifra valor={`${numero(n.explorados)}/${numero(n.sitios)}`} nombre="sitios" />
        <Cifra valor={numero(c.paginas)} nombre="páginas" />
        <Cifra valor={numero(c.candidatos_total)} nombre="candidatos" />
        <Cifra valor={numero(n.aceptados)} nombre="aceptados" detalle={n.fallidos ? `${n.fallidos} no se pudieron bajar` : undefined} />
        <Cifra valor={numero(c.documentos)} nombre="descargados" detalle={bytes(c.bytes)} />
        <Cifra
          valor={numero(n.fichas)}
          nombre="fichas"
          detalle={c.fichas?.revision ? `${c.fichas.revision} por revisar` : c.nuevos ? `${c.nuevos} nuevos` : undefined}
        />
      </Tarjeta>

      <div className="mt-8">
        <Pestanas
          valor={vista}
          alCambiar={setVista}
          opciones={[
            { valor: "actividad", texto: "Actividad" },
            { valor: "sitios", texto: `Sitios (${numero(n.sitios)})` },
            { valor: "candidatos", texto: `Candidatos (${numero(c.candidatos_total)})` },
            { valor: "documentos", texto: `Documentos (${numero(c.documentos)})` },
            { valor: "fallas", texto: `Fallas${n.tareasFallidas ? ` (${n.tareasFallidas})` : ""}` },
          ]}
        />
        <div className="mt-4">
          {vista === "actividad" && (
            <Tarjeta className="px-4 py-1">
              <Actividad eventos={propias} limite={40} />
            </Tarjeta>
          )}
          {vista === "sitios" && <Sitios id={id} />}
          {vista === "candidatos" && <TablaCandidatos fijos={{ corrida: id }} />}
          {vista === "documentos" && <Documentos id={id} />}
          {vista === "fallas" && <Fallas id={id} />}
        </div>
      </div>
    </div>
  );
}
