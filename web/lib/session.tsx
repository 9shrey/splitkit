"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type User } from "./api";

type Session = { user: User | null; setUser: (u: User | null) => void };
const SessionContext = createContext<Session>({ user: null, setUser: () => {} });
export const useSession = () => useContext(SessionContext);

export function Shell({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    api
      .me()
      .then((r) => setUser(r.user))
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (ready && !user && path !== "/login") router.replace("/login");
  }, [ready, user, path, router]);

  async function signOut() {
    await api.logout();
    setUser(null);
  }

  return (
    <SessionContext.Provider value={{ user, setUser }}>
      <header className="topbar">
        <Link href="/" className="brand">
          Splitkit
        </Link>
        {user && (
          <div className="account">
            <span>{user.name}</span>
            <button className="quiet" onClick={signOut}>
              Sign out
            </button>
          </div>
        )}
      </header>
      <main>{ready && (user || path === "/login") ? children : null}</main>
    </SessionContext.Provider>
  );
}
