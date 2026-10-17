import { level, type Bank } from "../meters.ts";

const range = (count: number, name: (n: number) => string) => Array.from({ length: count }, (_, i) => name(i + 1));
const inputs = [...range(8, n => `A${n}`), "MicL", "MicR", "G1", "G2", "SPL", "SPR", ...range(16, n => `O${n}`)];
const banks: Record<keyof Bank, [string, string[]]> = {
  inputs: ["Inputs", inputs],
  outputs: ["Outputs", [...range(10, n => `L${n}`), "G1", "G2", "SPL", "SPR", ...range(16, n => `O${n}`)]],
  headphones: ["Headphones", ["1L", "1R", "2L", "2R"]],
  playback: ["Playback", range(16, n => `${n}`)],
  mixers: ["Mixers", [1, 2, 3, 4].flatMap(n => [`${n}L`, `${n}R`])],
};
const levels: { key: keyof Bank; index: number; fill: HTMLElement }[] = [];

export function layout() {
  for (const key of Object.keys(banks) as (keyof Bank)[]) {
    const [heading, names] = banks[key];
    const section = document.createElement("section");
    const bank = Object.assign(document.createElement("div"), { className: names.length > 16 ? "bank wide" : "bank" });
    bank.style.setProperty("--count", String(names.length));
    names.forEach((name, index) => {
      const cell = Object.assign(document.createElement("div"), { className: "cell", title: name });
      const meter = Object.assign(document.createElement("div"), { className: "meter" });
      const fill = Object.assign(document.createElement("div"), { className: "fill" });
      meter.append(fill);
      levels.push({ key, index, fill });
      cell.append(meter, Object.assign(document.createElement("span"), { textContent: name }));
      bank.append(cell);
    });
    section.append(Object.assign(document.createElement("h2"), { textContent: heading }), bank);
    document.getElementById("meters")!.append(section);
  }
}

export function show(meters: Bank) {
  for (const { key, index, fill } of levels) drawLevel(fill, level(meters[key][index] ?? 0));
}

export function drawLevel(fill: HTMLElement, ratio: number, dimension: "height" | "width" = "height") {
  const db = 20 * Math.log10(Math.max(ratio, 1 / 16384));
  fill.style[dimension] = `${Math.min(100, Math.max(0, (db + 60) / 60 * 100))}%`;
  fill.className = db > -1 ? "fill clip" : db > -6 ? "fill hot" : "fill";
  return db;
}
