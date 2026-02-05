export type BaoEvent = {
  eventId: number;
  type: string;
  ts: number;
  payload: unknown;
};

export type UnlistenFn = () => void;
