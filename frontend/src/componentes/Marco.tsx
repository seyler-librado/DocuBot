import {
  ClipboardCheck,
  FileCog,
  LayoutDashboard,
  Library,
  ListFilter,
  Map as IconoMapa,
  Menu,
  Monitor,
  Moon,
  Play,
  Search,
  Settings,
  Sun,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useResumen } from "../api/consultas";
import { useEventos } from "../api/eventos";
import { useTema, type Tema } from "../util/tema";
import { cx } from "./ui";

const NAVEGACION = [
  { a: "/", texto: "Panel", icono: LayoutDashboard },
  { a: "/buscar", texto: "Buscar", icono: Search, atajo: "/" },
  { a: "/perfiles", texto: "Perfiles", icono: FileCog },
  { a: "/corridas", texto: "Corridas", icono: Play },
  { a: "/biblioteca", texto: "Biblioteca", icono: Library },
  { a: "/mapa", texto: "Mapa", icono: IconoMapa },
  { a: "/revision", texto: "Revisión", icono: ClipboardCheck, cuenta: "revision" as const },
  { a: "/candidatos", texto: "Candidatos", icono: ListFilter },
  { a: "/ajustes", texto: "Ajustes", icono: Settings },
];

const TEMAS: { valor: Tema; icono: typeof Sun; texto: string }[] = [
  { valor: "claro", icono: Sun, texto: "Claro" },
  { valor: "oscuro", icono: Moon, texto: "Oscuro" },
  { valor: "sistema", icono: Monitor, texto: "Como el sistema" },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" className="size-8" />
      <span className="text-lg font-semibold tracking-tight">DocuBot</span>
    </div>
  );
}

function Navegacion({ alElegir }: { alElegir?: () => void }) {
  const { data: resumen } = useResumen();
  const porRevisar = resumen?.fichas.revision ?? 0;
  return (
    <nav className="flex flex-col gap-0.5">
      {NAVEGACION.map(({ a, texto, icono: Icono, cuenta, atajo }) => (
        <NavLink
          key={a}
          to={a}
          end={a === "/"}
          onClick={alElegir}
          className={({ isActive }) =>
            cx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-marca-50 text-marca-900 dark:bg-marca-900/40 dark:text-marca-100"
                : "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100",
            )
          }
        >
          <Icono className="size-4 shrink-0" />
          <span className="flex-1">{texto}</span>
          {atajo && <kbd className="hidden rounded border border-stone-300 px-1.5 font-mono text-[10px] text-stone-400 lg:inline dark:border-stone-700">{atajo}</kbd>}
          {cuenta && porRevisar > 0 && (
            <span className="rounded-full bg-amber-100 px-1.5 text-xs tabular-nums text-amber-800 dark:bg-amber-950 dark:text-amber-300">
              {porRevisar}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function PiePanel() {
  const { conectado } = useEventos();
  const [tema, setTema] = useTema();
  return (
    <div className="space-y-3 border-t border-stone-200 pt-3 dark:border-stone-800">
      <div className="flex items-center gap-2 px-3 text-xs text-stone-500" title={conectado ? "Recibiendo eventos en vivo" : "Sin conexión en vivo; se actualiza cada tanto"}>
        <span className={cx("size-2 rounded-full", conectado ? "bg-emerald-500" : "bg-stone-400")} />
        {conectado ? "En vivo" : "Sin conexión en vivo"}
      </div>
      <div className="flex gap-1 px-2" role="radiogroup" aria-label="Tema">
        {TEMAS.map(({ valor, icono: Icono, texto }) => (
          <button
            key={valor}
            role="radio"
            aria-checked={tema === valor}
            title={texto}
            onClick={() => setTema(valor)}
            className={cx(
              "flex-1 rounded-md py-1.5",
              tema === valor ? "bg-stone-200 text-stone-900 dark:bg-stone-800 dark:text-stone-100" : "text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800",
            )}
          >
            <Icono className="mx-auto size-4" />
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Marco() {
  const [menu, setMenu] = useState(false);
  const { pathname } = useLocation();
  const navegar = useNavigate();
  useEffect(() => setMenu(false), [pathname]);
  // «/» desde cualquier pantalla lleva al buscador
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey) return;
      if ((e.target as HTMLElement)?.closest("input, textarea, select, [contenteditable]")) return;
      e.preventDefault();
      if (pathname === "/buscar") document.getElementById("buscador")?.focus();
      else navegar("/buscar");
    };
    addEventListener("keydown", tecla);
    return () => removeEventListener("keydown", tecla);
  }, [pathname, navegar]);
  const pantallaAncha = pathname.startsWith("/documentos/") || pathname === "/mapa";

  return (
    <div className="min-h-dvh lg:flex">
      {/* barra lateral (escritorio) */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col justify-between border-r border-stone-200 bg-white p-4 lg:flex dark:border-stone-800 dark:bg-stone-900">
        <div className="space-y-6">
          <Logo />
          <Navegacion />
        </div>
        <PiePanel />
      </aside>

      {/* barra superior (celular) */}
      <div className="sticky top-0 z-40 flex items-center justify-between border-b border-stone-200 bg-white/90 px-4 py-3 backdrop-blur lg:hidden dark:border-stone-800 dark:bg-stone-900/90">
        <Logo />
        <button onClick={() => setMenu(true)} className="rounded-md p-1.5 hover:bg-stone-100 dark:hover:bg-stone-800" aria-label="Abrir menú">
          <Menu className="size-5" />
        </button>
      </div>
      {menu && (
        <div className="fixed inset-0 z-50 bg-stone-950/40 lg:hidden" onClick={() => setMenu(false)}>
          <div className="flex h-full w-72 max-w-[85vw] flex-col justify-between bg-white p-4 dark:bg-stone-900" onClick={(e) => e.stopPropagation()}>
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <Logo />
                <button onClick={() => setMenu(false)} className="rounded-md p-1.5 hover:bg-stone-100 dark:hover:bg-stone-800" aria-label="Cerrar menú">
                  <X className="size-5" />
                </button>
              </div>
              <Navegacion alElegir={() => setMenu(false)} />
            </div>
            <PiePanel />
          </div>
        </div>
      )}

      <main className={cx("min-w-0 flex-1 px-4 py-6 sm:px-6 lg:py-8", !pantallaAncha && "mx-auto max-w-6xl")}>
        <Outlet />
      </main>
    </div>
  );
}
