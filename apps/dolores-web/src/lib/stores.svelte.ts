import { DoloresClient, type MessageEvent, type WebResult } from './DoloresClient';
import { AudioRecorder, VADAudioRecorder, getSharedAudioContext, getSharedStream } from './AudioRecorder';
import { AudioPlayer } from './AudioPlayer';
import { detectEmotion } from './avatar/EmotionDetector';
import { handleCallback, loadAuth, login, logout, isTokenExpired, refreshAccessToken, type OIDCConfig } from './auth';
import type { AvatarPhase, AvatarEmotion } from './avatar/types';

export type { AvatarPhase, AvatarEmotion };

export type { WebResult };

export interface WebResultsPayload {
  results?: WebResult[];
  query?: string;
  pageContent?: string;
  url?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  speakerName?: string;
  imageUrl?: string;
  isGeneratedImage?: boolean;
  webResults?: WebResultsPayload;
}

interface AppState {
  messages: ChatMessage[];
  connected: boolean;
  recording: boolean;
  thinking: boolean;
  transcription: string; // current/last speech-to-text result
  streamingText: string; // current assistant response being streamed
  settingsOpen: boolean;
  serverUrl: string;
  apiKey: string;
  userToken: string;
  voiceId: string;
  provider: string;
  model: string;
  ttsEnabled: boolean;
  audioPlaying: boolean;
  emotion: AvatarEmotion;
  viewMode: 'chat' | 'avatar';
  conversationId: string;
  vadMode: boolean;   // false = push-to-talk (default), true = auto-listen
  vadActive: boolean; // true if VAD is currently running
  vadStatus: string;  // Detailed status (e.g., 'loading models', 'listening')
  vadError: string | null;
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
    messages: (saved.messages || []).map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) })),
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
    model: saved.model || '',
    ttsEnabled: saved.ttsEnabled !== false,
    audioPlaying: false,
    emotion: 'neutral',
    viewMode: (saved.viewMode as 'chat' | 'avatar') || 'chat',
    conversationId: saved.conversationId || '',
    vadMode: saved.vadMode === true,
    vadActive: false,
    vadStatus: 'idle',
    vadError: null,
    oidcIssuer: saved.oidcIssuer || '',
    oidcClientId: saved.oidcClientId || '',
    oidcUser: auth?.userName || null,
  });

  const client = new DoloresClient();
  const recorder = new AudioRecorder();
  const vadRecorder = new VADAudioRecorder();
  const player = new AudioPlayer();

  player.onPlaybackStart(() => { state.audioPlaying = true; });
  player.onPlaybackEnd(() => { state.audioPlaying = false; });

  let thinkingTimer: any = null;
  function setThinking(val: boolean) {
    state.thinking = val;
    if (thinkingTimer) clearTimeout(thinkingTimer);
    if (val) {
      thinkingTimer = setTimeout(() => {
        state.thinking = false;
        thinkingTimer = null;
      }, 15000); // 15s watchdog
    } else {
      thinkingTimer = null;
    }
  }

  function pushMessage(msg: ChatMessage) {
    const limit = 50;
    const newMessages = [...state.messages, msg];
    if (newMessages.length > limit) {
      state.messages = newMessages.slice(newMessages.length - limit);
    } else {
      state.messages = newMessages;
    }
    saveSettings();
  }

  // Fetch backend defaults on startup if no local settings are saved
  const hasSaved = !!localStorage.getItem('dolores-settings');
  if (!hasSaved) {
    DoloresClient.getSettings(state.serverUrl, state.apiKey)
      .then((defaults: any) => {
        state.provider = defaults.default_provider || 'ollama';
        state.model = defaults.default_model || '';
        state.voiceId = defaults.default_voice_id || 'default';
      })
      .catch((e) => console.error('Failed to fetch backend defaults:', e));
  }

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
      case 'transcription.partial':
        state.transcription = msg.text;
        break;

      case 'transcription.final':
        state.transcription = msg.text;
        setThinking(true); // wait for response.text
        pushMessage({
          role: 'user',
          content: msg.text,
          timestamp: new Date(),
          speakerName: msg.speaker_name,
        });
        break;

      case 'response.emotion':
        state.emotion = msg.emotion as AvatarEmotion;
        break;

      case 'response.text':
        state.streamingText += msg.content;
        setThinking(false);
        break;
      case 'response.image':
        pushMessage({
          role: 'assistant',
          content: '',
          timestamp: new Date(),
          imageUrl: msg.image_data,
          isGeneratedImage: true,
        });
        setThinking(false);
        break;
      case 'response.web_results':
        pushMessage({
          role: 'assistant',
          content: '',
          timestamp: new Date(),
          webResults: {
            results: msg.results,
            query: msg.query,
            pageContent: msg.page_content,
            url: msg.url,
          },
        });
        setThinking(false);
        break;
      case 'response.end': {
        const fullText = msg.full_text || state.streamingText;
        if (fullText) {
          pushMessage({
            role: 'assistant',
            content: fullText,
            timestamp: new Date(),
          });
        }
        // Fallback emotion detection if no LLM tag was received
        if (state.emotion === 'neutral') {
          const detected = detectEmotion(fullText);
          if (detected.confidence > 0.2) {
            state.emotion = detected.emotion;
          }
        }
        state.streamingText = '';
        setThinking(false);
        break;
      }
      case 'error':
        if (msg.code === 'session_expired') {
          // Attempt silent token refresh, then prompt re-login if that fails
          const config = getOIDCConfig();
          if (config) {
            refreshAccessToken(config).then((refreshed) => {
              if (refreshed?.accessToken) {
                state.userToken = refreshed.accessToken;
                // Push the new token to the backend so subsequent requests use it
                client.updateToken(refreshed.accessToken);
                pushMessage({
                  role: 'assistant',
                  content: 'Session refreshed. Please try again.',
                  timestamp: new Date(),
                });
              } else {
                state.userToken = '';
                state.oidcUser = null;
                pushMessage({
                  role: 'assistant',
                  content: 'Your session has expired. Please login again in Settings.',
                  timestamp: new Date(),
                });
              }
            });
          } else {
            pushMessage({
              role: 'assistant',
              content: 'Your session has expired. Please login again in Settings.',
              timestamp: new Date(),
            });
          }
        } else {
          pushMessage({
            role: 'assistant',
            content: `Error: ${msg.message}`,
            timestamp: new Date(),
          });
        }
        setThinking(false);
        break;
    }
  });

  let isInitializingVAD = false;
  async function initVAD(): Promise<void> {
    if (isInitializingVAD) return;
    isInitializingVAD = true;
    state.vadError = null;
    state.vadStatus = 'Initializing...';
    console.log('[VAD] Starting initialization...');
    try {
      await vadRecorder.init({
        onSpeechStart: () => {
          if (state.audioPlaying) return; // Dolores speaking → ignore
          player.stop();
          state.recording = true;
          state.vadStatus = 'Speech detected';
          client.sendAudioStart();
        },
        onSpeechEnd: async (audio: Float32Array) => {
          if (!state.recording) return;
          state.recording = false;
          state.vadStatus = 'Processing...';
          const blob = VADAudioRecorder.encodeWav(audio);
          const buffer = await blob.arrayBuffer();
          if (buffer.byteLength < 1000) {
            state.vadStatus = 'Noise ignored';
            setTimeout(() => {
              if (state.vadActive) state.vadStatus = 'Listening (Auto)';
            }, 1500);
            return; // too short, ignore
          }
          setThinking(true);
          state.transcription = '';
          state.streamingText = '';
          state.emotion = 'neutral';
          client.sendAudioChunk(buffer);
          client.sendAudioEnd('audio/wav');
        },
      });
      console.log('[VAD] Recorder initialized, resuming...');
      await vadRecorder.resume();
      state.vadActive = true;
      state.vadStatus = 'Listening (Auto)';
      console.log('[VAD] Ready.');
    } catch (e) {
      state.vadError = String(e);
      state.vadStatus = 'Error';
      console.error('[VAD] Initialization failed:', e);
    } finally {
      isInitializingVAD = false;
    }
  }

  async function connect() {
    try {
      await getSharedAudioContext();
      await getSharedStream();
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
      if (state.vadMode) {
        await initVAD();
      } else {
        await recorder.init();
      }
      await client.connect({
        serverUrl: state.serverUrl,
        apiKey: state.apiKey,
        voiceId: state.voiceId,
        provider: state.provider,
        model: state.model || undefined,
        mode: state.ttsEnabled ? 'both' : 'text',
        conversationId: state.conversationId || undefined,
        userToken: state.userToken || undefined,
      });
      state.connected = true;
    } catch (e) {
      pushMessage({
        role: 'assistant',
        content: `Connection failed: ${e instanceof Error ? e.message : 'Unknown error'}`,
        timestamp: new Date(),
      });
    }
  }

  function disconnect() {
    client.disconnect();
    recorder.destroy();
    vadRecorder.destroy();
    state.connected = false;
  }

  async function sendText(text: string) {
    if (!client.connected) return;
    await getSharedAudioContext();
    pushMessage({ role: 'user', content: text, timestamp: new Date() });
    state.streamingText = '';
    setThinking(true);
    state.emotion = 'neutral'; // reset for new response
    client.sendText(text);
  }

  async function sendImageMessage(imageData: string, text: string) {
    if (!client.connected) return;
    await getSharedAudioContext();
    pushMessage({
      role: 'user',
      content: text || 'Image',
      timestamp: new Date(),
      imageUrl: imageData,
    });
    state.streamingText = '';
    setThinking(true);
    state.emotion = 'neutral';
    client.sendImage(imageData, text);
  }

  let recordingReady: Promise<void> | null = null;

  async function startRecording() {
    if (!client.connected || state.recording) return;
    await getSharedAudioContext();
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

    setThinking(true);
    state.transcription = '';
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
      model: state.model,
      viewMode: state.viewMode,
      conversationId: state.conversationId,
      oidcIssuer: state.oidcIssuer,
      oidcClientId: state.oidcClientId,
      ttsEnabled: state.ttsEnabled,
      vadMode: state.vadMode,
      messages: state.messages,
    }));
  }

  function toggleTts() {
    state.ttsEnabled = !state.ttsEnabled;
    if (state.ttsEnabled) {
      client.updateMode('both');
    } else {
      player.stop();
      client.updateMode('text');
    }
    saveSettings();
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

  function newConversation() {
    state.conversationId = '';
    state.messages = [];
    state.streamingText = '';
    state.emotion = 'neutral';
    saveSettings();
    // Reconnect with fresh conversation if currently connected
    if (client.connected) {
      disconnect();
      connect();
    }
  }

  let isInitialized = false;
  function init() {
    if (isInitialized) return;
    isInitialized = true;
    let isVisible = $state(typeof document !== 'undefined' ? !document.hidden : true);

    // Tab visibility listener
    $effect(() => {
      if (typeof document === 'undefined') return;
      const handleVisibility = () => { isVisible = !document.hidden; };
      document.addEventListener('visibilitychange', handleVisibility);
      return () => document.removeEventListener('visibilitychange', handleVisibility);
    });

    // VAD management (reactive)
    $effect(() => {
      if (state.vadMode && state.connected && isVisible) {
        if (!vadRecorder.initialized) {
          initVAD();
        } else {
          // Pause only if Dolores is speaking
          if (state.audioPlaying) {
            vadRecorder.pause();
            state.vadActive = false;
            state.vadStatus = 'Speaking (Paused)';
          } else {
            vadRecorder.start();
            state.vadActive = vadRecorder.initialized;
            if (state.vadActive) state.vadStatus = 'Listening (Auto)';
          }
        }
      } else {
        vadRecorder.pause();
        state.vadActive = false;
        state.vadStatus = state.vadMode ? 'Idle (VAD off)' : 'Push-to-talk';
      }
    });
  }

  return {
    get state() { return state; },
    get avatarPhase(): AvatarPhase { return getAvatarPhase(state); },
    get player() { return player; },
    init,
    connect,
    disconnect,
    sendText,
    sendImageMessage,
    startRecording,
    stopRecording,
    saveSettings,
    setViewMode,
    newConversation,
    oidcLogin,
    oidcLogout,
    oidcHandleCallback,
    toggleTts,
    testAudio: () => player.testAudio(),
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
