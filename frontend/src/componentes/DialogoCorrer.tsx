import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type CambiosCorrida, type FuenteConfig } from "../api/cliente";
import { useAjustes, usePerfil } from "../api/consultas";
import { Aviso, Boton, Cargando, Dialogo, Entrada, Etiqueta, Interruptor } from "./ui";

function describirFuente(f: FuenteConfig): string {
  switch (f.tipo) {
    case "semillas":
      return `${f.urls?.length ?? 0} URL(s) de inicio`;
    case "lista_dominios":
      return `dominios de ${f.archivo}`;
    case "buscador":
      return `${f.motor}: ${f.consultas?.[0] ?? ""}${(f.consultas?.length ?? 0) > 1 ? ` y ${f.consultas!.length - 1} más` : ""}`;
    case "commoncrawl":
    case "wayback":
      return f.patron ?? "";
    default:
      return "";
  }
}

const NOMBRES: Record<string, string> = {
  semillas: "Semillas",
  lista_dominios: "Lista de dominios",
  buscador: "Buscador",
  commoncrawl: "Common Crawl",
  wayback: "Internet Archive",
};

/** Lanzar una corrida de un perfil, con ajustes solo para esta vez. */
export default function DialogoCorrer({ perfil, abierto, alCerrar }: { perfil: string; abierto: boolean; alCerrar: () => void }) {
  const { data, isLoading } = usePerfil(abierto ? perfil : undefined);
  const { data: ajustes } = useAjustes();
  const navegar = useNavigate();
  const qc = useQueryClient();
  const config = data?.config;

  const [fuentes, setFuentes] = useState<number[]>([]);
  const [descargar, setDescargar] = useState(true);
  const [robots, setRobots] = useState(true);
  const [profundidad, setProfundidad] = useState("");
  const [paginas, setPaginas] = useState("");
  const [ritmo, setRitmo] = useState("");
  const [minimo, setMinimo] = useState("");

  useEffect(() => {
    if (!config) return;
    setFuentes(config.descubrimiento.fuentes.map((_, i) => i));
    setRobots(config.red.respetar_robots ?? ajustes?.red.respetar_robots ?? true);
    setProfundidad(String(config.descubrimiento.exploracion.profundidad));
    setPaginas(String(config.descubrimiento.exploracion.max_paginas));
    setRitmo(String(config.red.peticiones_por_segundo_por_dominio ?? ajustes?.red.peticiones_por_segundo_por_dominio ?? 1));
    setMinimo(String(config.documentos.puntaje_minimo));
  }, [config, ajustes]);

  const correr = useMutation({
    mutationFn: () => {
      const cambios: CambiosCorrida = {};
      if (!config) return Promise.reject(new Error("sin perfil"));
      const robotsBase = config.red.respetar_robots ?? ajustes?.red.respetar_robots ?? true;
      if (robots !== robotsBase) cambios.respetar_robots = robots;
      if (Number(profundidad) !== config.descubrimiento.exploracion.profundidad) cambios.profundidad = Number(profundidad);
      if (Number(paginas) !== config.descubrimiento.exploracion.max_paginas) cambios.max_paginas = Number(paginas);
      const ritmoBase = config.red.peticiones_por_segundo_por_dominio ?? ajustes?.red.peticiones_por_segundo_por_dominio ?? 1;
      if (Number(ritmo) !== ritmoBase) cambios.peticiones_por_segundo = Number(ritmo);
      if (Number(minimo) !== config.documentos.puntaje_minimo) cambios.puntaje_minimo = Number(minimo);
      return api.correr({ perfil, fuentes, descargar, ajustes: Object.keys(cambios).length ? cambios : undefined });
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["corridas"] });
      alCerrar();
      navegar(`/corridas/${c.id}`);
    },
  });

  return (
    <Dialogo
      abierto={abierto}
      alCerrar={alCerrar}
      titulo={`Correr «${perfil}»`}
      pie={
        <>
          <Boton variante="fantasma" onClick={alCerrar}>
            Cancelar
          </Boton>
          <Boton variante="principal" icono={<Play className="size-4" />} cargando={correr.isPending} disabled={!config || !fuentes.length} onClick={() => correr.mutate()}>
            Correr
          </Boton>
        </>
      }
    >
      {isLoading || !config ? (
        <Cargando />
      ) : (
        <div className="space-y-5">
          <fieldset>
            <legend className="mb-2 text-xs font-medium text-stone-600 dark:text-stone-400">Fuentes</legend>
            <div className="space-y-2">
              {config.descubrimiento.fuentes.map((f, i) => (
                <label key={i} className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1 accent-marca-600"
                    checked={fuentes.includes(i)}
                    onChange={(e) => setFuentes((fs) => (e.target.checked ? [...fs, i].sort() : fs.filter((x) => x !== i)))}
                  />
                  <span className="min-w-0">
                    <span className="font-medium">{NOMBRES[f.tipo] ?? f.tipo}</span>
                    <span className="block truncate text-xs text-stone-500">{describirFuente(f)}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="space-y-3">
            <Interruptor activo={descargar} alCambiar={setDescargar} texto="Descargar y hacer fichas" ayuda="Si lo apagas, solo descubre y califica; puedes descargar después." />
            <Interruptor
              activo={robots}
              alCambiar={setRobots}
              texto="Respetar robots.txt"
              ayuda={robots ? undefined : "Se pedirán también las rutas que los sitios excluyen. El ritmo por dominio se respeta igual."}
            />
          </div>

          <details className="rounded-lg border border-stone-200 p-3 dark:border-stone-800">
            <summary className="cursor-pointer text-sm font-medium">Ajustes avanzados (solo esta corrida)</summary>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Etiqueta texto="Profundidad" ayuda="clics desde la portada">
                <Entrada type="number" min={0} max={10} value={profundidad} onChange={(e) => setProfundidad(e.target.value)} />
              </Etiqueta>
              <Etiqueta texto="Páginas por sitio">
                <Entrada type="number" min={1} max={10000} value={paginas} onChange={(e) => setPaginas(e.target.value)} />
              </Etiqueta>
              <Etiqueta texto="Peticiones por segundo" ayuda="por dominio">
                <Entrada type="number" min={0.1} max={20} step={0.1} value={ritmo} onChange={(e) => setRitmo(e.target.value)} />
              </Etiqueta>
              <Etiqueta texto="Puntaje mínimo" ayuda="0 a 100">
                <Entrada type="number" min={0} max={100} value={minimo} onChange={(e) => setMinimo(e.target.value)} />
              </Etiqueta>
            </div>
            <p className="mt-3 text-xs text-stone-500">
              Los hilos por etapa son del worker: se cambian en config/docubot.yaml (sección trabajadores).
            </p>
          </details>
          {correr.isError && <Aviso>{(correr.error as Error).message}</Aviso>}
        </div>
      )}
    </Dialogo>
  );
}
