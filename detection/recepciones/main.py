"""
detectar_recepciones.py
=======================
Detecta recepciones de mercadería comparando stock de hoy vs ayer
y cierra automáticamente las órdenes correspondientes en BigQuery.

Corre independiente a las 8am UTC (5am Argentina).
"""

import os
import json
import time
from datetime import datetime
from google.cloud import bigquery
from google.oauth2 import service_account
import io
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

PROJECT = os.environ["BIGQUERY_PROJECT"]
DATASET = os.environ["BIGQUERY_DATASET"]
CARPETA_DRIVE_ID = os.environ["DRIVE_CARPETA_COMPRAS_ID"]

UMBRAL_UNIDADES = 10  # mínimo de unidades para considerar recepción

def get_bq_client():
    creds_json = os.environ.get("BIGQUERY_CREDS")
    if creds_json:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(creds_json)
        )
        return bigquery.Client(project=PROJECT, credentials=creds)
    return bigquery.Client(project=PROJECT)

def detectar_subidas_stock(bq):
    """
    Compara stock de hoy vs ayer descontando devoluciones de clientes.
    Si la subida de stock supera las devoluciones del día → es de proveedor.
    """
    query = f"""
    WITH subidas AS (
        SELECT
            COALESCE(hoy.sku, ayer.sku) AS sku,
            COALESCE(SUM(hoy.stock_disponible), 0)  AS stock_hoy,
            COALESCE(SUM(ayer.stock_disponible), 0) AS stock_ayer,
            COALESCE(SUM(hoy.stock_disponible), 0) -
            COALESCE(SUM(ayer.stock_disponible), 0) AS diferencia_bruta
        FROM `{PROJECT}.{DATASET}.stock_por_deposito` hoy
        FULL OUTER JOIN `{PROJECT}.{DATASET}.stock_por_deposito_ayer` ayer
            ON UPPER(TRIM(hoy.sku)) = UPPER(TRIM(ayer.sku))
        GROUP BY COALESCE(hoy.sku, ayer.sku)
        HAVING diferencia_bruta > 0
    ),
    devoluciones AS (
        SELECT
            UPPER(TRIM(sku)) AS sku,
            SUM(cantidad)    AS uds_devueltas
        FROM `{PROJECT}.{DATASET}.devoluciones_diarias`
        WHERE fecha = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
        GROUP BY UPPER(TRIM(sku))
    )
    SELECT
        s.sku,
        s.stock_hoy,
        s.stock_ayer,
        s.diferencia_bruta,
        COALESCE(d.uds_devueltas, 0) AS uds_devueltas,
        s.diferencia_bruta - COALESCE(d.uds_devueltas, 0) AS diferencia_neta
    FROM subidas s
    LEFT JOIN devoluciones d ON UPPER(TRIM(s.sku)) = d.sku
    WHERE s.diferencia_bruta - COALESCE(d.uds_devueltas, 0) > 0
    ORDER BY diferencia_neta DESC
    """
    rows = list(bq.query(query).result())
    return {str(r.sku).strip().upper(): {
        "sku":             r.sku,
        "stock_hoy":       r.stock_hoy,
        "stock_ayer":      r.stock_ayer,
        "diferencia":      r.diferencia_neta,
        "diferencia_bruta": r.diferencia_bruta,
        "uds_devueltas":   r.uds_devueltas
    } for r in rows}

def obtener_ordenes_activas(bq):
    """Devuelve órdenes activas agrupadas por SKU."""
    query = f"""
    SELECT
        o.id_orden,
        o.proveedor,
        o.fecha_orden,
        d.sku,
        d.cantidad_pedida,
        d.cantidad_recibida
    FROM `{PROJECT}.{DATASET}.ordenes_compra` o
    JOIN `{PROJECT}.{DATASET}.ordenes_compra_detalle` d
        ON o.id_orden = d.id_orden
    WHERE o.estado IN ('En camino', 'Recibido parcial')
    ORDER BY o.fecha_orden ASC
    """
    rows = list(bq.query(query).result())
    por_sku = {}
    for row in rows:
        sku = str(row.sku).strip().upper()
        if sku not in por_sku:
            por_sku[sku] = []
        por_sku[sku].append({
            "id_orden":          row.id_orden,
            "proveedor":         row.proveedor,
            "fecha_orden":       str(row.fecha_orden),
            "cantidad_pedida":   row.cantidad_pedida,
            "cantidad_recibida": row.cantidad_recibida or 0
        })
    return por_sku

