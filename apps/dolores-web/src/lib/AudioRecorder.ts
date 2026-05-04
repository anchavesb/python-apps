import { MicVAD, utils } from '@ricky0123/vad-web';

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
    oscillator.start(0);
    oscillator.stop(0.001);
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
    const assetPath = window.location.origin + '/vad/';
    
    console.log(`[VAD] Initializing with asset path: ${assetPath}`);
    
    this.vad = await MicVAD.new({
      model: 'v5',
      positiveSpeechThreshold: 0.85,
      negativeSpeechThreshold: 0.50,
      minSpeechMs: 150,
      preSpeechPadMs: 300,
      redemptionMs: 240,
      baseAssetPath: assetPath,
      onnxWASMBasePath: assetPath,
      workletURL: assetPath + 'vad.worklet.bundle.min.js',
      audioContext,
      getStream: getSharedStream,
      ortConfig: (ort) => {
        console.log('[VAD] Configuring ORT (disabling threads for Safari)...');
        ort.env.wasm.numThreads = 1;
        ort.env.wasm.proxy = false;
        ort.env.wasm.wasmPaths = {
          'ort-wasm-simd-threaded.wasm': assetPath + 'ort-wasm-simd-threaded.wasm',
          'ort-wasm-simd-threaded.mjs': assetPath + 'ort-wasm-simd-threaded.mjs',
          'ort-wasm-simd.wasm': assetPath + 'ort-wasm-simd.wasm',
          'ort-wasm-simd.mjs': assetPath + 'ort-wasm-simd.mjs',
          'ort-wasm.wasm': assetPath + 'ort-wasm.wasm',
          'ort-wasm.mjs': assetPath + 'ort-wasm.mjs',
        };
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
  }

  get initialized(): boolean {
    return this.vad !== null;
  }

  /** Encode Float32Array (16kHz mono PCM) → WAV Blob */
  static encodeWav(float32: Float32Array, sampleRate = 16000): Blob {
    return new Blob([utils.encodeWAV(float32, sampleRate)], { type: 'audio/wav' });
  }
}
