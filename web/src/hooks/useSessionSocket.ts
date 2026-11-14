import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { SessionSnapshot, WsEvent } from "../types";

const EMPTY_SNAPSHOT: SessionSnapshot = {
  status: "idle",
  run_mode: "attach",
  policy: "model",
  attempt_id: null,
  state: null,
  state_view: null,
  latest_decision: null,
  combat_assessment: null,
  run_context: null,
  recent_steps: [],
  stats: {
    steps: 0,
    verified_actions: 0,
    fallbacks: 0,
    policy_rules: 0,
    input_tokens: 0,
    output_tokens: 0,
  },
  last_error: null,
};

export function useSessionSocket() {
  const [snapshot, setSnapshot] = useState<SessionSnapshot>(EMPTY_SNAPSHOT);
  const [wsConnected, setWsConnected] = useState(false);
  const retryRef = useRef(0);

  const refreshSnapshot = useCallback(async () => {
    try {
      const next = await api.getSession();
      setSnapshot(next);
    } catch {
      // Ignore transient initial load errors while server boots.
    }
  }, []);

  useEffect(() => {
    void refreshSnapshot();

    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pingTimer: number | null = null;

    const connect = () => {
      if (disposed) return;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/api/ws`;
      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        if (disposed) return;
        retryRef.current = 0;
        setWsConnected(true);
        pingTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send("ping");
          }
        }, 20000);
      };

      socket.onmessage = (event) => {
        if (disposed) return;
        try {
          const msg = JSON.parse(event.data) as WsEvent;
          setSnapshot((prev) => applyWsEvent(prev, msg));
        } catch {
          // Ignore malformed WS payloads.
        }
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = () => {
        setWsConnected(false);
        if (pingTimer !== null) {
          window.clearInterval(pingTimer);
          pingTimer = null;
        }
        if (disposed) return;
        const delayMs = Math.min(8000, 600 * Math.pow(1.6, retryRef.current));
        retryRef.current += 1;
        reconnectTimer = window.setTimeout(connect, delayMs);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (pingTimer !== null) window.clearInterval(pingTimer);
      socket?.close();
    };
  }, [refreshSnapshot]);

  return { snapshot, setSnapshot, wsConnected, refreshSnapshot };
}

function applyWsEvent(prev: SessionSnapshot, event: WsEvent): SessionSnapshot {
  switch (event.type) {
    case "session_snapshot":
      return event.data;
    case "session_status":
      return {
        ...prev,
        status: event.data.status,
        run_mode: event.data.run_mode,
        policy: event.data.policy,
        attempt_id: event.data.attempt_id,
        last_error: event.data.last_error,
      };
    case "state_updated":
      return {
        ...prev,
        state: event.data.state,
        state_view: event.data.state_view,
        combat_assessment: event.data.combat_assessment,
        run_context: event.data.run_context,
      };
    case "decision_made": {
      const nextRecent = [...prev.recent_steps, event.data.step_record].slice(-200);
      return {
        ...prev,
        latest_decision: event.data.decision,
        stats: event.data.stats,
        recent_steps: nextRecent,
      };
    }
    case "run_finished":
      return {
        ...prev,
        status: "idle",
      };
    case "error":
      return {
        ...prev,
        last_error: event.data.message ?? event.data.error ?? prev.last_error,
      };
    case "pong":
    default:
      return prev;
  }
}
