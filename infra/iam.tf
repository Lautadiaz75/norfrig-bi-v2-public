resource "google_service_account" "norfrig_ingestion" {
  account_id   = "norfrig-ingestion"
  display_name = "Norfrig BI Ingestion"
  description  = "Service account para los containers de ingesta de Norfrig BI v2"
}

resource "google_project_iam_member" "bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.norfrig_ingestion.email}"
}

resource "google_project_iam_member" "bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.norfrig_ingestion.email}"
}