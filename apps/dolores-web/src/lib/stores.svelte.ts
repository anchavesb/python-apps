import { DoloresClient, type MessageEvent } from './DoloresClient';
import { AudioRecorder } from './AudioRecorder';
import { AudioPlayer } from './AudioPlayer';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface AppState {
  messages: ChatMessage[];
  connected: boolean;
  recording: boolean;
  thinking: boolean;
  streamingText: string;
  transcription: string;
  settingsOpen: boolean;
  serverUrl: string;
  apiKey: string;
  voiceId: string;
  provider: string;
}

function createAppState() {
  const saved = loadSettings();

  let state = $state<AppState>({
    messages: [],
    connected: false,
    recording: false,
    thinking: false,
    streamingText: '',
    transcription: '',
    settingsOpen: false,
    serverUrl: saved.serverUrl || 'http://localhost:8000',
    apiKey: saved.apiKey || '',
    voiceId: saved.voiceId || 'default',
    provider: saved.provider || 'ollama',
  });

  const client = new DoloresClient();
  const recorder = new AudioRecorder();
  const player = new AudioPlayer();

  client.onMessage((event) => {
    if (event instanceof ArrayBuffer) {
      player.enqueue(event);
      return;
    }

    const msg = event as MessageEvent;

    switch (msg.type) {
      case 'transcription.final':
        state.transcription = msg.text;
        state.messages = [...state.messages, { role: 'user', content: msg.text, timestamp: new Date() }];
        break;
      case 'response.text':
        state.streamingText += msg.content;
        state.thinking = false;
        break;
      case 'response.end':
        state.messages = [...state.messages, {
          role: 'assistant',
          content: msg.full_text || state.streamingText,
          timestamp: new Date(),
        }];
        state.streamingText = '';
        state.thinking = false;
        break;
      case 'error':
        state.messages = [...state.messages, {
          role: 'assistant',
          content: `Error: ${msg.message}`,
          timestamp: new Date(),
        }];
        state.thinking = false;
        break;
    }
  });

  async function connect() {
    try {
      await client.connect({
        serverUrl: state.serverUrl,
        apiKey: state.apiKey,
        voiceId: state.voiceId,
        provider: state.provider,
        mode: 'both',
      });
      state.connected = true;
    } catch (e) {
      state.messages = [...state.messages, {
        role: 'assistant',
        content: `Connection failed: ${e instanceof Error ? e.message : 'Unknown error'}`,
        timestamp: new Date(),
      }];
    }
  }

  function disconnect() {
    client.disconnect();
    state.connected = false;
  }

  async function sendText(text: string) {
    if (!client.connected) return;
    state.messages = [...state.messages, { role: 'user', content: text, timestamp: new Date() }];
    state.streamingText = '';
    state.thinking = true;
    client.sendText(text);
  }

  async function startRecording() {
    if (!client.connected) return;
    await recorder.start();
    state.recording = true;
    client.sendAudioStart();
  }

  async function stopRecording() {
    if (!recorder.recording) return;
    const blob = await recorder.stop();
    state.recording = false;
    state.thinking = true;
    state.streamingText = '';

    // Send audio data
    const buffer = await blob.arrayBuffer();
    client.sendAudioChunk(buffer);
    client.sendAudioEnd();
  }

  function saveSettings() {
    localStorage.setItem('dolores-settings', JSON.stringify({
      serverUrl: state.serverUrl,
      apiKey: state.apiKey,
      voiceId: state.voiceId,
      provider: state.provider,
    }));
  }

  return {
    get state() { return state; },
    connect,
    disconnect,
    sendText,
    startRecording,
    stopRecording,
    saveSettings,
    stopAudio: () => player.stop(),
  };
}

function loadSettings(): Partial<AppState> {
  try {
    const raw = localStorage.getItem('dolores-settings');
    if (raw) return JSON.parse(raw);
  } catch {}
  return {};
}

export const app = createAppState();
