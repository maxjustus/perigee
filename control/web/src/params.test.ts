import test from "node:test";
import assert from "node:assert/strict";
import { BALANCE, FADER, PAN, balanceCut, balanceDb, gainParam } from "./params.ts";

test("fader formats tenths of a dB with 600 at 0 dB", () => {
  assert.equal(FADER.format(600), "0.0");
  assert.equal(FADER.format(720), "+12.0");
  assert.equal(FADER.format(540), "\u22126.0");
  assert.equal(FADER.format(0), "\u2212\u221e");
});

test("fader parses typed values", () => {
  assert.equal(FADER.parse("-6"), 540);
  assert.equal(FADER.parse("+3.5"), 635);
  assert.equal(FADER.parse("\u22126 dB"), 540);
  assert.equal(FADER.parse("-inf"), 0);
  assert.equal(FADER.parse("\u2212\u221e"), 0);
  assert.equal(FADER.parse(""), null);
  assert.equal(FADER.parse("loud"), null);
});

test("fader raw text parses back to the same value", () => {
  for (const value of [0, 1, 255, 599, 600, 601, 720]) assert.equal(FADER.parse(FADER.raw(value)), value);
});

test("fader position is linear to +12 dB", () => {
  assert.equal(FADER.toPos(720), 1);
  assert.equal(FADER.toPos(360), 0.5);
  assert.equal(FADER.fromPos(0.5), 360);
  assert.equal(FADER.fromPos(2), 720);
});

test("pan formats and parses positions", () => {
  assert.equal(PAN.format(64), "C");
  assert.equal(PAN.format(44), "L20");
  assert.equal(PAN.format(69), "R5");
  assert.equal(PAN.parse("c"), 64);
  assert.equal(PAN.parse("L20"), 44);
  assert.equal(PAN.parse("r 5"), 69);
  assert.equal(PAN.parse("-10"), 54);
  assert.equal(PAN.parse("X"), null);
  for (let value = 0; value <= 127; value++) assert.equal(PAN.parse(PAN.raw(value)), value);
});

test("balance cut follows the measured points", () => {
  const points = [[0, 0], [16, -1.1], [32, -3.1], [48, -8.3], [63, -32.2], [64, -Infinity]];
  for (const [distance, cut] of points) assert.equal(balanceCut(distance), cut);
  assert.ok(Math.abs(balanceCut(24) - -2.1) < 1e-9);
});

test("balance cuts the far side of the pair", () => {
  assert.equal(balanceDb(64, 0), 0);
  assert.equal(balanceDb(32, 0), 0);
  assert.equal(balanceDb(32, 1), -3.1);
  assert.equal(balanceDb(80, 0), -1.1);
  assert.equal(balanceDb(80, 1), 0);
  assert.equal(balanceDb(0, 1), -Infinity);
});

test("balance formats the cut side", () => {
  assert.equal(BALANCE.format(64), "C");
  assert.equal(BALANCE.format(32), "R \u22123.1 dB");
  assert.equal(BALANCE.format(80), "L \u22121.1 dB");
  assert.equal(BALANCE.format(0), "R off");
});

test("balance parses positions and cuts", () => {
  assert.equal(BALANCE.parse("C"), 64);
  assert.equal(BALANCE.parse("L32"), 32);
  assert.equal(BALANCE.parse("R5"), 69);
  assert.equal(BALANCE.parse("R-3.1"), 32);
  assert.equal(BALANCE.parse("R 3.1 dB"), 32);
  assert.equal(BALANCE.parse("l \u22121.1db"), 80);
  assert.equal(BALANCE.parse("R off"), 0);
  assert.equal(BALANCE.parse("R"), null);
});

test("balance text at the measured points parses back to the same value", () => {
  for (const value of [0, 1, 16, 32, 48, 64, 80, 96, 112, 127]) {
    assert.equal(BALANCE.parse(BALANCE.format(value)), value);
  }
});

test("gain formats and parses whole dB", () => {
  const gain = gainParam(75);
  assert.equal(gain.format(34), "34 dB");
  assert.equal(gain.parse("34 dB"), 34);
  assert.equal(gain.parse("12.4"), 12);
  assert.equal(gain.parse(""), null);
  assert.equal(gain.toPos(75), 1);
});
