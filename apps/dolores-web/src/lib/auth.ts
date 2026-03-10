/**
 * Minimal OIDC Authorization Code + PKCE flow for SPA.
 *
 * Authenticates users via Authentik (or any OIDC provider) without
 * requiring a client secret. The access token is used for JWT passthrough
 * to downstream services (e.g. todo API).
 */

export interface OIDCConfig {
  issuer: string;    // e.g. https://auth.example.com/application/o/dolores/
  clientId: string;
  scopes?: string;   // defaults to "openid profile email"
  redirectUri?: string;
}

interface OIDCEndpoints {
  authorization_endpoint: string;
  token_endpoint: string;
  end_session_endpoint?: string;
}

interface TokenResponse {
  access_token: string;
  id_token?: string;
  refresh_token?: string;
  expires_in?: number;
  token_type: string;
}

export interface AuthState {
  accessToken: string | null;
  userName: string | null;
  userEmail: string | null;
  expiresAt: number | null;
}

const STORAGE_KEY = 'dolores-auth';
const PKCE_KEY = 'dolores-pkce';

// --- PKCE helpers ---

function generateRandomString(length: number): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, b => b.toString(16).padStart(2, '0')).join('').slice(0, length);
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  return crypto.subtle.digest('SHA-256', encoder.encode(plain));
}

function base64urlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// --- Discovery ---

let _endpoints: OIDCEndpoints | null = null;

async function discoverEndpoints(issuer: string): Promise<OIDCEndpoints> {
  if (_endpoints) return _endpoints;

  const url = `${issuer.replace(/\/$/, '')}/.well-known/openid-configuration`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`OIDC discovery failed: ${resp.status}`);
  const config = await resp.json();

  _endpoints = {
    authorization_endpoint: config.authorization_endpoint,
    token_endpoint: config.token_endpoint,
    end_session_endpoint: config.end_session_endpoint,
  };
  return _endpoints;
}

// --- Auth flow ---

export async function login(config: OIDCConfig): Promise<void> {
  const endpoints = await discoverEndpoints(config.issuer);
  const scopes = config.scopes || 'openid profile email';
  const redirectUri = config.redirectUri || `${window.location.origin}${import.meta.env.BASE_URL}`;

  // Generate PKCE
  const codeVerifier = generateRandomString(64);
  const codeChallenge = base64urlEncode(await sha256(codeVerifier));

  // Store PKCE state for callback
  const state = generateRandomString(32);
  sessionStorage.setItem(PKCE_KEY, JSON.stringify({ codeVerifier, state }));

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: redirectUri,
    scope: scopes,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });

  window.location.href = `${endpoints.authorization_endpoint}?${params}`;
}

export async function handleCallback(config: OIDCConfig): Promise<AuthState | null> {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const returnedState = params.get('state');

  if (!code) return null;

  // Verify state and get code verifier
  const stored = sessionStorage.getItem(PKCE_KEY);
  if (!stored) throw new Error('Missing PKCE state — login may have expired');
  const { codeVerifier, state } = JSON.parse(stored);

  if (returnedState !== state) throw new Error('OIDC state mismatch');
  sessionStorage.removeItem(PKCE_KEY);

  const endpoints = await discoverEndpoints(config.issuer);
  const redirectUri = config.redirectUri || `${window.location.origin}${import.meta.env.BASE_URL}`;

  // Exchange code for tokens
  const resp = await fetch(endpoints.token_endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config.clientId,
      code,
      redirect_uri: redirectUri,
      code_verifier: codeVerifier,
    }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Token exchange failed: ${resp.status} ${text}`);
  }

  const tokens: TokenResponse = await resp.json();

  // Decode ID token for user info (no validation needed — we just got it from the provider)
  let userName: string | null = null;
  let userEmail: string | null = null;
  if (tokens.id_token) {
    try {
      const payload = JSON.parse(atob(tokens.id_token.split('.')[1]));
      userName = payload.name || payload.preferred_username || null;
      userEmail = payload.email || null;
    } catch { /* ignore decode errors */ }
  }

  const authState: AuthState = {
    accessToken: tokens.access_token,
    userName,
    userEmail,
    expiresAt: tokens.expires_in ? Date.now() + tokens.expires_in * 1000 : null,
  };

  // Persist
  localStorage.setItem(STORAGE_KEY, JSON.stringify(authState));

  // Clean URL
  window.history.replaceState({}, '', window.location.pathname);

  return authState;
}

export function loadAuth(): AuthState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const state: AuthState = JSON.parse(raw);
    // Check expiry
    if (state.expiresAt && Date.now() > state.expiresAt) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return state;
  } catch {
    return null;
  }
}

export async function logout(config: OIDCConfig): Promise<void> {
  localStorage.removeItem(STORAGE_KEY);
  _endpoints = null;

  // Try to redirect to provider's end-session endpoint
  try {
    const endpoints = await discoverEndpoints(config.issuer);
    if (endpoints.end_session_endpoint) {
      const redirectUri = `${window.location.origin}${import.meta.env.BASE_URL}`;
      const params = new URLSearchParams({ post_logout_redirect_uri: redirectUri });
      window.location.href = `${endpoints.end_session_endpoint}?${params}`;
      return;
    }
  } catch { /* fall through to local logout */ }
}

export function isTokenExpired(state: AuthState): boolean {
  if (!state.expiresAt) return false;
  // Consider expired 60s before actual expiry
  return Date.now() > state.expiresAt - 60_000;
}
