import os
import json
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv
import structlog

load_dotenv()
log = structlog.get_logger()

BASE_URL  = "https://rest.contabilium.com"
TOKEN_TTL = 50 * 60
_token_cache = {}

PROJECT = os.environ["BIGQUERY_PROJECT"]
DATASET = os.environ["BIGQUERY_DATASET"]
TABLE   = f"{PROJECT}.{DATASET}.raw_ventas"
TABLE_H = f"{PROJECT}.{DATASET}.skus_huerfanos"

CUENTAS = [
    {
        "nombre": "Norfrig",
        "email":   os.environ["EMAIL_NORFRIG"],
        "api_key": os.environ["APIKEY_NORFRIG"],
    }
]

FECHA_HASTA = datetime.now().strftime("%Y-%m-%d")
FECHA_DESDE = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


# ── AUTH ───────────────────────────────────────────────────────────────────────

def obtener_token(cuenta):
    ahora = time.time()
    cache = _token_cache.get(cuenta["nombre"])
    if cache and (ahora - cache["ts"]) < TOKEN_TTL:
        return cache["token"]
    r = requests.post(
        f"{BASE_URL}/token",
        data={
            "grant_type":    "client_credentials",
            "client_id":     cuenta["email"],
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


# ── FILTROS ────────────────────────────────────────────────────────────────────

def es_venta_valida(tipo_fc, estado=""):
    if not tipo_fc:
        return False
    t = tipo_fc.upper().strip()
    e = (estado or "").upper().strip()
    if e in ("ANULADO", "CANCELADO", "RECHAZADO"):
        return False
    if t.startswith("NC"):
        return False
    if t in ("COT",) or t.startswith("FC") or t.startswith("ND") or t == "TK":
        return True
    return False


# ── API CONTABILIUM ────────────────────────────────────────────────────────────

def traer_ids(cuenta):
    ids, ids_vistos, ids_vistos_chunk = [], set(), set()
    page        = 1
    total_chunk = None

    while True:
        try:
            r = requests.get(
                f"{BASE_URL}/api/comprobantes/search",
                headers=get_headers(cuenta),
                params={
                    "fechaDesde": FECHA_DESDE,
                    "fechaHasta": FECHA_HASTA,
                    "page":       page,
                    "pageSize":   50,
                },
                timeout=30,
            )
            if r.status_code == 401:
                _token_cache.pop(cuenta["nombre"], None)
                continue
            if r.status_code != 200 or not r.text.strip():
                break

            data  = r.json()
            items = data.get("Items") or []

            if total_chunk is None:
                total_chunk = data.get("TotalItems", 0)

            if not items:
                break

            nuevos = 0
            for c in items:
                id_comp = c.get("Id")
                if id_comp in ids_vistos or id_comp in ids_vistos_chunk:
                    continue
                ids_vistos.add(id_comp)
                ids_vistos_chunk.add(id_comp)
                nuevos += 1

                tipo_fc = str(c.get("TipoFc") or "")
                estado  = str(c.get("Estado") or "")
                if not es_venta_valida(tipo_fc, estado):
                    continue

                ids.append({
                    "id":      id_comp,
                    "fecha":   c.get("FechaEmision") or c.get("FechaAlta"),
                    "tipo_fc": tipo_fc,
                    "numero":  c.get("Numero") or "",
                    "origen":  c.get("Origen") or "",
                })

            if nuevos == 0 or len(ids_vistos_chunk) >= total_chunk:
                break

            page += 1

        except Exception as e:
            log.error("ventas.error_paginando", cuenta=cuenta["nombre"], page=page, error=str(e))
            break

    return ids


def traer_detalle(item, cuenta):
    for intento in range(3):
        try:
            r = requests.get(
                f"{BASE_URL}/api/comprobantes/getbyid",
                headers=get_headers(cuenta),
                params={"id": item["id"]},
                timeout=30,
            )
            if r.status_code == 200 and r.text.strip():
                return r.json()
            if r.status_code == 401:
                _token_cache.pop(cuenta["nombre"], None)
        except Exception:
            time.sleep(intento + 1)
    return None


# ── BIGQUERY ───────────────────────────────────────────────────────────────────

def get_bq_client():
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["BIGQUERY_CREDS"]),
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    return bigquery.Client(project=PROJECT, credentials=credentials)


def escribir_bigquery(bq, df, tabla, schema, modo=bigquery.WriteDisposition.WRITE_APPEND):
    job_config = bigquery.LoadJobConfig(write_disposition=modo, schema=schema)
    job = bq.load_table_from_dataframe(df, tabla, job_config=job_config)
    job.result()


# ── VENTAS ─────────────────────────────────────────────────────────────────────

def cargar_ventas(bq):
    todas = []

    for cuenta in CUENTAS:
        log.info("ventas.procesando_cuenta", cuenta=cuenta["nombre"], fecha_desde=FECHA_DESDE)
        ids = traer_ids(cuenta)
        log.info("ventas.ids_encontrados", cuenta=cuenta["nombre"], total=len(ids))

        for item in ids:
            detalle = traer_detalle(item, cuenta)
            if not detalle:
                continue

            tipo_fc   = str(detalle.get("TipoFc") or item["tipo_fc"])
            es_cot    = tipo_fc.upper() == "COT"
            origen    = detalle.get("Origen") or item["origen"]
            items_det = detalle.get("Items") or []

            try:
                fecha = pd.to_datetime(item["fecha"]).strftime("%Y-%m-%d")
            except Exception:
                fecha = str(item["fecha"])[:10]

            for it in items_det:
                sku      = str(it.get("Codigo") or "").strip()
                cantidad = float(it.get("Cantidad") or 0)
                if not sku or cantidad <= 0:
                    continue
                todas.append({
                    "fecha":           fecha,
                    "cuenta":          cuenta["nombre"],
                    "id_comprobante":  item["id"],
                    "numero":          item["numero"],
                    "tipo_fc":         tipo_fc,
                    "es_cot":          es_cot,
                    "origen":          origen,
                    "sku":             sku,
                    "nombre_producto": it.get("Nombre") or "",
                    "cantidad":        cantidad,
                })

    if not todas:
        log.info("ventas.sin_datos")
        return None

    df = pd.DataFrame(todas)
    df["fecha"]          = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    df["cantidad"]       = df["cantidad"].astype(float)
    df["id_comprobante"] = df["id_comprobante"].astype(int)
    df["es_cot"]         = df["es_cot"].astype(bool)
    df = df.drop_duplicates(subset=["id_comprobante", "sku"])

    schema = [
        bigquery.SchemaField("fecha",           "DATE"),
        bigquery.SchemaField("cuenta",          "STRING"),
        bigquery.SchemaField("id_comprobante",  "INTEGER"),
        bigquery.SchemaField("numero",          "STRING"),
        bigquery.SchemaField("tipo_fc",         "STRING"),
        bigquery.SchemaField("es_cot",          "BOOLEAN"),
        bigquery.SchemaField("origen",          "STRING"),
        bigquery.SchemaField("sku",             "STRING"),
        bigquery.SchemaField("nombre_producto", "STRING"),
        bigquery.SchemaField("cantidad",        "FLOAT"),
    ]
    escribir_bigquery(bq, df, TABLE, schema)
    log.info("ventas.escritas", tabla=TABLE, filas=len(df))
    return df


def detectar_skus_huerfanos(bq, df):
    skus_maestro = {row.SKU for row in bq.query(
        f"SELECT DISTINCT SKU FROM `{PROJECT}.{DATASET}.maestro_productos`"
    ).result()}
    skus_nuevos = set(df["sku"].unique()) - skus_maestro

    if not skus_nuevos:
        log.info("ventas.skus_huerfanos.ninguno")
        return

    huerfanos = []
    for sku in skus_nuevos:
        filas_sku = df[df["sku"] == sku]
        huerfanos.append({
            "fecha_deteccion": pd.Timestamp.today().date(),
            "sku":             sku,
            "nombre_producto": filas_sku["nombre_producto"].iloc[0],
            "cuenta":          filas_sku["cuenta"].iloc[0],
            "veces_vendido":   int(filas_sku["cantidad"].sum()),
        })

    df_h = pd.DataFrame(huerfanos)
    df_h["fecha_deteccion"] = pd.to_datetime(df_h["fecha_deteccion"]).dt.date

    schema_h = [
        bigquery.SchemaField("fecha_deteccion", "DATE"),
        bigquery.SchemaField("sku",             "STRING"),
        bigquery.SchemaField("nombre_producto", "STRING"),
        bigquery.SchemaField("cuenta",          "STRING"),
        bigquery.SchemaField("veces_vendido",   "INTEGER"),
    ]
    escribir_bigquery(bq, df_h, TABLE_H, schema_h)
    log.warning("ventas.skus_huerfanos.detectados", count=len(skus_nuevos), tabla=TABLE_H)


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    log.info("ingesta_ventas.inicio", fecha_desde=FECHA_DESDE, fecha_hasta=FECHA_HASTA)

    bq = get_bq_client()
    df = cargar_ventas(bq)

    if df is not None:
        detectar_skus_huerfanos(bq, df)

    log.info("ingesta_ventas.fin")


if __name__ == "__main__":
    main()
