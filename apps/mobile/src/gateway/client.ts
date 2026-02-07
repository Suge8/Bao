export type GatewayClientOptions = {
  url: string;
  onEvent: (evt: unknown) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: unknown) => void;
};

type ConnectParams = {
  token: string;
  lastEventId?: number | null;
};

export class GatewayClient {
  private ws: WebSocket | null = null;
  private opts: GatewayClientOptions;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private manuallyClosed = true;
  private lastConnectParams: ConnectParams | null = null;

  constructor(opts: GatewayClientOptions) {
    this.opts = opts;
  }

  connect(params: ConnectParams) {
    this.manuallyClosed = false;
    this.lastConnectParams = params;
    this.clearReconnectTimer();
    this.disconnectSocket();
    this.openSocket(params);
  }

  private openSocket(params: ConnectParams) {
    const ws = new WebSocket(this.opts.url);
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.opts.onOpen?.();
      ws.send(JSON.stringify(this.createHelloFrame(params)));
    };

    ws.onmessage = (msg) => {
      try {
        this.opts.onEvent(this.parseMessageData(msg.data));
      } catch (error) {
        this.reportError(error);
      }
    };

    ws.onerror = (error) => this.reportError(error);

    ws.onclose = () => {
      this.opts.onClose?.();
      this.ws = null;
      if (!this.manuallyClosed) {
        this.scheduleReconnect();
      }
    };
  }

  disconnect() {
    this.manuallyClosed = true;
    this.clearReconnectTimer();
    this.disconnectSocket();
  }

  private disconnectSocket() {
    try {
      this.ws?.close();
    } finally {
      this.ws = null;
    }
  }

  private createHelloFrame(params: ConnectParams) {
    return {
      type: 'hello',
      token: params.token,
      lastEventId: params.lastEventId ?? null,
    };
  }

  private parseMessageData(data: unknown) {
    return typeof data === 'string' ? JSON.parse(data) : data;
  }

  private reportError(error: unknown) {
    this.opts.onError?.(error);
  }

  private clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private scheduleReconnect() {
    if (!this.lastConnectParams || this.reconnectTimer) return;
    const delay = Math.min(1000 * 2 ** this.reconnectAttempt, 10_000);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.manuallyClosed || !this.lastConnectParams) return;
      this.openSocket(this.lastConnectParams);
    }, delay);
  }

  send(frame: unknown) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(frame));
  }
}