def actualizar_orden(bq, id_orden, sku, cantidad_recibida_nueva):
    bq.query(f"""
        UPDATE `{PROJECT}.{DATASET}.ordenes_compra_detalle`
        SET cantidad_recibida = {int(cantidad_recibida_nueva)}
        WHERE id_orden = '{id_orden}' AND sku = '{sku}'
    """).result()

    check = list(bq.query(f"""
        SELECT
            SUM(cantidad_pedida)   AS pedido,
            SUM(cantidad_recibida) AS recibido
        FROM `{PROJECT}.{DATASET}.ordenes_compra_detalle`
        WHERE id_orden = '{id_orden}'
    """).result())

    nuevo_estado = "En camino"

    if check and check[0].pedido:
        pedido   = check[0].pedido
        recibido = check[0].recibido

        if recibido >= pedido * 0.95:
            bq.query(f"""
                UPDATE `{PROJECT}.{DATASET}.ordenes_compra_detalle`
                SET cantidad_recibida = cantidad_pedida
                WHERE id_orden = '{id_orden}'
            """).result()
            nuevo_estado = "Recibido"
            print(f"    ↳ Recibido completo ({int(recibido)}/{int(pedido)} uds)")
        else:
            print(f"    ↳ Recibido parcial ignorado — sigue En camino ({int(recibido)}/{int(pedido)} uds)")

    bq.query(f"""
        UPDATE `{PROJECT}.{DATASET}.ordenes_compra`
        SET estado = '{nuevo_estado}'
        WHERE id_orden = '{id_orden}'
    """).result()

    return nuevo_estado
CARPETA_DRIVE_ID = "1UiQ44cTxG0CWLP5Dp7BqGYkHZMrXnx1P"

DEPOSITOS_HABILITADOS_NOMBRES = {
    "LOCAL HUMBOLDT",
    "PILAR TRADE DEPOSITO",
    "MERCADOLIBRE FULL",
    "ZONA FRANCA"
}

TIPOS_EXCLUIR = {"NCA", "NDA", "NCT", "NCC", "NCB"}

def get_drive_service(creds):
    """Crea cliente de Google Drive."""
    return build("drive", "v3", credentials=creds)

def leer_excel_compras_drive(creds):
    service = get_drive_service(creds)

    results = service.files().list(
        q=f"'{CARPETA_DRIVE_ID}' in parents and trashed=false and "
          f"(mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' "
          f"or mimeType='application/vnd.ms-excel' "
          f"or mimeType='application/vnd.ms-excel.sheet.macroenabled.12')",
        orderBy="createdTime desc",
        pageSize=5,
        fields="files(id, name, createdTime)"
    ).execute()

    archivos = results.get("files", [])
    if not archivos:
        print("  Sin archivos Excel en la carpeta de Drive")
        return [], None

    archivo = archivos[0]
    id_archivo = archivo["id"]
    print(f"  Archivo: {archivo['name']} ({archivo['createdTime'][:10]})")

    request    = service.files().get_media(fileId=id_archivo)
    buffer     = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)
    df = pd.read_excel(buffer)

    # Filtrar compras con depósito habilitado y sin categoría
    df_compras = df[
        df["Deposito"].notna() &
        df["Deposito"].str.upper().str.strip().isin(
            {d.upper() for d in DEPOSITOS_HABILITADOS_NOMBRES}
        ) &
        df["Categoria"].isna() &
        ~df["Tipo"].isin(TIPOS_EXCLUIR)
    ].copy()

    if df_compras.empty:
        print("  Sin compras de repuestos en el Excel")
        return [], id_archivo

    # Construir lista con numero_factura + proveedor
    compras = []
    for _, row in df_compras.iterrows():
        compras.append({
            "numero":    str(row.get("Nro Factura", "")).strip(),
            "proveedor": str(row.get("Razon Social", "")).strip(),
            "ordenes":   ""  # se completa después
        })

    # Proveedores únicos
    proveedores = list({c["proveedor"] for c in compras})
    print(f"  Facturas nuevas a procesar: {len(compras)}")
    for p in proveedores:
        print(f"    → {p}")

    return compras, id_archivo

