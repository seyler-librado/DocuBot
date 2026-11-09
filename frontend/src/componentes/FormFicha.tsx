import { Save, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { DefCampo } from "../api/cliente";
import { AreaTexto, Boton, Entrada, Etiqueta, Selector } from "./ui";

type Valores = Record<string, unknown>;

const AYUDA: Partial<Record<DefCampo["tipo"], string>> = {
  fecha: "AAAA-MM-DD, AAAA-MM o AAAA",
  lista: "Uno por renglón",
  lugar: "Municipio, estado… tal como aparece",
};

function aTexto(v: unknown): string {
  if (v == null) return "";
  if (Array.isArray(v)) return v.join("\n");
  return String(v);
}

function desdeTexto(def: DefCampo, texto: string): unknown {
  if (def.tipo === "lista") return texto.split("\n").map((x) => x.trim()).filter(Boolean);
  if (def.tipo === "numero") return texto.trim() === "" ? null : Number(texto.replace(/,/g, ""));
  return texto.trim() === "" ? null : texto.trim();
}

function nombreBonito(nombre: string) {
  const t = nombre.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Campos de una ficha, editables según su tipo en el perfil. */
export default function FormFicha({
  campos,
  valores,
  guardando,
  alGuardar,
}: {
  campos: Record<string, DefCampo>;
  valores: Valores;
  guardando?: boolean;
  alGuardar: (v: Valores) => void;
}) {
  const inicial = useMemo(() => Object.fromEntries(Object.keys(campos).map((k) => [k, aTexto(valores[k])])), [campos, valores]);
  const [borrador, setBorrador] = useState<Record<string, string>>(inicial);
  useEffect(() => setBorrador(inicial), [inicial]);
  const cambiado = Object.keys(campos).some((k) => (borrador[k] ?? "") !== (inicial[k] ?? ""));

  const guardar = () =>
    alGuardar(Object.fromEntries(Object.entries(campos).map(([k, def]) => [k, desdeTexto(def, borrador[k] ?? "")])));

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        guardar();
      }}
    >
      {Object.entries(campos).map(([nombre, def]) => {
        const valor = borrador[nombre] ?? "";
        const fijar = (v: string) => setBorrador((b) => ({ ...b, [nombre]: v }));
        const etiqueta = `${nombreBonito(nombre)}${def.requerido ? " *" : ""}`;
        const ayuda = def.descripcion || AYUDA[def.tipo];
        if (def.tipo === "opcion") {
          return (
            <Etiqueta key={nombre} texto={etiqueta} ayuda={def.descripcion}>
              <Selector value={valor} onChange={(e) => fijar(e.target.value)}>
                <option value="">—</option>
                {def.opciones.map((o) => (
                  <option key={o}>{o}</option>
                ))}
                {valor && !def.opciones.includes(valor) && <option>{valor}</option>}
              </Selector>
            </Etiqueta>
          );
        }
        if (def.tipo === "lista" && def.opciones.length) {
          const elegidos = new Set(valor.split("\n").filter(Boolean));
          return (
            <fieldset key={nombre}>
              <legend className="mb-1 text-xs font-medium text-stone-600 dark:text-stone-400">{etiqueta}</legend>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {def.opciones.map((o) => (
                  <label key={o} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={elegidos.has(o)}
                      onChange={(e) => {
                        const nuevo = new Set(elegidos);
                        if (e.target.checked) nuevo.add(o);
                        else nuevo.delete(o);
                        fijar([...nuevo].join("\n"));
                      }}
                      className="accent-marca-600"
                    />
                    {o}
                  </label>
                ))}
              </div>
            </fieldset>
          );
        }
        if (def.tipo === "lista" || valor.length > 80) {
          return (
            <Etiqueta key={nombre} texto={etiqueta} ayuda={ayuda}>
              <AreaTexto value={valor} onChange={(e) => fijar(e.target.value)} rows={Math.min(8, Math.max(2, valor.split("\n").length + 1))} />
            </Etiqueta>
          );
        }
        return (
          <Etiqueta key={nombre} texto={etiqueta} ayuda={ayuda}>
            <Entrada
              value={valor}
              onChange={(e) => fijar(e.target.value)}
              inputMode={def.tipo === "numero" ? "decimal" : undefined}
              placeholder={def.tipo === "fecha" ? "2024-03-05" : undefined}
            />
          </Etiqueta>
        );
      })}
      <div className="flex gap-2 pt-1">
        <Boton type="submit" variante="principal" disabled={!cambiado} cargando={guardando} icono={<Save className="size-4" />}>
          Guardar cambios
        </Boton>
        {cambiado && (
          <Boton type="button" variante="fantasma" onClick={() => setBorrador(inicial)} icono={<Undo2 className="size-4" />}>
            Descartar
          </Boton>
        )}
      </div>
    </form>
  );
}
