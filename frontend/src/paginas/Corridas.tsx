import { Play } from "lucide-react";
import { Link } from "react-router-dom";
import { useCorridas } from "../api/consultas";
import { TarjetaCorrida } from "../componentes/corridas";
import { Boton, Cargando, Encabezado, Vacio } from "../componentes/ui";

export default function Corridas() {
  const { data, isLoading } = useCorridas(50);
  return (
    <div>
      <Encabezado
        titulo="Corridas"
        subtitulo="Cada corrida toma un perfil, descubre, califica, descarga y hace fichas."
        acciones={
          <Link to="/perfiles">
            <Boton variante="principal" icono={<Play className="size-4" />}>
              Nueva corrida
            </Boton>
          </Link>
        }
      />
      <div className="mt-6 space-y-3">
        {isLoading ? (
          <Cargando />
        ) : !data?.length ? (
          <Vacio titulo="Todavía no hay corridas">Elige un perfil y presiona «Correr».</Vacio>
        ) : (
          data.map((c) => <TarjetaCorrida key={c.id} c={c} />)
        )}
      </div>
    </div>
  );
}
