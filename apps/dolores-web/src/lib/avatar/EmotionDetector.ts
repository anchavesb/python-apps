import type { AvatarEmotion } from './types';

interface EmotionMatch {
  emotion: AvatarEmotion;
  confidence: number;
}

const PATTERNS: { emotion: AvatarEmotion; words: string[] }[] = [
  { emotion: 'happy', words: ['great', 'awesome', 'wonderful', 'fantastic', 'glad', 'love', 'enjoy', 'excited', 'delighted', 'happy', 'joy', 'excellent', 'amazing'] },
  { emotion: 'sad', words: ['sorry', 'unfortunately', 'sad', 'regret', 'miss', 'difficult', 'tough', 'loss', 'apologize', 'condolence'] },
  { emotion: 'curious', words: ['interesting', 'fascinating', 'wonder', 'curious', 'hmm', 'intriguing', 'tell me more', 'really'] },
  { emotion: 'surprised', words: ['wow', 'whoa', 'incredible', 'unbelievable', 'no way', 'seriously', 'oh my', 'unexpected'] },
  { emotion: 'empathetic', words: ['understand', 'feel', 'hear you', 'must be', 'that sounds', 'i can imagine', 'care', 'support', 'here for you'] },
];

export function detectEmotion(text: string): EmotionMatch {
  const lower = text.toLowerCase();
  let bestEmotion: AvatarEmotion = 'neutral';
  let bestScore = 0;

  for (const { emotion, words } of PATTERNS) {
    let score = 0;
    for (const word of words) {
      if (lower.includes(word)) score++;
    }
    if (score > bestScore) {
      bestScore = score;
      bestEmotion = emotion;
    }
  }

  // Exclamation marks boost surprised/happy
  const exclamations = (text.match(/!/g) || []).length;
  if (exclamations >= 2 && bestScore < 2) {
    return { emotion: 'surprised', confidence: 0.4 };
  }

  // Question marks can indicate curiosity
  const questions = (text.match(/\?/g) || []).length;
  if (questions >= 2 && bestScore < 2) {
    return { emotion: 'curious', confidence: 0.3 };
  }

  return {
    emotion: bestEmotion,
    confidence: bestScore > 0 ? Math.min(1, bestScore * 0.3) : 0,
  };
}
