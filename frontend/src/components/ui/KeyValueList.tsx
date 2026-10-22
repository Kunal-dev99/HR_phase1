import type { ReactNode } from "react";

export type KeyValueItem = { key: string; value: ReactNode };

export function KeyValueList({ items }: { items: KeyValueItem[] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
      {items.map((item) => (
        <div key={item.key} className="contents">
          <dt className="font-medium text-muted">{item.key}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
