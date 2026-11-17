import assert from "node:assert/strict";
import { test } from "node:test";
import { formatRupees, parseRupees, previewEqual, previewShares } from "./money.ts";

test("parses rupee strings to exact paise without float error", () => {
  assert.equal(parseRupees("19.99"), 1999);
  assert.equal(parseRupees("0.1"), 10);
  assert.equal(parseRupees("₹1,250.5"), 125050);
  assert.equal(parseRupees(" 300 "), 30000);
});

test("rejects anything that is not a positive amount with at most 2 decimals", () => {
  for (const bad of ["", "0", "0.00", "-5", "1.234", "abc", "1e3", "12.", "."]) {
    assert.equal(parseRupees(bad), null, bad);
  }
});

test("previews match the server's splits (same cases as tests/test_money.py)", () => {
  assert.deepEqual(Object.fromEntries(previewEqual(10000, [3, 1, 2])), { 1: 3334, 2: 3333, 3: 3333 });
  const percent = previewShares(99999, new Map([[1, 50], [2, 30], [3, 20]]));
  assert.deepEqual(Object.fromEntries(percent), { 1: 49999, 2: 30000, 3: 20000 });
});

test("formats paise with Indian digit grouping", () => {
  assert.equal(formatRupees(12345678), "₹1,23,456.78");
  assert.equal(formatRupees(30000), "₹300");
  assert.equal(formatRupees(-505), "−₹5.05");
  assert.equal(formatRupees(100, { sign: true }), "+₹1");
});
