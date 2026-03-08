export type MessageEvent =
  | { type: 'session.created'; session_id: string; conversation_id: string }
  | { type: 'transcription.partial'; text: string }
  | { type: 'transcription.final'; text: string }
  | { type: 'response.emotion'; emotion: string }
  | { type: 'response.text'; content: string }
  | { type: 'response.end'; full_text: string }
  | { type: 'error'; code: string; message: string };

export interface SessionConfig {
  serverUrl: string;
  apiKey: string;
  voiceId: string;
  provider: string;
  mode: 'voice' | 'text' | 'both';
  conversationId?: string;
}

export class DoloresClient {
  private ws: WebSocket | null = null;
  private messageHandler: ((event: MessageEvent | ArrayBuffer) => void) | null = null;
  sessionId = '';
  conversationId = '';

  onMessage(handler: (event: MessageEvent | ArrayBuffer) => void): void {
    this.messageHandler = handler;
  }

  async connect(config: SessionConfig): Promise<void> {
    return new Promise((resolve, reject) => {
      const wsUrl = config.serverUrl.replace(/^http/, 'ws');
      const url = `${wsUrl}/v1/conversation?token=${encodeURIComponent(config.apiKey)}`;

      this.ws = new WebSocket(url);
      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        this.ws!.send(JSON.stringify({
          type: 'session.start',
          voice_id: config.voiceId,
          provider: config.provider,
          mode: config.mode,
          token: config.apiKey,
          conversation_id: config.conversationId,
        }));
      };

      this.ws.onmessage = (evt) => {
        if (evt.data instanceof ArrayBuffer) {
          this.messageHandler?.(evt.data);
          return;
        }

        const msg = JSON.parse(evt.data) as MessageEvent;

        if (msg.type === 'session.created') {
          this.sessionId = msg.session_id;
          this.conversationId = msg.conversation_id;
          resolve();
        }

        this.messageHandler?.(msg);
      };

      this.ws.onerror = () => reject(new Error('WebSocket connection failed'));
      this.ws.onclose = () => { this.ws = null; };
    });
  }

  sendText(text: string): void {
    if (!this.ws) throw new Error('Not connected');
    this.ws.send(JSON.stringify({ type: 'text.send', text }));
  }

  sendAudioStart(): void {
    if (!this.ws) throw new Error('Not connected');
    this.ws.send(JSON.stringify({ type: 'audio.start' }));
  }

  sendAudioChunk(data: ArrayBuffer): void {
    if (!this.ws) throw new Error('Not connected');
    this.ws.send(data);
  }

  sendAudioEnd(contentType?: string): void {
    if (!this.ws) throw new Error('Not connected');
    this.ws.send(JSON.stringify({ type: 'audio.end', content_type: contentType }));
  }

  disconnect(): void {
    if (this.ws) {
      try {
        this.ws.send(JSON.stringify({ type: 'session.end' }));
      } catch {}
      this.ws.close();
      this.ws = null;
    }
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
