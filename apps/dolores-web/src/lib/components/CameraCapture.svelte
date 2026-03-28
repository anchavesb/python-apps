<script lang="ts">
  interface Props {
    onCapture: (imageData: string) => void;
    onCancel: () => void;
  }

  let { onCapture, onCancel }: Props = $props();

  let videoEl: HTMLVideoElement;
  let canvasEl: HTMLCanvasElement;
  let stream: MediaStream | null = null;
  let capturedImage: string | null = $state(null);
  let errorMessage: string | null = $state(null);

  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true });
      videoEl.srcObject = stream;
    } catch {
      errorMessage = 'Camera access denied or unavailable.';
    }
  }

  function stopCamera() {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
    }
  }

  function capture() {
    const ctx = canvasEl.getContext('2d');
    if (!ctx) return;
    canvasEl.width = videoEl.videoWidth;
    canvasEl.height = videoEl.videoHeight;
    ctx.drawImage(videoEl, 0, 0);
    capturedImage = canvasEl.toDataURL('image/jpeg', 0.85);
    stopCamera();
  }

  function retake() {
    capturedImage = null;
    startCamera();
  }

  function submit() {
    if (capturedImage) {
      stopCamera();
      onCapture(capturedImage);
    }
  }

  function cancel() {
    stopCamera();
    onCancel();
  }

  $effect(() => {
    startCamera();
    return () => stopCamera();
  });
</script>

<div class="modal-overlay" role="dialog" aria-modal="true" aria-label="Camera capture">
  <div class="modal">
    <h2 class="modal-title">Camera Capture</h2>

    {#if errorMessage}
      <p class="error">{errorMessage}</p>
    {:else if capturedImage}
      <img src={capturedImage} alt="Captured preview" class="preview-img" />
    {:else}
      <video bind:this={videoEl} autoplay playsinline class="video-feed"></video>
    {/if}

    <canvas bind:this={canvasEl} class="hidden-canvas"></canvas>

    <div class="modal-actions">
      {#if capturedImage}
        <button onclick={retake}>Retake</button>
        <button class="primary" onclick={submit}>Use Photo</button>
      {:else if !errorMessage}
        <button class="primary" onclick={capture}>Capture</button>
      {/if}
      <button onclick={cancel}>Cancel</button>
    </div>
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: #1e1e2e;
    border: 1px solid #3d3d5c;
    border-radius: 12px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-width: 480px;
    width: 100%;
  }

  .modal-title {
    margin: 0;
    font-size: 1.1em;
    color: #cdd6f4;
  }

  .video-feed,
  .preview-img {
    width: 100%;
    border-radius: 8px;
    max-height: 320px;
    object-fit: cover;
  }

  .hidden-canvas {
    display: none;
  }

  .error {
    color: #f38ba8;
    margin: 0;
  }

  .modal-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  button {
    padding: 8px 16px;
    border-radius: 6px;
    border: 1px solid #585b70;
    background: transparent;
    color: #cdd6f4;
    cursor: pointer;
    font-size: 0.9em;
  }

  button:hover {
    background: #313244;
  }

  button.primary {
    background: #89b4fa;
    border-color: #89b4fa;
    color: #1e1e2e;
  }

  button.primary:hover {
    background: #b4d0ff;
  }
</style>
