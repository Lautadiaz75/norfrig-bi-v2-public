import os
import json
import streamlit as st
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

PROJECT = os.environ["BIGQUERY_PROJECT"]
DATASET = os.environ["BIGQUERY_DATASET"]
APP_PASSWORD = os.environ.get("APP_PASSWORD", "norfrig2024")

COLORES_SEMAFORO = {
    "CRITICO":            "#FFCCCC",
    "REORDEN":            "#FFF2CC",
    "OK":                 "#CCFFCC",
    "FALTAN DATOS":       "#FF9999",
    "AGOTADO SIN VENTAS": "#FCE4D6",
    "SIN MOVIMIENTO":     "#EAEAEA",
    "REVISAR":            "#D5D5FF",
}

def get_bq_client():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["BIGQUERY_CREDS"]),
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    return bigquery.Client(project=PROJECT, credentials=creds)

@st.cache_data(ttl=300)
def cargar_proveedores():
    bq = get_bq_client()
    query = f"""
        SELECT DISTINCT proveedor, COUNT(*) as total_skus
        FROM `{PROJECT}.{DATASET}.mart_compra_precalculadas`
        GROUP BY proveedor
        ORDER BY proveedor
    """
    return bq.query(query).to_dataframe()

@st.cache_data(ttl=300)
def cargar_catalogo(proveedor):
    bq = get_bq_client()
    where = f"WHERE proveedor = '{proveedor}'" if proveedor != "TODOS" else ""
    query = f"""
        SELECT *
        FROM `{PROJECT}.{DATASET}.mart_compra_precalculadas`
        {where}
        ORDER BY orden_prioridad ASC, unidades_a_pedir DESC
    """
    return bq.query(query).to_dataframe()

@st.cache_data(ttl=60)
def cargar_ordenes():
    bq = get_bq_client()
    query = f"""
        SELECT o.id_orden, o.proveedor, o.fecha_orden,
               o.fecha_estimada_llegada, o.estado, o.total_uds,
               COUNT(d.sku) as skus,
               SUM(d.cantidad_pedida) as uds_pedidas,
               SUM(d.cantidad_recibida) as uds_recibidas
        FROM `{PROJECT}.{DATASET}.ordenes_compra` o
        LEFT JOIN `{PROJECT}.{DATASET}.ordenes_compra_detalle` d
            ON o.id_orden = d.id_orden
        GROUP BY o.id_orden, o.proveedor, o.fecha_orden,
                 o.fecha_estimada_llegada, o.estado, o.total_uds
        ORDER BY o.proveedor, o.fecha_orden DESC
    """
    return bq.query(query).to_dataframe()

def cargar_ya_pedido():
    bq = get_bq_client()
    query = f"""
        SELECT d.sku, SUM(d.cantidad_pedida - d.cantidad_recibida) AS ya_pedido
        FROM `{PROJECT}.{DATASET}.ordenes_compra_detalle` d
        JOIN `{PROJECT}.{DATASET}.ordenes_compra` o ON d.id_orden = o.id_orden
        WHERE o.estado IN ('En camino', 'Recibido parcial')
        GROUP BY d.sku
    """
    df = bq.query(query).to_dataframe()
    return dict(zip(df["sku"].str.strip().str.upper(), df["ya_pedido"]))

def confirmar_orden(proveedor, items):
    bq = get_bq_client()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    prov_slug = ''.join(c for c in proveedor if c.isalnum())[:10].upper()
    id_orden = f"OC-{fecha_hoy.replace('-','')}-{prov_slug}"

    lead_time = int(items[0].get("lead_time_dias") or 15)
    fecha_llegada = (datetime.now() + timedelta(days=lead_time)).strftime("%Y-%m-%d")
    total_uds = sum(int(i["mi_pedido"]) for i in items)

    bq.query(f"""
        INSERT INTO `{PROJECT}.{DATASET}.ordenes_compra`
        (id_orden, proveedor, fecha_orden, fecha_estimada_llegada, estado, total_uds, notas)
        VALUES ('{id_orden}', '{proveedor.replace("'","\\'")}',
                '{fecha_hoy}', '{fecha_llegada}', 'En camino', {total_uds}, '')
    """).result()

    valores = ",".join([
        f"('{id_orden}', '{str(i['sku']).replace(chr(39),'')}', "
        f"'{str(i['nombre_producto']).replace(chr(39),'')[:80]}', "
        f"{int(i['mi_pedido'])}, 0, {float(i.get('costo_sin_iva') or 0)})"
        for i in items
    ])
    bq.query(f"""
        INSERT INTO `{PROJECT}.{DATASET}.ordenes_compra_detalle`
        (id_orden, sku, nombre_producto, cantidad_pedida, cantidad_recibida, costo_sin_iva)
        VALUES {valores}
    """).result()

    cargar_ordenes.clear()
    return id_orden

