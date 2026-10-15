# API de Consultas de Liquidación de Manifiestos (Silogtran - Render)

API REST de alto rendimiento y bajo consumo de memoria (diseñada para el plan gratuito de Render con restricción de **≤ 512 MB de RAM**), encargada de automatizar el flujo de autenticación, selección de centro de costo y extracción del informe general de **liquidación de manifiestos** desde la plataforma **Silogtran** (construida sobre el framework PHP **PRADO**).

---

## 🚀 Características Principales

- **Automatización de Silogtran (PRADO Framework):** Manejo automático de viewstates (`PRADO_PAGESTATE`), campos ocultos y postbacks sin navegador visual (cero dependencias de Selenium/Playwright para mantener el consumo de RAM < 60 MB).
- **Selección Obligatoria de Centro de Costo:** Detección y selección automática del centro de costo configurado (`CONSTRUPROYEC-PRINCIPAL`), con detención segura (`SILOGTRAN_COST_CENTER_NOT_FOUND`) si no está disponible (nunca selecciona `CONSORCIO` por error).
- **Mantenimiento y Renovación de Sesión:** Mantiene cookies (`PHPSESSID`) activas (~15 min) y reautentica en segundo plano automáticamente si la sesión expira o es invalidada por Silogtran.
- **Protección contra Concurrencia (Locking):** Bloqueos asíncronos (`asyncio.Lock`) para evitar ráfagas de inicio de sesión simultáneas (login stampede).
- **Tokens Permanentes para Consumidores:** Tokens independientes de las cookies de Silogtran. El consumidor recibe un token criptográfico de larga duración (`Authorization: Bearer <TOKEN>`) que no vence a los 15 minutos y puede revocarse manualmente.
- **Parser de CSV Ultraliviano:** Utiliza la librería estándar `csv` de Python (sin sobrecostos de `pandas`). Detecta automáticamente delimitadores (`;`, `,`, `\t`), codificaciones (UTF-8, UTF-8 BOM, Latin-1 / Windows-1252) y formato monetario colombiano (`$ 1.500.000,50` -> `1500000.50`).
- **Caché Inteligente con Reúso de Sub-rangos:** Memoria LRU con TTL configurable. Si ya se consultó del `2026-01-01` al `2026-01-31`, una solicitud del `2026-01-10` al `2026-01-20` se responde al instante desde la memoria caché existente sin consultar a Silogtran.
- **Seguridad y Enmascaramiento de Logs:** Filtro que censura tokens, contraseñas y cookies de todos los registros de salida (`SecretMaskingFilter`).
- **Optimizado para Render Free Tier:** Compatible con despliegue Web Service mediante un solo worker de Gunicorn (`-w 1`) y health checks configurados (`/health`).

---

## 🏛️ Arquitectura del Proyecto

```text
API_Silog_Liq/
├── app/
│   ├── main.py                     # Instancia FastAPI, middleware de request_id y handlers de error
│   ├── core/
│   │   ├── config.py               # Variables de entorno con Pydantic Settings
│   │   ├── exceptions.py           # Jerarquía de excepciones y códigos de error unificados
│   │   ├── logging.py              # Logging estructurado con filtro de enmascaramiento de secretos
│   │   └── security.py             # Generación criptográfica, hashing SHA-256 y comparación segura
│   ├── models/
│   │   ├── schemas.py              # Esquemas Pydantic para peticiones, respuestas y metadatos
│   │   └── token_store.py          # Gestión y persistencia segura de tokens permanentes
│   ├── services/
│   │   ├── prado_parser.py         # Extracción de campos PRADO, viewstates y botones
│   │   ├── column_mapping.py       # Normalización y sinonimia de columnas de Silogtran
│   │   ├── csv_parser.py           # Parser liviano de CSV, limpieza de monedas y fechas ISO
│   │   ├── cache.py                # Caché en memoria LRU con soporte para sub-rangos y stampede lock
│   │   ├── rate_limiter.py         # Limitador de tasa por token/IP (sliding window)
│   │   └── silogtran_client.py     # Cliente HTTP persistente para automatizar Silogtran
│   └── api/
│       ├── deps.py                 # Inyección de dependencias (autenticación y rate limiting)
│       └── v1/
│           ├── router.py           # Agrupador de rutas v1
│           └── endpoints/
│               ├── health.py       # GET /health
│               ├── liquidaciones.py # GET /api/v1/liquidaciones
│               └── tokens.py       # Administración de tokens permanentes
├── tests/                          # 29 pruebas unitarias y de integración simuladas (100% mocks)
├── .env.example                    # Plantilla de variables de entorno
├── requirements.txt                # Dependencias fijadas y livianas
├── Dockerfile                      # Imagen multi-stage slim optimizada para Render
├── render.yaml                     # Blueprint de infraestructura como código en Render
└── README.md                       # Documentación técnica completa
```

