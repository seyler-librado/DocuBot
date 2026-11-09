"""Ejemplo de proveedor propio. Cópialo con otro nombre y adáptalo.

Uso:  DOCUBOT_IA__PROVEEDOR=mi_ia.py:MiIA
"""

from docubot.ia.base import ErrorIA, Proveedor, Respuesta


class EjemploIA(Proveedor):
    nombre = "ejemplo"
    vision = False  # True si tu modelo acepta imágenes (páginas escaneadas)

    async def _completar(self, sistema: str, usuario: str, imagenes: list[str]) -> Respuesta:
        r = await self.http.post(
            f"{self.ajustes.url.rstrip('/')}/generar",
            json={"sistema": sistema, "mensaje": usuario, "temperatura": self.ajustes.temperatura},
            headers={"Authorization": f"Bearer {self.llave}"} if self.llave else {},
        )
        self.revisar_estado(r)
        datos = r.json()
        if "texto" not in datos:
            raise ErrorIA(f"respuesta inesperada: {str(datos)[:200]}")
        return Respuesta(datos["texto"], modelo=datos.get("modelo", self.ajustes.modelo))
