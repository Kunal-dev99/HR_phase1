type Tone = "neutral" | "info" | "success" | "warning" | "error";

const TONES: Record<Tone, string> = {
  neutral: "bg-background text-muted border border-border",
  info: "bg-info-bg text-info-fg",
  success: "bg-success-bg text-success-fg",
  warning: "bg-warning-bg text-warning-fg",
  error: "bg-error-bg text-error-fg",
};

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  return (
    <span className={`inline-flex rounded-sm px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {label}
    </span>
  );
}
