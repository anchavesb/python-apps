export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private _mimeType = '';

  /** Acquire mic permission and keep stream alive to avoid re-prompting. */
  async init(): Promise<void> {
    if (this.stream) return;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this._mimeType = this.getSupportedMimeType();
  }

  async start(): Promise<void> {
    await this.init();
    this.chunks = [];

    const options: MediaRecorderOptions = {};
    if (this._mimeType) {
      options.mimeType = this._mimeType;
    }

    this.mediaRecorder = new MediaRecorder(this.stream!, options);

    this.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        this.chunks.push(e.data);
      }
    };

    this.mediaRecorder.start(250);
  }

  stop(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.mediaRecorder) {
        resolve(new Blob());
        return;
      }

      this.mediaRecorder.onstop = () => {
        const type = this.mediaRecorder?.mimeType || this._mimeType || 'audio/webm';
        const blob = new Blob(this.chunks, { type });
        this.mediaRecorder = null;
        this.chunks = [];
        resolve(blob);
      };

      this.mediaRecorder.stop();
    });
  }

  /** Release mic stream entirely (call on disconnect). */
  destroy(): void {
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    this.mediaRecorder = null;
    this.chunks = [];
  }

  get recording(): boolean {
    return this.mediaRecorder?.state === 'recording';
  }

  get mimeType(): string {
    return this._mimeType;
  }

  private getSupportedMimeType(): string {
    const types = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',             // iOS Safari
      'audio/ogg;codecs=opus',
      'audio/aac',             // iOS fallback
    ];
    for (const type of types) {
      if (MediaRecorder.isTypeSupported(type)) return type;
    }
    return '';
  }
}
