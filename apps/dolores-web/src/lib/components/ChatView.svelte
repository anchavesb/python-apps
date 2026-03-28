<script lang="ts">
  import ChatMessage from './ChatMessage.svelte';
  import VoiceButton from './VoiceButton.svelte';
  import CameraCapture from './CameraCapture.svelte';
  import { app } from '../stores.svelte';

  let inputText = $state('');
  let messagesEl: HTMLDivElement;
  let pendingImage: string | null = $state(null);
  let showCamera = $state(false);

  function handleSend() {
    const text = inputText.trim();
    if (!app.state.connected) return;
    if (pendingImage) {
      app.sendImageMessage(pendingImage, text);
      pendingImage = null;
      inputText = '';
    } else {
      if (!text) return;
      app.sendText(text);
      inputText = '';
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handlePaste(e: ClipboardEvent) {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const file = item.getAsFile();
        if (!file) continue;
        const dataUrl = await readFileAsDataUrl(file);
        pendingImage = await compressImage(dataUrl);
        return;
      }
    }
  }

  function readFileAsDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function compressImage(dataUrl: string): Promise<string> {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const maxDim = 1024;
        let { width, height } = img;
        if (width > maxDim || height > maxDim) {
          if (width >= height) {
            height = Math.round((height * maxDim) / width);
            width = maxDim;
          } else {
            width = Math.round((width * maxDim) / height);
            height = maxDim;
          }
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        canvas.getContext('2d')!.drawImage(img, 0, 0, width, height);
        resolve(canvas.toDataURL('image/jpeg', 0.85));
      };
      img.src = dataUrl;
    });
  }

  async function handleCameraCapture(imageData: string) {
    showCamera = false;
    pendingImage = await compressImage(imageData);
  }

  $effect(() => {
    if (app.state.messages.length || app.state.streamingText) {
      messagesEl?.scrollTo({ top: messagesEl.scrollHeight, behavior: 'smooth' });
    }
  });
</script>

{#if showCamera}
  <CameraCapture
    onCapture={handleCameraCapture}
    onCancel={() => (showCamera = false)}
  />
{/if}

<div class="chat-container">
  <div class="messages" bind:this={messagesEl}>
    {#each app.state.messages as msg}
      <ChatMessage
        role={msg.role}
        content={msg.content}
        speakerName={msg.speakerName}
        imageUrl={msg.imageUrl}
        isGeneratedImage={msg.isGeneratedImage}
      />
    {/each}

    {#if app.state.streamingText}
      <ChatMessage role="assistant" content={app.state.streamingText} streaming={true} />
    {/if}

    {#if app.state.thinking && !app.state.streamingText}
      <div class="thinking">Thinking...</div>
    {/if}
  </div>

  <div class="input-area input-area--column">
    {#if pendingImage}
      <div class="image-preview-strip">
        <img src={pendingImage} alt="Pending attachment" class="preview-thumb" />
        <button class="dismiss-btn" onclick={() => (pendingImage = null)} title="Remove image">×</button>
      </div>
    {/if}

    <div class="input-controls">
      <button class="new-chat-btn" onclick={() => app.newConversation()} title="New conversation">
        +
      </button>
      <textarea
        bind:value={inputText}
        onkeydown={handleKeydown}
        onpaste={handlePaste}
        placeholder={app.state.connected ? 'Type a message...' : 'Connect to start chatting'}
        disabled={!app.state.connected}
        rows="1"
      ></textarea>
      <button
        class="camera-btn"
        onclick={() => (showCamera = true)}
        disabled={!app.state.connected}
        title="Capture from camera"
        aria-label="Open camera"
      >
        📷
      </button>
      <button
        class="send-btn"
        onclick={handleSend}
        disabled={!app.state.connected || (!inputText.trim() && !pendingImage)}
      >
        Send
      </button>
      <VoiceButton />
    </div>
  </div>
</div>

<style>
  .input-area--column {
    flex-direction: column;
    align-items: stretch;
  }

  .input-controls {
    display: flex;
    gap: 8px;
    align-items: flex-end;
  }

  .image-preview-strip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 6px;
  }

  .preview-thumb {
    max-height: 60px;
    max-width: 100px;
    border-radius: 4px;
    object-fit: cover;
  }

  .dismiss-btn {
    background: none;
    border: none;
    color: var(--text-dim);
    font-size: 1.3em;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
  }

  .dismiss-btn:hover {
    color: var(--danger);
    background: none;
  }

  .camera-btn {
    background: transparent;
    border: 1px solid var(--border);
    font-size: 1.1em;
    padding: 8px 10px;
    flex-shrink: 0;
  }

  .camera-btn:hover:not(:disabled) {
    background: var(--accent-hover);
  }
</style>
