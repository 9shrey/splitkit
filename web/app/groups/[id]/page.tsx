"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError, type Group, type Member, type Split } from "@/lib/api";
import { formatRupees, parseRupees, previewEqual, previewShares } from "@/lib/money";
import { useSession } from "@/lib/session";

type Method = Split["method"];

export default function GroupPage() {
  const id = Number(useParams<{ id: string }>().id);
  const { user } = useSession();
  const [group, setGroup] = useState<Group | null>(null);
  const [missing, setMissing] = useState(false);

  const load = useCallback(() => {
    api.group(id).then(setGroup, (err) => {
      if (err instanceof ApiError && err.status === 404) setMissing(true);
    });
  }, [id]);
  useEffect(load, [load]);

  if (missing)
    return (
      <p className="muted">
        This group doesn&apos;t exist or you&apos;re not in it. <Link href="/">Back to your groups</Link>
      </p>
    );
  if (!group || !user) return null;

  const names = new Map(group.members.map((m) => [m.id, m.id === user.id ? "You" : m.name]));
  const name = (uid: number) => names.get(uid) ?? "Someone";

  return (
    <div className="group-page">
      <header className="group-head">
        <Link href="/" className="muted">
          Your groups
        </Link>
        <h1>{group.name}</h1>
        <AddMember groupId={group.id} onDone={setGroup} />
      </header>

      <div className="group-grid">
        <section className="card">
          <h2>Balances</h2>
          <BalanceChart members={group.members} me={user.id} />
          <h2 className="space-top">Settle up</h2>
          {group.settleUp.length === 0 ? (
            <p className="muted">Everyone is even.</p>
          ) : (
            <>
              <p className="hint">
                {group.settleUp.length} {group.settleUp.length === 1 ? "payment clears" : "payments clear"} every
                balance.
              </p>
              <ul className="transfers">
                {group.settleUp.map((t) => (
                  <li key={`${t.fromUser}-${t.toUser}`}>
                    <span>
                      <strong>{name(t.fromUser)}</strong> {t.fromUser === user.id ? "pay" : "pays"}{" "}
                      <strong>{name(t.toUser)}</strong>
                    </span>
                    <span className="amount">{formatRupees(t.amount)}</span>
                    <button
                      className="small"
                      onClick={async () =>
                        setGroup(
                          await api.recordPayment(group.id, {
                            fromUser: t.fromUser,
                            toUser: t.toUser,
                            amountPaise: t.amount,
                          }),
                        )
                      }
                    >
                      Mark paid
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <section>
          {/* Remount when membership changes so a new member starts included in the split. */}
          <AddExpense key={group.members.map((m) => m.id).join()} group={group} me={user.id} onDone={setGroup} />
          <h2 className="space-top">Activity</h2>
          {group.activity.length === 0 ? (
            <p className="muted">Nothing yet. Add the first expense.</p>
          ) : (
            <ul className="activity">
              {group.activity.map((a) =>
                a.kind === "expense" ? (
                  <li key={`e${a.id}`}>
                    <div>
                      <strong>{a.description}</strong>
                      <span className="muted">
                        {name(a.paidBy)} paid {formatRupees(a.amountPaise)}
                        {a.splitMethod !== "equal" && ` (split by ${a.splitMethod})`}
                      </span>
                    </div>
                    <YourShare expense={a} me={user.id} />
                    <button
                      className="quiet small"
                      aria-label={`Delete ${a.description}`}
                      onClick={async () => setGroup(await api.deleteExpense(group.id, a.id))}
                    >
                      Delete
                    </button>
                  </li>
                ) : (
                  <li key={`p${a.id}`} className="payment">
                    <div>
                      <strong>
                        {name(a.fromUser)} paid {name(a.toUser)}
                      </strong>
                      <span className="muted">Settled up</span>
                    </div>
                    <span className="amount">{formatRupees(a.amountPaise)}</span>
                  </li>
                ),
              )}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

/** One row per person, bars growing left (owes) or right (gets back) from a shared zero line. */
function BalanceChart({ members, me }: { members: Member[]; me: number }) {
  const max = Math.max(1, ...members.map((m) => Math.abs(m.balance)));
  const sorted = [...members].sort((a, b) => b.balance - a.balance);
  return (
    <ul className="chart" aria-label="Who owes and who gets back">
      {sorted.map((m) => {
        const pct = (Math.abs(m.balance) / max) * 100;
        const side = m.balance > 0 ? "gets" : m.balance < 0 ? "owes" : "even";
        return (
          <li key={m.id} className={side}>
            <span className="who">{m.id === me ? "You" : m.name}</span>
            <span className="track">
              <span className="half left">{side === "owes" && <span className="bar" style={{ width: `${pct}%` }} />}</span>
              <span className="half right">
                {side === "gets" && <span className="bar" style={{ width: `${pct}%` }} />}
              </span>
            </span>
            <span className="figure">
              {side === "even" ? "even" : `${side === "gets" ? "gets back" : "owes"} ${formatRupees(Math.abs(m.balance))}`}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function YourShare({ expense, me }: { expense: Extract<Group["activity"][number], { kind: "expense" }>; me: number }) {
  const mine = expense.shares.find((s) => s.userId === me)?.owedPaise ?? 0;
  const lent = expense.paidBy === me ? expense.amountPaise - mine : 0;
  if (lent > 0) return <span className="amount gets">you lent {formatRupees(lent)}</span>;
  if (mine > 0) return <span className="amount owes">your share {formatRupees(mine)}</span>;
  return <span className="amount muted">not involved</span>;
}

function AddMember({ groupId, onDone }: { groupId: number; onDone: (g: Group) => void }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      onDone(await api.addMember(groupId, email));
      setEmail("");
      setOpen(false);
      setError(null);
    } catch {
      setError("No Splitkit account uses that email. Ask them to sign up first.");
    }
  }

  if (!open)
    return (
      <button className="quiet" onClick={() => setOpen(true)}>
        Add someone
      </button>
    );
  return (
    <form className="inline-form" onSubmit={submit}>
      <input type="email" required autoFocus placeholder="their@email.com" value={email} onChange={(e) => setEmail(e.target.value)} />
      <button className="small">Add</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

function AddExpense({ group, me, onDone }: { group: Group; me: number; onDone: (g: Group) => void }) {
  const ids = group.members.map((m) => m.id);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [paidBy, setPaidBy] = useState(me);
  const [method, setMethod] = useState<Method>("equal");
  const [included, setIncluded] = useState<Set<number>>(() => new Set(ids));
  const [shares, setShares] = useState<Map<number, number>>(() => new Map(ids.map((i) => [i, 1])));
  const [exact, setExact] = useState<Map<number, string>>(() => new Map());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // One id per expense being entered. If the request is retried (double click, flaky network),
  // the server sees the same id and records the expense once.
  const requestId = useRef(crypto.randomUUID());

  const total = parseRupees(amount);
  const exactPaise = new Map(ids.map((i) => [i, parseRupees(exact.get(i) ?? "") ?? 0]));
  const exactSum = [...exactPaise.values()].reduce((a, b) => a + b, 0);
  const preview = !total
    ? new Map<number, number>()
    : method === "equal"
      ? previewEqual(total, [...included])
      : method === "shares"
        ? previewShares(total, shares)
        : exactPaise;

  function split(): Split {
    if (method === "equal") return { method, userIds: [...included] };
    if (method === "shares") return { method, shares: Object.fromEntries([...shares].filter(([, s]) => s > 0)) };
    return { method, amounts: Object.fromEntries([...exactPaise].filter(([, a]) => a > 0)) };
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!total) return setError("Enter an amount like 450 or 450.50.");
    if (method === "exact" && exactSum !== total)
      return setError(`The amounts add up to ${formatRupees(exactSum)}, not ${formatRupees(total)}.`);
    setBusy(true);
    setError(null);
    try {
      onDone(
        await api.addExpense(group.id, {
          description,
          amountPaise: total,
          paidBy,
          split: split(),
          clientRequestId: requestId.current,
        }),
      );
      requestId.current = crypto.randomUUID();
      setDescription("");
      setAmount("");
      setExact(new Map());
    } catch (err) {
      setError(err instanceof ApiError && err.code === "invalid_split" ? "That split doesn't work. Check the numbers." : "Couldn't add the expense. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card add-expense" onSubmit={submit}>
      <h2>Add an expense</h2>
      <div className="row-2">
        <label>
          What for
          <input required maxLength={120} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Dinner at Thalassa" />
        </label>
        <label>
          Amount (₹)
          <input required inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="2400" />
        </label>
      </div>
      <label>
        Paid by
        <select value={paidBy} onChange={(e) => setPaidBy(Number(e.target.value))}>
          {group.members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.id === me ? "You" : m.name}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="methods">
        <legend>Split</legend>
        {(["equal", "shares", "exact"] as const).map((m) => (
          <label key={m} className={method === m ? "on" : ""}>
            <input type="radio" name="method" checked={method === m} onChange={() => setMethod(m)} />
            {m === "equal" ? "Equally" : m === "shares" ? "By shares" : "Exact amounts"}
          </label>
        ))}
      </fieldset>

      <ul className="split-rows">
        {group.members.map((m) => (
          <li key={m.id}>
            {method === "equal" ? (
              <label className="check">
                <input
                  type="checkbox"
                  checked={included.has(m.id)}
                  onChange={(e) => {
                    const next = new Set(included);
                    if (e.target.checked) next.add(m.id);
                    else next.delete(m.id);
                    setIncluded(next);
                  }}
                />
                {m.id === me ? "You" : m.name}
              </label>
            ) : (
              <span>{m.id === me ? "You" : m.name}</span>
            )}
            {method === "shares" && (
              <input
                className="narrow"
                type="number"
                min={0}
                max={1000}
                aria-label={`Shares for ${m.name}`}
                value={shares.get(m.id) ?? 0}
                onChange={(e) => setShares(new Map(shares).set(m.id, Math.max(0, Math.floor(Number(e.target.value)) || 0)))}
              />
            )}
            {method === "exact" && (
              <input
                className="narrow"
                inputMode="decimal"
                aria-label={`Amount for ${m.name}`}
                placeholder="0"
                value={exact.get(m.id) ?? ""}
                onChange={(e) => setExact(new Map(exact).set(m.id, e.target.value))}
              />
            )}
            <span className="amount">{preview.get(m.id) ? formatRupees(preview.get(m.id)!) : "–"}</span>
          </li>
        ))}
      </ul>
      {method === "exact" && total ? (
        <p className={exactSum === total ? "hint" : "hint warn"}>
          {exactSum === total
            ? "Adds up."
            : exactSum < total
              ? `${formatRupees(total - exactSum)} left to assign`
              : `${formatRupees(exactSum - total)} too much`}
        </p>
      ) : null}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button className="primary" disabled={busy}>
        Add expense
      </button>
    </form>
  );
}
