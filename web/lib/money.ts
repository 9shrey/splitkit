/** Rupee strings <-> integer paise. Parsing is done on the digits, never through floats:
 *  parseFloat("19.99") * 100 is 1998.9999999999998. */

export function parseRupees(input: string): number | null {
  const s = input.trim().replace(/,/g, "").replace(/^₹/, "");
  const m = /^(\d{1,9})(?:\.(\d{1,2}))?$/.exec(s);
  if (!m) return null;
  const paise = Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
  return paise > 0 ? paise : null;
}

/** Preview of the server's split (app/money.py), so the form can show each share as you type.
 *  The server recomputes it; this copy only has to match for the preview to be honest. */
export function previewEqual(total: number, userIds: number[]): Map<number, number> {
  const ids = [...new Set(userIds)].sort((a, b) => a - b);
  const out = new Map<number, number>();
  if (!ids.length || total <= 0) return out;
  const base = Math.floor(total / ids.length);
  const extra = total % ids.length;
  ids.forEach((id, i) => out.set(id, base + (i < extra ? 1 : 0)));
  return out;
}

export function previewShares(total: number, shares: Map<number, number>): Map<number, number> {
  const entries = [...shares].filter(([, s]) => s > 0);
  const out = new Map<number, number>();
  const weight = entries.reduce((sum, [, s]) => sum + s, 0);
  if (!entries.length || total <= 0) return out;
  for (const [id, s] of entries) out.set(id, Math.floor((total * s) / weight));
  let leftover = total - [...out.values()].reduce((a, b) => a + b, 0);
  const byLoss = entries
    .map(([id, s]) => ({ id, loss: (total * s) % weight }))
    .sort((a, b) => b.loss - a.loss || a.id - b.id);
  for (const { id } of byLoss) {
    if (leftover-- <= 0) break;
    out.set(id, out.get(id)! + 1);
  }
  return out;
}

export function formatRupees(paise: number, opts: { sign?: boolean } = {}): string {
  const abs = Math.abs(paise);
  const whole = Math.floor(abs / 100).toLocaleString("en-IN");
  const frac = abs % 100;
  const body = `₹${whole}${frac ? `.${String(frac).padStart(2, "0")}` : ""}`;
  if (paise < 0) return `−${body}`;
  return opts.sign && paise > 0 ? `+${body}` : body;
}
