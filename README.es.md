# zepp-dashboard

**Saca tus datos de salud de la nube de Zepp/Amazfit y quédatelos.**

Tu pulsera Amazfit ya mide tu frecuencia cardíaca cada minuto, tus fases de
sueño, tu estrés, tu recuperación. Esos datos viven en la nube de Zepp y te
vuelven solo como las pantallas que Zepp decidió dibujar.

Este proyecto los trae a una base SQLite local, los sirve por una API HTTP
pequeña y los pinta en una web — cada capa usable **sin la de encima**. Cógelo
entero, o coge las cincuenta líneas que sacan un token.

*[Read me in English](README.md) · La documentación de `docs/` está en inglés.*

---

## ⭐ El fix de sesión y el truco del namespace

Si te llevas una sola cosa de este repositorio, llévate esta. No está documentada
en ningún otro sitio, y hacerlo mal te rompe el móvil.

**Zepp permite una sola sesión por `app_name`.** La app del móvil ocupa
`com.huami.midong`. Si tu script se loguea con ese mismo nombre, **el backend
expulsa a tu móvil**: se para la sincronización, se para la FC en tiempo real,
hasta que vuelvas a abrir la app.

> **Loguéate con `app_name = com.huami.webapp`.** Es otro slot de sesión y
> convive con el móvil.

Pero eso es solo la mitad. El header `appname` de **cada petición de datos**
selecciona el *namespace que se lee*, independientemente de la sesión. Con
`com.huami.webapp`, tu historial de entrenos sale **vacío** — el dashboard web no
lo expone.

> **Manda `appname: com.huami.midong` en los GET de datos.** Un GET nunca
> registra sesión, así que el móvil no se entera.

**Login como webapp, lectura como app del móvil.** En el código:
[`ingest/auth.py`](ingest/auth.py) (`HEADERS_ZEPP_LOGIN`) y
[`ingest/client.py`](ingest/client.py) (`DATA_HEADERS_BASE`).

El resto de la ingeniería inversa — endpoints, forma de los payloads, valores
centinela, anclajes de zona horaria, callejones sin salida — está en
**[docs/zepp-api.md](docs/zepp-api.md)**.

---

## Las cuatro capas

```
   Nube de Zepp (API no oficial)
        │   ingest/     auth · cliente HTTP · parsers puros
        ▼
   SQLite  data/zepp.db
        │   backend/    FastAPI, agregación y downsampling
        ▼
   API HTTP  /api/*
        │   frontend/   React + Recharts
        ▼
   Web
```

Cada flecha es una costura por la que puedes cortar. Los parsers no saben que
existe una base de datos; la API no sabe que existe una web.

## Elige tu ruta

