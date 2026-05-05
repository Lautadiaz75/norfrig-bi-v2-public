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
TABLE_DEV = f"{PROJECT}.{DATASET}.devoluciones_diarias"

CUENTAS = [
    {
        "nombre": "Norfrig",
        "email":   os.environ["EMAIL_NORFRIG"],
        "api_key": os.environ["APIKEY_NORFRIG"],
    }
]

FECHA_HASTA = datetime.now().strftime("%Y-%m-%d")
FECHA_DESDE = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


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


def get_bq_client():
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["BIGQUERY_CREDS"]),
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    return bigquery.Client(project=PROJECT, credentials=credentials)


def cargar_devoluciones(bq, cuenta):
    log.info("devoluciones.inicio", cuenta=cuenta["nombre"], fecha_desde=FECHA_DESDE)

    ids_nc = []
    page   = 1

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
            data  = r.json()
            items = data.get("Items") or []
            if not items:
                break

            for c in items:
                tipo = str(c.get("TipoFc") or "").upper().strip()
                if tipo.startswith("NC"):
                    ids_nc.append({
                        "id":      c.get("Id"),
                        "fecha":   c.get("FechaEmision") or c.get("FechaAlta"),
                        "tipo_fc": tipo,
                    })

            if len(items) < 50:
                break
            page += 1

        except Exception as e:
            log.error("devoluciones.error_paginando", page=page, error=str(e))
            break

    if not ids_nc:
        log.info("devoluciones.sin_ncs")
        return

    log.info("devoluciones.ncs_encontradas", total=len(ids_nc))
    devoluciones = []

    for item in ids_nc:
        detalle = traer_detalle(item, cuenta)
        if not detalle:
            continue

        try:
            fecha = pd.to_datetime(item["fecha"]).strftime("%Y-%m-%d")
        except Exception:
            fecha = str(item["fecha"])[:10]

        for it in detalle.get("Items") or []:
            sku      = str(it.get("Codigo") or "").strip()
            cantidad = abs(float(it.get("Cantidad") or 0))
            if not sku or cantidad <= 0:
                continue
            devoluciones.append({
                "fecha":          fecha,
                "cuenta":         cuenta["nombre"],
                "id_comprobante": item["id"],
                "tipo_fc":        item["tipo_fc"],
                "sku":            sku,
                "cantidad":       cantidad,
            })

    if not devoluciones:
        log.info("devoluciones.sin_items")
        return

    df = pd.DataFrame(devoluciones)
    df["fecha"]          = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    df["cantidad"]       = df["cantidad"].astype(float)
    df["id_comprobante"] = df["id_comprobante"].astype(int)

    schema = [
        bigquery.SchemaField("fecha",           "DATE"),
        bigquery.SchemaField("cuenta",          "STRING"),
        bigquery.SchemaField("id_comprobante",  "INTEGER"),
        bigquery.SchemaField("tipo_fc",         "STRING"),
        bigquery.SchemaField("sku",             "STRING"),
        bigquery.SchemaField("cantidad",        "FLOAT"),
    ]

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=schema
    )
    job = bq.load_table_from_dataframe(df, TABLE_DEV, job_config=job_config)
    job.result()
    log.info("devoluciones.escritas", filas=len(df), tabla=TABLE_DEV)


def main():
    log.info("ingesta_devoluciones.inicio", fecha_desde=FECHA_DESDE)
    bq = get_bq_client()
    for cuenta in CUENTAS:
        cargar_devoluciones(bq, cuenta)
    log.info("ingesta_devoluciones.fin")


if __name__ == "__main__":
    main()