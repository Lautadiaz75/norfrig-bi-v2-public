"""
sincronizar_stock.py
====================
Sincroniza stock por depósito desde la API de Contabilium a BigQuery.
Crea/actualiza la tabla stock_por_deposito con WRITE_TRUNCATE (reemplazo total).

Diseñado para correr en GitHub Actions junto con carga_diaria.py.
También se puede correr localmente.

Uso local:
    python sincronizar_stock.py

En GitHub Actions:
    Se llama desde carga_diaria.py o desde cron.yml como paso adicional.
"""

import requests
import time
import os
import json
import io
from datetime import datetime
from collections import Counter

# ── CONFIGURACIÓN ──────────────────────────────────────────────────────────────

CUENTAS = [
    {
        "nombre": "Norfrig",
        "email": os.environ["EMAIL_NORFRIG"],
        "api_key": os.environ["APIKEY_NORFRIG"],
        "depositos_habilitados": {
            20921: "LOCAL HUMBOLDT",
            9874:  "MERCADOLIBRE FULL",
            1577:  "PILAR TRADE DEPOSITO",
            22554: "ZONA FRANCA",
        },
    },
]

BASE_URL = "https://rest.contabilium.com"
TOKEN_TTL = 50 * 60  # renovar cada 50 min

# BigQuery
BQ_PROJECT = os.environ["BIGQUERY_PROJECT"]
BQ_DATASET = os.environ["BIGQUERY_DATASET"]
BQ_TABLE_DETALLE = "stock_por_deposito"
BQ_VIEW_CONSOLIDADO = "stock_consolidado"

PAGE_SIZE = 50  # máximo de la API
PAUSA_ENTRE_PAGINAS = 0.5   # segundos entre cada request
PAUSA_ENTRE_DEPOSITOS = 2   # segundos entre cada depósito
MAX_REINTENTOS_429 = 5      # reintentos ante rate limit

# ── TOKEN CACHE ────────────────────────────────────────────────────────────────

_token_cache = {}


def obtener_token(cuenta):
    """Obtiene o renueva el token OAuth2."""
    ahora = time.time()
    cache = _token_cache.get(cuenta["nombre"])
    if cache and (ahora - cache["ts"]) < TOKEN_TTL:
        return cache["token"]

    r = requests.post(
        f"{BASE_URL}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cuenta["email"],
            "client_secret": cuenta["api_key"],
        },
        timeout=20,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    _token_cache[cuenta["nombre"]] = {"token": token, "ts": ahora}
    return token


def get_headers(cuenta):
    return {"Authorization": f"Bearer {obtener_token(cuenta)}"}


# ── DESCARGA DE STOCK ──────────────────────────────────────────────────────────


