<script lang="ts">
  import { app } from '../stores.svelte';
  import { AvatarRenderer } from '../avatar/AvatarRenderer';
  import VoiceButton from './VoiceButton.svelte';

  let canvasEl: HTMLCanvasElement;
  const renderer = new AvatarRenderer();

  $effect(() => {
    if (canvasEl) {
      renderer.attach(canvasEl);
      return () => renderer.detach();
    }
  });

  $effect(() => {
    renderer.update(
      app.avatarPhase,
      app.state.emotion,
      app.player.getVolume()
    );
  });

  // Poll volume at 30fps for lip sync (volume changes don't trigger reactivity)
  $effect(() => {
    if (app.state.audioPlaying) {
      const id = setInterval(() => {
        renderer.update(app.avatarPhase, app.state.emotion, app.player.getVolume());
      }, 33);
      return () => clearInterval(id);
    }
  });

  // Last assistant message for display
  const lastResponse = $derived(() => {
    if (app.state.streamingText) return app.state.streamingText;
    const msgs = app.state.messages;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant') return msgs[i].content;
    }
    return '';
  });
</script>

<div class="avatar-container">
  <canvas bind:this={canvasEl} class="avatar-canvas"></canvas>

  <div class="avatar-overlays">
    {#if lastResponse()}
      <div class="avatar-response" class:streaming={!!app.state.streamingText}>
        {lastResponse()}
      </div>
    {/if}

    {#if app.state.transcription}
      <div class="avatar-transcription">
        {app.state.transcription}
      </div>
    {/if}
  </div>

  <div class="avatar-controls">
    <VoiceButton />
  </div>
</div>
