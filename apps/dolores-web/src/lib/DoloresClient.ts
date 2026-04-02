export type MessageEvent =
  | { type: 'session.created'; session_id: string; conversation_id: string }
  | { type: 'transcription.partial'; text: string }
  | { type: 'transcription.final'; text: string; speaker_name?: string; speaker_confidence?: number }
  | { type: 'response.emotion'; emotion: string }
  | { type: 'response.text'; content: string }
  | { type: 'response.end'; full_text: string }
  | { type: 'response.image'; image_data: string; prompt: string }
  | { type: 'error'; code: string; message: string };

export interface SpeakerProfile {
  id: string;
  name: string;
  email?: string;
  samples_count?: number;
}

export interface SessionConfig {
  serverUrl: string;
  apiKey: string;
  voiceId: string;
  provider: string;
  mode: 'voice' | 'text' | 'both';
  conversationId?: string;
  userToken?: string;  // OIDC access token forwarded to downstream services
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
          user_token: config.userToken,
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

  sendImage(imageData: string, text: string): void {
    if (!this.ws) throw new Error('Not connected');
    this.ws.send(JSON.stringify({ type: 'image.send', image_data: imageData, text }));
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

  updateToken(userToken: string): void {
    if (!this.ws) return;
    this.ws.send(JSON.stringify({ type: 'session.update_token', user_token: userToken }));
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

  static async listVoices(serverUrl: string, apiKey: string): Promise<{ id: string; name: string }[]> {
    const resp = await fetch(`${serverUrl}/v1/voices`, {
      headers: apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {},
    });
    if (!resp.ok) throw new Error(`Failed to fetch voices: ${resp.status}`);
    return resp.json();
  }

  static async listSpeakers(serverUrl: string, apiKey: string): Promise<SpeakerProfile[]> {
    const resp = await fetch(`${serverUrl}/v1/speakers`, {
      headers: apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {},
    });
    if (!resp.ok) throw new Error(`Failed to fetch speakers: ${resp.status}`);
    return resp.json();
  }

  static async enrollSpeaker(
    serverUrl: string,
    apiKey: string,
    name: string,
    audioBlobs: Blob[],
  ): Promise<SpeakerProfile> {
    const formData = new FormData();
    audioBlobs.forEach((blob, i) => {
      formData.append('files', blob, `sample_${i}.webm`);
    });
    const url = `${serverUrl}/v1/speakers?name=${encodeURIComponent(name)}`;
    const resp = await fetch(url, {
      method: 'POST',
      headers: apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {},
      body: formData,
    });
    if (!resp.ok) {
      const detail = await resp.text();
      throw new Error(`Failed to enroll speaker: ${detail}`);
    }
    return resp.json();
  }

  static async deleteSpeaker(serverUrl: string, apiKey: string, id: string): Promise<void> {
    const resp = await fetch(`${serverUrl}/v1/speakers/${id}`, {
      method: 'DELETE',
      headers: apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {},
    });
    if (!resp.ok) throw new Error(`Failed to delete speaker: ${resp.status}`);
  }

  static async getSettings(serverUrl: string, apiKey: string): Promise<{ default_provider: string, default_voice_id: string }> {
    const resp = await fetch(`${serverUrl}/v1/settings`, {
      headers: apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {},
    });
    if (!resp.ok) throw new Error(`Failed to fetch settings: ${resp.status}`);
    return resp.json();
  }
}
