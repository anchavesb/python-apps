<script lang="ts">
  import { app } from '../stores.svelte';

  function handlePointerDown() {
    if (!app.state.connected) return;
    app.startRecording();
  }

  function handlePointerUp() {
    if (app.state.recording) {
      app.stopRecording();
    }
  }
</script>

<button
  class="voice-btn"
  class:recording={app.state.recording}
  onpointerdown={handlePointerDown}
  onpointerup={handlePointerUp}
  onpointerleave={handlePointerUp}
  disabled={!app.state.connected}
  title="Hold to speak"
>
  {#if app.state.recording}
    Recording...
  {:else}
    Hold to Speak
  {/if}
</button>