def obtener_ordenes_por_proveedor(bq, proveedores):
    """Devuelve órdenes activas de los proveedores que entregaron."""
    if not proveedores:
        return {}

    # Escapar nombres para SQL
    lista = ", ".join(f"'{p.replace(chr(39), chr(39)*2)}'" for p in proveedores)

    query = f"""
    SELECT
        o.id_orden,
        o.proveedor,
        o.fecha_orden,
        d.sku,
        d.cantidad_pedida,
        d.cantidad_recibida
    FROM `{PROJECT}.{DATASET}.ordenes_compra` o
    JOIN `{PROJECT}.{DATASET}.ordenes_compra_detalle` d
        ON o.id_orden = d.id_orden
    WHERE o.estado IN ('En camino', 'Recibido parcial')
    AND UPPER(TRIM(o.proveedor)) IN (
        {", ".join(f"UPPER('{p.replace(chr(39), chr(39)*2)}')" for p in proveedores)}
    )
    ORDER BY o.fecha_orden ASC
    """
    rows = list(bq.query(query).result())
    por_sku = {}
    for row in rows:
        sku = str(row.sku).strip().upper()
        if sku not in por_sku:
            por_sku[sku] = []
        por_sku[sku].append({
            "id_orden":          row.id_orden,
            "proveedor":         row.proveedor,
            "fecha_orden":       str(row.fecha_orden),
            "cantidad_pedida":   row.cantidad_pedida,
            "cantidad_recibida": row.cantidad_recibida or 0
        })
    return por_sku

def obtener_facturas_ya_procesadas(bq):
    """Devuelve set de claves numero_factura|proveedor ya procesadas."""
    try:
        rows = list(bq.query(f"""
            SELECT CONCAT(numero_factura, '|', proveedor) AS clave
            FROM `{PROJECT}.{DATASET}.recepciones_procesadas`
        """).result())
        return {r.clave for r in rows}
    except Exception:
        return set()

def registrar_facturas_procesadas(bq, facturas, id_archivo):
    """Guarda las facturas procesadas para no volver a procesarlas."""
    if not facturas:
        return
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    valores = ",".join([
        f"('{f['numero'].replace(chr(39), '')}','{f['proveedor'].replace(chr(39), '')}','{fecha_hoy}','{id_archivo}','{f['ordenes']}')"
        for f in facturas
    ])
    bq.query(f"""
        INSERT INTO `{PROJECT}.{DATASET}.recepciones_procesadas`
        (numero_factura, proveedor, fecha_procesado, id_archivo_drive, ordenes_cerradas)
        VALUES {valores}
    """).result()

