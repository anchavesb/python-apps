<script lang="ts">
  import ChatView from './lib/components/ChatView.svelte';
  import Settings from './lib/components/Settings.svelte';
  import { app } from './lib/stores';
</script>

<main>
  <header>
    <h1>Dolores</h1>
    <div class="header-actions">
      {#if app.state.connected}
        <span class="status connected">Connected</span>
        <button onclick={() => app.disconnect()}>Disconnect</button>
      {:else}
        <span class="status disconnected">Disconnected</span>
        <button onclick={() => app.connect()}>Connect</button>
      {/if}
      <button onclick={() => app.state.settingsOpen = true}>Settings</button>
    </div>
  </header>

  <ChatView />

  {#if app.state.settingsOpen}
    <Settings />
  {/if}
</main>
