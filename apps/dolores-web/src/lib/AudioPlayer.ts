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

    if (this.audioContext.state === 'suspended') {
      console.log('[AudioPlayer] Resuming suspended context...');
      await this.audioContext.resume();
    }

    const data = this.queue.shift()!;
    console.log(`[AudioPlayer] Playing chunk, size=${data.byteLength}, queue=${this.queue.length}`);

    try {
      const audioBuffer = await this.audioContext.decodeAudioData(data.slice(0));
      console.log(`[AudioPlayer] Decoded: duration=${audioBuffer.duration.toFixed(2)}s`);
      const source = this.audioContext.createBufferSource();
      source.buffer = audioBuffer;

      // Route through analyser for volume detection
      this.analyser.connect(this.audioContext, source);

      source.onended = () => {
        this.analyser.disconnect();
        this.playNext();
      };
      source.start();
    } catch (e) {
      console.error('[AudioPlayer] Playback failed:', e);
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

  async testAudio(): Promise<void> {
    const ctx = await getSharedAudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 440;
    gain.gain.value = 0.1;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.5);
    console.log('[AudioPlayer] Playing test beep...');
  }
}
