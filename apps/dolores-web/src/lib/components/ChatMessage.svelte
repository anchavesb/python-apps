<script lang="ts">
  interface Props {
    role: 'user' | 'assistant';
    content: string;
    streaming?: boolean;
    speakerName?: string;
  }

  let { role, content, streaming = false, speakerName }: Props = $props();
</script>

<div class="message {role}" class:streaming>
  <div class="message-role">
    {role === 'user' ? 'You' : 'Dolores'}
    {#if speakerName}
      <span class="speaker-badge">{speakerName}</span>
    {/if}
  </div>
  <div class="message-content">{content}</div>
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
</style>
