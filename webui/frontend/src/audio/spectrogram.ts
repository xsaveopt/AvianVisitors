import { authHeaders } from '@/api/credentials';
import { recordingFileUrl } from '@/api/client';

let specCtx: AudioContext | null = null;
const decodedCache: Record<string, AudioBuffer> = {};

export function getSpecCtx(): AudioContext | null {
  if (!specCtx) {
    const C = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (C) {
      specCtx = new C();
    }
  }
  return specCtx;
}

export function cachedBuffer(file: string): AudioBuffer | undefined {
  return decodedCache[file];
}

export async function decodeRecording(file: string): Promise<AudioBuffer> {
  if (decodedCache[file]) {
    return decodedCache[file];
  }
  const ctx = getSpecCtx();
  if (!ctx) {
    throw new Error('WebAudio not available');
  }
  const res = await fetch(recordingFileUrl(file), { headers: authHeaders() });
  if (!res.ok) {
    throw new Error('HTTP ' + res.status);
  }
  const buf = await res.arrayBuffer();
  const audioBuffer = await ctx.decodeAudioData(buf);
  decodedCache[file] = audioBuffer;
  return audioBuffer;
}

function fft(real: Float32Array, imag: Float32Array): void {
  const n = real.length;
  let j = 0;
  for (let i = 0; i < n - 1; i++) {
    if (i < j) {
      const tr = real[i];
      real[i] = real[j];
      real[j] = tr;
      const ti = imag[i];
      imag[i] = imag[j];
      imag[j] = ti;
    }
    let k = n >> 1;
    while (k <= j) {
      j -= k;
      k >>= 1;
    }
    j += k;
  }
  for (let stage = 2; stage <= n; stage *= 2) {
    const half = stage >> 1;
    const ang = (-2 * Math.PI) / stage;
    const wR = Math.cos(ang);
    const wI = Math.sin(ang);
    for (let sBase = 0; sBase < n; sBase += stage) {
      let cR = 1;
      let cI = 0;
      for (let sb = 0; sb < half; sb++) {
        const a = sBase + sb;
        const b = a + half;
        const trA = real[b] * cR - imag[b] * cI;
        const tiA = real[b] * cI + imag[b] * cR;
        real[b] = real[a] - trA;
        imag[b] = imag[a] - tiA;
        real[a] = real[a] + trA;
        imag[a] = imag[a] + tiA;
        const nR = cR * wR - cI * wI;
        cI = cR * wI + cI * wR;
        cR = nR;
      }
    }
  }
}

export function paintSpectrogram(canvas: HTMLCanvasElement, audioBuffer: AudioBuffer): void {
  requestAnimationFrame(() => paintNow(canvas, audioBuffer));
}

function paintNow(canvas: HTMLCanvasElement, audioBuffer: AudioBuffer): void {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const strip = canvas.parentElement;
  const cssW = strip ? strip.clientWidth : canvas.clientWidth || 600;
  const cssH = strip ? strip.clientHeight : canvas.clientHeight || 88;
  if (cssW < 32 || cssH < 32) {
    requestAnimationFrame(() => paintNow(canvas, audioBuffer));
    return;
  }
  const W = Math.max(1, Math.floor(cssW * dpr));
  const H = Math.max(1, Math.floor(cssH * dpr));
  canvas.width = W;
  canvas.height = H;

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return;
  }
  const samples = audioBuffer.getChannelData(0);
  const sr = audioBuffer.sampleRate;
  const FFT_SIZE = 1024;
  const bins = FFT_SIZE >> 1;
  const nyquist = sr / 2;

  const fLo = 200;
  const fHi = Math.min(12000, nyquist);
  const binLo = Math.max(1, Math.floor((fLo / nyquist) * bins));
  const binHi = Math.min(bins - 1, Math.ceil((fHi / nyquist) * bins));

  const win = new Float32Array(FFT_SIZE);
  for (let i = 0; i < FFT_SIZE; i++) {
    win[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (FFT_SIZE - 1));
  }

  const hop = Math.max(1, Math.floor((samples.length - FFT_SIZE) / Math.max(1, W - 1)));
  const real = new Float32Array(FFT_SIZE);
  const imag = new Float32Array(FFT_SIZE);

  const imgData = ctx.createImageData(W, H);
  const data = imgData.data;

  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const BG_R = dark ? 23 : 245;
  const BG_G = dark ? 24 : 240;
  const BG_B = dark ? 28 : 230;
  const FG_R = dark ? 236 : 26;
  const FG_G = dark ? 232 : 22;
  const FG_B = dark ? 225 : 18;
  for (let p = 0; p < data.length; p += 4) {
    data[p] = BG_R;
    data[p + 1] = BG_G;
    data[p + 2] = BG_B;
    data[p + 3] = 255;
  }

  const rowToBin = new Int32Array(H);
  for (let row = 0; row < H; row++) {
    const t = 1 - row / (H - 1);
    const bin = Math.round(binLo + (binHi - binLo) * Math.pow(t, 1.55));
    rowToBin[row] = Math.max(binLo, Math.min(binHi, bin));
  }

  for (let col = 0; col < W; col++) {
    const start = col * hop;
    if (start + FFT_SIZE > samples.length) {
      break;
    }
    for (let s = 0; s < FFT_SIZE; s++) {
      real[s] = samples[start + s] * win[s];
      imag[s] = 0;
    }
    fft(real, imag);
    for (let row2 = 0; row2 < H; row2++) {
      const bin2 = rowToBin[row2];
      const re = real[bin2];
      const im = imag[bin2];
      const mag = Math.sqrt(re * re + im * im);
      const db = 20 * Math.log10(mag + 1e-9);
      let v = (db + 75) / 65;
      if (v < 0) {
        v = 0;
      } else if (v > 1) {
        v = 1;
      }
      const e = v * v * (3 - 2 * v);
      const r = BG_R + Math.round((FG_R - BG_R) * e);
      const g = BG_G + Math.round((FG_G - BG_G) * e);
      const b = BG_B + Math.round((FG_B - BG_B) * e);
      const px = (row2 * W + col) * 4;
      data[px] = r;
      data[px + 1] = g;
      data[px + 2] = b;
      data[px + 3] = 255;
    }
  }
  ctx.putImageData(imgData, 0, 0);
  canvas.classList.add('ready');
}
