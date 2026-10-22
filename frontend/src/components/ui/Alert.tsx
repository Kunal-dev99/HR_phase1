import type { ReactNode } from "react";

type Variant = "info" | "success" | "warning" | "error";

const VARIANTS: Record<Variant, string> = {
  info: "bg-info-bg text-info-fg",
  success: "bg-success-bg text-success-fg",
  warning: "bg-warning-bg text-warning-fg",
  error: "bg-error-bg text-error-fg",
};

export function Alert({
  variant = "info",
  title,
  children,
}: {
  variant?: Variant;
  title?: string;
  children: ReactNode;
}) {
  const role = variant === "error" || variant === "warning" ? "alert" : "status";
  return (
    <div role={role} className={`rounded-md p-4 text-sm ${VARIANTS[variant]}`}>
      {title ? <p className="mb-1 font-semibold">{title}</p> : null}
      <div>{children}</div>
    </div>
  );
}
