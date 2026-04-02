<script lang="ts">
  import WebResultsCard from './WebResultsCard.svelte';
  import type { WebResultsPayload } from '../stores.svelte';

  interface Props {
    role: 'user' | 'assistant';
    content: string;
    streaming?: boolean;
    speakerName?: string;
    imageUrl?: string;
    isGeneratedImage?: boolean;
    webResults?: WebResultsPayload;
  }

  let { role, content, streaming = false, speakerName, imageUrl, isGeneratedImage = false, webResults }: Props = $props();
</script>

<div class="message {role}" class:streaming>
  <div class="message-role">
    {role === 'user' ? 'You' : 'Dolores'}
    {#if speakerName}
      <span class="speaker-badge">{speakerName}</span>
    {/if}
  </div>
  {#if content}
    <div class="message-content">{content}</div>
  {/if}
  {#if imageUrl}
    <img
      src={imageUrl}
      alt={isGeneratedImage ? 'AI-generated artwork' : 'Attached photo'}
      class="message-image"
      class:generated={isGeneratedImage}
      class:user-thumb={!isGeneratedImage}
    />
    {#if isGeneratedImage}
      <a href={imageUrl} download="dolores-generated.png" class="download-link">Download</a>
    {/if}
  {/if}
  {#if webResults}
    <WebResultsCard payload={webResults} />
  {/if}
</div>

<style>
  .speaker-badge {
    display: inline-block;
    font-size: 0.7em;
    padding: 1px 6px;
    margin-left: 6px;
    border-radius: 8px;
    background: rgba(100, 149, 237, 0.2);
    color: cornflowerblue;
    vertical-align: middle;
  }

  .message-image {
    display: block;
    margin-top: 8px;
    border-radius: 6px;
  }

  .user-thumb {
    max-width: 200px;
    max-height: 200px;
    object-fit: cover;
  }

  .generated {
    max-width: 100%;
  }

  .download-link {
    display: inline-block;
    margin-top: 6px;
    font-size: 0.8em;
    color: cornflowerblue;
    text-decoration: underline;
  }

  .download-link:hover {
    color: #89b4fa;
  }
</style>
