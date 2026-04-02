<script lang="ts">
  import type { WebResultsPayload } from '../stores.svelte';

  interface Props {
    payload: WebResultsPayload;
  }

  let { payload }: Props = $props();
</script>

{#if payload.pageContent}
  <div class="web-page-panel">
    <div class="web-panel-header">
      <span class="web-icon">&#127760;</span>
      <a href={payload.url} target="_blank" rel="noopener noreferrer" class="web-url">
        {payload.url}
      </a>
    </div>
    <pre class="web-page-content">{payload.pageContent}</pre>
  </div>
{:else if payload.results && payload.results.length > 0}
  <div class="web-results">
    {#if payload.query}
      <div class="web-results-header">
        <span class="web-icon">&#127760;</span>
        Web results for <em>{payload.query}</em>
      </div>
    {/if}
    <ul class="result-list">
      {#each payload.results as result}
        <li class="result-card">
          <a
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            class="result-title"
          >
            {result.title}
          </a>
          {#if result.snippet}
            <p class="result-snippet">{result.snippet}</p>
          {/if}
          <span class="result-url">{result.url}</span>
        </li>
      {/each}
    </ul>
  </div>
{:else}
  <div class="web-no-results">No web results found.</div>
{/if}

<style>
  .web-icon {
    margin-right: 6px;
  }

  .web-results-header {
    font-size: 0.85em;
    color: var(--text-dim);
    margin-bottom: 10px;
  }

  .result-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .result-card {
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.03);
  }

  .result-title {
    display: block;
    font-size: 0.95em;
    font-weight: 600;
    color: cornflowerblue;
    text-decoration: none;
    margin-bottom: 4px;
    word-break: break-word;
  }

  .result-title:hover {
    text-decoration: underline;
    color: #89b4fa;
  }

  .result-snippet {
    font-size: 0.85em;
    color: var(--text-dim);
    margin: 0 0 6px 0;
    line-height: 1.4;
  }

  .result-url {
    font-size: 0.75em;
    color: var(--text-dim);
    opacity: 0.7;
    word-break: break-all;
  }

  .web-page-panel {
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }

  .web-panel-header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    background: rgba(255, 255, 255, 0.05);
    border-bottom: 1px solid var(--border);
    font-size: 0.8em;
  }

  .web-url {
    color: cornflowerblue;
    text-decoration: none;
    word-break: break-all;
  }

  .web-url:hover {
    text-decoration: underline;
  }

  .web-page-content {
    padding: 12px;
    margin: 0;
    font-size: 0.8em;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
    max-height: 400px;
    overflow-y: auto;
    color: var(--text-dim);
  }

  .web-no-results {
    font-size: 0.85em;
    color: var(--text-dim);
    font-style: italic;
  }
</style>
