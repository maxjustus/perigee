import type { Bar } from "../bar.ts";
import { clear, ingest, newSide, settle, toDb, type Bank, type Hold, type Side } from "../meters.ts";
import { FADER, clamp, minus } from "../params.ts";
import { get } from "../store.ts";

export type Meter = { bar: Bar; keys: string[]; position(amplitude: number, side: number): number; peakText?: boolean };
export type Mini = { keys: string[]; cell: HTMLElement; level: HTMLElement };

const sides = new Map<string, Side>();

function side(key: string) {
  let found = sides.get(key);
  if (!found) sides.set(key, found = newSide());
  return found;
}

export function receive(bank: Bank) {
  const now = performance.now();
  for (const name of ["inputs", "playback", "mixers"]) {
    bank[name].forEach((word, index) => ingest(side(`${name}/${index}`), word, now));
  }
}

export function meterKey(channel: number, mix: number) {
  if (channel <= 30) return `inputs/${channel - 1}`;
  if (channel <= 46) return `playback/${channel - 31}`;
  return `mixers/${2 * (mix - 1) + channel - 47}`;
}

export const dbfs = (amplitude: number) => amplitude ? clamp((toDb(amplitude) + 60) / 60, 0, 1) : 0;
export const bus = (amplitude: number) => amplitude ? FADER.toPos(clamp(600 + toDb(amplitude) * 10, 0, 720)) : 0;

export const clearKeys = (keys: string[]) => keys.forEach(key => clear(side(key)));
export const clearAll = () => sides.forEach(clear);
export const anyClipped = () => [...sides.values()].some(found => found.clipped);

export function settleAll(dt: number, now: number) {
  const peakHold = (get("meters/peakHold") ?? "Off") as Hold;
  const overHold = (get("meters/overHold") ?? "Off") as Hold;
  for (const found of sides.values()) settle(found, dt, now, peakHold, overHold);
}

export function paint(meter: Meter) {
  const list = meter.keys.map(side);
  const bands = list.map((found, index) => ({
    peak: meter.position(found.peak, index),
    avg: meter.position(Math.sqrt(found.power), index),
  }));
  const hold = get("meters/peakHold") === "Off" ? 0 : Math.max(...list.map((found, index) => meter.position(found.hold, index)));
  const peak = Math.max(...list.map(found => found.hold));
  const text = meter.peakText ? ` \u00b7 pk ${peak ? minus(Math.max(-60, toDb(peak)).toFixed(1)) : "\u2212\u221e"}` : "";
  meter.bar.paint(bands, hold, list.some(found => found.clipped), text);
}

export function paintMini({ keys, cell, level }: Mini) {
  const list = keys.map(side);
  level.style.height = `${dbfs(Math.max(0, ...list.map(found => found.peak))) * 100}%`;
  cell.classList.toggle("clip", list.some(found => found.clipped));
}
