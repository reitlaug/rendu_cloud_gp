# Pipeline Cloud Asynchrone — Documents + IA + Notifications + DLQ

Architecture événementielle Azure : un document uploadé est traité de façon
asynchrone (tagging IA), suivi en temps réel côté React, avec gestion d'erreurs
via Dead Letter Queue.

> Stack : React (Vite) · FastAPI · Azure Functions (Python v2) · Service Bus +
> DLQ · Cosmos DB · Azure OpenAI · SignalR (Serverless) · Terraform · GitLab CI/CD

## Arborescence

```
.
├── api/                 # FastAPI : création doc, SAS, /documents/{id}/retry
├── functions/           # Azure Functions (Python v2)
│   ├── function_app.py  # blob_uploaded, process_document, dlq_alert, negotiate
│   └── shared/          # cosmos, signalr, ai_tagging, servicebus, logging
├── frontend/            # React + @microsoft/signalr (temps réel)
├── terraform/           # Infra complète (Service Bus DLQ, Cosmos, SignalR...)
├── .gitlab-ci.yml       # Pipeline CI/CD
├── architecture.md      # Schéma d'architecture
└── README.md
```

## Flux

1. React crée le document (`POST /documents` → FastAPI) et reçoit une **URL SAS**.
2. React **upload** le fichier dans `input/` (Blob Storage).
3. **`blob_uploaded`** (Blob Trigger) → publie un message Service Bus + notif `UPLOADED` + status `QUEUED`.
4. **`process_document`** (Service Bus Trigger) → `PROCESSING` → **IA tagging** → Cosmos `PROCESSED` → notif avec tags.
5. En cas d'échec répété (3 tentatives) → message en **DLQ**.
6. **`dlq_alert`** (DLQ Trigger) → Cosmos `status=ERROR` + `errorMessage` + notif `ERROR`.
7. `POST /documents/{id}/retry` republie le message pour relancer.

## Lancer en local

### 1. API FastAPI
```bash
cd api
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # remplir les valeurs
uvicorn main:app --reload --port 8000
```

### 2. Azure Functions
```bash
cd functions
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp local.settings.json.example local.settings.json   # remplir les valeurs
func start
```

### 3. Frontend React
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Provisionner l'infra (Terraform)
```bash
cd terraform
terraform init
terraform apply
# Récupérer les connection strings :
terraform output -json
```

## Dead Letter Queue

La queue `documents` est configurée avec `max_delivery_count = 3` et
`dead_lettering_on_message_expiration = true` (voir `terraform/main.tf`).
Un message provoque un passage en DLQ si :

- message JSON mal formé,
- `documentId` manquant ou document introuvable,
- fichier vide,
- échec répété de l'appel IA / exception non gérée.

La function `dlq_alert` écoute `documents/$DeadLetterQueue`.

## Observabilité

Tous les logs sont structurés et contiennent **`correlationId`** + **`documentId`** +
`step` + `status`. Application Insights est connecté via la Function App (Terraform).

## Variables GitLab CI/CD (Settings > CI/CD > Variables)

```
AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
AZURE_FUNCTION_APP_NAME, AZURE_RESOURCE_GROUP, AZURE_STATIC_WEB_APP_TOKEN
COSMOS_ENDPOINT, COSMOS_KEY, SERVICE_BUS_CONNECTION_STRING
SIGNALR_CONNECTION_STRING, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT
```

> Les secrets ne sont jamais commités (voir `.gitignore`).

## Tests de validation

| Cas                      | Résultat attendu |
|--------------------------|------------------|
| fichier valide           | PROCESSED        |
| fichier vide             | ERROR (DLQ)      |
| document introuvable     | ERROR (DLQ)      |
| message invalide         | DLQ              |
| échec IA répété          | fallback ou DLQ  |
