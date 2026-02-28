/**
 * WhatsApp client wrapper using Baileys.
 * Based on OpenClaw's working implementation.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  downloadMediaMessage,
} from "@whiskeysockets/baileys";

import { Boom } from "@hapi/boom";
import qrcode from "qrcode-terminal";
import pino from "pino";

const VERSION = "0.1.0";

export interface InboundMessage {
  id: string;
  sender: string;
  pn: string;
  participant: string;
  content: string;
  timestamp: number;
  isGroup: boolean;
  media?: { data: string; mimetype: string; filename?: string };
}

export interface WhatsAppClientOptions {
  authDir: string;
  onMessage: (msg: InboundMessage) => void;
  onQR: (qr: string) => void;
  onStatus: (status: string) => void;
}

export class WhatsAppClient {
  private sock: any = null;
  private options: WhatsAppClientOptions;
  private reconnecting = false;

  constructor(options: WhatsAppClientOptions) {
    this.options = options;
  }

  async connect(): Promise<void> {
    const logger = pino({ level: "silent" });
    const { state, saveCreds } = await useMultiFileAuthState(
      this.options.authDir,
    );
    const { version } = await fetchLatestBaileysVersion();

    console.log(`Using Baileys version: ${version.join(".")}`);

    // Create socket following OpenClaw's pattern
    this.sock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      version,
      logger,
      printQRInTerminal: false,
      browser: ["bao", "cli", VERSION],
      syncFullHistory: false,
      markOnlineOnConnect: false,
    });

    // Handle WebSocket errors
    if (this.sock.ws && typeof this.sock.ws.on === "function") {
      this.sock.ws.on("error", (err: Error) => {
        console.error("WebSocket error:", err.message);
      });
    }

    // Handle connection updates
    this.sock.ev.on("connection.update", async (update: any) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        // Display QR code in terminal
        console.log("\n📱 Scan this QR code with WhatsApp (Linked Devices):\n");
        qrcode.generate(qr, { small: true });
        this.options.onQR(qr);
      }

      if (connection === "close") {
        const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        console.log(
          `Connection closed. Status: ${statusCode}, Will reconnect: ${shouldReconnect}`,
        );
        this.options.onStatus("disconnected");

        if (shouldReconnect && !this.reconnecting) {
          this.reconnecting = true;
          console.log("Reconnecting in 5 seconds...");
          setTimeout(() => {
            this.reconnecting = false;
            this.connect();
          }, 5000);
        }
      } else if (connection === "open") {
        console.log("✅ Connected to WhatsApp");
        this.options.onStatus("connected");
      }
    });

    // Save credentials on update
    this.sock.ev.on("creds.update", saveCreds);

    // Handle incoming messages
    this.sock.ev.on(
      "messages.upsert",
      async ({ messages, type }: { messages: any[]; type: string }) => {
        if (type !== "notify") return;

        for (const msg of messages) {
          // Skip own messages
          if (msg.key.fromMe) continue;
          // Skip status updates
          if (msg.key.remoteJid === "status@broadcast") continue;
          const content = this.extractMessageContent(msg);
          if (!content) continue;
          const isGroup = msg.key.remoteJid?.endsWith("@g.us") || false;
          // Try to download media if present
          const media = await this.downloadMedia(msg);
          this.options.onMessage({
            id: msg.key.id || "",
            sender: msg.key.remoteJid || "",
            pn: msg.key.remoteJidAlt || "",
            participant: msg.key.participant || "",
            content,
            timestamp: msg.messageTimestamp as number,
            isGroup,
            ...(media && { media }),
          });
        }
      },
    );
  }

  private extractMessageContent(msg: any): string | null {
    const message = msg.message;
    if (!message) return null;

    // Text message
    if (message.conversation) {
      return message.conversation;
    }

    // Extended text (reply, link preview)
    if (message.extendedTextMessage?.text) {
      return message.extendedTextMessage.text;
    }

    // Image (with or without caption)
    if (message.imageMessage) {
      return message.imageMessage.caption || "[Image]";
    }

    // Video (with or without caption)
    if (message.videoMessage) {
      return message.videoMessage.caption || "[Video]";
    }

    // Document (with or without caption)
    if (message.documentMessage) {
      const name = message.documentMessage.fileName || "file";
      return message.documentMessage.caption || `[Document: ${name}]`;
    }

    // Voice/Audio message
    if (message.audioMessage) {
      return "[Voice Message]";
    }

    return null;
  }

  private async downloadMedia(
    msg: any,
  ): Promise<{ data: string; mimetype: string; filename?: string } | null> {
    const message = msg.message;
    if (!message) return null;
    const mediaMsg =
      message.imageMessage ||
      message.videoMessage ||
      message.documentMessage ||
      message.audioMessage;
    if (!mediaMsg) return null;
    try {
      const buffer = await downloadMediaMessage(msg, "buffer", {});
      const mimetype = mediaMsg.mimetype || "application/octet-stream";
      const filename = mediaMsg.fileName || undefined;
      return {
        data: (buffer as Buffer).toString("base64"),
        mimetype,
        filename,
      };
    } catch (err) {
      console.error("Failed to download media:", err);
      return null;
    }
  }

  async sendMessage(to: string, text: string): Promise<void> {
    if (!this.sock) {
      throw new Error("Not connected");
    }

    await this.sock.sendMessage(to, { text });
  }

  async disconnect(): Promise<void> {
    if (this.sock) {
      this.sock.end(undefined);
      this.sock = null;
    }
  }
}
