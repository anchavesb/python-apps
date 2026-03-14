<script lang="ts">
  import ChatMessage from './ChatMessage.svelte';
  import VoiceButton from './VoiceButton.svelte';
  import { app } from '../stores.svelte';

  let inputText = $state('');
  let messagesEl: HTMLDivElement;

  function handleSend() {
    const text = inputText.trim();
    if (!text || !app.state.connected) return;
    app.sendText(text);
    inputText = '';
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  $effect(() => {
    // Auto-scroll when new messages arrive
    if (app.state.messages.length || app.state.streamingText) {
      messagesEl?.scrollTo({ top: messagesEl.scrollHeight, behavior: 'smooth' });
    }
  });
</script>

<div class="chat-container">
  <div class="messages" bind:this={messagesEl}>
    {#each app.state.messages as msg}
      <ChatMessage role={msg.role} content={msg.content} speakerName={msg.speakerName} />
    {/each}

    {#if app.state.streamingText}
      <ChatMessage role="assistant" content={app.state.streamingText} streaming={true} />
    {/if}

    {#if app.state.thinking && !app.state.streamingText}
      <div class="thinking">Thinking...</div>
    {/if}
  </div>

  <div class="input-area">
    <button class="new-chat-btn" onclick={() => app.newConversation()} title="New conversation">
      +
    </button>
    <textarea
      bind:value={inputText}
      onkeydown={handleKeydown}
      placeholder={app.state.connected ? 'Type a message...' : 'Connect to start chatting'}
      disabled={!app.state.connected}
      rows="1"
    ></textarea>
    <button class="send-btn" onclick={handleSend} disabled={!app.state.connected || !inputText.trim()}>
      Send
    </button>
    <VoiceButton />
  </div>
</div>
