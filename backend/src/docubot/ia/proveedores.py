"""Proveedores incluidos.

| proveedor      | url por omisión                | llave            | notas |
|----------------|--------------------------------|------------------|-------|
| ollama         | http://ollama:11434/v1         | no               | local: docker compose --profile ollama |
| openai         | https://api.openai.com/v1      | sí               | |
| openai_compat  | (obligatoria)                  | según servidor   | Groq, OpenRouter, LM Studio, vLLM, Gemini... |
| anthropic      | https://api.anthropic.com/v1   | sí               | |
"""

from typing import Any

from docubot.ia.base import ErrorIA, ErrorIAPermanente, Proveedor, Respuesta


class OpenAICompat(Proveedor):
    """Cualquier servidor con la API de chat de OpenAI (/v1/chat/completions)."""

    nombre = "openai_compat"
    vision = True
    url_por_omision = ""
    necesita_llave = False

    @property
    def url(self) -> str:
        url = (self.ajustes.url or self.url_por_omision).rstrip("/")
        if not url:
            raise ErrorIAPermanente(f"el proveedor {self.nombre} necesita ia.url (la raíz /v1 del servidor)")
        return url

    def _cabeceras(self) -> dict[str, str]:
        if self.necesita_llave and not self.llave:
            raise ErrorIAPermanente(f"el proveedor {self.nombre} necesita una llave: DOCUBOT_IA__LLAVE en .env")
        return {"Authorization": f"Bearer {self.llave}"} if self.llave else {}

    async def _completar(self, sistema: str, usuario: str, imagenes: list[str]) -> Respuesta:
        if not self.modelo:
            raise ErrorIAPermanente(f"falta ia.modelo para el proveedor {self.nombre}")
        contenido: Any = usuario
        if imagenes:
            contenido = [{"type": "text", "text": usuario}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}} for b64 in imagenes
            ]
        cuerpo = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": contenido}],
            "temperature": self.ajustes.temperatura,
            "max_tokens": self.ajustes.max_tokens_salida,
        }
        r = await self.http.post(f"{self.url}/chat/completions", json=cuerpo, headers=self._cabeceras())
        self.revisar_estado(r)
        d = r.json()
        try:
            texto = d["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ErrorIA(f"{self.nombre}: respuesta sin texto: {str(d)[:200]}") from None
        uso = d.get("usage") or {}
        return Respuesta(texto, d.get("model", self.modelo), uso.get("prompt_tokens"), uso.get("completion_tokens"))

    async def salud(self) -> dict[str, Any]:
        try:
            r = await self.http.get(f"{self.url}/models", headers=self._cabeceras(), timeout=10)
            self.revisar_estado(r)
            modelos = [m.get("id") for m in r.json().get("data", [])]
            ok = not self.modelo or not modelos or self.modelo in modelos
            detalle = "" if ok else f"el modelo '{self.modelo}' no está en el servidor"
            return {"ok": ok, "modelo": self.modelo, "modelos": modelos, "detalle": detalle}
        except Exception as error:
            return {"ok": False, "modelo": self.modelo, "detalle": str(error)}


class Ollama(OpenAICompat):
    nombre = "ollama"
    url_por_omision = "http://ollama:11434/v1"

    async def salud(self) -> dict[str, Any]:
        d = await super().salud()
        if d.get("ok") is False and self.modelo and d.get("modelos") is not None:
            d["detalle"] += f" (descárgalo con: docker compose exec ollama ollama pull {self.modelo})"
        return d


class OpenAI(OpenAICompat):
    nombre = "openai"
    url_por_omision = "https://api.openai.com/v1"
    necesita_llave = True


class Anthropic(Proveedor):
    nombre = "anthropic"
    vision = True
    version_api = "2023-06-01"

    @property
    def url(self) -> str:
        return (self.ajustes.url or "https://api.anthropic.com/v1").rstrip("/")

    def _cabeceras(self) -> dict[str, str]:
        if not self.llave:
            raise ErrorIAPermanente("el proveedor anthropic necesita una llave: DOCUBOT_IA__LLAVE en .env")
        return {"x-api-key": self.llave, "anthropic-version": self.version_api}

    async def _completar(self, sistema: str, usuario: str, imagenes: list[str]) -> Respuesta:
        if not self.modelo:
            raise ErrorIAPermanente("falta ia.modelo para el proveedor anthropic")
        contenido = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}} for b64 in imagenes
        ] + [{"type": "text", "text": usuario}]
        cuerpo = {
            "model": self.modelo,
            "max_tokens": self.ajustes.max_tokens_salida,
            "temperature": self.ajustes.temperatura,
            "system": sistema,
            "messages": [{"role": "user", "content": contenido}],
        }
        r = await self.http.post(f"{self.url}/messages", json=cuerpo, headers=self._cabeceras())
        self.revisar_estado(r)
        d = r.json()
        texto = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        uso = d.get("usage") or {}
        return Respuesta(texto, d.get("model", self.modelo), uso.get("input_tokens"), uso.get("output_tokens"))

    async def salud(self) -> dict[str, Any]:
        try:
            r = await self.http.get(f"{self.url}/models", headers=self._cabeceras(), timeout=10)
            self.revisar_estado(r)
            modelos = [m.get("id") for m in r.json().get("data", [])]
            return {"ok": True, "modelo": self.modelo, "modelos": modelos, "detalle": ""}
        except Exception as error:
            return {"ok": False, "modelo": self.modelo, "detalle": str(error)}


INCLUIDOS: dict[str, type[Proveedor]] = {
    "ollama": Ollama,
    "openai": OpenAI,
    "openai_compat": OpenAICompat,
    "anthropic": Anthropic,
}