---

## ⚙️ Variables de Entorno

Copie `.env.example` a `.env` para desarrollo local:

| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `SILOGTRAN_BASE_URL` | URL base del servidor Silogtran | `https://construproyec.colombiasoftware.net` |
| `SILOGTRAN_LOGIN_URL` | URL de la página de login | `.../index.php?page=Login` |
| `SILOGTRAN_REPORT_URL` | URL del informe general de liquidaciones | `.../index.php?page=Despacho.Liquidacionmanifiesto.InformeGeneral_111` |
| `SILOGTRAN_USERNAME` | Usuario de Silogtran | *(Obligatorio en producción)* |
| `SILOGTRAN_PASSWORD` | Contraseña de Silogtran | *(Obligatorio en producción)* |
| `SILOGTRAN_COST_CENTER` | Centro de costo principal obligatorio | `CONSTRUPROYEC-PRINCIPAL` |
| `API_TOKEN` | Token permanente para consumidor único | *(Configurable en Render)* |
| `ADMIN_API_KEY` | Clave secreta para endpoints administrativos | *(Configurable en Render)* |
| `CACHE_TTL_SECONDS` | Tiempo de vida de la caché en segundos | `900` (15 minutos) |
| `MAX_CACHE_ENTRIES` | Límite de entradas en caché LRU | `500` |
| `MAX_DATE_RANGE_DAYS` | Límite máximo de días por consulta | `31` |
| `REQUEST_TIMEOUT_SECONDS`| Timeout HTTP hacia Silogtran (segundos) | `60` |
| `RATE_LIMIT_PER_MINUTE` | Límite de peticiones por minuto por token | `60` |
| `LOG_LEVEL` | Nivel de registro (`INFO`, `DEBUG`, `WARNING`)| `INFO` |

---

## 📦 Instalación y Ejecución Local

### 1. Clonar y crear entorno virtual

```bash
git clone <URL_DEL_REPOSITORIO>
cd API_Silog_Liq

# Crear entorno virtual con Python 3.11 o superior
python -m venv .venv

# Activar en Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# O en Linux/macOS:
source .venv/bin/activate

# Instalar requerimientos
pip install -r requirements.txt
```

### 2. Configurar `.env`

```bash
cp .env.example .env
# Modifique .env con sus credenciales de prueba o producción
```

### 3. Iniciar el servidor de desarrollo

```bash
uvicorn app.main:app --reload --port 8000
```

Documentación interactiva disponible en:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Pruebas Automatizadas

El proyecto incluye una suite de pruebas completa ejecutada con `pytest`. Todas las interacciones con Silogtran están completamente simuladas mediante mocks, por lo que **no realizan peticiones reales a la plataforma durante los tests**.

```bash
# Ejecutar todas las pruebas con detalle
pytest -v
```

### Cobertura de las 16 pruebas requeridas:

