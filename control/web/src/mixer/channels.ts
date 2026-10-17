import { get } from "../store.ts";

// Mixer channels 1-30 are the inputs in meter order, 31-46 are Playback 1-16, and 47-48 are the mix output.
// Channel 10 does not exist: the mixer takes the front mic as mono on channel 9.
const range = (first: number, last: number) => Array.from({ length: last - first + 1 }, (_, i) => first + i);
const names = [...range(1, 8).map(n => `A${n}`), "Mic", "", "Gtr 1", "Gtr 2", "S/PDIF L", "S/PDIF R",
               ...range(1, 16).map(n => `Opt ${n}`), ...range(1, 16).map(n => `Play ${n}`)];

export type Group = { id: string; title: string; channels: number[]; color: string };

export const groups: Group[] = [
  { id: "analog", title: "Analog", channels: range(1, 8), color: "#ff9f43" },
  { id: "front", title: "Mic & guitar", channels: [9, 11, 12], color: "#ff6b9a" },
  { id: "spdif", title: "S/PDIF", channels: [13, 14], color: "#f2d16b" },
  { id: "optical", title: "Optical", channels: range(15, 30), color: "#b48cf2" },
  { id: "playback", title: "Playback", channels: range(31, 46), color: "#4fd1c5" },
];
export const OUTPUT_COLOR = "#a3a8f0";
export const OUTPUTS: [number, number] = [47, 48];
export const MIXES = [1, 2, 3, 4];

export const strip = (mix: number, channel: number, control: string) => `mixers/${mix}/channels/${channel}/${control}`;
export const enabled = (channel: number) => `mixers/channels/${channel}/enabled`;
export const stereoFlag = (channel: number) => `mixers/channels/${channel}/stereo`;

export const pairable = (channel: number) => channel <= 46 && channel !== 9;
const isStereo = (channel: number) => pairable(channel) && get(stereoFlag(channel - 1 + channel % 2)) === true;

// A unit is one row: a mono channel, or a stereo pair with its first channel first.
export type Unit = [number] | [number, number];

export function units(group: Group) {
  const list: Unit[] = [];
  for (const channel of group.channels) {
    if (list.some(unit => unit.includes(channel))) continue;
    list.push(isStereo(channel) && channel % 2 ? [channel, channel + 1] : [channel]);
  }
  return list;
}

export const channelName = (channel: number) => names[channel - 1] ?? `Channel ${channel}`;

export function unitName([left, right]: Unit) {
  if (!right) return channelName(left);
  const [a, b] = [channelName(left), channelName(right)];
  if (a.endsWith(" L") && b.endsWith(" R")) return a.slice(0, -2);
  return `${a}\u2013${b.match(/\d+$/)![0]}`;
}

export function inputPath(channel: number) {
  if (channel <= 8) return `inputs/analog/${channel}`;
  if (channel === 9) return "inputs/frontMic";
  return channel === 11 || channel === 12 ? `inputs/guitar/${channel - 10}` : null;
}

export function linkPath(channel: number) {
  if (channel <= 8) return `inputs/analog/${channel - 1 + channel % 2}-${channel + channel % 2}/link`;
  return channel === 11 || channel === 12 ? "inputs/guitar/1-2/link" : null;
}

export const partner = (channel: number) => channel % 2 ? channel + 1 : channel - 1;
