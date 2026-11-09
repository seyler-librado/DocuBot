"""Filtro de dominios permitidos y bloqueados.

'sitio.org' y '*.sitio.org' coinciden con sitio.org y con todos sus subdominios
(www.sitio.org, datos.sitio.org...). Lo bloqueado gana sobre lo permitido.
"""

from collections.abc import Iterable

from docubot.red.urls import host_de


def coincide(host: str, patron: str) -> bool:
    base = patron.removeprefix("*.")
    return host == base or host.endswith("." + base)


class FiltroDominios:
    def __init__(self, permitir: Iterable[str] = (), bloquear: Iterable[str] = ()) -> None:
        self.permitir = [p.lower() for p in permitir]
        self.bloquear = [p.lower() for p in bloquear]

    def permitido(self, url_o_host: str) -> bool:
        host = host_de(url_o_host) if "/" in url_o_host else url_o_host.lower().rstrip(".")
        if not host:
            return False
        if any(coincide(host, p) for p in self.bloquear):
            return False
        return not self.permitir or any(coincide(host, p) for p in self.permitir)
