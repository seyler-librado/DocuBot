const numeros = new Intl.NumberFormat("es-MX");

export const numero = (n: number | null | undefined) => (n == null ? "—" : numeros.format(n));

export function bytes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  const unidades = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < unidades.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${unidades[i]}`;
}

const relativo = new Intl.RelativeTimeFormat("es", { numeric: "auto" });

export function haceCuanto(fecha: string | number | null | undefined): string {
  if (fecha == null) return "—";
  const ms = typeof fecha === "number" ? fecha : new Date(fecha).getTime();
  const s = Math.round((ms - Date.now()) / 1000);
  const abs = Math.abs(s);
  if (abs < 45) return "hace un momento";
  if (abs < 3600) return relativo.format(Math.round(s / 60), "minute");
  if (abs < 86400) return relativo.format(Math.round(s / 3600), "hour");
  if (abs < 86400 * 30) return relativo.format(Math.round(s / 86400), "day");
  return new Date(ms).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" });
}

export function fecha(f: string | null | undefined): string {
  if (!f) return "—";
  return new Date(f).toLocaleString("es-MX", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export const dominio = (url: string | null | undefined) => {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};

export function duracion(desde: string | null, hasta: string | null): string {
  if (!desde) return "—";
  const s = Math.round(((hasta ? new Date(hasta).getTime() : Date.now()) - new Date(desde).getTime()) / 1000);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}
