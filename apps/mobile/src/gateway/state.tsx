import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { GatewayClient } from './client';
import { loadGatewayPreferences, saveGatewayPreferences } from './preferences';
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

const MAX_EVENT_HISTORY = 2000;
const ERROR_EVENT_LIST_LIMIT = 120;

type GatewayState = {
  url: string;
  token: string;
  connected: boolean;
  connectionError: string | null;
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
  runTroubleshootActions: () => void;
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

function resolveConnectionError(err: unknown): string {
  if (err instanceof Error && err.message.trim()) return err.message;
  return 'gateway connection failed';
}

export function GatewayProvider({ children }: { children: React.ReactNode }) {
  const [url, setUrl] = useState('ws://127.0.0.1:3901/ws');
  const [token, setToken] = useState('');
  const [connected, setConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
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
  const [prefsReady, setPrefsReady] = useState(false);

  const clientRef = useRef<GatewayClient | null>(null);

  const sendFrame = useCallback((frame: unknown) => {
    clientRef.current?.send(frame);
  }, []);

  const clearClient = useCallback(() => {
    clientRef.current?.disconnect();
    clientRef.current = null;
  }, []);

  const onEvent = useCallback((evt: unknown) => {
    setEvents((prev) => {
      const next = [...prev, evt];
      return next.length > MAX_EVENT_HISTORY ? next.slice(-MAX_EVENT_HISTORY) : next;
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

  const applyPreferences = useCallback(
    (prefs: {
      url: string;
      token: string;
      selectedCategory: MobileEventCategory;
      errorDimension: MobileErrorAggregateDimension;
      selectedErrorProvider: string | null;
      selectedErrorSessionId: string | null;
      errorWarnThreshold: number;
      errorCriticalThreshold: number;
    }) => {
      setUrl(prefs.url);
      setToken(prefs.token);
      setLastToken(prefs.token);
      setSelectedCategory(prefs.selectedCategory);
      setErrorDimension(prefs.errorDimension);
      setSelectedErrorProvider(prefs.selectedErrorProvider);
      setSelectedErrorSessionId(prefs.selectedErrorSessionId);
      setErrorWarnThreshold(prefs.errorWarnThreshold);
      setErrorCriticalThreshold(prefs.errorCriticalThreshold);
    },
    [],
  );

  const connect = useCallback(
    async (params: { url: string; token: string }) => {
      setUrl(params.url);
      setToken(params.token);
      setConnectionError(null);

      const shouldResetHistory = params.url !== url || params.token !== lastToken;
      if (shouldResetHistory) {
        setEvents([]);
        setLastEventId(null);
      }
      setReplayActive(!shouldResetHistory && lastEventId != null);

      clearClient();

      const c = new GatewayClient({
        url: params.url,
        onEvent,
        onOpen: () => {
          setConnected(true);
          setConnectionError(null);
        },
        onClose: () => setConnected(false),
        onError: (err) => setConnectionError(resolveConnectionError(err)),
      });
      clientRef.current = c;
      c.connect({
        token: params.token,
        lastEventId: shouldResetHistory ? null : lastEventId,
      });
      setLastToken(params.token);
    },
    [clearClient, lastEventId, lastToken, onEvent, url],
  );

  const disconnect = useCallback(() => {
    clearClient();
    setConnected(false);
    setReplayActive(false);
  }, [clearClient]);

  const sendMessage = useCallback((params: { sessionId: string; text: string }) => {
    sendFrame({ type: 'sendMessage', sessionId: params.sessionId, text: params.text });
  }, [sendFrame]);

  const listSessions = useCallback(() => sendFrame({ type: 'listSessions' }), [sendFrame]);
  const listTasks = useCallback(() => sendFrame({ type: 'listTasks' }), [sendFrame]);
  const listDimsums = useCallback(() => sendFrame({ type: 'listDimsums' }), [sendFrame]);
  const listMemories = useCallback(() => sendFrame({ type: 'listMemories' }), [sendFrame]);
  const getSettings = useCallback(() => sendFrame({ type: 'getSettings' }), [sendFrame]);
  const runTroubleshootActions = useCallback(() => {
    listSessions();
    listTasks();
    listDimsums();
    listMemories();
    getSettings();
  }, [getSettings, listDimsums, listMemories, listSessions, listTasks]);

  const setErrorThresholds = useCallback((thresholds: { warn: number; critical: number }) => {
    const warn = Math.max(1, Math.floor(thresholds.warn));
    const critical = Math.max(warn, Math.floor(thresholds.critical));
    setErrorWarnThreshold(warn);
    setErrorCriticalThreshold(critical);
  }, []);

  useEffect(() => {
    let active = true;
    void loadGatewayPreferences().then((prefs) => {
      if (!active) return;
      if (prefs) applyPreferences(prefs);
      setPrefsReady(true);
    });
    return () => {
      active = false;
    };
  }, [applyPreferences]);

  useEffect(() => {
    if (!prefsReady) return;
    saveGatewayPreferences({
      url,
      token,
      selectedCategory,
      errorDimension,
      selectedErrorProvider,
      selectedErrorSessionId,
      errorWarnThreshold,
      errorCriticalThreshold,
    });
  }, [
    prefsReady,
    url,
    token,
    selectedCategory,
    errorDimension,
    selectedErrorProvider,
    selectedErrorSessionId,
    errorWarnThreshold,
    errorCriticalThreshold,
  ]);

  const api = useMemo<GatewayState>(() => {
    const eventCounts = countEventsByCategory(events);
    const errorAggregates = aggregateErrorEvents(events, errorDimension);
    const errorAlerts = buildErrorAlerts(errorAggregates, errorWarnThreshold, errorCriticalThreshold);
    const providerFilter = errorDimension === 'provider' ? selectedErrorProvider : null;
    const sessionFilter = errorDimension === 'session' ? selectedErrorSessionId : null;
    const errorEvents = listErrorEvents(events, {
      provider: providerFilter,
      sessionId: sessionFilter,
      limit: ERROR_EVENT_LIST_LIMIT,
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
      connectionError,
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
      runTroubleshootActions,
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
    connectionError,
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
    runTroubleshootActions,
    setErrorThresholds,
  ]);

  return <GatewayContext.Provider value={api}>{children}</GatewayContext.Provider>;
}

export function useGateway(): GatewayState {
  const ctx = useContext(GatewayContext);
  if (!ctx) throw new Error('useGateway must be used within GatewayProvider');
  return ctx;
}