1. **Validación de fechas:** Formatos inválidos, `fecha_inicio > fecha_fin`, y rangos que exceden `MAX_DATE_RANGE_DAYS`.
2. **Autenticación mediante token de API:** Token ausente, inválido, timing-safe compare y revocación.
3. **Inicio de sesión simulado en Silogtran:** Extracción de viewstate y campos de formulario PRADO.
4. **Selección automática del centro de costo:** Localización de `CONSTRUPROYEC-PRINCIPAL` e ignora `CONSORCIO`.
5. **Error controlado de centro de costo:** Detención con `SILOGTRAN_COST_CENTER_NOT_FOUND` si el centro no existe.
6. **Manejo de cookies y persistencia:** Almacenamiento continuo de cookies de sesión.
7. **Detección de sesión expirada:** Redirección detectada y reautenticación automática transparente.
8. **Descarga de CSV simulado:** Extracción directa de contenido CSV y enlaces de descarga.
9. **Detección de delimitador y codificación:** Soporte para `;`, `,`, `\t`, UTF-8, UTF-8 BOM y Latin-1/CP1252.
10. **Conversión de tipos:** Conversión robusta de valores monetarios colombianos (`$ 1.500.000,50` -> `float`), enteros y fechas ISO.
11. **Valores vacíos y columnas dinámicas:** Tolerancia a columnas desconocidas ubicadas en `campos_adicionales`.
12. **Uso de caché:** Inserción, lectura, TTL y expiración.
13. **Consultas repetidas y sub-rangos:** Respuesta inmediata y filtrado en memoria de sub-intervalos de fechas.
14. **Manejo de errores y timeouts:** Conversión de caídas y timeouts de Silogtran en HTTP 502 / 504.
15. **Formato unificado de respuestas de error:** Estructura JSON estándar con `code`, `message` y `request_id`.
16. **Verificación de secretos en logs:** Validación de que ningún token, contraseña o cookie aparezca en logs.

---

## 📖 Guía de Uso de la API (con `curl`)

### 1. Comprobación de salud

```bash
curl -X GET "http://localhost:8000/health"
```

Respuesta:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2026-10-15T20:00:00Z",
  "silogtran_session": "active"
}
```

### 2. Generar un Token Permanente para un Consumidor (Admin)

```bash
curl -X POST "http://localhost:8000/api/v1/admin/tokens" \
  -H "Authorization: Bearer <ADMIN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"nombre": "Integración ERP Principal"}'
```

Respuesta (el token completo **sólo se entrega en esta llamada**):
```json
{
  "success": true,
  "token": "tok_live_a1b2c3d4e5f678901234567890abcdef1234567890abcdef",
  "token_info": {
    "id": "e4f8b1c2-3d4a-4b5c-8d9e-1f2a3b4c5d6e",
    "nombre": "Integración ERP Principal",
    "prefijo": "tok_live_a1b2...",
    "activo": true,
    "created_at": "2026-10-15T20:05:00Z",
    "last_used_at": null,
    "revoked_at": null
  },
  "warning": "Guarde este token ahora. No volverá a mostrarse completo."
}
```

### 3. Consultar Liquidación de Manifiestos

El consumidor solo necesita enviar su token permanente en el encabezado `Authorization`:

```bash
curl -X GET "http://localhost:8000/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-31&page=1&page_size=50" \
  -H "Authorization: Bearer <TOKEN_PERMANENTE>"
```

Respuesta exitosa:
```json
{
  "success": true,
  "data": [
    {
      "id_manifiesto": 12345,
      "numero_manifiesto": "M-2026-000123",
      "fecha": "2026-01-15",
      "placa": "ABC123",
      "conductor": "JUAN PEREZ",
      "documento_conductor": "12345678",
      "origen": "BOGOTA",
      "destino": "MEDELLIN",
      "valor_flete": 1500000.5,
      "valor_anticipo": 500000.0,
      "valor_retencion": 15000.0,
      "valor_descuento": 0.0,
      "valor_neto": 985000.5,
      "estado": "LIQUIDADO",
      "observaciones": "DESPACHO NORMAL",
      "campos_adicionales": {}
    }
  ],
  "meta": {
    "fecha_inicio": "2026-01-01",
    "fecha_fin": "2026-01-31",
    "total_registros": 1,
    "page": 1,
    "page_size": 50,
    "total_pages": 1,
    "from_cache": false,
    "generated_at": "2026-10-15T20:10:00Z"
  }
}
```

### 4. Forzar Actualización (Ignorar Caché)

```bash
curl -X GET "http://localhost:8000/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-31&force_refresh=true" \
  -H "Authorization: Bearer <TOKEN_PERMANENTE>"
