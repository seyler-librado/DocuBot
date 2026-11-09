import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MapPin, Pencil } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type LugarDocumento as TipoLugar } from "../api/cliente";
import { useBuscarLugares } from "../api/consultas";
import { useDiferido } from "../util/diferido";
import { Boton, Entrada, Insignia, Tarjeta } from "./ui";

const ORIGEN: Record<string, string> = {
  fuente: "por la fuente",
  "fuente+contenido": "por la fuente y el texto",
  contenido: "por el texto",
  manual: "elegido a mano",
};

function Buscador({ catalogo, alElegir }: { catalogo: string; alElegir: (id: number) => void }) {
  const [texto, setTexto] = useState("");
  const q = useDiferido(texto, 250);
  const { data } = useBuscarLugares(catalogo, q);
  return (
    <div className="mt-3">
      <Entrada autoFocus placeholder="Busca un lugar…" value={texto} onChange={(e) => setTexto(e.target.value)} />
      {!!data?.length && (
        <ul className="mt-1 max-h-56 overflow-y-auto rounded-lg border border-stone-200 dark:border-stone-700">
          {data.map((l) => (
            <li key={l.id}>
              <button onClick={() => alElegir(l.id)} className="w-full px-3 py-1.5 text-left text-sm hover:bg-stone-100 dark:hover:bg-stone-800">
                {l.nombre}
                <span className="text-xs text-stone-500">
                  {" "}
                  · {l.nivel}
                  {l.padre && `, ${l.padre}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Dónde aplica un documento, con opción de corregirlo. */
export default function LugarDocumento({ documentoId, lugares, catalogo }: { documentoId: number; lugares: TipoLugar[]; catalogo: string | null }) {
  const [editando, setEditando] = useState(false);
  const qc = useQueryClient();
  const asignar = useMutation({
    mutationFn: (lugarId: number) => api.asignarLugar(documentoId, lugarId),
    onSuccess: () => {
      setEditando(false);
      for (const c of ["documento", "mapa", "dudosos"]) qc.invalidateQueries({ queryKey: [c] });
    },
  });
  const cat = catalogo ?? lugares[0]?.catalogo ?? null;
  if (!cat) return null;

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-stone-500">Dónde aplica</h2>
      <Tarjeta className="p-4">
        {!lugares.length && <p className="text-sm text-stone-500">Todavía no se ubica.</p>}
        {lugares.map((l, i) => (
          <div key={i} className="text-sm">
            {l.lugar_id ? (
              <div className="flex flex-wrap items-center gap-2">
                <MapPin className="size-4 text-marca-600" />
                <Link to={`/mapa`} className="font-medium hover:text-marca-700">
                  {l.nombre}
                </Link>
                {l.padre && <span className="text-stone-500">{l.padre}</span>}
                <Insignia tono={l.estado === "revision" ? "aviso" : l.origen === "manual" ? "marca" : "neutro"}>
                  {l.estado === "revision" ? "la fuente y el texto no coinciden" : ORIGEN[l.origen] ?? l.origen}
                </Insignia>
              </div>
            ) : (
              <p className="text-stone-600 dark:text-stone-400">
                {l.estado === "ambiguo" ? "El nombre corresponde a varios lugares. ¿Cuál es?" : "No se encontró un lugar en el documento."}
              </p>
            )}
            {(l.estado === "ambiguo" || l.estado === "revision") && l.candidatos.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {l.candidatos.map((c) => (
                  <Boton key={c.id} tamano="sm" cargando={asignar.isPending && asignar.variables === c.id} onClick={() => asignar.mutate(c.id)}>
                    {c.nombre}
                    {c.padre && <span className="font-normal text-stone-500">, {c.padre}</span>}
                  </Boton>
                ))}
              </div>
            )}
          </div>
        ))}
        {editando ? (
          <Buscador catalogo={cat} alElegir={(id) => asignar.mutate(id)} />
        ) : (
          <Boton variante="fantasma" tamano="sm" className="mt-3" icono={<Pencil className="size-3.5" />} onClick={() => setEditando(true)}>
            {lugares.some((l) => l.lugar_id) ? "Cambiar lugar" : "Elegir lugar"}
          </Boton>
        )}
      </Tarjeta>
    </section>
  );
}
