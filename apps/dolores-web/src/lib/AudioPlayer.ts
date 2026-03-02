export class AudioPlayer {
  private audioContext: AudioContext | null = null;
  private queue: ArrayBuffer[] = [];
  private playing = false;

  enqueue(data: ArrayBuffer): void {
    this.queue.push(data);
    if (!this.playing) {
      this.playNext();
    }
  }

  private async playNext(): Promise<void> {
    if (this.queue.length === 0) {
      this.playing = false;
      return;
    }

    this.playing = true;

    if (!this.audioContext) {
      this.audioContext = new AudioContext();
    }

    const data = this.queue.shift()!;

    try {
      const audioBuffer = await this.audioContext.decodeAudioData(data.slice(0));
      const source = this.audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.audioContext.destination);
      source.onended = () => this.playNext();
      source.start();
    } catch {
      // Skip undecodable audio, continue with next
      this.playNext();
    }
  }

  stop(): void {
    this.queue = [];
    this.playing = false;
  }
}
