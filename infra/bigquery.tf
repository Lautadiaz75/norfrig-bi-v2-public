resource "google_bigquery_dataset" "norfrig_bi_dev" {
  dataset_id  = var.dataset_id
  location    = var.region
  description = "Dataset principal de Norfrig BI v2 — ambiente dev"
}

resource "google_bigquery_table" "raw_ventas" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "raw_ventas"
  deletion_protection = false

  schema = jsonencode([
    { name = "fecha",           type = "DATE",    mode = "NULLABLE" },
    { name = "cuenta",          type = "STRING",  mode = "NULLABLE" },
    { name = "id_comprobante",  type = "INTEGER", mode = "NULLABLE" },
    { name = "numero",          type = "STRING",  mode = "NULLABLE" },
    { name = "tipo_fc",         type = "STRING",  mode = "NULLABLE" },
    { name = "es_cot",          type = "BOOLEAN", mode = "NULLABLE" },
    { name = "origen",          type = "STRING",  mode = "NULLABLE" },
    { name = "sku",             type = "STRING",  mode = "NULLABLE" },
    { name = "nombre_producto", type = "STRING",  mode = "NULLABLE" },
    { name = "cantidad",        type = "FLOAT",   mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "stock_por_deposito" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "stock_por_deposito"
  deletion_protection = false

  schema = jsonencode([
    { name = "fecha_sync",       type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "cuenta",           type = "STRING",    mode = "NULLABLE" },
    { name = "deposito_id",      type = "INTEGER",   mode = "NULLABLE" },
    { name = "deposito_nombre",  type = "STRING",    mode = "NULLABLE" },
    { name = "sku",              type = "STRING",    mode = "NULLABLE" },
    { name = "stock_actual",     type = "FLOAT",     mode = "NULLABLE" },
    { name = "stock_reservado",  type = "FLOAT",     mode = "NULLABLE" },
    { name = "stock_disponible", type = "FLOAT",     mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "devoluciones_diarias" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "devoluciones_diarias"
  deletion_protection = false

  schema = jsonencode([
    { name = "fecha",           type = "DATE",    mode = "NULLABLE" },
    { name = "cuenta",          type = "STRING",  mode = "NULLABLE" },
    { name = "id_comprobante",  type = "INTEGER", mode = "NULLABLE" },
    { name = "tipo_fc",         type = "STRING",  mode = "NULLABLE" },
    { name = "sku",             type = "STRING",  mode = "NULLABLE" },
    { name = "cantidad",        type = "FLOAT",   mode = "NULLABLE" },
  ])
}
resource "google_bigquery_table" "skus_huerfanos" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "skus_huerfanos"
  deletion_protection = false

  schema = jsonencode([
    { name = "fecha_deteccion", type = "DATE",    mode = "NULLABLE" },
    { name = "sku",             type = "STRING",  mode = "NULLABLE" },
    { name = "nombre_producto", type = "STRING",  mode = "NULLABLE" },
    { name = "cuenta",          type = "STRING",  mode = "NULLABLE" },
    { name = "veces_vendido",   type = "INTEGER", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "stock_por_deposito_ayer" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "stock_por_deposito_ayer"
  deletion_protection = false

  schema = jsonencode([
    { name = "fecha_sync",       type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "cuenta",           type = "STRING",    mode = "NULLABLE" },
    { name = "deposito_id",      type = "INTEGER",   mode = "NULLABLE" },
    { name = "deposito_nombre",  type = "STRING",    mode = "NULLABLE" },
    { name = "sku",              type = "STRING",    mode = "NULLABLE" },
    { name = "stock_actual",     type = "FLOAT",     mode = "NULLABLE" },
    { name = "stock_reservado",  type = "FLOAT",     mode = "NULLABLE" },
    { name = "stock_disponible", type = "FLOAT",     mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "maestro_productos" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "maestro_productos"
  deletion_protection = false

  schema = jsonencode([
    { name = "Tipo",             type = "STRING",  mode = "NULLABLE" },
    { name = "SKU",              type = "STRING",  mode = "NULLABLE" },
    { name = "Nombre",           type = "STRING",  mode = "NULLABLE" },
    { name = "Estado",           type = "STRING",  mode = "NULLABLE" },
    { name = "Costo Interno",    type = "FLOAT64", mode = "NULLABLE" },
    { name = "Precio",           type = "FLOAT64", mode = "NULLABLE" },
    { name = "Stock Disponible", type = "FLOAT64", mode = "NULLABLE" },
    { name = "Rubro",            type = "STRING",  mode = "NULLABLE" },
    { name = "Sub Rubro",        type = "STRING",  mode = "NULLABLE" },
    { name = "Proveedor",        type = "STRING",  mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "dim_productos" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "dim_productos"
  deletion_protection = false

  schema = jsonencode([
    { name = "sku",                  type = "STRING", mode = "NULLABLE" },
    { name = "id_proveedor",         type = "STRING", mode = "NULLABLE" },
    { name = "estado_planificacion", type = "STRING", mode = "NULLABLE" },
    { name = "sku_ancestro",         type = "STRING", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "dim_proveedores" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "dim_proveedores"
  deletion_protection = false

  schema = jsonencode([
    { name = "id_proveedor",         type = "STRING",  mode = "NULLABLE" },
    { name = "nombre_proveedor",     type = "STRING",  mode = "NULLABLE" },
    { name = "lead_time_dias",       type = "INTEGER", mode = "NULLABLE" },
    { name = "dias_stock_seguridad", type = "INTEGER", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "ordenes_compra" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "ordenes_compra"
  deletion_protection = false

  schema = jsonencode([
    { name = "id_orden",                  type = "STRING",  mode = "NULLABLE" },
    { name = "proveedor",                 type = "STRING",  mode = "NULLABLE" },
    { name = "fecha_orden",               type = "DATE",    mode = "NULLABLE" },
    { name = "fecha_estimada_llegada",    type = "DATE",    mode = "NULLABLE" },
    { name = "estado",                    type = "STRING",  mode = "NULLABLE" },
    { name = "total_uds",                 type = "INTEGER", mode = "NULLABLE" },
    { name = "notas",                     type = "STRING",  mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "ordenes_compra_detalle" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "ordenes_compra_detalle"
  deletion_protection = false

  schema = jsonencode([
    { name = "id_orden",           type = "STRING",  mode = "NULLABLE" },
    { name = "sku",                type = "STRING",  mode = "NULLABLE" },
    { name = "nombre_producto",    type = "STRING",  mode = "NULLABLE" },
    { name = "cantidad_pedida",    type = "INTEGER", mode = "NULLABLE" },
    { name = "cantidad_recibida",  type = "INTEGER", mode = "NULLABLE" },
    { name = "costo_sin_iva",      type = "FLOAT64", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "recepciones_procesadas" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "recepciones_procesadas"
  deletion_protection = false

  schema = jsonencode([
    { name = "numero_factura",    type = "STRING", mode = "NULLABLE" },
    { name = "proveedor",         type = "STRING", mode = "NULLABLE" },
    { name = "fecha_procesado",   type = "DATE",   mode = "NULLABLE" },
    { name = "id_archivo_drive",  type = "STRING", mode = "NULLABLE" },
    { name = "ordenes_cerradas",  type = "STRING", mode = "NULLABLE" },
  ])
}
resource "google_bigquery_table" "diccionario_combos" {
  dataset_id          = google_bigquery_dataset.norfrig_bi_dev.dataset_id
  table_id            = "diccionario_combos"
  deletion_protection = false

  schema = jsonencode([
    { name = "SKU Combo",             type = "STRING",  mode = "NULLABLE" },
    { name = "Estado",                type = "STRING",  mode = "NULLABLE" },
    { name = "Nombre",                type = "STRING",  mode = "NULLABLE" },
    { name = "Descripcion",           type = "STRING",  mode = "NULLABLE" },
    { name = "CC Compras",            type = "STRING",  mode = "NULLABLE" },
    { name = "CC Ventas",             type = "FLOAT64", mode = "NULLABLE" },
    { name = "CC Mercaderia",         type = "INT64",   mode = "NULLABLE" },
    { name = "Observaciones",         type = "STRING",  mode = "NULLABLE" },
    { name = "Costo Interno Combo",   type = "FLOAT64", mode = "NULLABLE" },
    { name = "Rentabilidad Combo",    type = "FLOAT64", mode = "NULLABLE" },
    { name = "Precio Unitario Combo", type = "STRING",  mode = "NULLABLE" },
    { name = "Iva Combo",             type = "STRING",  mode = "NULLABLE" },
    { name = "Precio Final Combo",    type = "FLOAT64", mode = "NULLABLE" },
    { name = "Precio Automatico",     type = "STRING",  mode = "NULLABLE" },
    { name = "Moneda",                type = "STRING",  mode = "NULLABLE" },
    { name = "Cantidad",              type = "FLOAT64", mode = "NULLABLE" },
    { name = "Codigo",                type = "STRING",  mode = "NULLABLE" },
    { name = "Item",                  type = "STRING",  mode = "NULLABLE" },
    { name = "Costo Interno",         type = "FLOAT64", mode = "NULLABLE" },
    { name = "Rentabilidad",          type = "FLOAT64", mode = "NULLABLE" },
    { name = "Precio Unitario",       type = "FLOAT64", mode = "NULLABLE" },
    { name = "Iva",                   type = "INT64",   mode = "NULLABLE" },
    { name = "Precio Final",          type = "FLOAT64", mode = "NULLABLE" },
  ])
}