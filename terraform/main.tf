terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group
  location = var.location
}

# ---------------------------------------------------------------------------
# Storage + container input/
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "sa" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "input" {
  name                  = "input"
  storage_account_name  = azurerm_storage_account.sa.name
  container_access_type = "private"
}

# ---------------------------------------------------------------------------
# Service Bus + queue avec DLQ (max_delivery_count = 3)
# ---------------------------------------------------------------------------
resource "azurerm_servicebus_namespace" "sb" {
  name                = var.servicebus_namespace
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "Standard"
}

resource "azurerm_servicebus_queue" "documents" {
  name         = "documents"
  namespace_id = azurerm_servicebus_namespace.sb.id

  max_delivery_count                      = 3
  dead_lettering_on_message_expiration    = true
  lock_duration                           = "PT1M"
  default_message_ttl                     = "P14D"
}

# ---------------------------------------------------------------------------
# Cosmos DB (NoSQL)
# ---------------------------------------------------------------------------
resource "azurerm_cosmosdb_account" "cosmos" {
  name                = var.cosmos_account_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.rg.location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "db" {
  name                = "documents"
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
}

resource "azurerm_cosmosdb_sql_container" "container" {
  name                  = "documents"
  resource_group_name   = azurerm_resource_group.rg.name
  account_name          = azurerm_cosmosdb_account.cosmos.name
  database_name         = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths   = ["/id"]
}

# ---------------------------------------------------------------------------
# SignalR (mode Serverless)
# ---------------------------------------------------------------------------
resource "azurerm_signalr_service" "signalr" {
  name                = var.signalr_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  sku {
    name     = "Free_F1"
    capacity = 1
  }

  service_mode = "Serverless"

  cors {
    allowed_origins = ["*"]
  }
}

# ---------------------------------------------------------------------------
# Application Insights
# ---------------------------------------------------------------------------
resource "azurerm_application_insights" "ai" {
  name                = "${var.function_app_name}-ai"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  application_type    = "web"
}

# ---------------------------------------------------------------------------
# Function App (Linux, Python)
# ---------------------------------------------------------------------------
resource "azurerm_service_plan" "plan" {
  name                = "${var.function_app_name}-plan"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = "Linux"
  sku_name            = "Y1" # Consumption
}

resource "azurerm_linux_function_app" "func" {
  name                       = var.function_app_name
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  service_plan_id            = azurerm_service_plan.plan.id
  storage_account_name       = azurerm_storage_account.sa.name
  storage_account_access_key = azurerm_storage_account.sa.primary_access_key

  site_config {
    application_stack {
      python_version = "3.11"
    }
    application_insights_connection_string = azurerm_application_insights.ai.connection_string
  }

  app_settings = {
    "FUNCTIONS_WORKER_RUNTIME"   = "python"
    "ServiceBusConnection"       = azurerm_servicebus_namespace.sb.default_primary_connection_string
    "SERVICE_BUS_QUEUE"          = azurerm_servicebus_queue.documents.name
    "COSMOS_ENDPOINT"            = azurerm_cosmosdb_account.cosmos.endpoint
    "COSMOS_KEY"                 = azurerm_cosmosdb_account.cosmos.primary_key
    "COSMOS_DATABASE"            = "documents"
    "COSMOS_CONTAINER"           = "documents"
    "SignalRConnectionString"    = azurerm_signalr_service.signalr.primary_connection_string
    "SIGNALR_HUB"                = "documents"
    "AZURE_OPENAI_ENDPOINT"      = var.azure_openai_endpoint
    "AZURE_OPENAI_API_KEY"       = var.azure_openai_api_key
    "AZURE_OPENAI_DEPLOYMENT"    = var.azure_openai_deployment
  }
}

# ---------------------------------------------------------------------------
# Static Web App (frontend React)
# ---------------------------------------------------------------------------
resource "azurerm_static_web_app" "swa" {
  name                = var.static_web_app_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.swa_location
  sku_tier            = "Free"
  sku_size            = "Free"
}
