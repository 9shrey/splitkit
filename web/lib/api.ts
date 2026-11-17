export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public details?: Record<string, unknown> | { field: string; message: string }[],
  ) {
    super(code);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.error ?? "request_failed", data.details);
  return data as T;
}

export type User = { id: number; email: string; name: string };
export type GroupSummary = { id: number; name: string; memberCount: number; myBalance: number };
export type Member = { id: number; name: string; email: string; balance: number };
export type Transfer = { fromUser: number; toUser: number; amount: number };
export type ExpenseItem = {
  kind: "expense";
  id: number;
  description: string;
  amountPaise: number;
  paidBy: number;
  splitMethod: "equal" | "shares" | "exact";
  shares: { userId: number; owedPaise: number }[];
  createdAt: string;
};
export type PaymentItem = {
  kind: "payment";
  id: number;
  fromUser: number;
  toUser: number;
  amountPaise: number;
  createdAt: string;
};
export type Group = {
  id: number;
  name: string;
  members: Member[];
  settleUp: Transfer[];
  activity: (ExpenseItem | PaymentItem)[];
};
export type Split =
  | { method: "equal"; userIds: number[] }
  | { method: "shares"; shares: Record<number, number> }
  | { method: "exact"; amounts: Record<number, number> };

export const api = {
  me: () => call<{ user: User | null }>("GET", "/auth/me"),
  signup: (email: string, name: string, password: string) =>
    call<{ user: User }>("POST", "/auth/signup", { email, name, password }),
  login: (email: string, password: string) => call<{ user: User }>("POST", "/auth/login", { email, password }),
  logout: () => call<void>("POST", "/auth/logout"),
  groups: () => call<GroupSummary[]>("GET", "/groups"),
  createGroup: (name: string, memberEmails: string[]) => call<Group>("POST", "/groups", { name, memberEmails }),
  group: (id: number) => call<Group>("GET", `/groups/${id}`),
  addMember: (id: number, email: string) => call<Group>("POST", `/groups/${id}/members`, { email }),
  addExpense: (
    id: number,
    body: { description: string; amountPaise: number; paidBy: number; split: Split; clientRequestId: string },
  ) => call<Group>("POST", `/groups/${id}/expenses`, body),
  deleteExpense: (id: number, expenseId: number) => call<Group>("DELETE", `/groups/${id}/expenses/${expenseId}`),
  recordPayment: (id: number, body: { fromUser: number; toUser: number; amountPaise: number }) =>
    call<Group>("POST", `/groups/${id}/payments`, body),
};
