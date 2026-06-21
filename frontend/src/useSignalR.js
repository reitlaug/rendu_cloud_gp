import { useEffect, useRef, useState } from "react";
import {
  HubConnectionBuilder,
  HttpTransportType,
  LogLevel,
} from "@microsoft/signalr";

const FUNCTIONS_BASE = import.meta.env.VITE_FUNCTIONS_URL || "http://localhost:7071/api";

/**
 * Connecte le client au SignalR Service en mode serverless :
 *  1. POST /negotiate -> { url, accessToken }
 *  2. Ouverture de la connexion vers le service
 *  3. Écoute du target "documentUpdate"
 */
export function useSignalR(onUpdate) {
  const [connected, setConnected] = useState(false);
  const connectionRef = useRef(null);

  useEffect(() => {
    let stopped = false;

    async function start() {
      const res = await fetch(`${FUNCTIONS_BASE}/negotiate`, { method: "POST" });
      const info = await res.json();

      const connection = new HubConnectionBuilder()
        .withUrl(info.url, {
          accessTokenFactory: () => info.accessToken,
          transport: HttpTransportType.WebSockets,
        })
        .withAutomaticReconnect()
        .configureLogging(LogLevel.Information)
        .build();

      connection.on("documentUpdate", (payload) => {
        onUpdate(payload);
      });

      connection.onreconnected(() => setConnected(true));
      connection.onclose(() => setConnected(false));

      try {
        await connection.start();
        if (!stopped) {
          connectionRef.current = connection;
          setConnected(true);
        }
      } catch (e) {
        console.error("SignalR start failed", e);
      }
    }

    start();
    return () => {
      stopped = true;
      connectionRef.current?.stop();
    };
  }, []);

  return { connected };
}
