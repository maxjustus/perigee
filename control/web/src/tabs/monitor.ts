import { drawLevel } from "./meters.ts";

const channel = document.getElementById("monitor-channel") as HTMLSelectElement;
const listenButton = document.getElementById("monitor-listen")!;
const levelFill = document.getElementById("monitor-level")!;
const levelText = document.getElementById("monitor-db") as HTMLOutputElement;
let socket: WebSocket | null = null, audio: AudioContext | null = null, playAt = 0, peak = 0, peakQueued = false;

export function start(port: number, captureNames: string[]) {
  channel.append(...captureNames.map((name, index) => new Option(name, String(index + 1))));
  channel.value = localStorage.getItem("monitorChannel") ?? "9";
  channel.onchange = () => {
    localStorage.setItem("monitorChannel", channel.value);
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ channel: Number(channel.value) }));
  };
  listenButton.onclick = () => {
    const on = listenButton.getAttribute("aria-pressed") !== "true";
    listenButton.setAttribute("aria-pressed", String(on));
    if (on) {
      listen(port);
    } else {
      socket?.close();
      socket = null;
      peak = 0;
      showPeak(0);
    }
  };
}

// iOS starts Web Audio only from a tap. It mutes Web Audio with the ringer switch unless the session type is playback.
function listen(port: number) {
  const session = (navigator as Navigator & { audioSession?: { type: string } }).audioSession;
  if (session) session.type = "playback";
  audio ??= new AudioContext();
  audio.resume();
  const current = new WebSocket(`ws://${location.hostname}:${port}`);
  current.binaryType = "arraybuffer";
  current.onopen = () => current.send(JSON.stringify({ channel: Number(channel.value) }));
  current.onmessage = event => play(event.data);
  current.onclose = () => setTimeout(() => { if (socket === current) listen(port); }, 1000);
  socket = current;
}

// Each frame is the sample rate as a little-endian uint32, then int16 samples. The lead absorbs Wi-Fi jitter.
function play(frame: ArrayBuffer) {
  const rate = new DataView(frame).getUint32(0, true);
  const samples = new Int16Array(frame, 4);
  if (samples.length === 0 || !audio) return;
  const buffer = audio.createBuffer(1, samples.length, rate);
  const data = buffer.getChannelData(0);
  let high = 0;
  samples.forEach((sample, index) => {
    data[index] = sample / 32768;
    high = Math.max(high, Math.abs(data[index]));
  });
  showPeak(high);
  const source = audio.createBufferSource();
  source.buffer = buffer;
  source.connect(audio.destination);
  if (playAt < audio.currentTime || playAt > audio.currentTime + 0.5) playAt = audio.currentTime + 0.1;
  source.start(playAt);
  playAt += buffer.duration;
}

function showPeak(ratio: number) {
  peak = Math.max(peak, ratio);
  if (peakQueued) return;
  peakQueued = true;
  requestAnimationFrame(() => {
    peakQueued = false;
    const db = drawLevel(levelFill, peak, "width");
    levelText.value = peak ? `${db.toFixed(1)} dB` : "−∞";
    peak = 0;
  });
}
