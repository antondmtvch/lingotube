# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![extension release](https://img.shields.io/github/v/release/antondmtvch/lingotube?filter=extension-v*&label=extension)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)
[![skills.sh](https://skills.sh/b/antondmtvch/lingotube)](https://skills.sh/antondmtvch/lingotube)

[English](/README.md) · [Русский](/docs/readme/README.ru.md) · [简体中文](/docs/readme/README.zh-Hans.md) · [繁體中文](/docs/readme/README.zh-Hant.md) · [हिन्दी](/docs/readme/README.hi.md) · **Español** · [Français](/docs/readme/README.fr.md) · [العربية](/docs/readme/README.ar.md) · [বাংলা](/docs/readme/README.bn.md) · [Português](/docs/readme/README.pt.md) · [ไทย](/docs/readme/README.th.md) · [日本語](/docs/readme/README.ja.md) · [Tiếng Việt](/docs/readme/README.vi.md) · [Deutsch](/docs/readme/README.de.md)

lingotube obtiene los subtítulos, la transcripción y el resumen de un vídeo de YouTube. El proyecto tiene tres partes: una herramienta de línea de comandos, un skill para agentes de IA y una extensión del navegador (en desarrollo) que muestra subtítulos traducidos sobre el reproductor.
El texto procede del chat integrado de YouTube («Preguntar», Gemini) en la página del vídeo.
Todas las solicitudes se hacen en nombre de tu cuenta de YouTube.

> [!WARNING]
> La herramienta usa una solicitud del chat de YouTube **interna y sin documentar**. YouTube puede
> cambiarla sin previo aviso, y entonces la herramienta dejará de funcionar hasta que se actualice.
> Las Condiciones del Servicio de YouTube no permiten el acceso automatizado: usas la herramienta
> bajo tu propio riesgo. Las solicitudes se envían una a una, con una pausa entre ellas, pero no hay
> garantía de que tu cuenta no sea restringida.
> El soporte es en la medida de lo posible, en tiempo libre y sin plazos.

> [!NOTE]
> Las preguntas y respuestas quedan en el historial de chat de tu cuenta. El chat no está disponible
> en Rusia ni en la mayor parte de la UE, ni bajo algunos vídeos.

**Contenido**

- [Qué incluye](#qué-incluye)
- [Herramienta de línea de comandos (CLI)](#herramienta-de-línea-de-comandos-cli)
  - [Funciones](#funciones)
  - [Instalación](#instalación)
  - [Inicio rápido](#inicio-rápido)
  - [Comandos](#comandos)
  - [Cookies e inicio de sesión](#cookies-e-inicio-de-sesión)
  - [Modos de traducción](#modos-de-traducción)
  - [Códigos de salida](#códigos-de-salida)
- [Skill para agentes de IA](#skill-para-agentes-de-ia)
- [Extensión del navegador](#extensión-del-navegador)
- [Limitaciones](#limitaciones)
- [Desarrollo](#desarrollo)

## Qué incluye

| Componente | Qué hace |
|---|---|
| [Herramienta de línea de comandos (CLI)](#herramienta-de-línea-de-comandos-cli) | El comando `lingotube`: obtiene los subtítulos, la transcripción y el resumen de un vídeo como archivos o JSON. |
| [Skill para agentes de IA](#skill-para-agentes-de-ia) | Permite que un agente de IA (Claude Code, Codex, Cursor y otros) resuma un vídeo, haga una transcripción o subtítulos y encuentre un momento a partir de una descripción. Ejecuta la herramienta de línea de comandos. |
| [Extensión del navegador](#extensión-del-navegador) | Subtítulos traducidos sobre el reproductor de YouTube, en cualquier idioma. En desarrollo. |

## Herramienta de línea de comandos (CLI)

Todo lo de esta sección trata del comando `lingotube`. El skill y la extensión tienen sus propias secciones más abajo.

### Funciones

- **Subtítulos** en cualquier idioma, en los formatos `srt`, `vtt` y `json`.
- **Transcripción** en el idioma original con marcas de tiempo.
- **Resumen** del vídeo.
- **Tres modos de traducción**: el chat integrado de YouTube, tu propio modelo con una API compatible con OpenAI,
  o un agente de IA que traduce la transcripción por sí mismo.
- **Caché y reanudación**: los vídeos largos se procesan por partes y, tras un fallo, el trabajo continúa donde se detuvo.
- **Salida legible por máquinas** con `--json` para scripts y agentes de IA.

### Instalación

Necesitas [uv](https://docs.astral.sh/uv/). uv descarga por sí mismo la versión de Python adecuada.

```sh
uv tool install --python 3.14 git+https://github.com/antondmtvch/lingotube
```

O desde una copia local del repositorio:

```sh
uv tool install --python 3.14 .
```

Actualizar y desinstalar:

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

### Inicio rápido

1. Inicia sesión en YouTube. En Chrome o Edge lo más sencillo es:

   ```sh
   lingotube login
   ```

   Se abre una ventana del navegador con un perfil independiente de lingotube. Inicia sesión en tu cuenta y **cierra la
   ventana del navegador**: el comando espera a que la cierres. En Firefox basta con iniciar sesión en YouTube como siempre.

2. Comprueba que todo está listo:

   ```sh
   lingotube doctor
   ```

   `doctor` comprueba las fuentes de cookies, el inicio de sesión en la cuenta y la disponibilidad del chat en un vídeo de prueba.
   Solo abre el chat y no escribe nada en él.

3. Obtén los subtítulos:

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang es
   ```

### Comandos

| Comando | Qué hace |
|---|---|
| `lingotube subs <enlace> --lang es` | Crea un archivo de subtítulos en el idioma elegido. |
| `lingotube summary <enlace> --lang es` | Muestra un resumen en el idioma elegido. |
| `lingotube transcript <enlace>` | Genera una transcripción en el idioma original con marcas de tiempo (JSON por defecto). |
| `lingotube build <enlace> --lang es --from <archivo>` | Toma una traducción ya hecha, la compara con el original y genera los subtítulos. |
| `lingotube login [--browser chrome\|edge]` | Abre una ventana de inicio de sesión en YouTube y guarda las cookies. |
| `lingotube logout` | Elimina el perfil de inicio de sesión y las cookies guardadas. |
| `lingotube doctor` | Comprueba que todo está listo: cookies, inicio de sesión y chat en un vídeo de prueba. |

`<enlace>` es cualquier enlace a un vídeo de YouTube o un identificador de vídeo.

Opciones principales:

- `--lang <código>` — idioma del resultado (`ru`, `en`, `es`, etc.). Sin esta opción, el idioma se toma de la configuración.
- `--format srt|vtt|json` — formato de los subtítulos, `srt` por defecto.
- `-o <ruta>` — dónde escribir el resultado. Con `-o -` el resultado va a la salida estándar.
- `--offset <segundos>` — desplaza todos los subtítulos; se admiten números decimales y negativos.
- `--cookies-file <ruta>` / `--browser <nombre>` — fuente de cookies.
- `--no-cache` — no usar la caché.
- `--json` — un único documento JSON `{"ok", "result", "warnings", "error"}`.

Un identificador que empieza por guion se pasa después de `--`:

```sh
lingotube subs --lang es -- -n5MqamatXE
```

### Cookies e inicio de sesión

La herramienta toma la primera fuente adecuada en este orden:

1. Un archivo `cookies.txt`: la opción `--cookies-file`, la variable `LINGOTUBE_COOKIES_FILE` o la ruta de la configuración.
2. Un navegador elegido explícitamente: la opción `--browser` o `browser` en la configuración.
3. El perfil de inicio de sesión de lingotube, si se creó con `lingotube login`.
4. Si no, se prueban por turno Firefox, Chrome, Edge y Brave.

En Windows, Chrome y Edge protegen sus cookies y normalmente no se pueden leer directamente.
Para ellos usa `lingotube login`. Exportar un archivo sigue siendo una vía de reserva.

> [!CAUTION]
> El archivo `cookies.txt` da acceso a tu cuenta. Guárdalo como una contraseña y no lo pongas
> en repositorios ni en carpetas compartidas. Las cookies, los tokens y las cabeceras de autorización
> nunca aparecen en la salida, los mensajes de error ni en `--json`: en su lugar se muestra `***`.

Si las cookies dejan de funcionar (código de salida `4`), ejecuta `lingotube login` de nuevo o exporta un archivo nuevo.

### Modos de traducción

| Modo | Cuándo se activa | Quién traduce |
|---|---|---|
| **Chat** (por defecto) | no hay nada configurado | el chat de YouTube devuelve enseguida el texto en el idioma pedido |
| **Modelo propio** | la sección `[translator]` está en la configuración | tu modelo con una API compatible con OpenAI |
| **Agente** | `transcript` → traducción → `build` | un agente de IA o tú a mano; lingotube solo comprueba la traducción y genera los subtítulos |

La configuración está en `settings.toml`:

- Windows: `%LOCALAPPDATA%\lingotube\settings.toml`
- macOS: `~/Library/Application Support/lingotube/settings.toml`
- Linux: `~/.config/lingotube/settings.toml`

Ejemplo del modo «modelo propio»:

```toml
lang = "es"

[translator]
base_url = "https://api.openai.com/v1"   # o un modelo local, p. ej. http://127.0.0.1:11434/v1
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # nombre de la variable de entorno con la clave
batch_size = 40
```

La clave nunca se escribe en el archivo de configuración: la herramienta la lee solo de la variable de entorno.

Modo «agente»:

```sh
lingotube transcript <enlace> -o orig.json          # el original en JSON
# traduce el campo text de cada línea sin cambiar id ni tiempo y guárdalo como es.json
lingotube build <enlace> --lang es --from es.json   # comprobación y generación de los subtítulos
```

> [!TIP]
> Para mantener la traducción literal, usa el modo «modelo propio» o «agente»: primero obtienen el original
> y la traducción se comprueba por números de línea. El chat puede parafrasear o fusionar frases.

### Códigos de salida

| Código | Significado |
|---|---|
| `0` | Éxito. |
| `1` | Otro error. |
| `2` | Opciones del comando no válidas. |
| `3` | El chat no está disponible para este vídeo o cuenta. |
| `4` | Problema de inicio de sesión: cookies no encontradas o caducadas, o falta la clave del modelo. |
| `5` | Resultado incompleto: el archivo se ha escrito, pero la transcripción no llega al final del vídeo. |
| `6` | Fallo de red tras agotar los reintentos. |
| `7` | Los datos no superaron la validación. |
| `8` | YouTube cambió el formato que lee lingotube. Actualice lingotube: vea la sección «Instalación». |
| `130` | Interrumpido por el usuario (Ctrl+C). |

## Skill para agentes de IA

El skill ejecuta la [herramienta de línea de comandos](#herramienta-de-línea-de-comandos-cli) por el agente, así que instala primero la herramienta y después el skill.


El repositorio incluye un skill en el formato abierto Agent Skills. Con él, un agente de IA (Claude Code, Codex,
Cursor, Gemini CLI y otros) resume vídeos, genera transcripciones y subtítulos, encuentra
un momento a partir de su descripción y ayuda con la instalación y el inicio de sesión.

```sh
npx skills add antondmtvch/lingotube
```

Sin Node.js, copia la carpeta `skills/lingotube/` en la carpeta de skills de tu agente
(`~/.claude/skills/` para Claude Code o `~/.agents/skills/` para la mayoría de los demás).

Después, dale al agente un enlace y dile qué necesitas:

```text
Resume este vídeo: https://youtu.be/VIDEO_ID
¿En qué momento del vídeo se habla del montaje? https://youtu.be/VIDEO_ID
Genera subtítulos en español para https://youtu.be/VIDEO_ID
```

## Extensión del navegador

Una extensión Manifest V3 para Chrome, Edge y Firefox que muestra subtítulos traducidos sobre el reproductor de YouTube. Está en desarrollo.

- Un botón del reproductor activa los subtítulos; el panel con el texto se puede arrastrar.
- Eliges uno de 30 idiomas o escribes el tuyo.
- Los tiempos y el texto original proceden de los propios subtítulos de YouTube; el chat solo los traduce.
- Funciona en el navegador donde ya has iniciado sesión en YouTube, por lo que no hay que configurar cookies.

Todavía no está en ninguna tienda. Descarga los archivos para tu navegador desde la [página de versiones](https://github.com/antondmtvch/lingotube/releases):

- Chrome: descarga `lingotube-<version>-chromium.zip` y descomprímelo en una carpeta que vayas a conservar. Abre `chrome://extensions`, activa el «Modo de desarrollador», pulsa «Cargar descomprimida» y elige esa carpeta. Chrome te recuerda al iniciarse que hay extensiones en modo de desarrollador. Para actualizar, sustituye los archivos de la carpeta y pulsa el botón de recarga en la tarjeta de la extensión.
- Edge: usa el mismo archivo. Abre `edge://extensions`, activa el «Modo de desarrollador», pulsa «Cargar sin empaquetar» y elige la carpeta.
- Firefox 140 o posterior: descarga `lingotube-<version>-firefox.xpi`, arrastra el archivo a la ventana de Firefox (o abre `about:addons`, pulsa el icono del engranaje y elige «Instalar complemento desde archivo…») y confirma la instalación.

Brave, Opera y Vivaldi no se han probado.

## Limitaciones

Estas limitaciones se aplican a los tres componentes, porque todos dependen del chat de YouTube.


- El chat solo funciona para usuarios con sesión iniciada mayores de 13 años, no está disponible en todos los países
  ni bajo todos los vídeos.
- Las cuentas de marca no son compatibles: se usa la cuenta principal del navegador.
- Una hora de vídeo tarda varios minutos: las solicitudes van una a una.
- Los tiempos de las líneas los fija el chat. En vídeos largos, algunas líneas pueden desfasarse varios
  segundos; un desfase constante se corrige con la opción `--offset`.
- No se garantiza que el texto de los vídeos largos sea literal: el chat a veces responde con un texto
  de significado cercano y la herramienta no lo detecta. Para usos importantes, comprueba el resultado con la grabación.
- No hay compatibilidad con proxy.

## Desarrollo

Las dependencias y el entorno se gestionan con uv:

```sh
uv sync
uv run pytest
uv run ruff check
```

Cobertura de pruebas (los valores de las insignias de arriba se midieron con estos comandos y se actualizan a mano):

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

Estructura del proyecto:

- `src/lingotube/` — el núcleo: CLI, autorización, chat, traducción, caché y escritura de resultados.
- `skills/lingotube/` — el skill para agentes de IA.
- `extension/` — la extensión del navegador.
- `tests/` — pruebas de Python.
- `docs/readme/` — traducciones de este README.
