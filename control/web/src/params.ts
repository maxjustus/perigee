export type Param = {
  min: number;
  max: number;
  home: number;
  step: number;
  fine: number;
  bipolar?: boolean;
  toPos(value: number): number;
  fromPos(position: number): number;
  format(value: number): string;
  raw(value: number): string;
  parse(text: string): number | null;
};

export const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));
export const minus = (text: string) => text.replace(/-/g, "\u2212");
const ascii = (text: string) => text.trim().replace(/\u2212/g, "-");

// Fader values are tenths of a dB: 600 is 0 dB, 720 is +12 dB, and 0 closes the channel.
export const FADER: Param = {
  min: 0, max: 720, home: 600, step: 10, fine: 1,
  toPos: value => value / 720,
  fromPos: position => clamp(position, 0, 1) * 720,
  format: value => value === 0 ? "\u2212\u221e" : minus(`${value > 600 ? "+" : ""}${((value - 600) / 10).toFixed(1)}`),
  raw: value => value === 0 ? "-inf" : ((value - 600) / 10).toFixed(1),
  parse: text => {
    const clean = ascii(text).replace(/\s*db$/i, "");
    if (/^-?(inf|\u221e)$/i.test(clean)) return 0;
    const number = Number(clean);
    return clean && Number.isFinite(number) ? Math.round(600 + number * 10) : null;
  },
};

const formatPan = (value: number) => value === 64 ? "C" : value < 64 ? `L${64 - value}` : `R${value - 64}`;

export const PAN: Param = {
  min: 0, max: 127, home: 64, step: 1, fine: 1, bipolar: true,
  toPos: value => value / 127,
  fromPos: position => clamp(position, 0, 1) * 127,
  format: formatPan,
  raw: formatPan,
  parse: text => {
    const match = ascii(text).toUpperCase().match(/^(?:C|([LR])\s*(\d+)|([-+]?\d+))$/);
    if (!match) return null;
    if (match[1]) return 64 + (match[1] === "L" ? -1 : 1) * Number(match[2]);
    return match[3] ? 64 + Number(match[3]) : 64;
  },
};

// In a stereo pair, the first channel's pan is the balance of the pair and the second channel's pan does nothing.
// The balance cuts the far side by these amounts, in dB, at each distance from center, as measured on the unit.
type Points = [[number, number], ...[number, number][]];

const BALANCE_CUT: Points = [[0, 0], [16, -1.1], [32, -3.1], [48, -8.3], [63, -32.2]];
const invert = ([distance, cut]: [number, number]): [number, number] => [-cut, distance];
const BALANCE_DISTANCE: Points = [invert(BALANCE_CUT[0]), ...BALANCE_CUT.slice(1).map(invert)];

function interpolate(x: number, [first, ...rest]: Points) {
  let [x0, y0] = first;
  for (const [x1, y1] of rest) {
    if (x <= x1) return y0 + (y1 - y0) * (x - x0) / (x1 - x0);
    [x0, y0] = [x1, y1];
  }
  return y0;
}

export const balanceCut = (distance: number) => distance >= 64 ? -Infinity : interpolate(distance, BALANCE_CUT);

// Side 0 is the first channel of the pair, the left side.
export const balanceDb = (pan: number, side: number) =>
  side === 0 ? (pan > 64 ? balanceCut(pan - 64) : 0) : (pan < 64 ? balanceCut(64 - pan) : 0);

const cutText = (distance: number) => distance >= 64 ? "off" : `${minus(balanceCut(distance).toFixed(1))} dB`;

export const BALANCE: Param = {
  ...PAN,
  format: value => value === 64 ? "C" : value < 64 ? `R ${cutText(64 - value)}` : `L ${cutText(value - 64)}`,
  // "L32" is a position. "R-3", "R 3 dB" and "R off" cut the right side by that much.
  parse: text => {
    const cut = ascii(text).toUpperCase().replace(/\s+/g, "").match(/^([LR])(OFF|-\d+(?:\.\d+)?(?:DB)?|\d+(?:\.\d+)?DB)$/);
    const [, side, amount] = cut ?? [];
    if (side === undefined || amount === undefined) return PAN.parse(text);
    const distance = amount === "OFF" ? 64 : Math.round(interpolate(Math.abs(parseFloat(amount)), BALANCE_DISTANCE));
    return side === "R" ? 64 - distance : 64 + distance;
  },
};

export function gainParam(max: number): Param {
  return {
    min: 0, max, home: 0, step: 1, fine: 1,
    toPos: value => value / max,
    fromPos: position => clamp(position, 0, 1) * max,
    format: value => `${value} dB`,
    raw: value => `${value}`,
    parse: text => {
      const clean = ascii(text).replace(/\s*db$/i, "");
      const number = Number(clean);
      return clean && Number.isFinite(number) ? Math.round(number) : null;
    },
  };
}
