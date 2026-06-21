variable "resource_group" { default = "rg-doc-pipeline" }
variable "location" { default = "francecentral" }
variable "swa_location" { default = "westeurope" }

variable "storage_account_name" { default = "stdocpipeline01" }
variable "servicebus_namespace" { default = "sb-doc-pipeline-01" }
variable "cosmos_account_name" { default = "cosmos-doc-pipeline-01" }
variable "signalr_name" { default = "signalr-doc-pipeline-01" }
variable "function_app_name" { default = "func-doc-pipeline-01" }
variable "static_web_app_name" { default = "swa-doc-pipeline-01" }

variable "azure_openai_endpoint" {
  type    = string
  default = ""
}
variable "azure_openai_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
variable "azure_openai_deployment" {
  type    = string
  default = "gpt-4o-mini"
}
