<script lang="ts">
  import ChatView from './lib/components/ChatView.svelte';
  import AvatarView from './lib/components/AvatarView.svelte';
  import Settings from './lib/components/Settings.svelte';
  import { app } from './lib/stores.svelte';

  // Initialize background services (VAD, etc)
  app.init();

  // Support ?view=avatar URL param for kiosk mode
  const params = new URLSearchParams(window.location.search);
  if (params.get('view') === 'avatar') {
    app.setViewMode('avatar');
  }

  // Handle OIDC callback (?code=...)
  if (params.has('code')) {
    app.oidcHandleCallback().catch((e) => {
      console.error('OIDC callback failed:', e);
    });
  }
</script>

<main>
  <header class:avatar-header={app.state.viewMode === 'avatar'}>
    <h1>Dolores</h1>
    <div class="header-actions">
      {#if app.state.oidcUser}
        <span class="user-name">{app.state.oidcUser}</span>
      {/if}
      <button
        class="view-toggle"
        onclick={() => app.setViewMode(app.state.viewMode === 'chat' ? 'avatar' : 'chat')}
      >
        {app.state.viewMode === 'chat' ? 'Avatar' : 'Chat'}
      </button>
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

  {#if app.state.viewMode === 'avatar'}
    <AvatarView />
  {:else}
    <ChatView />
  {/if}

  {#if app.state.settingsOpen}
    <Settings />
  {/if}
</main>
