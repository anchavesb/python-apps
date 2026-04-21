<script lang="ts">
  import { app } from '../stores.svelte';
  import { DoloresClient, type SpeakerProfile } from '../DoloresClient';

  function handleSave() {
    app.saveSettings();
    app.state.settingsOpen = false;
  }

  function handleClose() {
    app.state.settingsOpen = false;
  }

  $effect(() => {
    // Automatically set default model when provider changes
    const p = providers.find(pr => pr.name === app.state.provider);
    if (p && (!app.state.model || !p.models.includes(app.state.model))) {
      app.state.model = p.default_model;
    }
  });

  let loginError = $state('');
  let voices = $state<{ id: string; name: string }[]>([]);
  let loadingVoices = $state(false);
  let voiceError = $state('');

  // Provider/Model state
  let providers = $state<{ name: string; models: string[]; default_model: string }[]>([]);
  let loadingProviders = $state(false);
  let providerError = $state('');

  // Speaker state
  let speakers = $state<SpeakerProfile[]>([]);
  let loadingSpeakers = $state(false);
  let speakerError = $state('');
  let enrollName = $state('');
  let enrolling = $state(false);
  let enrollRecording = $state(false);
  let enrollSamples = $state<Blob[]>([]);
  let enrollMediaRecorder: MediaRecorder | null = null;

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

  async function loadProviders() {
    loadingProviders = true;
    providerError = '';
    try {
      providers = await DoloresClient.listProviders(app.state.serverUrl, app.state.apiKey);
    } catch (e: any) {
      providerError = e.message || 'Failed to load providers';
    } finally {
      loadingProviders = false;
    }
  }

  $effect(() => {
    if (app.state.settingsOpen && providers.length === 0) {
      loadProviders();
    }
  });

  async function loadSpeakers() {
    loadingSpeakers = true;
    speakerError = '';
    try {
      speakers = await DoloresClient.listSpeakers(app.state.serverUrl, app.state.apiKey);
    } catch (e: any) {
      speakerError = e.message || 'Failed to load speakers';
    } finally {
      loadingSpeakers = false;
    }
  }

  async function startEnrollRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      enrollMediaRecorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];

      enrollMediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      enrollMediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: enrollMediaRecorder?.mimeType || 'audio/webm' });
        enrollSamples = [...enrollSamples, blob];
        stream.getTracks().forEach(t => t.stop());
        enrollRecording = false;
      };

      enrollMediaRecorder.start();
      enrollRecording = true;
    } catch (e: any) {
      speakerError = 'Microphone access denied';
    }
  }

  function stopEnrollRecording() {
    if (enrollMediaRecorder && enrollMediaRecorder.state === 'recording') {
      enrollMediaRecorder.stop();
    }
  }

  async function handleEnroll() {
    if (!enrollName.trim() || enrollSamples.length === 0) return;
    enrolling = true;
    speakerError = '';
    try {
      await DoloresClient.enrollSpeaker(
        app.state.serverUrl,
        app.state.apiKey,
        enrollName.trim(),
        enrollSamples,
      );
      enrollName = '';
      enrollSamples = [];
      await loadSpeakers();
    } catch (e: any) {
      speakerError = e.message || 'Enrollment failed';
    } finally {
      enrolling = false;
    }
  }

  async function handleDeleteSpeaker(id: string) {
    try {
      await DoloresClient.deleteSpeaker(app.state.serverUrl, app.state.apiKey, id);
      speakers = speakers.filter(s => s.id !== id);
    } catch (e: any) {
      speakerError = e.message || 'Delete failed';
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
      <div class="voice-row">
        {#if providers.length > 0}
          <select bind:value={app.state.provider}>
            {#each providers as p}
              <option value={p.name}>{p.name.charAt(0).toUpperCase() + p.name.slice(1)}</option>
            {/each}
          </select>
        {:else}
          <select bind:value={app.state.provider}>
            <option value="ollama">Ollama (Local)</option>
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai">OpenAI</option>
          </select>
        {/if}
        <button class="voice-load-btn" onclick={loadProviders} disabled={loadingProviders}>
          {loadingProviders ? '...' : 'Load'}
        </button>
      </div>
    </label>

    <label>
      LLM Model
      <div class="voice-row">
        {#if providers.length > 0}
          {@const currentProvider = providers.find(p => p.name === app.state.provider)}
          {#if currentProvider}
            <select bind:value={app.state.model}>
              {#each currentProvider.models as m}
                <option value={m}>{m}</option>
              {/each}
            </select>
          {:else}
            <input type="text" bind:value={app.state.model} placeholder="Model name" />
          {/if}
        {:else}
          <input type="text" bind:value={app.state.model} placeholder="Model name" />
        {/if}
      </div>
    </label>

    <label class="checkbox-label">
      <input type="checkbox" bind:checked={app.state.vadMode} />
      Auto-listen (VAD)
    </label>

    <fieldset>
      <legend>Speaker Profiles</legend>
      <div class="speaker-list-header">
        <button class="voice-load-btn" onclick={loadSpeakers} disabled={loadingSpeakers}>
          {loadingSpeakers ? '...' : 'Load Speakers'}
        </button>
      </div>

      {#if speakers.length > 0}
        <ul class="speaker-list">
          {#each speakers as speaker}
            <li>
              <span class="speaker-name">{speaker.name}</span>
              <span class="speaker-samples">{speaker.samples_count ?? 0} samples</span>
              <button class="speaker-delete-btn" onclick={() => handleDeleteSpeaker(speaker.id)}>x</button>
            </li>
          {/each}
        </ul>
      {:else if !loadingSpeakers}
        <p class="hint">No speakers enrolled yet.</p>
      {/if}

      <div class="enroll-section">
        <input type="text" bind:value={enrollName} placeholder="Speaker name" class="enroll-name" />
        <div class="enroll-controls">
          {#if enrollRecording}
            <button onclick={stopEnrollRecording} class="enroll-btn recording">Stop</button>
          {:else}
            <button onclick={startEnrollRecording} class="enroll-btn">Record Sample</button>
          {/if}
          <span class="sample-count">{enrollSamples.length} sample{enrollSamples.length !== 1 ? 's' : ''}</span>
          <button
            class="primary enroll-btn"
            onclick={handleEnroll}
            disabled={enrolling || !enrollName.trim() || enrollSamples.length === 0}
          >
            {enrolling ? '...' : 'Enroll'}
          </button>
        </div>
      </div>

      {#if speakerError}
        <p class="error" style="color: #e74c3c; font-size: 0.8em; margin-top: 4px;">{speakerError}</p>
      {/if}
    </fieldset>

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
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 0.9rem;
    margin: 8px 0;
  }
  .checkbox-label input {
    width: auto;
    margin: 0;
  }
  .speaker-list {
    list-style: none;
    padding: 0;
    margin: 8px 0;
  }
  .speaker-list li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.1);
  }
  .speaker-name {
    flex: 1;
    font-weight: 500;
  }
  .speaker-samples {
    font-size: 0.8em;
    opacity: 0.6;
  }
  .speaker-delete-btn {
    padding: 2px 8px;
    font-size: 0.75rem;
    border-radius: 4px;
    cursor: pointer;
  }
  .speaker-list-header {
    margin-bottom: 8px;
  }
  .enroll-section {
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .enroll-name {
    width: 100%;
  }
  .enroll-controls {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .enroll-btn {
    padding: 4px 10px;
    font-size: 0.8rem;
  }
  .enroll-btn.recording {
    background: #e74c3c;
    color: white;
  }
  .sample-count {
    font-size: 0.8em;
    opacity: 0.7;
  }
</style>
