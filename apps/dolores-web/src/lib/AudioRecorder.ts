import { MicVAD } from '@ricky0123/vad-web';

function encodeWavPCM16(float32: Float32Array, sampleRate = 16000): ArrayBuffer {
  const numSamples = float32.length;
  const bytesPerSample = 2;
  const blockAlign = 1 * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = numSamples * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };

  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);            // fmt chunk size
  view.setUint16(20, 1, true);             // PCM format tag = 0x0001
  view.setUint16(22, 1, true);             // channels = mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);            // bits per sample
  writeStr(36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < numSamples; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return buffer;
}

let sharedAudioContext: AudioContext | null = null;
let sharedStream: MediaStream | null = null;

/** Get or create a shared AudioContext. Must be called from a user interaction on Safari. */
export async function getSharedAudioContext(): Promise<AudioContext> {
  if (!sharedAudioContext) {
    // @ts-ignore - Support legacy webkitAudioContext if needed
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    sharedAudioContext = new AudioContextClass();
  }
  
  if (sharedAudioContext.state === 'suspended') {
    await sharedAudioContext.resume();
  }

  // Safari/iOS "unlock": play a short burst of silence
  if (sharedAudioContext.state === 'running') {
    const oscillator = sharedAudioContext.createOscillator();
    const gain = sharedAudioContext.createGain();
    gain.gain.value = 0; // silence
    oscillator.connect(gain);
    gain.connect(sharedAudioContext.destination);
    const now = sharedAudioContext.currentTime;
    oscillator.start(now);
    oscillator.stop(now + 0.05);
  }
  
  return sharedAudioContext;
}

/** Pre-acquire mic stream to unlock it for Safari. */
export async function getSharedStream(): Promise<MediaStream> {
  if (!sharedStream || !sharedStream.active) {
    sharedStream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        channelCount: 1,
        echoCancellation: true,
        autoGainControl: true,
        noiseSuppression: true,
      } 
    });
  }
  return sharedStream;
}

/** Stop the shared stream and release the microphone. */
export function stopSharedStream(): void {
  if (sharedStream) {
    sharedStream.getTracks().forEach(t => t.stop());
    sharedStream = null;
  }
}

export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private _mimeType = '';

  /** Acquire mic permission and keep stream alive to avoid re-prompting. */
  async init(): Promise<void> {
    if (this.stream) return;
    this.stream = await getSharedStream();
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
    stopSharedStream();
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

export class VADAudioRecorder {
  private vad: MicVAD | null = null;

  async init(callbacks: {
    onSpeechStart: () => void;
    onSpeechEnd: (audio: Float32Array) => void;
  }): Promise<void> {
    const audioContext = await getSharedAudioContext();
    const assetPath = window.location.origin + '/app/vad/';
    
    console.log(`[VAD] Final fix init. Asset path: ${assetPath}`);
    
    // Instead of importing 'ort' (which is not exported from the root),
    // we set the WASM paths via the callback.
    this.vad = await MicVAD.new({
      model: 'v5',
      positiveSpeechThreshold: 0.85,
      negativeSpeechThreshold: 0.50,
      minSpeechMs: 300,          // ~300ms minimum utterance
      preSpeechPadMs: 300,       // 300ms pre-buffer (capture word start)
      redemptionMs: 1000,        // 1s silence before onSpeechEnd fires
      baseAssetPath: assetPath,
      onnxWASMBasePath: assetPath,
      workletURL: assetPath + 'vad.worklet.bundle.min.js',
      audioContext,
      getStream: getSharedStream,
      ortConfig: (ort: any) => {
        console.log('[VAD] Configuring ORT (disabling threads for Safari)...');
        ort.env.wasm.numThreads = 1;
        ort.env.wasm.proxy = false;
        ort.env.wasm.wasmPaths = assetPath;
      },
      ...callbacks,
    } as any);
  }

  start(): void {
    this.vad?.start();
  }

  pause(): void {
    this.vad?.pause();
  }

  /** Force resume of AudioContext (needed for Safari on first interaction) */
  async resume(): Promise<void> {
    await getSharedAudioContext();
    if (this.vad) {
      await this.vad.start();
    }
  }

  destroy(): void {
    this.vad?.destroy();
    this.vad = null;
    stopSharedStream();
  }

  get initialized(): boolean {
    return this.vad !== null;
  }

  /** Encode Float32Array (16kHz mono PCM) → WAV Blob */
  static encodeWav(float32: Float32Array, sampleRate = 16000): Blob {
    return new Blob([encodeWavPCM16(float32, sampleRate)], { type: 'audio/wav' });
  }
}
