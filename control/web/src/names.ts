// The service gives the mixes their vendor names. The UI calls them Mix 1 to Mix 4. Apps name the computer inputs of
// Mix 4 "FX Send", so its name keeps that word.
const MIXES = ["Mixer 1", "Mixer 2", "Mixer 3", "FX Send"];

export const mixSource = (mix: number) => MIXES[mix - 1];
export const mixName = (source: string) => source === "FX Send" ? "Mix 4 \u00b7 FX Send"
  : MIXES.includes(source) ? `Mix ${MIXES.indexOf(source) + 1}` : source;
