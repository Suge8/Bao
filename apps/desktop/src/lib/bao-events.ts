import { listen } from "@tauri-apps/api/event";

export type BaoEventV1 = {
  eventId: number;
  ts: number;
  type: string;
  sessionId?: string | null;
  messageId?: string | null;
  deviceId?: string | null;
  payload: unknown;
};

export type BaoEventListener = (evt: BaoEventV1) => void;

export async function subscribeBaoEvents(listener: BaoEventListener) {
  // Payload is BaoEventV1 from Rust.
  const unlisten = await listen<BaoEventV1>("bao:event", (event) => {
    listener(event.payload);
  });
  return unlisten;
}