def descargar_stock_deposito(cuenta, deposito_id, deposito_nombre):
    """
    Descarga todo el stock de un depósito paginando.
    Solo incluye SKUs con stock > 0 para reducir volumen.
    Incluye throttling y reintentos para evitar HTTP 429.
    Deduplicación por SKU dentro del mismo depósito.
    """
    filas = []
    skus_vistos = set()  # evitar duplicados por retry de página
    page = 0
    fecha_sync = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    while True:
        exito = False

        for intento in range(MAX_REINTENTOS_429):
            try:
                r = requests.get(
                    f"{BASE_URL}/api/inventarios/getStockByDeposito",
                    headers=get_headers(cuenta),
                    params={"id": deposito_id, "page": page, "pageSize": PAGE_SIZE},
                    timeout=30,
                )

                if r.status_code == 401:
                    _token_cache.pop(cuenta["nombre"], None)
                    time.sleep(1)
                    continue

                if r.status_code == 429:
                    espera = 3 * (intento + 1)  # 3s, 6s, 9s, 12s, 15s
                    print(f"\n    ⏳ Rate limit en page {page}, esperando {espera}s (intento {intento+1}/{MAX_REINTENTOS_429})...", end=" ")
                    time.sleep(espera)
                    continue

                if r.status_code != 200:
                    print(f"\n    ⚠ HTTP {r.status_code} en page {page} — parando depósito")
                    return filas

                data = r.json()
                items = data.get("Items", [])

                if not items:
                    return filas

                for item in items:
                    stock_actual = float(item.get("StockActual", 0))
                    stock_reservado = float(item.get("StockReservado", 0))

                    if stock_actual == 0 and stock_reservado == 0:
                        continue

                    sku = str(item.get("Codigo", "")).strip()
                    sku_upper = sku.upper()

                    # Evitar duplicados dentro del mismo depósito
                    if sku_upper in skus_vistos:
                        continue
                    skus_vistos.add(sku_upper)

                    filas.append({
                        "fecha_sync": fecha_sync,
                        "cuenta": cuenta["nombre"],
                        "deposito_id": deposito_id,
                        "deposito_nombre": deposito_nombre,
                        "sku": sku,
                        "stock_actual": stock_actual,
                        "stock_reservado": stock_reservado,
                        "stock_disponible": float(item.get("StockConReservas", 0)),
                    })

                exito = True

                if len(items) < PAGE_SIZE:
                    return filas

                # Pausa entre páginas para no saturar la API
                time.sleep(PAUSA_ENTRE_PAGINAS)
                break

            except Exception as e:
                print(f"\n    ✗ Error en page {page} intento {intento+1}: {e}")
                time.sleep(2 * (intento + 1))

        if not exito:
            print(f"\n    ✗ Agotados reintentos en page {page} — parando depósito")
            break

        page += 1

    return filas


def descargar_stock_cuenta(cuenta):
    """Descarga stock de todos los depósitos habilitados de una cuenta."""
    todas_las_filas = []

    for dep_id, dep_nombre in cuenta["depositos_habilitados"].items():
        print(f"  📦 {dep_nombre} (ID={dep_id})...", end=" ")
        filas = descargar_stock_deposito(cuenta, dep_id, dep_nombre)
        print(f"{len(filas)} SKUs con stock")
        todas_las_filas.extend(filas)

        # Pausa entre depósitos para respetar rate limit
        if len(cuenta["depositos_habilitados"]) > 1:
            time.sleep(PAUSA_ENTRE_DEPOSITOS)

    return todas_las_filas


# ── BIGQUERY ───────────────────────────────────────────────────────────────────


def get_bq_client():
    """Inicializa cliente BigQuery (GH Actions o local)."""
    from google.cloud import bigquery

    creds_json = os.environ.get("BIGQUERY_CREDS")
    if creds_json:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(creds_json)
            f.flush()
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name

    return bigquery.Client(project=BQ_PROJECT)


def escribir_a_bigquery(filas):
    """Escribe las filas en stock_por_deposito con WRITE_TRUNCATE."""
    from google.cloud import bigquery

    if not filas:
        print("  ⚠ Sin datos para escribir")
        return

    client = get_bq_client()
    table_ref = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE_DETALLE}"

    schema = [
        bigquery.SchemaField("fecha_sync", "TIMESTAMP"),
        bigquery.SchemaField("cuenta", "STRING"),
        bigquery.SchemaField("deposito_id", "INTEGER"),
        bigquery.SchemaField("deposito_nombre", "STRING"),
        bigquery.SchemaField("sku", "STRING"),
        bigquery.SchemaField("stock_actual", "FLOAT"),
        bigquery.SchemaField("stock_reservado", "FLOAT"),
        bigquery.SchemaField("stock_disponible", "FLOAT"),
    ]

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition="WRITE_TRUNCATE",
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )

    ndjson = "\n".join(json.dumps(row) for row in filas)
    json_file = io.BytesIO(ndjson.encode("utf-8"))

    job = client.load_table_from_file(json_file, table_ref, job_config=job_config)
    job.result()

    print(f"  ✓ {len(filas)} filas escritas en {table_ref}")


