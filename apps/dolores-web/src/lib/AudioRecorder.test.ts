import { describe, it, expect } from 'vitest';
import { VADAudioRecorder } from './AudioRecorder';

describe('VADAudioRecorder.encodeWav', () => {
  it('produces a WAV blob with correct MIME type', () => {
    const silence = new Float32Array(1600);  // 100ms @ 16kHz
    const blob = VADAudioRecorder.encodeWav(silence);
    expect(blob.type).toBe('audio/wav');
    expect(blob.size).toBeGreaterThan(44);   // at minimum the WAV header
  });

  it('handles empty audio gracefully', () => {
    const empty = new Float32Array(0);
    const blob = VADAudioRecorder.encodeWav(empty);
    expect(blob.size).toBeGreaterThanOrEqual(44);  // header only
  });
});
