import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/cliente";
import { useDudosos, useFichas, useResumen } from "../api/consultas";
import { Portada } from "../componentes/documentos";
import { Boton, Cargando, Confianza, Encabezado, Insignia, Paginacion, Pestanas, Tarjeta, Vacio } from "../componentes/ui";
import { dominio, haceCuanto } from "../util/formato";

type Vista = "revision" | "error" | "ilegible" | "lugares";
const LIMITE = 30;

export default function Revision() {
  const [params] = useSearchParams();
  const [vista, setVista] = useState<Vista>((params.get("vista") as Vista) || "revision");
  const [desde, setDesde] = useState(0);
  const { data: resumen } = useResumen();
  const { data, isLoading } = useFichas({ estado: vista === "lugares" ? "revision" : vista, limite: LIMITE, desde });
  const { data: dudosos } = useDudosos({ limite: LIMITE, desde: vista === "lugares" ? desde : 0 });
  const asignar = useMutation({
    mutationFn: ({ id, lugar }: { id: number; lugar: number }) => api.asignarLugar(id, lugar),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dudosos"] });
      qc.invalidateQueries({ queryKey: ["mapa"] });
    },
  });
  const qc = useQueryClient();
  const aprobar = useMutation({
    mutationFn: ({ id, perfil }: { id: number; perfil: string }) => api.aprobarFicha(id, perfil),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fichas"] });
      qc.invalidateQueries({ queryKey: ["resumen"] });
    },
  });
  const f = resumen?.fichas ?? {};

  return (
    <div>
      <Encabezado
        titulo="Revisión"
        subtitulo="Fichas en las que la IA dudó: falta un dato, el tipo no coincide o el título no aparece en el documento."
      />
      <div className="mt-6">
        <Pestanas
          valor={vista}
          alCambiar={(v) => {
            setVista(v);
            setDesde(0);
          }}
          opciones={[
            { valor: "revision", texto: `Por revisar${f.revision ? ` (${f.revision})` : ""}` },
            { valor: "error", texto: `Con error${f.error ? ` (${f.error})` : ""}` },
            { valor: "ilegible", texto: `Ilegibles${f.ilegible ? ` (${f.ilegible})` : ""}` },
            { valor: "lugares", texto: `Lugares por decidir${dudosos?.total ? ` (${dudosos.total})` : ""}` },
          ]}
        />
      </div>
      {vista === "lugares" ? (
        <div className="mt-4">
          {!dudosos?.elementos.length ? (
            <Vacio icono={<ClipboardCheck className="size-8" />} titulo="Ningún lugar por decidir" />
          ) : (
            <div className="space-y-3">
              {dudosos.elementos.map((x) => (
                <Tarjeta key={x.documento_id} className="flex gap-4 p-3">
                  <Link to={`/documentos/${x.documento_id}`} className="shrink-0">
                    <Portada id={x.documento_id} className="h-28 w-20 rounded-md border border-stone-200 dark:border-stone-700" />
                  </Link>
                  <div className="min-w-0 flex-1">
                    <Link to={`/documentos/${x.documento_id}`} className="line-clamp-2 font-medium hover:text-marca-700 dark:hover:text-marca-100">
                      {x.titulo || "Sin título"}
                    </Link>
                    <p className="mt-0.5 truncate text-xs text-stone-500">{dominio(x.url)}</p>
                    <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">
                      {x.estado === "ambiguo" ? "El nombre corresponde a varios lugares:" : "La fuente y el texto apuntan a lugares distintos:"}
                    </p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {x.candidatos.map((c) => (
                        <Boton key={c.id} tamano="sm" onClick={() => asignar.mutate({ id: x.documento_id, lugar: c.id })}>
                          {c.nombre}
                          {c.padre && <span className="font-normal text-stone-500">, {c.padre}</span>}
                        </Boton>
                      ))}
                    </div>
                  </div>
                </Tarjeta>
              ))}
            </div>
          )}
          {dudosos && <Paginacion total={dudosos.total} limite={LIMITE} desde={desde} alCambiar={setDesde} />}
        </div>
      ) : (
      <div className="mt-4">
        {isLoading ? (
          <Cargando />
        ) : !data?.elementos.length ? (
          <Vacio icono={<ClipboardCheck className="size-8" />} titulo={vista === "revision" ? "Nada pendiente de revisar" : "No hay fichas aquí"} />
        ) : (
          <div className="space-y-3">
            {data.elementos.map((x) => (
              <Tarjeta key={`${x.documento_id}-${x.perfil}`} className="flex gap-4 p-3">
                <Link to={`/documentos/${x.documento_id}`} className="shrink-0">
                  <Portada id={x.documento_id} className="h-28 w-20 rounded-md border border-stone-200 dark:border-stone-700" />
                </Link>
                <div className="min-w-0 flex-1">
                  <Link to={`/documentos/${x.documento_id}`} className="line-clamp-2 font-medium hover:text-marca-700 dark:hover:text-marca-100">
                    {x.titulo || "Sin título"}
                  </Link>
                  <p className="mt-0.5 truncate text-xs text-stone-500">
                    {dominio(x.url)} · {x.perfil} · {haceCuanto(x.actualizado)}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Confianza valor={x.confianza} />
                    {x.tipo_esperado && <Insignia tono="marca">se esperaba {x.tipo_esperado}</Insignia>}
                    {x.tipo_ia && x.tipo_ia !== x.tipo_esperado && <Insignia tono="aviso">IA: {x.tipo_ia === "OTRO" ? "otro tipo" : x.tipo_ia}</Insignia>}
                  </div>
                  {!!x.motivos.length && <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">{x.motivos.join(" · ")}</p>}
                </div>
                <div className="flex shrink-0 flex-col gap-2">
                  <Link to={`/documentos/${x.documento_id}`}>
                    <Boton variante="principal" tamano="sm" className="w-full">
                      Revisar
                    </Boton>
                  </Link>
                  {vista === "revision" && (
                    <Boton tamano="sm" icono={<CheckCheck className="size-3.5" />} onClick={() => aprobar.mutate({ id: x.documento_id, perfil: x.perfil })}>
                      Aprobar
                    </Boton>
                  )}
                </div>
              </Tarjeta>
            ))}
          </div>
        )}
        {data && <Paginacion total={data.total} limite={LIMITE} desde={desde} alCambiar={setDesde} />}
      </div>
      )}
    </div>
  );
}
