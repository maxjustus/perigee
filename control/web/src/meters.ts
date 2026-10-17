// Each meter word holds a linear peak in bits 13:0 with full scale at 0x3FFF, and bit 15 flags an over
// (NOTES-vendor-driver.md, meter buffer). Each word is the peak of one update, so the UI adds the ballistics.
const FULL = 0x3fff;
const OVER = 0x8000;
const UPDATE = 1 / 30;
const AVERAGE = 0.3;

// The params of a meters notification: arrays of meter words by source.
export type Bank = Record<"inputs" | "outputs" | "headphones" | "playback" | "mixers", number[]>;

export const level = (word: number) => (word & FULL) / FULL;
export const over = (word: number) => (word & OVER) !== 0;
export const toDb = (amplitude: number) => 20 * Math.log10(Math.max(amplitude, 1e-6));

// The values of meters/peakHold and meters/overHold.
export type Hold = "Off" | "2 Seconds" | "Infinite";

export type Side = { peak: number; power: number; hold: number; holdAt: number; clipAt: number; clipped: boolean };

export const newSide = (): Side => ({ peak: 0, power: 0, hold: 0, holdAt: 0, clipAt: -Infinity, clipped: false });

export function ingest(side: Side, word: number, now: number) {
  const value = level(word);
  side.peak = Math.max(side.peak, value);
  side.power += (value ** 2 - side.power) * (1 - Math.exp(-UPDATE / AVERAGE));
  if (value >= side.hold) Object.assign(side, { hold: value, holdAt: now });
  if (over(word)) side.clipAt = now;
}

const clipWindow = { Off: 120, "2 Seconds": 2000, Infinite: Infinity };

// Peaks fall at 20 dB/s. A peak hold falls the same way after its hold time.
export function settle(side: Side, dt: number, now: number, peakHold: Hold, overHold: Hold) {
  const fall = 10 ** -dt;
  side.peak *= fall;
  const held = peakHold === "Infinite" || (peakHold === "2 Seconds" && now - side.holdAt < 2000);
  if (!held) side.hold = Math.max(side.peak, side.hold * fall);
  side.clipped = now - side.clipAt < clipWindow[overHold];
}

export function clear(side: Side) {
  side.clipAt = -Infinity;
  side.hold = side.peak;
}
