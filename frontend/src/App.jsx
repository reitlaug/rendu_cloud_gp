import { useState, useCallback } from "react";
import { useSignalR } from "./useSignalR";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STATUS_COLORS = {
  CREATED: "#64748b",
  UPLOADED: "#3b82f6",
  QUEUED: "#6366f1",
  PROCESSING: "#f59e0b",
  PROCESSED: "#22c55e",
  ERROR: "#ef4444",
};

// ordre des étapes pour la barre de progression
const FLOW = ["CREATED", "UPLOADED", "QUEUED", "PROCESSING", "PROCESSED"];

function ProgressSteps({ status }) {
  const isError = status === "ERROR";
  const currentIdx = FLOW.indexOf(status);
  return (
    <div className="steps">
      {FLOW.map((_, i) => (
        <div
          key={i}
          className={
            "step " + (isError ? "error" : i <= currentIdx ? "done" : "")
          }
        />
      ))}
    </div>
  );
}

export default function App() {
  const [docs, setDocs] = useState({});
  const [file, setFile] = useState(null);

  const onUpdate = useCallback((payload) => {
    setDocs((prev) => ({
      ...prev,
      [payload.documentId]: {
        ...prev[payload.documentId],
        documentId: payload.documentId,
        status: payload.status,
        message: payload.message,
        tags: payload.tags ?? prev[payload.documentId]?.tags,
      },
    }));
  }, []);

  const { connected } = useSignalR(onUpdate);

  async function handleUpload() {
    if (!file) return;
    const createRes = await fetch(`${API_BASE}/documents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fileName: file.name }),
    });
    const { documentId, uploadUrl } = await createRes.json();

    setDocs((prev) => ({
      ...prev,
      [documentId]: { documentId, status: "CREATED", message: "Création du document...", fileName: file.name },
    }));

    await fetch(uploadUrl, {
      method: "PUT",
      headers: { "x-ms-blob-type": "BlockBlob" },
      body: file,
    });
    setFile(null);
  }

  async function handleRetry(documentId) {
    await fetch(`${API_BASE}/documents/${documentId}/retry`, { method: "POST" });
  }

  const list = Object.values(docs).reverse();

  return (
    <div className="container">
      <div className="header">
        <h1>Pipeline Documents</h1>
        <p>Traitement asynchrone · Tagging IA · Notifications temps réel</p>
      </div>

      <div style={{ textAlign: "center" }}>
        <span className="pill">
          <span className={"dot " + (connected ? "on" : "off")} />
          SignalR {connected ? "connecté" : "déconnecté"}
        </span>
      </div>

      <div className="upload">
        <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <button className="btn" onClick={handleUpload} disabled={!file}>
          Uploader
        </button>
      </div>

      <div className="cards">
        {list.length === 0 && (
          <div className="empty">Aucun document. Upload un fichier pour démarrer le pipeline.</div>
        )}
        {list.map((doc) => (
          <div className="card" key={doc.documentId}>
            <div className="card-top">
              <span className="doc-id">
                #{doc.documentId}
                {doc.fileName ? <span style={{ color: "var(--muted)", fontWeight: 400 }}> · {doc.fileName}</span> : null}
              </span>
              <span
                className={"badge " + (doc.status === "PROCESSING" ? "processing" : "")}
                style={{ background: STATUS_COLORS[doc.status] || "#64748b" }}
              >
                {doc.status}
              </span>
            </div>

            <ProgressSteps status={doc.status} />

            {doc.message && <p className="msg">{doc.message}</p>}

            {doc.tags && doc.tags.length > 0 && (
              <div className="tags">
                {doc.tags.map((t) => (
                  <span className="tag" key={t}>#{t}</span>
                ))}
              </div>
            )}

            {doc.status === "ERROR" && (
              <button className="btn ghost" style={{ marginTop: 14 }} onClick={() => handleRetry(doc.documentId)}>
                ↻ Relancer
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
