import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { GatewayClient } from './client';
import {
  aggregateErrorEvents,
  buildErrorAlerts,
  countEventsByCategory,
  getEventId,
  listErrorEvents,
  type MobileErrorAggregateDimension,
  type MobileEventCategory,
  type MobileEventErrorAlert,
  type MobileEventErrorAggregate,
  type MobileEventErrorItem,
} from './events';

type GatewayState = {
  url: string;
  token: string;
  connected: boolean;
  replayActive: boolean;
  lastEventId: number | null;
  events: unknown[];
  eventCounts: Record<MobileEventCategory, number>;
  errorAggregates: MobileEventErrorAggregate[];
  errorAlerts: MobileEventErrorAlert[];
  errorEvents: MobileEventErrorItem[];
  selectedCategory: MobileEventCategory;
  errorDimension: MobileErrorAggregateDimension;
  selectedErrorProvider: string | null;
  selectedErrorSessionId: string | null;
  errorWarnThreshold: number;
  errorCriticalThreshold: number;

  connect: (params: { url: string; token: string }) => Promise<void>;
  disconnect: () => void;

  sendMessage: (params: { sessionId: string; text: string }) => void;
  listSessions: () => void;
  listTasks: () => void;
  listDimsums: () => void;
  listMemories: () => void;
  getSettings: () => void;
  setSelectedCategory: (category: MobileEventCategory) => void;
  setErrorDimension: (dimension: MobileErrorAggregateDimension) => void;
  setSelectedErrorProvider: (provider: string | null) => void;
  setSelectedErrorSessionId: (sessionId: string | null) => void;
  setErrorThresholds: (thresholds: { warn: number; critical: number }) => void;
};

const GatewayContext = createContext<GatewayState | null>(null);

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}

export function GatewayProvider({ children }: { children: React.ReactNode }) {
  const [url, setUrl] = useState('ws://127.0.0.1:3901/ws');
  const [token, setToken] = useState('');
  const [connected, setConnected] = useState(false);
  const [replayActive, setReplayActive] = useState(false);
  const [events, setEvents] = useState<unknown[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<MobileEventCategory>('message');
  const [errorDimension, setErrorDimension] = useState<MobileErrorAggregateDimension>('global');
  const [selectedErrorProvider, setSelectedErrorProvider] = useState<string | null>(null);
  const [selectedErrorSessionId, setSelectedErrorSessionId] = useState<string | null>(null);
  const [errorWarnThreshold, setErrorWarnThreshold] = useState(3);
  const [errorCriticalThreshold, setErrorCriticalThreshold] = useState(6);
  const [lastEventId, setLastEventId] = useState<number | null>(null);
  const [lastToken, setLastToken] = useState('');

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
      if (typeof t === 'string') {
        setToken(t);
        setLastToken(t);
      }
    }
  }, []);

  const connect = useCallback(
    async (params: { url: string; token: string }) => {
      setUrl(params.url);
      setToken(params.token);

      const shouldResetHistory = params.url !== url || params.token !== lastToken;
      if (shouldResetHistory) {
        setEvents([]);
        setLastEventId(null);
      }
      setReplayActive(!shouldResetHistory && lastEventId != null);

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
      c.connect({
        token: params.token,
        lastEventId: shouldResetHistory ? null : lastEventId,
      });
      setLastToken(params.token);
    },
    [lastEventId, lastToken, onEvent, url],
  );

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
    clientRef.current = null;
    setConnected(false);
    setReplayActive(false);
  }, []);

  const sendMessage = useCallback((params: { sessionId: string; text: string }) => {
    clientRef.current?.send({ type: 'sendMessage', sessionId: params.sessionId, text: params.text });
  }, []);

  const listSessions = useCallback(() => clientRef.current?.send({ type: 'listSessions' }), []);
  const listTasks = useCallback(() => clientRef.current?.send({ type: 'listTasks' }), []);
  const listDimsums = useCallback(() => clientRef.current?.send({ type: 'listDimsums' }), []);
  const listMemories = useCallback(() => clientRef.current?.send({ type: 'listMemories' }), []);
  const getSettings = useCallback(() => clientRef.current?.send({ type: 'getSettings' }), []);

  const setErrorThresholds = useCallback((thresholds: { warn: number; critical: number }) => {
    const warn = Math.max(1, Math.floor(thresholds.warn));
    const critical = Math.max(warn, Math.floor(thresholds.critical));
    setErrorWarnThreshold(warn);
    setErrorCriticalThreshold(critical);
  }, []);

  const api = useMemo<GatewayState>(() => {
    const eventCounts = countEventsByCategory(events);
    const errorAggregates = aggregateErrorEvents(events, errorDimension);
    const errorAlerts = buildErrorAlerts(errorAggregates, errorWarnThreshold, errorCriticalThreshold);
    const providerFilter = errorDimension === 'provider' ? selectedErrorProvider : null;
    const sessionFilter = errorDimension === 'session' ? selectedErrorSessionId : null;
    const errorEvents = listErrorEvents(events, {
      provider: providerFilter,
      sessionId: sessionFilter,
      limit: 120,
    });

    const setErrorDimensionSafe = (dimension: MobileErrorAggregateDimension) => {
      setErrorDimension(dimension);
      if (dimension !== 'provider') setSelectedErrorProvider(null);
      if (dimension !== 'session') setSelectedErrorSessionId(null);
    };

    return {
      url,
      token,
      connected,
      replayActive,
      lastEventId,
      events,
      eventCounts,
      errorAggregates,
      errorAlerts,
      errorEvents,
      selectedCategory,
      errorDimension,
      selectedErrorProvider,
      selectedErrorSessionId,
      errorWarnThreshold,
      errorCriticalThreshold,
      connect,
      disconnect,
      sendMessage,
      listSessions,
      listTasks,
      listDimsums,
      listMemories,
      getSettings,
      setSelectedCategory,
      setErrorDimension: setErrorDimensionSafe,
      setSelectedErrorProvider,
      setSelectedErrorSessionId,
      setErrorThresholds,
    };
  }, [
    url,
    token,
    connected,
    replayActive,
    lastEventId,
    events,
    selectedCategory,
    errorDimension,
    selectedErrorProvider,
    selectedErrorSessionId,
    errorWarnThreshold,
    errorCriticalThreshold,
    connect,
    disconnect,
    sendMessage,
    listSessions,
    listTasks,
    listDimsums,
    listMemories,
    getSettings,
    setErrorThresholds,
  ]);

  return <GatewayContext.Provider value={api}>{children}</GatewayContext.Provider>;
}

export function useGateway(): GatewayState {
  const ctx = useContext(GatewayContext);
  if (!ctx) throw new Error('useGateway must be used within GatewayProvider');
  return ctx;
}
