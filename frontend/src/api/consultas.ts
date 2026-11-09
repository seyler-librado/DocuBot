// Consultas con caché (TanStack Query). Los eventos en vivo invalidan estas claves.

import { useQuery } from "@tanstack/react-query";
import { api } from "./cliente";

type Filtros = Record<string, string | number | undefined>;

export const useSalud = () => useQuery({ queryKey: ["salud"], queryFn: api.salud, refetchInterval: 30_000 });
export const useAjustes = () => useQuery({ queryKey: ["ajustes"], queryFn: api.ajustes, staleTime: 60_000 });
export const useResumen = () => useQuery({ queryKey: ["resumen"], queryFn: api.resumen, refetchInterval: 30_000 });
export const useSaludIA = () => useQuery({ queryKey: ["ia"], queryFn: api.saludIA, staleTime: 30_000 });

export const usePerfiles = () => useQuery({ queryKey: ["perfiles"], queryFn: api.perfiles });
export const usePerfil = (nombre: string | undefined) =>
  useQuery({ queryKey: ["perfil", nombre], queryFn: () => api.perfil(nombre!), enabled: !!nombre, retry: false });
export const usePerfilYaml = (nombre: string) =>
  useQuery({ queryKey: ["perfil", nombre, "yaml"], queryFn: () => api.perfilYaml(nombre) });

export const useCorridas = (limite = 20) =>
  useQuery({ queryKey: ["corridas", limite], queryFn: () => api.corridas(limite), refetchInterval: 20_000 });
export const useCorrida = (id: number) =>
  useQuery({
    queryKey: ["corrida", id],
    queryFn: () => api.corrida(id),
    refetchInterval: (q) => (q.state.data?.estado === "corriendo" ? 10_000 : false),
  });
export const useSitios = (id: number, estado?: string) =>
  useQuery({ queryKey: ["sitios", id, estado], queryFn: () => api.sitios(id, estado) });
export const useFallas = (id: number) => useQuery({ queryKey: ["corrida", id, "fallas"], queryFn: () => api.fallas(id) });

export const useCandidatos = (f: Filtros) =>
  useQuery({ queryKey: ["candidatos", f], queryFn: () => api.candidatos(f), placeholderData: (previo) => previo });
export const useDocumentos = (f: Filtros) =>
  useQuery({ queryKey: ["documentos", f], queryFn: () => api.documentos(f), placeholderData: (previo) => previo });
export const useDocumento = (id: number) => useQuery({ queryKey: ["documento", id], queryFn: () => api.documento(id) });
export const useMapa = (perfil: string | undefined, corrida?: number) =>
  useQuery({ queryKey: ["mapa", perfil, corrida], queryFn: () => api.mapa(perfil!, corrida), enabled: !!perfil });
export const useNiveles = (catalogo: string | undefined) =>
  useQuery({ queryKey: ["niveles", catalogo], queryFn: () => api.niveles(catalogo!), enabled: !!catalogo, staleTime: 300_000 });
export const useDudosos = (f: Filtros) =>
  useQuery({ queryKey: ["dudosos", f], queryFn: () => api.dudosos(f), placeholderData: (previo) => previo });
export const useBuscarLugares = (catalogo: string | undefined, q: string) =>
  useQuery({ queryKey: ["lugares", catalogo, q], queryFn: () => api.buscarLugares(catalogo!, q), enabled: !!catalogo && q.length >= 2 });

export const useBuscar = (f: Filtros) =>
  useQuery({
    queryKey: ["buscar", f],
    queryFn: () => api.buscar(f),
    enabled: typeof f.q === "string" && f.q.trim().length >= 2,
    placeholderData: (previo) => previo,
    retry: false,
  });
export const useEstadoBusqueda = () => useQuery({ queryKey: ["busqueda"], queryFn: api.estadoBusqueda, refetchInterval: 30_000 });

export const useFichas = (f: Filtros) =>
  useQuery({ queryKey: ["fichas", f], queryFn: () => api.fichas(f), placeholderData: (previo) => previo });
