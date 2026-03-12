<script lang="ts">
  import { app } from '../stores.svelte';

  function handleSave() {
    app.saveSettings();
    app.state.settingsOpen = false;
  }

  function handleClose() {
    app.state.settingsOpen = false;
  }

  let loginError = $state('');

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
      Voice ID
      <input type="text" bind:value={app.state.voiceId} placeholder="default" />
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
