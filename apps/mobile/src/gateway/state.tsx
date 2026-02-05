import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { GatewayClient } from './client';

type GatewayState = {
  url: string;
  token: string;
  connected: boolean;
  lastEventId: number | null;
  events: unknown[];

  connect: (params: { url: string; token: string }) => Promise<void>;
  disconnect: () => void;

  sendMessage: (params: { sessionId: string; text: string }) => void;
  listSessions: () => void;
  listTasks: () => void;
  listDimsums: () => void;
  listMemories: () => void;
  getSettings: () => void;
};

const GatewayContext = createContext<GatewayState | null>(null);

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}

function getEventId(v: unknown): number | null {
  if (!isObject(v)) return null;
  const raw = v.eventId;
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  return null;
}

export function GatewayProvider({ children }: { children: React.ReactNode }) {
  const [url, setUrl] = useState('ws://127.0.0.1:3901/ws');
  const [token, setToken] = useState('');
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<unknown[]>([]);
  const [lastEventId, setLastEventId] = useState<number | null>(null);

  const clientRef = useRef<GatewayClient | null>(null);

  const onEvent = useCallback((evt: unknown) => {
    setEvents((prev) => {
      const next = [...prev, evt];
      return next.length > 2000 ? next.slice(-2000) : next;
    });

    const eid = getEventId(evt);
    if (eid != null) setLastEventId((cur) => (cur == null ? eid : Math.max(cur, eid)));

    if (isObject(evt) && evt.type === 'auth.paired' && isObject(evt.payload)) {
      const t = evt.payload.token;
      if (typeof t === 'string') setToken(t);
    }
  }, []);

  const connect = useCallback(
    async (params: { url: string; token: string }) => {
      setUrl(params.url);
      setToken(params.token);
      setEvents([]);
      setLastEventId(null);

      clientRef.current?.disconnect();
      clientRef.current = null;

      const c = new GatewayClient({
        url: params.url,
        onEvent,
        onOpen: () => setConnected(true),
        onClose: () => setConnected(false),
        onError: () => {},
      });
      clientRef.current = c;
      c.connect({ token: params.token, lastEventId: null });
    },
    [onEvent],
  );

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
    clientRef.current = null;
    setConnected(false);
  }, []);

  const sendMessage = useCallback((params: { sessionId: string; text: string }) => {
    clientRef.current?.send({ type: 'sendMessage', sessionId: params.sessionId, text: params.text });
  }, []);

  const listSessions = useCallback(() => clientRef.current?.send({ type: 'listSessions' }), []);
  const listTasks = useCallback(() => clientRef.current?.send({ type: 'listTasks' }), []);
  const listDimsums = useCallback(() => clientRef.current?.send({ type: 'listDimsums' }), []);
  const listMemories = useCallback(() => clientRef.current?.send({ type: 'listMemories' }), []);
  const getSettings = useCallback(() => clientRef.current?.send({ type: 'getSettings' }), []);

  const api = useMemo<GatewayState>(() => {
    return {
      url,
      token,
      connected,
      lastEventId,
      events,
      connect,
      disconnect,
      sendMessage,
      listSessions,
      listTasks,
      listDimsums,
      listMemories,
      getSettings,
    };
  }, [url, token, connected, lastEventId, events, connect, disconnect, sendMessage, listSessions, listTasks, listDimsums, listMemories, getSettings]);

  return <GatewayContext.Provider value={api}>{children}</GatewayContext.Provider>;
}

export function useGateway(): GatewayState {
  const ctx = useContext(GatewayContext);
  if (!ctx) throw new Error('useGateway must be used within GatewayProvider');
  return ctx;
}
