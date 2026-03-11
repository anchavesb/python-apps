import { DoloresClient, type MessageEvent } from './DoloresClient';
import { AudioRecorder } from './AudioRecorder';
import { AudioPlayer } from './AudioPlayer';
import { detectEmotion } from './avatar/EmotionDetector';
import { handleCallback, loadAuth, login, logout, isTokenExpired, refreshAccessToken, type OIDCConfig } from './auth';
import type { AvatarPhase, AvatarEmotion } from './avatar/types';

export type { AvatarPhase, AvatarEmotion };

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
  userToken: string;
  voiceId: string;
  provider: string;
  audioPlaying: boolean;
  emotion: AvatarEmotion;
  viewMode: 'chat' | 'avatar';
  conversationId: string;
  // OIDC
  oidcIssuer: string;
  oidcClientId: string;
  oidcUser: string | null;  // display name from OIDC
}

function getAvatarPhase(s: AppState): AvatarPhase {
  if (s.recording) return 'listening';
  if (s.thinking && !s.streamingText) return 'thinking';
  if (s.audioPlaying || s.streamingText) return 'speaking';
  return 'idle';
}

function createAppState() {
  const saved = loadSettings();
  const auth = loadAuth();

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
    userToken: auth?.accessToken || '',
    voiceId: saved.voiceId || 'default',
    provider: saved.provider || 'ollama',
    audioPlaying: false,
    emotion: 'neutral',
    viewMode: (saved.viewMode as 'chat' | 'avatar') || 'chat',
    conversationId: saved.conversationId || '',
    oidcIssuer: saved.oidcIssuer || '',
    oidcClientId: saved.oidcClientId || '',
    oidcUser: auth?.userName || null,
  });

  const client = new DoloresClient();
  const recorder = new AudioRecorder();
  const player = new AudioPlayer();

  player.onPlaybackStart(() => { state.audioPlaying = true; });
  player.onPlaybackEnd(() => { state.audioPlaying = false; });

  client.onMessage((event) => {
    if (event instanceof ArrayBuffer) {
      player.enqueue(event);
      return;
    }

    const msg = event as MessageEvent;

    switch (msg.type) {
      case 'session.created':
        if (msg.conversation_id) {
          state.conversationId = msg.conversation_id;
          saveSettings();
        }
        break;
      case 'transcription.final':
        state.transcription = msg.text;
        state.messages = [...state.messages, { role: 'user', content: msg.text, timestamp: new Date() }];
        break;
      case 'response.emotion':
        state.emotion = msg.emotion as AvatarEmotion;
        break;
      case 'response.text':
        state.streamingText += msg.content;
        state.thinking = false;
        break;
      case 'response.end': {
        const fullText = msg.full_text || state.streamingText;
        state.messages = [...state.messages, {
          role: 'assistant',
          content: fullText,
          timestamp: new Date(),
        }];
        // Fallback emotion detection if no LLM tag was received
        if (state.emotion === 'neutral') {
          const detected = detectEmotion(fullText);
          if (detected.confidence > 0.2) {
            state.emotion = detected.emotion;
          }
        }
        state.streamingText = '';
        state.thinking = false;
        break;
      }
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
      // Refresh expired OIDC token before connecting
      if (state.userToken) {
        const auth = loadAuth();
        if (auth && isTokenExpired(auth)) {
          const config = getOIDCConfig();
          if (config) {
            const refreshed = await refreshAccessToken(config);
            if (refreshed?.accessToken) {
              state.userToken = refreshed.accessToken;
            } else {
              state.userToken = '';
              state.oidcUser = null;
              state.messages = [...state.messages, {
                role: 'assistant',
                content: 'Your session has expired. Please login again in Settings.',
                timestamp: new Date(),
              }];
              return;
            }
          }
        }
      }

      // Acquire mic permission early and keep stream alive to avoid re-prompting on iOS
      await recorder.init();
      await client.connect({
        serverUrl: state.serverUrl,
        apiKey: state.apiKey,
        voiceId: state.voiceId,
        provider: state.provider,
        mode: 'both',
        conversationId: state.conversationId || undefined,
        userToken: state.userToken || undefined,
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
    recorder.destroy();
    state.connected = false;
  }

  async function sendText(text: string) {
    if (!client.connected) return;
    state.messages = [...state.messages, { role: 'user', content: text, timestamp: new Date() }];
    state.streamingText = '';
    state.thinking = true;
    state.emotion = 'neutral'; // reset for new response
    client.sendText(text);
  }

  let recordingReady: Promise<void> | null = null;

  async function startRecording() {
    if (!client.connected || state.recording) return;
    player.stop(); // Stop TTS playback to prevent echo/feedback
    state.recording = true;
    recordingReady = recorder.start().then(() => {
      client.sendAudioStart();
    });
  }

  async function stopRecording() {
    if (!state.recording) return;
    // Wait for start to fully complete before stopping
    if (recordingReady) {
      await recordingReady;
      recordingReady = null;
    }

    const blob = await recorder.stop();
    state.recording = false;

    const buffer = await blob.arrayBuffer();
    if (buffer.byteLength === 0) return; // Nothing recorded (too short)

    state.thinking = true;
    state.streamingText = '';
    state.emotion = 'neutral'; // reset for new response

    // Send audio data with content type for iOS compatibility
    client.sendAudioChunk(buffer);
    client.sendAudioEnd(recorder.mimeType || undefined);
  }

  function saveSettings() {
    localStorage.setItem('dolores-settings', JSON.stringify({
      serverUrl: state.serverUrl,
      apiKey: state.apiKey,
      voiceId: state.voiceId,
      provider: state.provider,
      viewMode: state.viewMode,
      conversationId: state.conversationId,
      oidcIssuer: state.oidcIssuer,
      oidcClientId: state.oidcClientId,
    }));
  }

  function setViewMode(mode: 'chat' | 'avatar') {
    state.viewMode = mode;
    saveSettings();
  }

  function getOIDCConfig(): OIDCConfig | null {
    if (!state.oidcIssuer || !state.oidcClientId) return null;
    return { issuer: state.oidcIssuer, clientId: state.oidcClientId };
  }

  async function oidcLogin() {
    const config = getOIDCConfig();
    if (!config) return;
    saveSettings();
    await login(config);
  }

  async function oidcLogout() {
    const config = getOIDCConfig();
    state.userToken = '';
    state.oidcUser = null;
    if (config) {
      await logout(config);
    }
  }

  async function oidcHandleCallback(): Promise<boolean> {
    const config = getOIDCConfig();
    if (!config) return false;
    const auth = await handleCallback(config);
    if (auth) {
      state.userToken = auth.accessToken || '';
      state.oidcUser = auth.userName;
      return true;
    }
    return false;
  }

  return {
    get state() { return state; },
    get avatarPhase(): AvatarPhase { return getAvatarPhase(state); },
    get player() { return player; },
    connect,
    disconnect,
    sendText,
    startRecording,
    stopRecording,
    saveSettings,
    setViewMode,
    oidcLogin,
    oidcLogout,
    oidcHandleCallback,
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
