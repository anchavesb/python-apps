<script lang="ts">
  import { app } from '../stores.svelte';
  import { DoloresClient } from '../DoloresClient';

  function handleSave() {
    app.saveSettings();
    app.state.settingsOpen = false;
  }

  function handleClose() {
    app.state.settingsOpen = false;
  }

  let loginError = $state('');
  let voices = $state<{ id: string; name: string }[]>([]);
  let loadingVoices = $state(false);
  let voiceError = $state('');

  async function loadVoices() {
    loadingVoices = true;
    voiceError = '';
    try {
      voices = await DoloresClient.listVoices(app.state.serverUrl, app.state.apiKey);
    } catch (e: any) {
      voiceError = e.message || 'Failed to load voices';
    } finally {
      loadingVoices = false;
    }
  }

  async function handleLogin() {
    loginError = '';
    app.saveSettings();
    try {
      await app.oidcLogin();
    } catch (e: any) {
      loginError = e.message || String(e);
      console.error('OIDC login failed:', e);
    }
  }

  async function handleLogout() {
    await app.oidcLogout();
  }
</script>

<div class="modal-overlay" onclick={handleClose}>
  <div class="modal" onclick={(e) => e.stopPropagation()}>
    <h2>Settings</h2>

    <label>
      Server URL
      <input type="text" bind:value={app.state.serverUrl} placeholder="http://localhost:8000" />
    </label>

    <label>
      API Key
      <input type="password" bind:value={app.state.apiKey} placeholder="Enter API key" />
    </label>

    <label>
      Voice
      <div class="voice-row">
        {#if voices.length > 0}
          <select bind:value={app.state.voiceId}>
            <option value="default">Default</option>
            {#each voices as voice}
              <option value={voice.id}>{voice.name}</option>
            {/each}
          </select>
        {:else}
          <input type="text" bind:value={app.state.voiceId} placeholder="default" />
        {/if}
        <button class="voice-load-btn" onclick={loadVoices} disabled={loadingVoices}>
          {loadingVoices ? '...' : 'Load'}
        </button>
      </div>
      {#if voiceError}
        <p class="error" style="color: #e74c3c; font-size: 0.8em; margin-top: 4px;">{voiceError}</p>
      {/if}
    </label>

    <label>
      LLM Provider
      <select bind:value={app.state.provider}>
        <option value="ollama">Ollama (Local)</option>
        <option value="anthropic">Anthropic (Claude)</option>
        <option value="openai">OpenAI</option>
      </select>
    </label>

    <fieldset>
      <legend>Authentication (OIDC)</legend>
      <label>
        Issuer URL
        <input type="text" bind:value={app.state.oidcIssuer} placeholder="https://auth.example.com/application/o/dolores/" />
      </label>
      <label>
        Client ID
        <input type="text" bind:value={app.state.oidcClientId} placeholder="OIDC client ID" />
      </label>
      {#if app.state.oidcUser}
        <div class="auth-status">
          Logged in as <strong>{app.state.oidcUser}</strong>
          <button onclick={handleLogout}>Logout</button>
        </div>
      {:else if app.state.oidcIssuer && app.state.oidcClientId}
        <button class="primary" onclick={handleLogin}>Login with OIDC</button>
        {#if loginError}
          <p class="error" style="color: #e74c3c; font-size: 0.85em; margin-top: 0.5em;">{loginError}</p>
        {/if}
      {:else}
        <p class="hint">Configure issuer and client ID to enable login.</p>
      {/if}
    </fieldset>

    <div class="modal-actions">
      <button onclick={handleClose}>Cancel</button>
      <button class="primary" onclick={handleSave}>Save</button>
    </div>
  </div>
</div>

<style>
  .voice-row {
    display: flex;
    gap: 6px;
  }
  .voice-row select,
  .voice-row input {
    flex: 1;
    min-width: 0;
  }
  .voice-load-btn {
    padding: 6px 12px;
    font-size: 0.8rem;
    flex-shrink: 0;
  }
</style>
