# Norfrig BI v2

Sistema de Business Intelligence end-to-end construido para una empresa de repuestos de electrodomésticos. Automatiza la ingesta de datos desde un ERP, transforma la información en BigQuery y genera un semáforo de stock para optimizar las decisiones de compra.

> Sistema en producción desde 2026. Construido en paralelo a la v1 sin interrumpir el servicio.

---

## El problema que resuelve

La empresa maneja +3.000 SKUs distribuidos en 4 depósitos con múltiples proveedores y lead times distintos. Sin un sistema de BI, las decisiones de compra se tomaban manualmente revisando planillas. El resultado: quiebres de stock en productos críticos y sobrestock en productos sin movimiento.

Norfrig BI v2 calcula automáticamente qué comprar, cuánto y cuándo — considerando demanda histórica, estacionalidad, combos de productos y lead time por proveedor.

---

## Arquitectura

```
Contabilium ERP (API REST)
         ↓
┌─────────────────────────────┐
│   Ingesta (Docker)          │
│   ventas / stock /          │
│   devoluciones / recepciones│
└────────────┬────────────────┘
             ↓
┌────────────────────────────┐
│   Google BigQuery          │
│   raw_ventas               │
│   stock_por_deposito       │
│   devoluciones_diarias     │
│   ordenes_compra           │
└────────────┬───────────────┘
             ↓
┌────────────────────────────┐
│   dbt (15 modelos)         │
│   staging → intermediate   │
│   → mart_compra_precalc    │
└────────────┬───────────────┘
             ↓
┌──────────────┐  ┌──────────────┐
│  Cloud Run   │  │  Streamlit   │
│  API REST    │  │  Recepción   │
└──────┬───────┘  └──────────────┘
       ↓
Google Sheets + Apps Script
(catálogo + PDF de órdenes)
```

---

## Stack

| Capa | Tecnologías |
|------|-------------|
| Ingesta | Python, Docker, Docker Compose |
| Infraestructura | Terraform, GCP (BigQuery, Cloud Run, IAM) |
| Transformación | dbt, SQL |
| Orquestación | GitHub Actions |
| API | Python, Cloud Run, functions-framework |
| Frontend | Google Sheets, Apps Script, Streamlit |
| Observabilidad | structlog, Cloud Monitoring |

---

## Estructura del repo

```
norfrig-bi-v2/
├── ingestion/
│   ├── ventas/          # Ingesta de ventas desde Contabilium
│   ├── stock/           # Sincronización de stock por depósito
│   └── devoluciones/    # Ingesta de notas de crédito
├── detection/
│   └── recepciones/     # Detección automática de recepciones
├── transform/
│   └── norfrig_dbt/     # Modelos dbt (staging → intermediate → marts)
├── api/                 # API REST en Cloud Run
├── sheets/              # App Streamlit de recepción
├── infra/               # Infraestructura como código (Terraform)
└── .github/workflows/   # CI/CD pipeline
```

---

## Pipeline diario

```
08:00 UTC
  → dbt test             (valida calidad de datos)
  → ingesta ventas       (Docker)
  → ingesta devoluciones (Docker)
  → ingesta stock        (Docker — ~9 min, 4 depósitos)
  → dbt run              (recalcula semáforo)
  → dbt test             (valida outputs)
  → detección recepciones (Docker)
```

Cada job tiene dependencias explícitas con `needs:` — si uno falla, los siguientes no corren.

---

## Modelos dbt

**Staging** — limpieza y estandarización de datos raw  
**Intermediate** — lógica de negocio: estacionalidad, combos, demanda proyectada  
**Marts** — outputs finales consumidos por el frontend

El mart principal `mart_compra_precalculadas` reemplaza una query monolítica de 100+ líneas con una cadena de 13 modelos testeados y documentados.

---

## Métricas

- **200.000+** filas de historial de ventas procesadas
- **2.979** SKUs sincronizados diariamente desde 4 depósitos
- **15** modelos dbt con **7** tests automáticos de calidad
- Pipeline diario corriendo sin intervención manual

---

## Setup local

```bash
# Clonar el repo
git clone https://github.com/Lautadiaz75/norfrig-bi-v2-public.git
cd norfrig-bi-v2-public

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Copiar y completar variables de entorno
cp .env.example .env

# Correr un container
docker build -t norfrig-ventas ./ingestion/ventas
docker run --env-file .env norfrig-ventas
```

---

## Variables de entorno

Crear un archivo `.env` basado en `.env.example`:

```
EMAIL_NORFRIG=              # Email de Contabilium
APIKEY_NORFRIG=             # API Key de Contabilium
BIGQUERY_PROJECT=           # ID del proyecto GCP
BIGQUERY_DATASET=           # Dataset de BigQuery
BIGQUERY_CREDS=             # JSON del service account (una línea)
DRIVE_CARPETA_COMPRAS_ID=   # ID de carpeta en Google Drive
APP_PASSWORD=               # Contraseña del Streamlit
```

---

## Autor

**Lautaro Diaz**  
Estudiante de Tecnicatura en Desarrollo de Software — UADE  
[LinkedIn](https://linkedin.com/in/lautaro-diaz-0bb1b8221) · [GitHub](https://github.com/Lautadiaz75)