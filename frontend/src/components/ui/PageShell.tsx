import type { ReactNode } from "react";
import { DevPrincipalPicker } from "@/dev-auth/DevPrincipalPicker";
import { isDevAuthEnabled } from "@/dev-auth/config";

export function PageShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-h-full">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-6 py-4">
          <h1 className="text-xl font-semibold">{title}</h1>
          {isDevAuthEnabled() ? <DevPrincipalPicker /> : null}
        </div>
      </header>
      <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-8">{children}</main>
    </div>
  );
}
