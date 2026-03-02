<script lang="ts">
  interface Props {
    role: 'user' | 'assistant';
    content: string;
    streaming?: boolean;
  }

  let { role, content, streaming = false }: Props = $props();
</script>

<div class="message {role}" class:streaming>
  <div class="message-role">{role === 'user' ? 'You' : 'Dolores'}</div>
  <div class="message-content">{content}</div>
</div>
