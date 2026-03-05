import {
  type AvatarPhase,
  type AvatarEmotion,
  type EmotionParams,
  PHASE_COLORS,
  PHASE_GLOW_COLORS,
  EMOTION_PARAMS,
} from './types';

interface RenderState {
  phase: AvatarPhase;
  emotion: AvatarEmotion;
  volume: number;
}

interface AnimState {
  // Lerped values for smooth transitions
  glowR: number; glowG: number; glowB: number; glowA: number;
  eyeOpenness: number;
  eyeDroop: number;
  browRaise: number;
  browFurrow: number;
  mouthSmile: number;
  mouthOpen: number;
  headTilt: number;
  // Idle micro-animations
  blinkTimer: number;
  blinkActive: boolean;
  lookX: number;
  lookY: number;
  lookTimer: number;
  // Thinking bounce
  bounceOffset: number;
  // Time
  t: number;
}

function parseColor(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b];
}

function parseRgba(rgba: string): [number, number, number, number] {
  const m = rgba.match(/[\d.]+/g);
  if (!m) return [0, 0, 0, 0];
  return [+m[0], +m[1], +m[2], +m[3]];
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

const LERP_SPEED = 0.08; // ~300ms at 30fps
const TARGET_FPS = 30;
const FRAME_TIME = 1000 / TARGET_FPS;

export class AvatarRenderer {
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private animId = 0;
  private lastFrame = 0;
  private state: RenderState = { phase: 'idle', emotion: 'neutral', volume: 0 };

  private anim: AnimState = {
    glowR: 83, glowG: 52, glowB: 131, glowA: 0.4,
    eyeOpenness: 0.7, eyeDroop: 0, browRaise: 0, browFurrow: 0,
    mouthSmile: 0.1, mouthOpen: 0, headTilt: 0,
    blinkTimer: 3000, blinkActive: false,
    lookX: 0, lookY: 0, lookTimer: 5000,
    bounceOffset: 0,
    t: 0,
  };

  attach(canvas: HTMLCanvasElement): void {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d')!;
    this.lastFrame = performance.now();
    this.loop();
  }

  detach(): void {
    if (this.animId) cancelAnimationFrame(this.animId);
    this.animId = 0;
    this.canvas = null;
    this.ctx = null;
  }

  update(phase: AvatarPhase, emotion: AvatarEmotion, volume: number): void {
    this.state = { phase, emotion, volume };
  }

  private loop = (): void => {
    if (!this.canvas || !this.ctx) return;
    this.animId = requestAnimationFrame(this.loop);

    const now = performance.now();
    const dt = now - this.lastFrame;
    if (dt < FRAME_TIME) return; // frame skip for 30fps target
    this.lastFrame = now;

    this.updateAnimation(dt);
    this.render(dt);
  };

  private updateAnimation(dt: number): void {
    const a = this.anim;
    const { phase, emotion, volume } = this.state;
    const ep = EMOTION_PARAMS[emotion];
    const [gr, gg, gb, ga] = parseRgba(PHASE_GLOW_COLORS[phase]);

    a.t += dt;

    // Lerp glow color
    a.glowR = lerp(a.glowR, gr, LERP_SPEED);
    a.glowG = lerp(a.glowG, gg, LERP_SPEED);
    a.glowB = lerp(a.glowB, gb, LERP_SPEED);
    a.glowA = lerp(a.glowA, ga, LERP_SPEED);

    // Lerp emotion params
    a.eyeDroop = lerp(a.eyeDroop, ep.eyeDroop, LERP_SPEED);
    a.browRaise = lerp(a.browRaise, ep.browRaise, LERP_SPEED);
    a.browFurrow = lerp(a.browFurrow, ep.browFurrow, LERP_SPEED);
    a.headTilt = lerp(a.headTilt, ep.headTilt, LERP_SPEED);

    // Eye openness: depends on phase + emotion + blink
    let targetEyeOpen = ep.eyeOpenness;
    if (phase === 'thinking') targetEyeOpen = 0.35;
    if (phase === 'listening') targetEyeOpen = Math.max(ep.eyeOpenness, 0.9);

    // Blink
    a.blinkTimer -= dt;
    if (a.blinkTimer <= 0 && !a.blinkActive) {
      a.blinkActive = true;
      a.blinkTimer = 150; // blink duration
    } else if (a.blinkActive) {
      if (a.blinkTimer <= 0) {
        a.blinkActive = false;
        // Random next blink: 2-6 seconds
        a.blinkTimer = 2000 + Math.random() * 4000;
        if (phase === 'sad') a.blinkTimer *= 1.5; // slower blink when sad
      }
      targetEyeOpen = 0.05;
    }
    a.eyeOpenness = lerp(a.eyeOpenness, targetEyeOpen, a.blinkActive ? 0.3 : LERP_SPEED);

    // Mouth: emotion base + volume when speaking
    let targetMouthSmile = ep.mouthSmile;
    let targetMouthOpen = ep.mouthOpen;
    if (phase === 'speaking') {
      targetMouthOpen = Math.max(ep.mouthOpen, volume * 0.7);
    }
    a.mouthSmile = lerp(a.mouthSmile, targetMouthSmile, LERP_SPEED);
    a.mouthOpen = lerp(a.mouthOpen, targetMouthOpen, 0.2); // faster for lip sync

    // Idle look-around
    if (phase === 'idle') {
      a.lookTimer -= dt;
      if (a.lookTimer <= 0) {
        a.lookX = (Math.random() - 0.5) * 0.3;
        a.lookY = (Math.random() - 0.5) * 0.15;
        a.lookTimer = 3000 + Math.random() * 4000;
      }
    } else if (phase === 'listening') {
      a.lookX = 0;
      a.lookY = 0;
    }

    // Thinking bounce
    if (phase === 'thinking') {
      a.bounceOffset = Math.sin(a.t / 600) * 4;
    } else {
      a.bounceOffset = lerp(a.bounceOffset, 0, LERP_SPEED);
    }
  }

  private render(dt: number): void {
    const canvas = this.canvas!;
    const ctx = this.ctx!;
    const a = this.anim;
    const { phase } = this.state;

    // Resize canvas to match display size
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const w = rect.width;
    const h = rect.height;
    const cx = w / 2;
    const cy = h / 2 + a.bounceOffset;
    const faceRadius = Math.min(w, h) * 0.28;

    // Clear
    ctx.clearRect(0, 0, w, h);

    // Apply head tilt
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(a.headTilt * 0.1);
    ctx.translate(-cx, -cy);

    // Glow
    const gradient = ctx.createRadialGradient(cx, cy, faceRadius * 0.8, cx, cy, faceRadius * 1.8);
    gradient.addColorStop(0, `rgba(${a.glowR}, ${a.glowG}, ${a.glowB}, ${a.glowA})`);
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);

    // Pulsing glow for listening
    if (phase === 'listening') {
      const pulse = 0.5 + 0.5 * Math.sin(a.t / 400);
      const pulseGrad = ctx.createRadialGradient(cx, cy, faceRadius, cx, cy, faceRadius * 1.5);
      pulseGrad.addColorStop(0, `rgba(${a.glowR}, ${a.glowG}, ${a.glowB}, ${pulse * 0.3})`);
      pulseGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = pulseGrad;
      ctx.fillRect(0, 0, w, h);
    }

    // Face circle
    const [fr, fg, fb] = parseColor(PHASE_COLORS[phase]);
    ctx.beginPath();
    ctx.arc(cx, cy, faceRadius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${fr}, ${fg}, ${fb}, 0.15)`;
    ctx.fill();
    ctx.strokeStyle = `rgba(${fr}, ${fg}, ${fb}, 0.5)`;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Eyes
    this.drawEyes(ctx, cx, cy, faceRadius);

    // Eyebrows
    this.drawBrows(ctx, cx, cy, faceRadius);

    // Mouth
    this.drawMouth(ctx, cx, cy, faceRadius);

    ctx.restore();
  }

  private drawEyes(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number): void {
    const a = this.anim;
    const eyeSpacing = r * 0.35;
    const eyeY = cy - r * 0.1;
    const eyeWidth = r * 0.18;
    const eyeHeight = r * 0.22 * a.eyeOpenness;
    const droopOffset = a.eyeDroop * r * 0.05;

    for (const side of [-1, 1]) {
      const ex = cx + side * eyeSpacing;
      const ey = eyeY + droopOffset * (side === -1 ? 1 : 0.7);

      // Eye white
      ctx.beginPath();
      ctx.ellipse(ex + a.lookX * r * 0.05, ey + a.lookY * r * 0.05, eyeWidth, Math.max(eyeHeight, 1), 0, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(224, 224, 224, 0.9)';
      ctx.fill();

      // Pupil
      if (a.eyeOpenness > 0.1) {
        const pupilR = eyeWidth * 0.5;
        ctx.beginPath();
        ctx.arc(ex + a.lookX * r * 0.08, ey + a.lookY * r * 0.04, pupilR, 0, Math.PI * 2);
        ctx.fillStyle = '#1a1a2e';
        ctx.fill();

        // Pupil highlight
        ctx.beginPath();
        ctx.arc(ex + a.lookX * r * 0.08 + pupilR * 0.3, ey + a.lookY * r * 0.04 - pupilR * 0.3, pupilR * 0.3, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.fill();
      }
    }
  }

  private drawBrows(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number): void {
    const a = this.anim;
    const eyeSpacing = r * 0.35;
    const browY = cy - r * 0.28;
    const browWidth = r * 0.22;

    for (const side of [-1, 1]) {
      const bx = cx + side * eyeSpacing;
      const raiseOffset = -a.browRaise * r * 0.08;
      const furrowInner = a.browFurrow * r * 0.04;

      ctx.beginPath();
      ctx.moveTo(bx - browWidth, browY + raiseOffset + furrowInner * side);
      ctx.quadraticCurveTo(
        bx, browY + raiseOffset - r * 0.03,
        bx + browWidth, browY + raiseOffset - furrowInner * side
      );
      ctx.strokeStyle = 'rgba(224, 224, 224, 0.7)';
      ctx.lineWidth = r * 0.03;
      ctx.lineCap = 'round';
      ctx.stroke();
    }
  }

  private drawMouth(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number): void {
    const a = this.anim;
    const mouthY = cy + r * 0.3;
    const mouthWidth = r * 0.3;
    const smileCurve = a.mouthSmile * r * 0.12;
    const openHeight = a.mouthOpen * r * 0.15;

    if (openHeight > 1) {
      // Open mouth (speaking or surprised)
      ctx.beginPath();
      ctx.moveTo(cx - mouthWidth, mouthY);
      ctx.quadraticCurveTo(cx, mouthY + smileCurve + openHeight, cx + mouthWidth, mouthY);
      ctx.quadraticCurveTo(cx, mouthY + smileCurve - openHeight * 0.3, cx - mouthWidth, mouthY);
      ctx.fillStyle = 'rgba(26, 26, 46, 0.8)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(224, 224, 224, 0.6)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    } else {
      // Closed mouth (line/smile/frown)
      ctx.beginPath();
      ctx.moveTo(cx - mouthWidth, mouthY);
      ctx.quadraticCurveTo(cx, mouthY + smileCurve, cx + mouthWidth, mouthY);
      ctx.strokeStyle = 'rgba(224, 224, 224, 0.7)';
      ctx.lineWidth = r * 0.025;
      ctx.lineCap = 'round';
      ctx.stroke();
    }
  }
}
