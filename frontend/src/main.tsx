import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Link, RouterProvider } from "react-router-dom";
import { ProveedorEventos } from "./api/eventos";
import Marco from "./componentes/Marco";
import { Cargando, Vacio } from "./componentes/ui";
import Ajustes from "./paginas/Ajustes";
import Biblioteca from "./paginas/Biblioteca";
import Buscar from "./paginas/Buscar";
import Candidatos from "./paginas/Candidatos";
import CorridaDetalle from "./paginas/CorridaDetalle";
import Corridas from "./paginas/Corridas";
import Panel from "./paginas/Panel";
import PerfilDetalle from "./paginas/PerfilDetalle";
import Perfiles from "./paginas/Perfiles";
import Revision from "./paginas/Revision";
import "./index.css";

// el visor de PDF pesa: se carga solo al abrir un documento
const Documento = lazy(() => import("./paginas/Documento"));
const Mapa = lazy(() => import("./paginas/Mapa"));

const consultas = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: true } },
});

function NoEncontrada() {
  return (
    <Vacio titulo="Esta página no existe">
      <Link to="/" className="text-marca-700 underline">
        Volver al panel
      </Link>
    </Vacio>
  );
}

const rutas = createBrowserRouter([
  {
    element: <Marco />,
    children: [
      { path: "/", element: <Panel /> },
      { path: "/buscar", element: <Buscar /> },
      { path: "/perfiles", element: <Perfiles /> },
      { path: "/perfiles/:nombre", element: <PerfilDetalle /> },
      { path: "/corridas", element: <Corridas /> },
      { path: "/corridas/:id", element: <CorridaDetalle /> },
      { path: "/biblioteca", element: <Biblioteca /> },
      {
        path: "/documentos/:id",
        element: (
          <Suspense fallback={<Cargando />}>
            <Documento />
          </Suspense>
        ),
      },
      {
        path: "/mapa",
        element: (
          <Suspense fallback={<Cargando />}>
            <Mapa />
          </Suspense>
        ),
      },
      { path: "/revision", element: <Revision /> },
      { path: "/candidatos", element: <Candidatos /> },
      { path: "/ajustes", element: <Ajustes /> },
      { path: "*", element: <NoEncontrada /> },
    ],
  },
]);

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <QueryClientProvider client={consultas}>
      <ProveedorEventos>
        <RouterProvider router={rutas} />
      </ProveedorEventos>
    </QueryClientProvider>
  </StrictMode>,
);