| Lo que quieres | Lee | Tiempo |
|---|---|---|
| **Solo echar un vistazo**, con datos inventados y sin cuenta | [Pruébalo](#pruébalo-sin-cuenta) | 2 min |
| **Solo un token** de mi cuenta, nada más | [docs/01-login.md](docs/01-login.md) | 5 min |
| **Los datos, en mi propia base** — Postgres, InfluxDB, CSV, lo que sea | [docs/02-extract.md](docs/02-extract.md) | 20 min |
| **El esquema y la API HTTP**, la interfaz me la hago yo | [docs/03-database.md](docs/03-database.md) | 30 min |
| **Todo**, web incluida | [docs/04-web.md](docs/04-web.md) | 45 min |
| **Cómo funciona la API de Zepp** (referencia) | [docs/zepp-api.md](docs/zepp-api.md) | — |

El arranque más rápido posible:

```bash
uv sync
cp ingest/config.example.toml ingest/config.toml   # rellena email y password
uv run python -m ingest.auth                       # -> tu app_token
```

---

## Pruébalo sin cuenta

Noventa días de datos inventados sobre el backend y la web de verdad. Sin cuenta
de Zepp, sin config y sin usar nada tuyo.

```bash
uv sync
(cd frontend && npm install && npm run build)
uv run python -m demo        # -> http://localhost:8000
```

Todo se puede pinchar y editar: la cola de revisión, las etiquetas, los
entrenos. Los datos viven en `data/demo.db`. Al arrancar se regeneran si tienen
más de tres horas o son de otro día, para que siempre terminen cerca de ahora
(un servidor ya en marcha no se regenera). `--reset` deshace lo que hayas
tocado. El sync responde `"modo demo: sincronización desactivada"`.

![Panel: el día contra su banda de 30 días, siete series en un mismo eje](docs/img/panel.png)
![Entrenos: una sesión de fuerza con sus series de Hevy sobre la FC del strap](docs/img/entrenos.png)
![Músculos: volumen semanal de fuerza sobre la figura anatómica](docs/img/musculos.png)

---

## Qué obtienes, si te lo llevas todo

- **Frecuencia cardíaca** por minuto, con los huecos reales pintados como huecos
- **Sueño** — hipnograma por fases, score, tendencia semanal y **siestas**, que
  el payload esconde en un bloque aparte que casi nadie lee
- **Estrés** — la serie dispersa que pinta de verdad la app, no un modelo interno
- **BioCharge** desglosado en `mental` y `physical`, que la app oficial no separa
- **Readiness**, HRV, FC en reposo, frecuencia respiratoria, VO2max, carga de
  entreno, pasos
- **Entrenos** con overlay de FC, zonas de frecuencia, carga y training effect,
  más una cola de revisión para las actividades auto-detectadas
- **Fuerza**, cruzada con [Hevy](https://www.hevyapp.com/): ejercicio, series,
  peso y grupo muscular curado sobre la fisiología del strap — justo lo que el
  reloj no puede hacer, porque falla el ejercicio en torno al 80% de las veces
- **Anotaciones** sobre la línea de tiempo ("reunión tensa", "café doble")
- **Volumen semanal por músculo** sobre una figura anatómica
- **Instalable en el móvil** (PWA) y usable **sin conexión**: lo último que
  viste sigue ahí aunque no haya red

## Requisitos

- Python ≥ 3.11 y [uv](https://docs.astral.sh/uv/)
- Node ≥ 22, solo si quieres la web
- Una cuenta Zepp con **email + password**

## Limitaciones conocidas

- **Solo email + password.** Las cuentas con **SSO** (Xiaomi, Google, Apple) o
  **2FA** no funcionan con este flujo de autenticación.
- **Región.** El host de la API es configurable pero solo está validado para la
  UE (`eu-central-1`).
- **Un dispositivo, una cuenta.** Todo esto se validó con un único Amazfit Helio
  Strap. Los codes de deporte y algunos detalles de los payloads pueden cambiar
  en tu dispositivo — ver
  [docs/02-extract.md](docs/02-extract.md#other-devices-and-regions).
- **Un solo usuario.** Sin cuentas ni multi-tenancy. `api_token` es un secreto
  compartido, no un sistema de login.
- **Interfaz en español.** La web (y los mensajes de error de la API) están en
  español; la documentación de `docs/` está en inglés.

## Roadmap

Diseñado, no construido. Ausente de la UI en vez de dejado como stub:

- `POST /api/ask` — pestaña de IA. Context-builder sobre la base de datos,
  enviado a un endpoint compatible con OpenAI con `base_url` configurable, para
  que valga un modelo local y tu resumen de salud no salga de tu máquina.
- Serie intradía de respiratorio (ahora solo se guarda la mediana diaria; el
  crudo ya se conserva).

## ⚠️ Disclaimer

Este proyecto usa una **API no oficial** de Zepp/Huami, obtenida por **ingeniería
inversa**. No está avalada ni soportada por Zepp/Amazfit.

Los endpoints **pueden cambiar o dejar de funcionar** en cualquier momento, y
existe un **riesgo teórico de bloqueo de la cuenta**. Úsalo bajo tu propia
responsabilidad y solo con **tu propia cuenta y tus propios datos**.

Software entregado **"AS IS"**, sin garantías — ver [LICENSE](LICENSE).

## Licencia

[MIT](LICENSE). Terceros: [frontend/THIRD_PARTY.md](frontend/THIRD_PARTY.md).
