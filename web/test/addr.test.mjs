// Run with: node --test web/test/
import test from "node:test";
import assert from "node:assert/strict";
import { b58decode, b58encode, checkT, bech32mDecode, texToT1, shardOf } from "../addr.js";

const T1 = "t1gsBrGZGMyDGZw2icGnMpVBuEGVWip5kH8";
const T3 = "t3cw1VYCzDzi2hHuQmYWQWipbUFtUqt7zap";

test("base58 round-trips, including leading zero bytes", () => {
  for (const a of [T1, T3, "1111", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"]) {
    assert.equal(b58encode(b58decode(a)), a);
  }
  assert.equal(b58decode("0OIl"), null);
});

test("checkT accepts real mainnet t1/t3 addresses", async () => {
  assert.equal(await checkT(T1), true);
  assert.equal(await checkT(T3), true);
});

test("checkT rejects typos and other-network addresses", async () => {
  assert.equal(await checkT(T1.slice(0, -1) + "9"), false);
  assert.equal(await checkT("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"), false); // Bitcoin
  assert.equal(await checkT(""), false);
});

test("shard index matches the Rust shard_of vectors", () => {
  assert.equal(shardOf("t11111"), "t1_0000");
  assert.equal(shardOf("t1zz11"), "t1_3363");
  assert.equal(shardOf("t1"), null);
  assert.equal(shardOf("t10OOO"), null);
});

test("shards are shared: addresses with the same prefix collide on purpose", () => {
  assert.equal(shardOf(T1), shardOf(T1.slice(0, 4) + "x".repeat(31)));
});

test("ZIP 320 TEX address decodes to its t1 address", async () => {
  // ZIP 320 example TEX address; expected t1 independently derived with a Python reference decoder.
  const t1 = await texToT1("tex1s2rt77ggv6q989lr49rkgzmh5slsksa9khdgte");
  assert.equal(t1, "t1VmmGiyjVNeCjxDZzg7vZmd99WyzVby9yC");
  assert.equal(await checkT(t1), true);
});

test("TEX decoding rejects bad checksums and wrong prefixes", async () => {
  assert.equal(await texToT1("tex1s2rt77ggv6q989lr49rkgzmh5slsksa9khdgtf"), null);
  assert.equal(bech32mDecode("not-bech32"), null);
});
