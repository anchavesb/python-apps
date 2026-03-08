<script lang="ts">
  import { app } from '../stores.svelte';

  function handlePointerDown(e: PointerEvent) {
    e.preventDefault();
    if (!app.state.connected) return;
    app.startRecording();
  }

  function handlePointerUp(e: PointerEvent) {
    e.preventDefault();
    if (app.state.recording) {
      app.stopRecording();
    }
  }

  function handleContextMenu(e: Event) {
    e.preventDefault();
  }
</script>

<button
  class="voice-btn"
  class:recording={app.state.recording}
  onpointerdown={handlePointerDown}
  onpointerup={handlePointerUp}
  onpointerleave={handlePointerUp}
  onpointercancel={handlePointerUp}
  oncontextmenu={handleContextMenu}
  disabled={!app.state.connected}
  title="Hold to speak"
>
  {#if app.state.recording}
    Recording...
  {:else}
    Hold to Speak
  {/if}
</button>
