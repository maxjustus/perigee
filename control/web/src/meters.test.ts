import test from "node:test";
import assert from "node:assert/strict";
import { clear, ingest, level, newSide, over, settle, toDb } from "./meters.ts";

const near = (actual: number, expected: number) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`);

test("a meter word holds a linear peak in bits 13:0 and the over flag in bit 15", () => {
  assert.equal(level(0xbfff), 1);
  assert.equal(over(0xbfff), true);
  assert.equal(level(0x3fff), 1);
  assert.equal(over(0x3fff), false);
  near(level(0x2000), 0x2000 / 0x3fff);
  near(toDb(level(0x2000)), 20 * Math.log10(0x2000 / 0x3fff));
  assert.equal(level(0), 0);
});

test("the peak takes the highest word and falls at 20 dB/s", () => {
  const side = newSide();
  ingest(side, 0x3fff, 0);
  ingest(side, 0x2000, 0);
  assert.equal(side.peak, 1);
  settle(side, 1, 1000, "Off", "Off");
  near(side.peak, 0.1);
  settle(side, 0.5, 1500, "Off", "Off");
  near(toDb(side.peak), -30);
});

test("the average reaches 63% of the power in 300 ms", () => {
  const side = newSide();
  for (let update = 0; update < 9; update++) ingest(side, 0x3fff, update * 33);
  near(side.power, 1 - Math.exp(-1));
});

test("a 2 second peak hold stays, then falls", () => {
  const side = newSide();
  ingest(side, 0x3fff, 0);
  settle(side, 1.9, 1900, "2 Seconds", "Off");
  assert.equal(side.hold, 1);
  settle(side, 1, 2900, "2 Seconds", "Off");
  near(side.hold, 0.1);
});

test("an infinite peak hold stays and an off hold follows the peak", () => {
  const held = newSide();
  const free = newSide();
  for (const side of [held, free]) ingest(side, 0x3fff, 0);
  settle(held, 10, 10000, "Infinite", "Off");
  settle(free, 1, 1000, "Off", "Off");
  assert.equal(held.hold, 1);
  near(free.hold, free.peak);
});

test("the clip latch follows the over hold", () => {
  const latch = (overHold: "Off" | "2 Seconds" | "Infinite", at: number) => {
    const side = newSide();
    ingest(side, 0xbfff, 0);
    settle(side, at / 1000, at, "Off", overHold);
    return side.clipped;
  };
  assert.equal(latch("Off", 100), true);
  assert.equal(latch("Off", 120), false);
  assert.equal(latch("2 Seconds", 1999), true);
  assert.equal(latch("2 Seconds", 2000), false);
  assert.equal(latch("Infinite", 3600000), true);
});

test("a full-scale word without the over flag does not clip", () => {
  const side = newSide();
  ingest(side, 0x3fff, 0);
  settle(side, 0, 0, "Off", "Infinite");
  assert.equal(side.clipped, false);
});

test("clear removes the clip latch and the held peak", () => {
  const side = newSide();
  ingest(side, 0xbfff, 0);
  settle(side, 1, 1000, "Infinite", "Infinite");
  clear(side);
  settle(side, 0, 1000, "Infinite", "Infinite");
  assert.equal(side.clipped, false);
  near(side.hold, 0.1);
});
