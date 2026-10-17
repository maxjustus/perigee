import assert from "node:assert/strict";
import test from "node:test";
import { level, over } from "./meters.ts";
import { BALANCE, FADER, PAN, gainParam, type Param } from "./params.ts";

// A fixed seed keeps a failure reproducible.
function random(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 2 ** 32;
  };
}

const pieces = ["0", "1", "6", "9", "12", "64", "127", "720", ".", "-", "+", "\u2212", " ", "L", "R", "C", "l", "r",
                "dB", "db", "inf", "\u221e", "off", "OFF", "e", "x", "NaN", "Infinity", "\u00a0", ""];

function texts(count: number) {
  const next = random(1);
  return Array.from({ length: count }, () =>
    Array.from({ length: Math.floor(next() * 6) }, () => pieces[Math.floor(next() * pieces.length)]).join(""));
}

const params: [string, Param][] = [["fader", FADER], ["pan", PAN], ["balance", BALANCE], ["gain", gainParam(75)]];

test("parse returns null or an integer for any text", () => {
  for (const text of texts(20000)) {
    for (const [name, param] of params) {
      const value = param.parse(text);
      assert.ok(value === null || Number.isInteger(value), `${name} parsed ${JSON.stringify(text)} as ${value}`);
    }
  }
});

test("parse reads back the raw text of every value", () => {
  for (const [name, param] of params) {
    for (let value = param.min; value <= param.max; value++) {
      assert.equal(param.parse(param.raw(value)), value, `${name} ${value}`);
    }
  }
});

test("every meter word decodes to a level from 0 to 1", () => {
  for (let word = 0; word <= 0xffff; word++) {
    const value = level(word);
    assert.ok(value >= 0 && value <= 1, `word ${word}`);
    assert.equal(over(word), word >= 0x8000);
  }
});
