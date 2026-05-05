import functions_framework
from google.cloud import bigquery
import json

client = bigquery.Client(project="norfrig-bi-dev")  # ← cambiado

@functions_framework.http
def generar_orden(request):
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}

    request_args = request.args
    proveedor = request_args.get('proveedor', 'TODOS')

    query = "SELECT * FROM `norfrig-bi-dev.norfrig_bi_dev.mart_compra_precalculadas`"  # ← cambiado
    job_config = bigquery.QueryJobConfig()

    if proveedor != 'TODOS':
        query += " WHERE proveedor = @prov"
        job_config.query_parameters = [
            bigquery.ScalarQueryParameter("prov", "STRING", proveedor)
        ]
    
    query += " ORDER BY proveedor, orden_prioridad ASC, unidades_a_pedir DESC"

    try:
        query_job = client.query(query, job_config=job_config)
        resultados = [dict(row) for row in query_job]
        return (json.dumps(resultados, default=str), 200, headers)
    except Exception as e:
        return (json.dumps({"error": str(e)}), 500, headers)