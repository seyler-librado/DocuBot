# Extensiones: proveedores de IA propios

Si tu IA no habla el protocolo de OpenAI ni el de Anthropic (un servidor
interno, un asistente con su propia API...), escribe aquí un proveedor y
apúntale desde `config/docubot.yaml` o `.env`:

```bash
DOCUBOT_IA__PROVEEDOR=mi_ia.py:MiIA      # archivo.py:Clase dentro de esta carpeta
DOCUBOT_IA__URL=https://mi-servidor/api
DOCUBOT_IA__LLAVE=...
```

Esta carpeta **no se versiona** (salvo este README y `ejemplo_proveedor.py`):
tus direcciones y la forma de hablar con tus servidores se quedan en tu
máquina.

Un proveedor es una clase que hereda de `docubot.ia.base.Proveedor` e
implementa `_completar(sistema, usuario, imagenes)`; ver
`ejemplo_proveedor.py`. Tiene a la mano:

| atributo | qué es |
|---|---|
| `self.ajustes` | la sección `ia` de los ajustes (url, modelo, temperatura, max_tokens_salida...) |
| `self.llave` | la llave, o `None` |
| `self.http` | un `httpx.AsyncClient` con el timeout configurado |
| `self.revisar_estado(r)` | convierte errores HTTP en `ErrorIA` (reintentar), `ErrorIAPermanente` o `Desborde` (no cabe) |

Los reintentos ante fallas pasajeras los hace la clase base.

Para probarlo:

```bash
docker compose exec api docubot ia probar
```