```

### 5. Formato Unificado de Error

En caso de fallo (por ejemplo, timeout de Silogtran o fecha inválida):
```json
{
  "success": false,
  "error": {
    "code": "SILOGTRAN_TIMEOUT",
    "message": "Silogtran no respondió dentro del tiempo esperado.",
    "request_id": "a9f3b1c2"
  }
}
```

---

## 🚢 Despliegue en Render

El repositorio incluye la configuración lista para desplegar en Render como **Web Service**.

### Opción 1: Despliegue con Blueprint (`render.yaml`)

1. Suba este repositorio a su cuenta de GitHub o GitLab.
2. Inicie sesión en [Render Dashboard](https://dashboard.render.com).
3. Seleccione **Blueprints** -> **New Blueprint Instance**.
4. Conecte su repositorio. Render detectará automáticamente el archivo `render.yaml`.
5. En la sección de Environment Variables, configure los valores secretos:
   - `SILOGTRAN_USERNAME`
   - `SILOGTRAN_PASSWORD`
   - `API_TOKEN`
   - `ADMIN_API_KEY`
6. Haga clic en **Apply**.

### Opción 2: Despliegue Manual como Web Service

1. En Render, cree un **New Web Service** y conecte su repositorio.
2. Configure los siguientes parámetros:
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:$PORT app.main:app`
   - **Health Check Path:** `/health`
   - **Plan:** `Free` (0.1 CPU, 512 MB RAM)
3. Agregue las variables de entorno detalladas en la tabla de configuración.

### ⚠️ Consideraciones del Plan Gratuito de Render (512 MB RAM)

- **Un solo worker:** Se utiliza `-w 1` para garantizar que la memoria residente del proceso permanezca típicamente entre 50 y 90 MB, muy por debajo del límite de 512 MB.
- **Sin pandas:** El procesamiento del CSV utiliza generadores de la biblioteca estándar `csv`, evitando los picos de 150+ MB de memoria asociados a `pandas`.
- **Suspensión por inactividad (Spin-down):** Si no recibe tráfico durante 15 minutos, Render suspende la instancia gratuita. La primera petición posterior tardará aproximadamente 30-50 segundos en despertar el servicio (cold start).
- **Caché en memoria efímera:** Cuando Render reinicia o suspende el contenedor, la caché en memoria se reinicializa. Para entornos de producción con alta concurrencia persistente, la arquitectura de `BaseCache` permite conectar un Redis externo (`RedisCache`) sin modificar la lógica de los controladores.

---

## 🛠️ Diagnóstico y Adaptación al Tráfico Real de Silogtran

Las instalaciones de Silogtran en PHP PRADO pueden variar sutilmente en los IDs generados para sus controles HTML. La aplicación incluye adaptadores automáticos y heurísticas:

1. **Campos de formulario:** Si en su instalación específica de Silogtran los campos de texto tienen nombres particulares, puede sobrescribirlos sin modificar código mediante:
   - `SILOGTRAN_USER_FIELD`: Nombre del campo de usuario (ej. `ctl0$Content$txtUsuario`).
   - `SILOGTRAN_PASS_FIELD`: Nombre del campo de contraseña (ej. `ctl0$Content$txtClave`).
   - `SILOGTRAN_COST_CENTER_FIELD`: Nombre del `<select>` de centros de costo.
   - `SILOGTRAN_DATE_START_FIELD`: Nombre del campo fecha inicial.
   - `SILOGTRAN_DATE_END_FIELD`: Nombre del campo fecha final.
2. **Inspección de tráfico HTTP:**
   - Puede abrir las DevTools del navegador (F12) en la pestaña **Network**.
   - Realice el login manual y genere el informe una vez.
   - Observe los campos del formulario enviados en el `POST` para verificar si coinciden con los detectados por `PradoParser`.
