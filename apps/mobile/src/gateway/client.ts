export type GatewayClientOptions = {
  url: string;
  onEvent: (evt: unknown) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: unknown) => void;
};

export class GatewayClient {
  private ws: WebSocket | null = null;
  private opts: GatewayClientOptions;

  constructor(opts: GatewayClientOptions) {
    this.opts = opts;
  }

  connect(params: { token: string; lastEventId?: number | null }) {
    this.disconnect();

    const ws = new WebSocket(this.opts.url);
    this.ws = ws;

    ws.onopen = () => {
      this.opts.onOpen?.();
      const hello = {
        type: 'hello',
        token: params.token,
        lastEventId: params.lastEventId ?? null,
      };
      ws.send(JSON.stringify(hello));
    };

    ws.onmessage = (msg) => {
      try {
        const data = typeof msg.data === 'string' ? JSON.parse(msg.data) : msg.data;
        this.opts.onEvent(data);
      } catch (e) {
        this.opts.onError?.(e);
      }
    };

    ws.onerror = (e) => {
      this.opts.onError?.(e);
    };

    ws.onclose = () => {
      this.opts.onClose?.();
      this.ws = null;
    };
  }

  disconnect() {
    try {
      this.ws?.close();
    } finally {
      this.ws = null;
    }
  }

  send(frame: unknown) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(frame));
  }
}
