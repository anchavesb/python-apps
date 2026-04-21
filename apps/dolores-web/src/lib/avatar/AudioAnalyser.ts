export class AudioAnalyser {
  private analyser: AnalyserNode | null = null;
  private dataArray: Uint8Array | null = null;

  connect(audioContext: AudioContext, sourceNode: AudioNode): AnalyserNode {
    this.analyser = audioContext.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.smoothingTimeConstant = 0.8;
    this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    sourceNode.connect(this.analyser);
    this.analyser.connect(audioContext.destination);
    return this.analyser;
  }

  /** Returns normalized volume 0-1. */
  getVolume(): number {
    if (!this.analyser || !this.dataArray) return 0;
    this.analyser.getByteFrequencyData(this.dataArray as Uint8Array<any>);
    let sum = 0;
    for (let i = 0; i < this.dataArray.length; i++) {
      sum += this.dataArray[i];
    }
    return Math.min(1, (sum / this.dataArray.length) / 128);
  }

  disconnect(): void {
    if (this.analyser) {
      try { this.analyser.disconnect(); } catch {}
      this.analyser = null;
      this.dataArray = null;
    }
  }
}
