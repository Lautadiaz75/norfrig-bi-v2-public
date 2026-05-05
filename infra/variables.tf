variable "project_id" {
  description = "ID del proyecto GCP"
  type        = string
}

variable "region" {
  description = "Region de GCP"
  type        = string
  default     = "southamerica-east1"
}

variable "dataset_id" {
  description = "ID del dataset de BigQuery"
  type        = string
  default     = "norfrig_bi_dev"
}