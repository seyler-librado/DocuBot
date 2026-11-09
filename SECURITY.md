# Seguridad

## Reportar una vulnerabilidad

No abras un *issue* público. Escribe por el aviso privado de seguridad del
repositorio (pestaña **Security → Report a vulnerability**) con:

- qué encontraste y cómo reproducirlo;
- qué versión o *commit* usas;
- el impacto que crees que tiene.

Responderemos en cuanto podamos y te avisaremos cuando haya una corrección.

## Lo que conviene saber

- **No expongas DocuBot a internet tal cual.** La interfaz no tiene usuarios
  ni contraseña, y desde ella se pueden lanzar corridas. Por omisión escucha
  solo en `127.0.0.1`. Para acceso remoto, usa una VPN o un proxy con
  autenticación.
- **El contenido descargado no es confiable.** Los PDFs y las páginas vienen
  de sitios de terceros:
  - se guardan por su huella y nunca se ejecutan;
  - a la IA se le indica que no siga instrucciones que vengan dentro de un
    documento;
  - los proveedores de IA se usan sin herramientas.
- **Llaves:** van en `.env`, que no se versiona. La API nunca las devuelve.
