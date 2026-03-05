export type AvatarPhase = 'idle' | 'listening' | 'thinking' | 'speaking';
export type AvatarEmotion = 'neutral' | 'curious' | 'happy' | 'sad' | 'surprised' | 'empathetic';

export const PHASE_COLORS: Record<AvatarPhase, string> = {
  idle: '#533483',
  listening: '#1e90ff',
  thinking: '#f0a500',
  speaking: '#0ddb6a',
};

export const PHASE_GLOW_COLORS: Record<AvatarPhase, string> = {
  idle: 'rgba(83, 52, 131, 0.4)',
  listening: 'rgba(30, 144, 255, 0.5)',
  thinking: 'rgba(240, 165, 0, 0.4)',
  speaking: 'rgba(13, 219, 106, 0.4)',
};

export interface EmotionParams {
  eyeOpenness: number;
  eyeDroop: number;
  browRaise: number;
  browFurrow: number;
  mouthSmile: number;
  mouthOpen: number;
  headTilt: number;
}

export const EMOTION_PARAMS: Record<AvatarEmotion, EmotionParams> = {
  neutral: {
    eyeOpenness: 0.7, eyeDroop: 0, browRaise: 0, browFurrow: 0,
    mouthSmile: 0.1, mouthOpen: 0, headTilt: 0,
  },
  curious: {
    eyeOpenness: 0.85, eyeDroop: 0, browRaise: 0.5, browFurrow: 0,
    mouthSmile: 0.1, mouthOpen: 0.1, headTilt: 0.15,
  },
  happy: {
    eyeOpenness: 0.6, eyeDroop: 0, browRaise: 0.2, browFurrow: 0,
    mouthSmile: 0.9, mouthOpen: 0.2, headTilt: 0,
  },
  sad: {
    eyeOpenness: 0.5, eyeDroop: 0.5, browRaise: 0, browFurrow: 0.3,
    mouthSmile: -0.4, mouthOpen: 0, headTilt: -0.05,
  },
  surprised: {
    eyeOpenness: 1.0, eyeDroop: 0, browRaise: 0.9, browFurrow: 0,
    mouthSmile: 0, mouthOpen: 0.6, headTilt: 0,
  },
  empathetic: {
    eyeOpenness: 0.6, eyeDroop: 0.15, browRaise: 0.2, browFurrow: 0.1,
    mouthSmile: 0.3, mouthOpen: 0, headTilt: 0.05,
  },
};