def crear_vista_consolidada():
    """
    Crea la VIEW stock_consolidado que suma stock por SKU
    de todos los depósitos habilitados.

    Esta vista reemplaza maestro_productos.`Stock Disponible` en el semáforo.
    """
    from google.cloud import bigquery

    client = get_bq_client()

    view_sql = f"""
    CREATE OR REPLACE VIEW `{BQ_PROJECT}.{BQ_DATASET}.{BQ_VIEW_CONSOLIDADO}` AS
    SELECT
        sku,
        SUM(stock_actual) AS stock_actual_total,
        SUM(stock_reservado) AS stock_reservado_total,
        SUM(stock_disponible) AS stock_disponible_total,
        MAX(fecha_sync) AS ultima_sync,
        STRING_AGG(
            CONCAT(cuenta, '/', deposito_nombre, ':', CAST(CAST(stock_disponible AS INT64) AS STRING)),
            ' | '
        ) AS detalle_depositos
    FROM `{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE_DETALLE}`
    GROUP BY sku
    """

    client.query(view_sql).result()
    print(f"  ✓ Vista {BQ_VIEW_CONSOLIDADO} creada/actualizada")


# ── MAIN ───────────────────────────────────────────────────────────────────────


def sincronizar_stock():
    """Función principal — se puede llamar desde carga_diaria.py."""
    print(f"\n{'='*55}")
    print(f"  SINCRONIZACIÓN DE STOCK POR DEPÓSITO")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    todas_las_filas = []
    inicio = time.time()

    for cuenta in CUENTAS:
        print(f"\n🔄 {cuenta['nombre']} ({len(cuenta['depositos_habilitados'])} depósitos):")

        try:
            obtener_token(cuenta)
            filas = descargar_stock_cuenta(cuenta)
            todas_las_filas.extend(filas)
        except Exception as e:
            print(f"  ✗ Error en {cuenta['nombre']}: {e}")
            continue

    elapsed = round(time.time() - inicio, 1)

    print(f"\n📊 Resumen:")
    print(f"  Total SKUs con stock: {len(todas_las_filas)}")
    print(f"  Tiempo API: {elapsed}s")

    if not todas_las_filas:
        print("  ⚠ No se descargó stock. Abortando escritura a BigQuery.")
        return False

    # ── DEDUPLICAR ──────────────────────────────────────────────────
    # Clave única: cuenta + deposito_id + sku (normalizado)
    # Si hay duplicados, quedarse con el último (más reciente)
    antes = len(todas_las_filas)

    # Normalizar SKUs: strip + upper para consistencia
    for fila in todas_las_filas:
        fila["sku"] = fila["sku"].strip()

    dedup = {}
    for fila in todas_las_filas:
        clave = (fila["cuenta"], fila["deposito_id"], fila["sku"].upper())
        dedup[clave] = fila  # último gana

    todas_las_filas = list(dedup.values())
    despues = len(todas_las_filas)

    if antes != despues:
        print(f"  ⚠ Deduplicados: {antes} → {despues} ({antes - despues} duplicados removidos)")

    por_deposito = Counter(f["deposito_nombre"] for f in todas_las_filas)
    for dep, count in por_deposito.most_common():
        print(f"    {dep}: {count} SKUs")

    print(f"\n💾 Escribiendo a BigQuery...")
    try:
        # Guardar stock de ayer antes de sobreescribir
        try:
            client = get_bq_client()
            client.query(f"""
                CREATE OR REPLACE TABLE `{BQ_PROJECT}.{BQ_DATASET}.stock_por_deposito_ayer` AS
                SELECT * FROM `{BQ_PROJECT}.{BQ_DATASET}.stock_por_deposito`
            """).result()
            print("  ✓ stock_por_deposito_ayer guardado")
        except Exception as e:
            print(f"  Aviso: no se pudo guardar stock ayer: {e}")

        escribir_a_bigquery(todas_las_filas)
        crear_vista_consolidada()
    except Exception as e:
        print(f"  ✗ Error BigQuery: {e}")
        return False

    print(f"\n✅ Sincronización completa en {round(time.time() - inicio, 1)}s")
    return True


if __name__ == "__main__":
    sincronizar_stock()