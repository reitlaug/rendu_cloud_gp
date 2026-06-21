# Schéma d'architecture

```text
┌─────────────┐        upload SAS (PUT)        ┌──────────────────────┐
│   React     │ ──────────────────────────────▶│  Blob Storage        │
│  (Vite)     │                                 │  container input/    │
└─────────────┘                                 └──────────┬───────────┘
      ▲                                                      │ Blob Trigger
      │ notifications temps réel (SignalR)                   ▼
      │                                          ┌──────────────────────┐
┌─────┴─────────────┐                            │ Function              │
│ Azure SignalR     │◀───────────────────────────│ blob_uploaded         │
│ Service           │        notify UPLOADED      │ - extrait infos       │
│ (Serverless)      │                             │ - publie Service Bus  │
└───────────────────┘                             │ - status QUEUED       │
      ▲   ▲                                        └──────────┬───────────┘
      │   │                                                    │
      │   │                                                    ▼
      │   │                                         ┌──────────────────────┐
      │   │   notify PROCESSING / PROCESSED         │ Service Bus Queue     │
      │   └─────────────────────────────────────────│ "documents"           │
      │                                              │ max_delivery_count=3  │
      │                                              └────┬─────────────┬────┘
      │                                                   │             │ échec x3
      │                                                   ▼             ▼
      │                                      ┌──────────────────┐  ┌──────────────┐
      │                                      │ Function          │  │  DLQ         │
      │                                      │ process_document  │  │ $DeadLetter  │
      │                                      │ - PROCESSING      │  └──────┬───────┘
      │                                      │ - IA tagging      │         │ DLQ Trigger
      │                                      │ - Cosmos update   │         ▼
      │                                      │ - PROCESSED       │  ┌──────────────────┐
      │                                      └─────────┬─────────┘  │ Function         │
      │   notify ERROR                                 │            │ dlq_alert        │
      └────────────────────────────────────────────────┼───────────│ - status ERROR   │
                                                        ▼            │ - errorMessage   │
                                              ┌──────────────────┐  └──────────────────┘
                                              │  Cosmos DB       │
                                              │  (NoSQL)         │
                                              └──────────────────┘

         ┌──────────────┐   POST /documents          ┌──────────────┐
         │   FastAPI    │   POST /documents/{id}/retry│  Service Bus │
         │              │ ───────────────────────────▶│              │
         └──────────────┘                              └──────────────┘
```

## États métier

```
CREATED → UPLOADED → QUEUED → PROCESSING → PROCESSED
                                   ↘ ERROR (via DLQ)
```

## Flux de notifications SignalR (target `documentUpdate`)

| Étape              | status      | message                  | tags |
|--------------------|-------------|--------------------------|------|
| Blob reçu          | UPLOADED    | Fichier reçu             | —    |
| Début traitement   | PROCESSING  | Traitement IA en cours   | —    |
| Fin traitement     | PROCESSED   | Tagging terminé          | ✔    |
| Échec / DLQ        | ERROR       | Erreur de traitement     | —    |
```
