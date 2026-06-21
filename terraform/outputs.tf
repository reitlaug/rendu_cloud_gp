output "function_app_name" {
  value = azurerm_linux_function_app.func.name
}

output "function_app_default_hostname" {
  value = azurerm_linux_function_app.func.default_hostname
}

output "storage_connection_string" {
  value     = azurerm_storage_account.sa.primary_connection_string
  sensitive = true
}

output "servicebus_connection_string" {
  value     = azurerm_servicebus_namespace.sb.default_primary_connection_string
  sensitive = true
}

output "cosmos_endpoint" {
  value = azurerm_cosmosdb_account.cosmos.endpoint
}

output "cosmos_key" {
  value     = azurerm_cosmosdb_account.cosmos.primary_key
  sensitive = true
}

output "signalr_connection_string" {
  value     = azurerm_signalr_service.signalr.primary_connection_string
  sensitive = true
}

output "static_web_app_default_hostname" {
  value = azurerm_static_web_app.swa.default_host_name
}

output "static_web_app_api_key" {
  value     = azurerm_static_web_app.swa.api_key
  sensitive = true
}