def main():
    print("=" * 55)
    print("  DETECCIÓN AUTOMÁTICA DE RECEPCIONES")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # Credenciales
    creds_json = os.environ.get("BIGQUERY_CREDS")
    if creds_json:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=[
                "https://www.googleapis.com/auth/bigquery",
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        )

    bq = bigquery.Client(project=PROJECT, credentials=creds)

    # ── Señal 1: Excel de Drive ───────────────────────────────────────────────
    print("\n📂 Leyendo Excel de compras desde Drive...")
    compras_drive = []
    id_archivo = None
    proveedores_con_entrega = []

    try:
        compras_drive, id_archivo = leer_excel_compras_drive(creds)

        if compras_drive:
            ya_procesadas = obtener_facturas_ya_procesadas(bq)
            compras_nuevas = [
                c for c in compras_drive
                if (c["numero"] + "|" + c["proveedor"]) not in ya_procesadas
            ]
            saltadas = len(compras_drive) - len(compras_nuevas)
            if saltadas > 0:
                print(f"  {saltadas} facturas ya procesadas — saltando")
            print(f"  Facturas nuevas a procesar: {len(compras_nuevas)}")
            proveedores_con_entrega = list({c["proveedor"] for c in compras_nuevas})
            compras_drive = compras_nuevas

    except Exception as e:
        print(f"  Error leyendo Drive: {e}")

    # ── Señal 2: Comparación de stock ─────────────────────────────────────────
    print("\n📊 Comparando stock de hoy vs ayer...")
    subidas = {}
    try:
        bq.query(
            f"SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.stock_por_deposito_ayer`"
        ).result()
        subidas = detectar_subidas_stock(bq)
        print(f"  SKUs con subida >= {UMBRAL_UNIDADES} uds: {len(subidas)}")
    except Exception as e:
        print(f"  Error comparando stock: {e}")

    # ── Combinar señales ──────────────────────────────────────────────────────
    print("\n🔗 Combinando señales...")

    if proveedores_con_entrega:
        ordenes_por_sku = obtener_ordenes_por_proveedor(bq, proveedores_con_entrega)
        print(f"  SKUs con órdenes de proveedores que entregaron: {len(ordenes_por_sku)}")
    else:
        print("  Sin Excel disponible — usando solo comparación de stock")
        ordenes_por_sku = obtener_ordenes_activas(bq)

    if not ordenes_por_sku:
        print("  Sin órdenes activas para procesar")
        return

    if subidas:
        coincidencias = {
            sku: datos for sku, datos in subidas.items()
            if sku in ordenes_por_sku
        }
        print(f"  SKUs con subida de stock Y orden activa: {len(coincidencias)}")
    else:
        print("  Sin datos de stock — cerrando por proveedor del Excel")
        coincidencias = {
            sku: {"diferencia": ordenes[0]["cantidad_pedida"], "stock_hoy": 0, "stock_ayer": 0}
            for sku, ordenes in ordenes_por_sku.items()
        }

    if not coincidencias:
        print("  Sin coincidencias para cerrar")
        return

    # ── Actualizar órdenes ────────────────────────────────────────────────────
    print("\n✅ Actualizando órdenes...")
    actualizaciones = []

    for sku, datos in coincidencias.items():
        for orden in ordenes_por_sku[sku]:
            ya_recibido = orden["cantidad_recibida"] or 0
            nueva_cant  = int(min(
                ya_recibido + datos["diferencia"],
                orden["cantidad_pedida"]
            ))
            nuevo_estado = actualizar_orden(bq, orden["id_orden"], sku, nueva_cant)
            msg = (f"  ✅ {sku} → {orden['id_orden']} "
                   f"| +{datos['diferencia']} uds "
                   f"| {ya_recibido} → {nueva_cant}/{orden['cantidad_pedida']} "
                   f"| {nuevo_estado}")
            print(msg)
            actualizaciones.append(msg)

    # ── Registrar facturas procesadas ─────────────────────────────────────────
    if compras_drive and id_archivo and actualizaciones:
        for c in compras_drive:
            c["ordenes"] = ", ".join([
                a for a in actualizaciones
                if c["proveedor"].upper() in a.upper()
            ])[:200]
        try:
            registrar_facturas_procesadas(bq, compras_drive, id_archivo)
            print(f"  {len(compras_drive)} facturas registradas como procesadas")
        except Exception as e:
            print(f"  Aviso: no se pudo registrar facturas procesadas: {e}")

    print(f"\n{'='*55}")
    print(f"  RESUMEN: {len(actualizaciones)} actualizaciones")
    print("=" * 55)


if __name__ == "__main__":
    main()