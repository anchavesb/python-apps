import { AudioAnalyser } from './avatar/AudioAnalyser';
import { getSharedAudioContext } from './AudioRecorder';

export class AudioPlayer {
  private audioContext: AudioContext | null = null;
  private queue: ArrayBuffer[] = [];
  private playing = false;
  private analyser = new AudioAnalyser();
  private _onPlaybackStart: (() => void) | null = null;
  private _onPlaybackEnd: (() => void) | null = null;

  onPlaybackStart(cb: () => void): void { this._onPlaybackStart = cb; }
  onPlaybackEnd(cb: () => void): void { this._onPlaybackEnd = cb; }

  getVolume(): number {
    return this.analyser.getVolume();
  }

  enqueue(data: ArrayBuffer): void {
    this.queue.push(data);
    if (!this.playing) {
      this.playNext();
    }
  }

  private async playNext(): Promise<void> {
    if (this.queue.length === 0) {
      this.playing = false;
      this._onPlaybackEnd?.();
      return;
    }

    if (!this.playing) {
      this.playing = true;
      this._onPlaybackStart?.();
    }

    if (!this.audioContext) {
      this.audioContext = await getSharedAudioContext();
    }

    const data = this.queue.shift()!;

    try {
      const audioBuffer = await this.audioContext.decodeAudioData(data.slice(0));
      const source = this.audioContext.createBufferSource();
      source.buffer = audioBuffer;

      // Route through analyser for volume detection
      this.analyser.connect(this.audioContext, source);

      source.onended = () => {
        this.analyser.disconnect();
        this.playNext();
      };
      source.start();
    } catch {
      // Skip undecodable audio, continue with next
      this.playNext();
    }
  }

  stop(): void {
    this.queue = [];
    this.playing = false;
    this.analyser.disconnect();
    this._onPlaybackEnd?.();
  }
}
