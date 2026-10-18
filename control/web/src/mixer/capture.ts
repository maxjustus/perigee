import { mixName, mixSource } from "../names.ts";
import type { Value } from "../store.ts";

type Get = (path: string) => Value | undefined;

// Computer input pairs 1-2 to 29-30 carry these inputs by default. The unit always sends Mix 1 on 31-32 and Mix 4
// (FX Send) on 33-34.
const HOME = ["Analog 1-2", "Analog 3-4", "Analog 5-6", "Analog 7-8", "Front Panel Mic", "Guitar 1-2", "S/PDIF Coax",
              ...Array.from({ length: 8 }, (_, i) => `Optical ${2 * i + 1}-${2 * i + 2}`)];
const PAIRS = HOME.map((_, i) => `${2 * i + 1}-${2 * i + 2}`);
const FIXED: Record<number, string> = { 1: "31-32", 4: "33-34" };

const path = (pair: string) => `capture/${pair}`;
const dash = (text: string) => text.replace(/(\d)-(\d)/g, "$1\u2013$2");

export const pairsOf = (mix: number, get: Get) => PAIRS.filter(pair => get(path(pair)) === mixSource(mix));

// One mix goes to at most one pair here. A pair that the mix leaves gets its default input back.
export function place(mix: number, pair: string | null, get: Get) {
  const changes: Record<string, Value> = pair ? { [path(pair)]: mixSource(mix) } : {};
  for (const other of pairsOf(mix, get)) {
    if (other !== pair) changes[path(other)] = HOME[PAIRS.indexOf(other)];
  }
  return changes;
}

// Mixer channels 1-30 are the inputs in the order of the computer input channels.
export function replacement(channel: number, get: Get) {
  if (channel > 30) return null;
  const value = get(path(PAIRS[(channel - 1) >> 1]));
  return value === undefined || value === HOME[(channel - 1) >> 1] ? null : label(value);
}

export function options(mix: number, get: Get) {
  const off = FIXED[mix] ? `Channels ${dash(FIXED[mix])} only` : "Off";
  return [{ value: "", text: off }, ...PAIRS.map(pair => {
    const value = get(path(pair));
    const now = value === undefined || value === mixSource(mix) ? "" : ` \u00b7 replaces ${label(value)}`;
    return { value: pair, text: `Channels ${dash(pair)}${now}` };
  })];
}

const label = (value: Value) => dash(mixName(String(value)));

export const homeOf = (pair: string) => dash(HOME[PAIRS.indexOf(pair)]);

// CoreAudio names the computer input channels by their default inputs, so apps keep these names after a change.
export function channelName(channel: number, appName: string, get: Get) {
  const now = replacement(channel, get);
  return now ? `${appName} (now ${now})` : appName;
}

export function appNames(pair: string, captureNames: string[]) {
  const [left, right] = pair.split("-").map(channel => captureNames[Number(channel) - 1]);
  return left && right ? `\u201c${left}\u201d and \u201c${right}\u201d` : null;
}