def cambiar_estado_orden(id_orden, nuevo_estado):
    bq = get_bq_client()
    bq.query(f"""
        UPDATE `{PROJECT}.{DATASET}.ordenes_compra`
        SET estado = '{nuevo_estado}'
        WHERE id_orden = '{id_orden}'
    """).result()
    if nuevo_estado == "Recibido":
        bq.query(f"""
            UPDATE `{PROJECT}.{DATASET}.ordenes_compra_detalle`
            SET cantidad_recibida = cantidad_pedida
            WHERE id_orden = '{id_orden}'
        """).result()
    cargar_ordenes.clear()

# ── LOGIN ────────────────────────────────────────────────────────────────────

def login():
    st.title("Norfrig BI")
    st.subheader("Ingresá la contraseña para continuar")
    pwd = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if pwd == APP_PASSWORD:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta")

# ── APP PRINCIPAL ─────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Norfrig BI", layout="wide")

    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if not st.session_state["autenticado"]:
        login()
        return

    st.title("Norfrig BI")

    tab1, tab2, tab3 = st.tabs(["Catálogo de Compras", "Órdenes Activas", "Recepción"])

    # ── TAB 1: CATÁLOGO ───────────────────────────────────────────────────────
    with tab1:
        proveedores_df = cargar_proveedores()
        opciones = ["TODOS"] + proveedores_df["proveedor"].tolist()
        proveedor = st.selectbox("Proveedor", opciones)

        if st.button("Cargar catálogo"):
            cargar_catalogo.clear()

        with st.spinner("Cargando..."):
            df = cargar_catalogo(proveedor)
            ya_pedido = cargar_ya_pedido()

        if df.empty:
            st.info("Sin datos para este proveedor.")
            return

        df["ya_pedido"] = df["sku"].str.strip().str.upper().map(ya_pedido).fillna(0).astype(int)
        df["mi_pedido"] = 0

        cols_mostrar = ["proveedor", "sku", "nombre_producto", "semaforo",
                        "stock_actual", "avg_diario_proy", "dias_stock_restante",
                        "unidades_a_pedir", "ya_pedido", "lead_time_dias", "costo_sin_iva"]

        st.dataframe(
            df[cols_mostrar].style.apply(
                lambda row: [f"background-color: {COLORES_SEMAFORO.get(row['semaforo'], '#FFFFFF')}" 
                           if col == 'semaforo' else '' for col in cols_mostrar],
                axis=1
            ),
            use_container_width=True,
            height=500
        )

        st.subheader("Generar orden de compra")
        st.caption("Completá las cantidades y confirmá la orden")

        cols_editar = ["sku", "nombre_producto", "semaforo", "unidades_a_pedir", "mi_pedido"]
        df_editable = st.data_editor(
            df[cols_editar].copy(),
            column_config={
                "mi_pedido": st.column_config.NumberColumn("Mi Pedido", min_value=0, step=1),
                "sku": st.column_config.TextColumn("SKU", disabled=True),
                "nombre_producto": st.column_config.TextColumn("Producto", disabled=True),
                "semaforo": st.column_config.TextColumn("Semáforo", disabled=True),
                "unidades_a_pedir": st.column_config.NumberColumn("Sugerido", disabled=True),
            },
            use_container_width=True,
            hide_index=True,
        )

        items_pedido = df_editable[df_editable["mi_pedido"] > 0].to_dict("records")

        if items_pedido:
            total_uds = sum(int(i["mi_pedido"]) for i in items_pedido)
            st.info(f"{len(items_pedido)} productos seleccionados — {total_uds} unidades totales")

            if st.button("Confirmar orden", type="primary"):
                for item in items_pedido:
                    sku = item["sku"]
                    row = df[df["sku"] == sku].iloc[0]
                    item["lead_time_dias"] = row.get("lead_time_dias", 15)
                    item["nombre_producto"] = row.get("nombre_producto", "")
                    item["costo_sin_iva"] = row.get("costo_sin_iva", 0)

                with st.spinner("Guardando orden en BigQuery..."):
                    id_orden = confirmar_orden(proveedor, items_pedido)
                st.success(f"Orden {id_orden} confirmada — {total_uds} unidades")

    # ── TAB 2: ÓRDENES ────────────────────────────────────────────────────────
    with tab2:
        if st.button("Actualizar órdenes"):
            cargar_ordenes.clear()

        ordenes = cargar_ordenes()

        if ordenes.empty:
            st.info("No hay órdenes registradas.")
        else:
            st.dataframe(ordenes, use_container_width=True, hide_index=True)

            st.subheader("Modificar orden")
            id_sel = st.selectbox("Seleccioná una orden", ordenes["id_orden"].tolist())
            accion = st.radio("Acción", ["Marcar como Recibido", "Revertir a En camino", "Eliminar orden"])

            if accion == "Eliminar orden":
                st.warning(f"Vas a eliminar la orden {id_sel}. Esta acción no se puede deshacer.")

            if st.button("Ejecutar"):
                if accion == "Eliminar orden":
                    bq = get_bq_client()
                    bq.query(f"""
                        DELETE FROM `{PROJECT}.{DATASET}.ordenes_compra_detalle`
                        WHERE id_orden = '{id_sel}'
                    """).result()
                    bq.query(f"""
                        DELETE FROM `{PROJECT}.{DATASET}.ordenes_compra`
                        WHERE id_orden = '{id_sel}'
                    """).result()
                    cargar_ordenes.clear()
                    st.success(f"Orden {id_sel} eliminada")
                else:
                    nuevo_estado = "Recibido" if accion == "Marcar como Recibido" else "En camino"
                    cambiar_estado_orden(id_sel, nuevo_estado)
                    st.success(f"Orden {id_sel} → {nuevo_estado}")

    # ── TAB 3: RECEPCIÓN ──────────────────────────────────────────────────────
    with tab3:
        st.subheader("Registrar recepción de mercadería")
        st.caption("Seleccioná una orden activa y confirmá qué llegó")

        ordenes_activas = cargar_ordenes()
        ordenes_activas = ordenes_activas[ordenes_activas["estado"].isin(["En camino", "Recibido parcial"])]

        if ordenes_activas.empty:
            st.info("No hay órdenes activas.")
        else:
            id_orden = st.selectbox("Orden", ordenes_activas["id_orden"].tolist())

            bq = get_bq_client()
            detalle = bq.query(f"""
                SELECT sku, nombre_producto, cantidad_pedida, cantidad_recibida
                FROM `{PROJECT}.{DATASET}.ordenes_compra_detalle`
                WHERE id_orden = '{id_orden}'
                ORDER BY sku
            """).to_dataframe()

            detalle["recibido_ahora"] = detalle["cantidad_pedida"] - detalle["cantidad_recibida"]

            detalle_editable = st.data_editor(
                detalle,
                column_config={
                    "recibido_ahora": st.column_config.NumberColumn("Recibido ahora", min_value=0, step=1),
                    "sku": st.column_config.TextColumn(disabled=True),
                    "nombre_producto": st.column_config.TextColumn(disabled=True),
                    "cantidad_pedida": st.column_config.NumberColumn(disabled=True),
                    "cantidad_recibida": st.column_config.NumberColumn(disabled=True),
                },
                use_container_width=True,
                hide_index=True,
            )

            if st.button("Confirmar recepción", type="primary"):
                bq2 = get_bq_client()
                for _, row in detalle_editable.iterrows():
                    nueva_cant = int(row["cantidad_recibida"]) + int(row["recibido_ahora"])
                    bq2.query(f"""
                        UPDATE `{PROJECT}.{DATASET}.ordenes_compra_detalle`
                        SET cantidad_recibida = {nueva_cant}
                        WHERE id_orden = '{id_orden}' AND sku = '{row['sku']}'
                    """).result()

                check = bq2.query(f"""
                    SELECT SUM(cantidad_pedida) as pedido, SUM(cantidad_recibida) as recibido
                    FROM `{PROJECT}.{DATASET}.ordenes_compra_detalle`
                    WHERE id_orden = '{id_orden}'
                """).to_dataframe()

                pedido = check["pedido"].iloc[0]
                recibido = check["recibido"].iloc[0]
                nuevo_estado = "Recibido" if recibido >= pedido * 0.95 else "Recibido parcial"

                bq2.query(f"""
                    UPDATE `{PROJECT}.{DATASET}.ordenes_compra`
                    SET estado = '{nuevo_estado}'
                    WHERE id_orden = '{id_orden}'
                """).result()

                cargar_ordenes.clear()
                st.success(f"Recepción confirmada — orden {id_orden} → {nuevo_estado}")

if __name__ == "__main__":
    main()