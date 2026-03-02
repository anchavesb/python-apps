<script lang="ts">
  import { app } from '../stores';

  function handleSave() {
    app.saveSettings();
    app.state.settingsOpen = false;
  }

  function handleClose() {
    app.state.settingsOpen = false;
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

    <div class="modal-actions">
      <button onclick={handleClose}>Cancel</button>
      <button class="primary" onclick={handleSave}>Save</button>
    </div>
  </div>
</div>
