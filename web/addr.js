// Pure address helpers for the checker: Base58Check, ZIP 320 TEX (Bech32m) and the
// privacy shard index. No DOM access, so they are unit-tested in Node (web/test/addr.test.mjs).

export const BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

/** Shard name for a t-address; must stay identical to `shard_of` in src/report.rs. */
export function shardOf(addr) {
  const i = BASE58.indexOf(addr[2]), j = BASE58.indexOf(addr[3]);
  if (addr.length < 4 || i < 0 || j < 0) return null;
  return `${addr.slice(0, 2)}_${String(i * 58 + j).padStart(4, "0")}`;
}

export function b58decode(str) {
  let n = 0n;
  for (const ch of str) {
    const i = BASE58.indexOf(ch);
    if (i < 0) return null;
    n = n * 58n + BigInt(i);
  }
  const bytes = [];
  while (n > 0n) { bytes.unshift(Number(n & 0xffn)); n >>= 8n; }
  for (const ch of str) { if (ch === "1") bytes.unshift(0); else break; }
  return new Uint8Array(bytes);
}
export function b58encode(bytes) {
  let n = 0n;
  for (const b of bytes) n = n * 256n + BigInt(b);
  let out = "";
  while (n > 0n) { out = BASE58[Number(n % 58n)] + out; n /= 58n; }
  for (const b of bytes) { if (b === 0) out = "1" + out; else break; }
  return out;
}
export async function sha256d(bytes) {
  const a = await crypto.subtle.digest("SHA-256", bytes);
  return new Uint8Array(await crypto.subtle.digest("SHA-256", a));
}
export async function checkT(addr) {
  const raw = b58decode(addr);
  if (!raw || raw.length !== 26) return false;
  const sum = await sha256d(raw.slice(0, 22));
  return sum.slice(0, 4).every((b, i) => b === raw[22 + i]) && raw[0] === 0x1c && (raw[1] === 0xb8 || raw[1] === 0xbd);
}
export function bech32mDecode(str) {
  const CH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
  const lower = str.toLowerCase();
  const pos = lower.lastIndexOf("1");
  if (pos < 1 || pos + 7 > lower.length) return null;
  const hrp = lower.slice(0, pos);
  const data = [...lower.slice(pos + 1)].map((c) => CH.indexOf(c));
  if (data.some((d) => d < 0)) return null;
  const polymod = (values) => {
    const G = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
    let chk = 1;
    for (const v of values) {
      const top = chk >>> 25;
      chk = ((chk & 0x1ffffff) << 5) ^ v;
      for (let i = 0; i < 5; i++) if ((top >>> i) & 1) chk ^= G[i];
    }
    return chk >>> 0;
  };
  const exp = [...hrp].map((c) => c.charCodeAt(0) >> 5).concat([0], [...hrp].map((c) => c.charCodeAt(0) & 31));
  if (polymod(exp.concat(data)) !== 0x2bc830a3) return null;
  const words = data.slice(0, -6);
  let acc = 0, bits = 0;
  const out = [];
  for (const w of words) { acc = (acc << 5) | w; bits += 5; while (bits >= 8) { bits -= 8; out.push((acc >> bits) & 0xff); } }
  if (bits >= 5 || ((acc << (8 - bits)) & 0xff)) return null;
  return { hrp, bytes: new Uint8Array(out) };
}
export async function texToT1(tex) {
  const d = bech32mDecode(tex);
  if (!d || d.hrp !== "tex" || d.bytes.length !== 20) return null;
  const payload = new Uint8Array(22);
  payload.set([0x1c, 0xb8]);
  payload.set(d.bytes, 2);
  const sum = await sha256d(payload);
  const full = new Uint8Array(26);
  full.set(payload);
  full.set(sum.slice(0, 4), 22);
  return b58encode(full);
}
