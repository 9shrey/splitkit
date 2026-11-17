"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type GroupSummary } from "@/lib/api";
import { formatRupees } from "@/lib/money";

function balanceLine(paise: number) {
  if (paise > 0) return <span className="gets">you get back {formatRupees(paise)}</span>;
  if (paise < 0) return <span className="owes">you owe {formatRupees(-paise)}</span>;
  return <span className="muted">settled up</span>;
}

export default function GroupsPage() {
  const router = useRouter();
  const [groups, setGroups] = useState<GroupSummary[] | null>(null);
  const [name, setName] = useState("");
  const [emails, setEmails] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.groups().then(setGroups);
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const list = emails
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const g = await api.createGroup(name, list);
      router.push(`/groups/${g.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "users_not_found") {
        const missing = (err.details as { emails: string[] }).emails.join(", ");
        setError(`No account for ${missing}. Ask them to sign up first, then add them.`);
      } else {
        setError("Couldn't create the group. Check the emails and try again.");
      }
    }
  }

  if (!groups) return null;
  const total = groups.reduce((sum, g) => sum + g.myBalance, 0);

  return (
    <div className="groups-page">
      <section>
        <h1>Your groups</h1>
        {groups.length > 0 && <p className="overall">Overall, {balanceLine(total)}.</p>}
        {groups.length === 0 ? (
          <p className="muted">No groups yet. Make one for a trip, a flat or a dinner.</p>
        ) : (
          <ul className="group-list">
            {groups.map((g) => (
              <li key={g.id}>
                <Link href={`/groups/${g.id}`}>
                  <strong>{g.name}</strong>
                  <span className="muted">{g.memberCount} people</span>
                  {balanceLine(g.myBalance)}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <form className="card new-group" onSubmit={create}>
        <h2>New group</h2>
        <label>
          Name
          <input required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="Goa, March" />
        </label>
        <label>
          Add people by email
          <textarea
            rows={3}
            value={emails}
            onChange={(e) => setEmails(e.target.value)}
            placeholder="ravi@example.com, meera@example.com"
          />
          <span className="hint">They need a Splitkit account. You can add more people later.</span>
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="primary">Create group</button>
      </form>
    </div>
  );
}
