import { apiFetch, type ApiResult } from "./client";
import type { components } from "./schema";

// All request/response shapes come from the generated schema (D-23); none are hand-written.
export type Schemas = components["schemas"];

export function createScreeningRun(
  externalRequisitionId: string,
): Promise<ApiResult<Schemas["ScreeningRunAccepted"]>> {
  const body: Schemas["ScreeningRunCreateRequest"] = { external_requisition_id: externalRequisitionId };
  return apiFetch("/api/v1/screening-runs", { method: "POST", body: JSON.stringify(body) });
}

export function getScreeningRun(runId: string): Promise<ApiResult<Schemas["ScreeningRunStatusResponse"]>> {
  return apiFetch(`/api/v1/screening-runs/${encodeURIComponent(runId)}`);
}
