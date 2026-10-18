import test from "node:test";
import assert from "node:assert/strict";
import { appNames, options, pairsOf, place, replacement } from "./capture.ts";

const values = (entries: Record<string, string>) => (path: string) => entries[path];

test("a mix is on each computer input pair that carries its source", () => {
  const get = values({ "capture/1-2": "Mixer 2", "capture/5-6": "Mixer 3", "capture/29-30": "Mixer 2" });
  assert.deepEqual(pairsOf(2, get), ["1-2", "29-30"]);
  assert.deepEqual(pairsOf(4, get), []);
});

test("a place moves the mix and gives each other pair back its own input", () => {
  const get = values({ "capture/1-2": "Mixer 2", "capture/13-14": "Mixer 2" });
  assert.deepEqual(place(2, "3-4", get),
                   { "capture/3-4": "Mixer 2", "capture/1-2": "Analog 1-2", "capture/13-14": "S/PDIF Coax" });
  assert.deepEqual(place(4, null, values({ "capture/29-30": "FX Send" })), { "capture/29-30": "Optical 15-16" });
});

test("a channel names the source that took its place on the computer", () => {
  const get = values({ "capture/1-2": "Mixer 2", "capture/9-10": "Front Panel Mic", "capture/29-30": "Playback 3-4" });
  assert.equal(replacement(1, get), "Mix 2");
  assert.equal(replacement(2, get), "Mix 2");
  assert.equal(replacement(30, get), "Playback 3\u20134");
  assert.equal(replacement(9, get), null);
  assert.equal(replacement(3, get), null);
  assert.equal(replacement(31, get), null);
});

test("each option names the source that the mix replaces", () => {
  const get = values({ "capture/1-2": "Mixer 2", "capture/3-4": "Mixer 3", "capture/5-6": "Playback 1-2" });
  const [off, first, second, third] = options(2, get);
  assert.deepEqual(off, { value: "", text: "Off" });
  assert.deepEqual(first, { value: "1-2", text: "Channels 1\u20132" });
  assert.deepEqual(second, { value: "3-4", text: "Channels 3\u20134 \u00b7 replaces Mix 3" });
  assert.deepEqual(third, { value: "5-6", text: "Channels 5\u20136 \u00b7 replaces Playback 1\u20132" });
  assert.equal(options(1, get)[0].text, "Channels 31\u201332 only");
  assert.equal(options(4, get)[0].text, "Channels 33\u201334 only");
});

test("apps keep the default channel names", () => {
  assert.equal(appNames("3-4", ["Analog 1", "Analog 2", "Analog 3", "Analog 4"]), "\u201cAnalog 3\u201d and \u201cAnalog 4\u201d");
  assert.equal(appNames("3-4", []), null);
});
