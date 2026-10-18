import test from "node:test";
import assert from "node:assert/strict";
import { mixName, mixSource } from "./names.ts";

test("the UI calls the four mixes Mix 1 to Mix 4", () => {
  assert.equal(mixName("Mixer 1"), "Mix 1");
  assert.equal(mixName("FX Send"), "Mix 4 \u00b7 FX Send");
  assert.equal(mixName("Playback 1-2"), "Playback 1-2");
  assert.equal(mixSource(4), "FX Send");
});
