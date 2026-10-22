import type { ApiResult } from "./client";
import type { Schemas } from "./screening-runs";

export type Operation = "create" | "get";

const PERMISSION: Record<Operation, string> = {
  create: "screening_run:create",
  get: "screening_run:read",
};

// User-facing message for a failed screening-run call (FE-4.2).
export function errorMessage(result: Extract<ApiResult<unknown>, { ok: false }>, op: Operation): string {
  const { status, correlationId } = result;
  if (status === 401) return "No signed-in user. Pick a dev principal.";
  if (status === 403) return `You do not have permission (${PERMISSION[op]}).`;
  if (op === "get" && (status === 404 || status === 422)) return "Run not found, or you cannot see it.";
  if (op === "create" && status === 404) return "Screening runs are not enabled on the backend.";
  if (op === "create" && status === 422) {
    const detail = (result.error as Schemas["HTTPValidationError"] | null)?.detail;
    const msgs = Array.isArray(detail) ? detail.map((d) => d.msg).filter(Boolean) : [];
    return msgs.length > 0 ? msgs.join(" ") : "The request was not valid.";
  }
  if (status === 0 || status >= 500) {
    return `Backend unavailable. Try again.${correlationId ? ` (Correlation ID: ${correlationId})` : ""}`;
  }
  return `Request failed (HTTP ${status}).${correlationId ? ` (Correlation ID: ${correlationId})` : ""}`;
}

export type BriefCallOperation = "get_brief" | "approve";

// User-facing message for a failed role-brief call (FE-7.2).
export function roleBriefErrorMessage(
  result: Extract<ApiResult<unknown>, { ok: false }>,
  op: BriefCallOperation,
): string {
  const { status } = result;
  if (op === "approve" && status === 403) return "You do not have permission to approve (role_brief:approve).";
  if (op === "approve" && status === 409) return "This brief can no longer be approved. Refresh.";
  if (op === "get_brief" && status === 404) return "No role brief yet.";
  return errorMessage(result, "get");
}

const COMPLETION_REASON_LABELS: Record<Schemas["CompletionReason"], string> = {
  requisition_not_found: "Requisition not found in the HR System",
  requisition_not_eligible_status: "Requisition is not in an eligible status",
  requisition_incomplete: "Requisition is missing required fields",
  hr_system_unavailable: "HR System unavailable",
  hr_response_invalid: "HR System returned an invalid response",
  ingestion_interrupted: "Requisition ingestion was interrupted",
  role_brief_ai_unavailable: "The AI service was unavailable. Start a new run to try again.",
  role_brief_output_invalid: "The AI output failed validation; no brief was stored.",
};

// Unknown (future) codes are shown raw.
export function completionReasonLabel(code: string): string {
  return (COMPLETION_REASON_LABELS as Record<string, string>)[code] ?? code;
}
