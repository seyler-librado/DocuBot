# Preguntas frecuentes

**¿Qué necesito para correrlo?**
Docker con Docker Compose v2.24 o más reciente. La IA es opcional:
- sin IA, DocuBot descubre, descarga, extrae el texto, ubica y busca;
- con IA, además hace las fichas.

La búsqueda por tema corre en CPU y no necesita GPU.

**¿Cuánta máquina necesito?**
Sin IA local, cualquier computadora con 4 GB de RAM libres. El modelo de
búsqueda por tema ocupa unos 500 MB en memoria. Una IA local con Ollama ya
pide una máquina con 16 GB o más (mejor con GPU); si no la tienes, usa un
proveedor remoto.

**La construcción de la imagen de la base de datos se queda colgada descargando paquetes.**
Algunas redes (corporativas, de gobierno) bloquean las descargas que se
identifican como `apt` de Debian. Agrega a `.env`:

```
APT_USER_AGENT=Mozilla/5.0
```

y vuelve a construir: `docker compose build db`.

**¿Es legal? ¿Es educado?**
DocuBot descarga documentos que los sitios publican abiertamente:
- respeta robots.txt;
- se identifica con su propio user agent: pon en `red.user_agent` una URL o
  un correo para que un administrador pueda contactarte;
- pide a un ritmo moderado por dominio.

Desactivar robots.txt es posible, pero es tu responsabilidad. Revisa las
condiciones de uso de los sitios y de los datos que reúnes.

**¿Dónde quedan los documentos?**
En `almacen/`, junto al proyecto, organizados por su huella sha256. La base
de datos vive en el volumen de Docker `pgdata`.

**¿Cómo respaldo todo?**
```bash
docker compose exec db pg_dump -U docubot docubot > respaldo.sql
```
y copia la carpeta `almacen/`.

**¿Cómo actualizo DocuBot?**
```bash
git pull
docker compose up -d --build
```
Las migraciones de la base se aplican solas al arrancar.

**Una corrida descubrió miles de candidatos. ¿Los baja todos?**
Solo los aceptados (los que llegan al puntaje mínimo). Puedes correr sin
descargar (`--sin-descargar`, o apagarlo en el diálogo), revisar en
Candidatos y luego bajar los mejores con `docubot descargar <corrida> --limite N`.

**Un sitio está hecho en JavaScript y no se ven sus documentos.**
Todavía no se exploran sitios que necesitan un navegador para mostrar sus
enlaces (`exploracion.javascript` está reservado para eso). Mientras tanto,
prueba con un buscador (`usar: documentos`), Common Crawl o las semillas
directas a las páginas de documentos.

**La IA se equivoca en un campo siempre igual.**
Mejora la `descripcion` del campo en el perfil, agrega contexto en
`fichas.instrucciones` y mide el cambio con un [conjunto dorado](ia.md#qué-tan-bien-lo-hace-el-conjunto-dorado).

**¿Puedo usar mi propio servidor de IA?**
Sí. Si habla la API de OpenAI, usa `openai_compat` con su URL. Si no, escribe
un proveedor en `config/extensiones/` ([cómo](../config/extensiones/README.md)).

**¿Cómo abro la base de datos con un cliente (DBeaver, psql)?**
Escucha solo en tu máquina, en `127.0.0.1:5433` (`DB_PUERTO` en `.env`).
Usuario `docubot`; la contraseña es `POSTGRES_PASSWORD` de tu `.env`.

**¿Puedo exponerlo en internet?**
No tal cual: la interfaz no tiene usuarios ni contraseña y deja lanzar
corridas. Escucha solo en `127.0.0.1`. Si necesitas acceso remoto, ponlo detrás
de una VPN o de un proxy con autenticación.
