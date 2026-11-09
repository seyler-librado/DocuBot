import { ArrowLeft, Play } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { usePerfil, usePerfilYaml } from "../api/consultas";
import DialogoCorrer from "../componentes/DialogoCorrer";
import { Aviso, Boton, Cargando, Encabezado, Insignia, Pestanas, Seccion, Tarjeta } from "../componentes/ui";

function Fila({ nombre, children }: { nombre: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-2.5 sm:grid-cols-[180px_1fr]">
      <dt className="text-sm text-stone-500">{nombre}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  );
}

export default function PerfilDetalle() {
  const { nombre = "" } = useParams();
  const { data, isLoading, error } = usePerfil(nombre);
  const yaml = usePerfilYaml(nombre);
  const [vista, setVista] = useState<"resumen" | "yaml">("resumen");
  const [correr, setCorrer] = useState(false);

  if (isLoading) return <Cargando />;
  if (error || !data) return <Aviso>No se encontró el perfil «{nombre}».</Aviso>;
  const c = data.config;

  return (
    <div>
      <Link to="/perfiles" className="mb-3 inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-800 dark:hover:text-stone-200">
        <ArrowLeft className="size-4" /> Perfiles
      </Link>
      <Encabezado
        titulo={data.nombre}
        subtitulo={<span className="font-mono">{data.archivo}</span>}
        acciones={
          data.valido && (
            <Boton variante="principal" icono={<Play className="size-4" />} onClick={() => setCorrer(true)}>
              Correr
            </Boton>
          )
        }
      />
      {!data.valido && (
        <div className="mt-4">
          <Aviso>
            <p className="font-medium">Este perfil tiene errores:</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 font-mono text-xs">
              {data.errores.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </Aviso>
        </div>
      )}
      <div className="mt-6">
        <Pestanas
          valor={vista}
          alCambiar={setVista}
          opciones={[
            { valor: "resumen", texto: "Resumen" },
            { valor: "yaml", texto: "YAML" },
          ]}
        />
      </div>

      {vista === "yaml" ? (
        <pre className="mt-4 overflow-x-auto rounded-xl bg-stone-900 p-4 font-mono text-xs leading-relaxed text-stone-100">{yaml.data ?? "…"}</pre>
      ) : !c ? null : (
        <>
          {c.descripcion && <p className="mt-4 text-stone-600 dark:text-stone-400">{c.descripcion}</p>}
          <Seccion titulo="Dónde busca">
            <Tarjeta className="px-4">
              <dl className="divide-y divide-stone-100 dark:divide-stone-800">
                <Fila nombre="Dominios permitidos">{c.descubrimiento.dominios.permitir.join(", ") || "cualquiera"}</Fila>
                {!!c.descubrimiento.dominios.bloquear.length && <Fila nombre="Bloqueados">{c.descubrimiento.dominios.bloquear.join(", ")}</Fila>}
                {c.descubrimiento.fuentes.map((f, i) => (
                  <Fila key={i} nombre={`Fuente ${i}: ${f.tipo}`}>
                    {f.urls && <span className="break-all">{f.urls.join(", ")}</span>}
                    {f.archivo && <span className="font-mono">{f.archivo}</span>}
                    {f.consultas && (
                      <span>
                        {f.motor}: {f.consultas.map((q) => `«${q}»`).join(", ")} {f.usar && <Insignia>{f.usar}</Insignia>}
                      </span>
                    )}
                    {f.patron && <span className="font-mono">{f.patron}</span>}
                  </Fila>
                ))}
                <Fila nombre="Exploración">
                  profundidad {c.descubrimiento.exploracion.profundidad} · hasta {c.descubrimiento.exploracion.max_paginas} páginas por sitio
                  {c.descubrimiento.exploracion.sitemap ? " · con sitemap" : ""}
                </Fila>
                <Fila nombre="robots.txt">{c.red.respetar_robots === false ? "se ignora en este perfil" : "se respeta"}</Fila>
              </dl>
            </Tarjeta>
          </Seccion>
          <Seccion titulo="Qué documentos cuentan">
            <Tarjeta className="px-4">
              <dl className="divide-y divide-stone-100 dark:divide-stone-800">
                <Fila nombre="Extensiones">{c.documentos.extensiones.join(", ")}</Fila>
                <Fila nombre="Modo">{c.documentos.modo === "todos" ? "todos los documentos" : `palabras (mínimo ${c.documentos.puntaje_minimo} puntos)`}</Fila>
                {Object.entries(c.documentos.tipos).map(([clave, t]) => (
                  <Fila key={clave} nombre={clave}>
                    <span className="font-medium">{t.nombre}</span>
                    <span className="block font-mono text-xs text-stone-500">{[...t.patrones, ...t.palabras].join(" · ")}</span>
                  </Fila>
                ))}
                {!!c.documentos.excluir.length && <Fila nombre="Excluir">{c.documentos.excluir.join(", ")}</Fila>}
              </dl>
            </Tarjeta>
          </Seccion>
          <Seccion titulo="Ficha">
            {Object.keys(c.fichas.campos).length ? (
              <Tarjeta className="px-4">
                <dl className="divide-y divide-stone-100 dark:divide-stone-800">
                  {Object.entries(c.fichas.campos).map(([n, def]) => (
                    <Fila key={n} nombre={n}>
                      <Insignia>{def.tipo}</Insignia> {def.requerido && <Insignia tono="aviso">obligatorio</Insignia>}
                      {def.opciones.length > 0 && <span className="ml-1 text-xs text-stone-500">{def.opciones.join(" | ")}</span>}
                      {def.descripcion && <span className="block text-xs text-stone-500">{def.descripcion}</span>}
                    </Fila>
                  ))}
                </dl>
              </Tarjeta>
            ) : (
              <p className="text-sm text-stone-500">Este perfil no define campos de ficha.</p>
            )}
          </Seccion>
        </>
      )}
      {correr && <DialogoCorrer perfil={nombre} abierto alCerrar={() => setCorrer(false)} />}
    </div>
  );
}
