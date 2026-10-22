import type { InputHTMLAttributes } from "react";

export function TextField({
  id,
  label,
  error,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { id: string; label: string; error?: string }) {
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        className="rounded-md border border-border bg-surface px-3 py-2 text-base"
        {...props}
      />
      {error ? (
        <p id={errorId} className="text-sm text-error-fg">
          {error}
        </p>
      ) : null}
    </div>
  );
}
