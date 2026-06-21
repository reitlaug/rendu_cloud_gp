import { useState, useCallback } from "react";
import { useSignalR } from "./useSignalR";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STATUS_COLORS = {
  CREATED: "#9ca3af",
  UPLOADED: "#3b82f6",
  QUEUED: "#6366f1",
  PROCESSING: "#f59e0b",
  PROCESSED: "#22c55e",
  ERROR: "#ef4444",
};

export default function App() {
  const [docs, setDocs] = useState({});
  const [file, setFile] = useState(null);

  // Réception des notifications temps réel
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

    // 1. Crée le document + récupère l'URL SAS
    const createRes = await fetch(`${API_BASE}/documents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fileName: file.name }),
    });
    const { documentId, uploadUrl } = await createRes.json();

    setDocs((prev) => ({
      ...prev,
      [documentId]: { documentId, status: "CREATED", message: "Création..." },
    }));

    // 2. Upload direct dans Blob Storage via SAS
    await fetch(uploadUrl, {
      method: "PUT",
      headers: { "x-ms-blob-type": "BlockBlob" },
      body: file,
    });
    // À partir d'ici, le Blob Trigger prend le relais (notifs temps réel)
  }

  async function handleRetry(documentId) {
    await fetch(`${API_BASE}/documents/${documentId}/retry`, { method: "POST" });
  }

  return (
    <div style={{ fontFamily: "system-ui", maxWidth: 720, margin: "40px auto", padding: 16 }}>
      <h1>Pipeline Documents</h1>
      <p>
        SignalR :{" "}
        <strong style={{ color: connected ? "#22c55e" : "#ef4444" }}>
          {connected ? "connecté" : "déconnecté"}
        </strong>
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <button onClick={handleUpload} disabled={!file}>
          Uploader
        </button>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {Object.values(docs).map((doc) => (
          <div
            key={doc.documentId}
            style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 12 }}
          >
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span><strong>#{doc.documentId}</strong></span>
              <span
                style={{
                  background: STATUS_COLORS[doc.status] || "#9ca3af",
                  color: "white", borderRadius: 12, padding: "2px 10px", fontSize: 12,
                }}
              >
                {doc.status}
              </span>
            </div>
            <p style={{ margin: "8px 0", color: "#6b7280" }}>{doc.message}</p>
            {doc.tags && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {doc.tags.map((t) => (
                  <span key={t} style={{ background: "#eef2ff", borderRadius: 6, padding: "2px 8px", fontSize: 12 }}>
                    {t}
                  </span>
                ))}
              </div>
            )}
            {doc.status === "ERROR" && (
              <button onClick={() => handleRetry(doc.documentId)} style={{ marginTop: 8 }}>
                Relancer
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
