import { useMutation } from "@tanstack/react-query";
import { Zap } from "lucide-react";
import type { ReactNode } from "react";
import { api } from "../api/cliente";
import { useAjustes, useEstadoBusqueda, useSalud, useSaludIA } from "../api/consultas";
import { Aviso, Boton, Cargando, Encabezado, Insignia, Seccion, Tarjeta } from "../componentes/ui";

function Fila({ nombre, children }: { nombre: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 text-sm">
      <dt className="text-stone-500">{nombre}</dt>
      <dd className="min-w-0 truncate text-right">{children}</dd>
    </div>
  );
}

const sino = (v: boolean) => (v ? "sí" : "no");

export default function Ajustes() {
  const { data: a, isLoading } = useAjustes();
  const { data: salud } = useSalud();
  const { data: ia } = useSaludIA();
  const probar = useMutation({ mutationFn: api.probarIA });
  const { data: busqueda } = useEstadoBusqueda();
  const indexar = useMutation({ mutationFn: api.indexar });
  if (isLoading || !a) return <Cargando />;
  const resultado = probar.data;

  return (
    <div>
      <Encabezado titulo="Ajustes" subtitulo="La configuración con la que corre DocuBot ahora." />
      <div className="mt-6">
        <Aviso tono="info">
          Para cambiarla, edita <code className="font-mono">config/docubot.yaml</code> (o <code className="font-mono">.env</code> para llaves) y reinicia:{" "}
          <code className="font-mono">docker compose up -d</code>. Los ajustes de una sola corrida (robots.txt, ritmo, profundidad) se eligen al
          lanzarla.
        </Aviso>
      </div>

      <div className="grid gap-x-6 md:grid-cols-2">
        <Seccion titulo="Inteligencia artificial">
          <Tarjeta className="px-4 py-2">
            <dl className="divide-y divide-stone-100 dark:divide-stone-800">
              <Fila nombre="Proveedor">{a.ia.proveedor === "ninguno" ? "ninguno (sin fichas)" : a.ia.proveedor}</Fila>
              <Fila nombre="Modelo">{a.ia.modelo || ia?.modelo || "el del servidor"}</Fila>
              <Fila nombre="Estado">
                {ia?.ok == null ? "—" : ia.ok ? <Insignia tono="ok">responde</Insignia> : <Insignia tono="error">no responde</Insignia>}
              </Fila>
              <Fila nombre="Lee escaneados">{sino(a.ia.vision)}</Fila>
              <Fila nombre="Páginas que lee">
                {a.ia.paginas} de texto · {a.ia.paginas_imagen} como imagen
              </Fila>
            </dl>
            {ia?.detalle && <p className="pb-2 text-xs text-rose-600 dark:text-rose-400">{ia.detalle}</p>}
            {a.ia.proveedor !== "ninguno" && (
              <div className="flex items-center gap-3 border-t border-stone-100 py-3 dark:border-stone-800">
                <Boton icono={<Zap className="size-4" />} cargando={probar.isPending} onClick={() => probar.mutate()}>
                  Probar
                </Boton>
                {resultado && (
                  <span className="text-sm">
                    {resultado.ok ? `Respondió «${resultado.eco}» en ${resultado.segundos} s` : `No respondió: ${resultado.detalle ?? ""}`}
                  </span>
                )}
              </div>
            )}
          </Tarjeta>
        </Seccion>

        <Seccion titulo="Búsqueda">
          <Tarjeta className="px-4 py-2">
            <dl className="divide-y divide-stone-100 dark:divide-stone-800">
              <Fila nombre="Por palabras">{busqueda ? `${busqueda.palabras.documentos} documentos con texto` : "—"}</Fila>
              <Fila nombre="Por tema">
                {!busqueda ? "—" : busqueda.tema.activa ? `${busqueda.tema.proveedor}` : "apagada"}
              </Fila>
              {busqueda?.tema.modelo && (
                <Fila nombre="Modelo">
                  <span className="font-mono text-xs" title={busqueda.tema.modelo}>{busqueda.tema.modelo.split("/").pop()}</span>
                </Fila>
              )}
              {busqueda?.tema.activa && (
                <Fila nombre="Indexados">
                  {busqueda.tema.documentos} documentos · {busqueda.tema.fragmentos} fragmentos
                  {!!busqueda.tema.faltan && <span className="text-amber-600"> · faltan {busqueda.tema.faltan}</span>}
                </Fila>
              )}
            </dl>
            {!!busqueda?.tema.faltan && (
              <div className="border-t border-stone-100 py-3 dark:border-stone-800">
                <Boton cargando={indexar.isPending} onClick={() => indexar.mutate()}>
                  Indexar los que faltan
                </Boton>
                {indexar.data && <span className="ml-3 text-sm text-stone-500">{indexar.data.encolados} en la cola</span>}
              </div>
            )}
          </Tarjeta>
        </Seccion>

        <Seccion titulo="Trabajadores por etapa">
          <Tarjeta className="px-4 py-2">
            <dl className="divide-y divide-stone-100 dark:divide-stone-800">
              {Object.entries(a.trabajadores).map(([etapa, n]) => (
                <Fila key={etapa} nombre={etapa}>
                  {n} a la vez
                </Fila>
              ))}
            </dl>
          </Tarjeta>
        </Seccion>

        <Seccion titulo="Red">
          <Tarjeta className="px-4 py-2">
            <dl className="divide-y divide-stone-100 dark:divide-stone-800">
              <Fila nombre="Identificación">
                <span className="font-mono text-xs" title={a.red.user_agent}>
                  {a.red.user_agent}
                </span>
              </Fila>
              <Fila nombre="Ritmo por dominio">
                {a.red.peticiones_por_segundo_por_dominio} por segundo · {a.red.simultaneas_por_dominio} a la vez
              </Fila>
              <Fila nombre="robots.txt">{a.red.respetar_robots ? "se respeta" : "se ignora"}</Fila>
              <Fila nombre="Reintentos">
                {a.red.reintentos} · espera hasta {a.red.timeout} s
              </Fila>
              <Fila nombre="Certificados inválidos">{a.red.reintentar_sin_tls ? "se reintenta sin verificar" : "se rechazan"}</Fila>
            </dl>
          </Tarjeta>
        </Seccion>

        <Seccion titulo="Buscadores y almacén">
          <Tarjeta className="px-4 py-2">
            <dl className="divide-y divide-stone-100 dark:divide-stone-800">
              <Fila nombre="SearXNG">
                <span className="font-mono text-xs">{a.buscadores.searxng_url}</span>
              </Fila>
              {Object.entries(a.buscadores.con_llave).map(([motor, tiene]) => (
                <Fila key={motor} nombre={motor}>
                  {tiene ? <Insignia tono="ok">con llave</Insignia> : <span className="text-stone-400">sin llave</span>}
                </Fila>
              ))}
              <Fila nombre="Tamaño máximo">{a.almacen.tamano_max_mb} MB por documento</Fila>
              <Fila nombre="Respaldo Internet Archive">{sino(a.almacen.respaldo_wayback)}</Fila>
              <Fila nombre="Base de datos">
                {salud?.base_datos.ok ? `Postgres ${salud.base_datos.postgres?.split(" ")[0]}` : "sin conexión"}
              </Fila>
              <Fila nombre="Versión">{salud?.version ?? "—"}</Fila>
            </dl>
          </Tarjeta>
        </Seccion>
      </div>
      <p className="mt-6 text-xs text-stone-400">
        API: <a href="/api/docs" className="underline">documentación interactiva</a>
      </p>
    </div>
  );
}
