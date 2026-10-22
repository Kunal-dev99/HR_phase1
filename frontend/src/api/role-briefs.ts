import { apiFetch, type ApiResult } from "./client";
import type { Schemas } from "./screening-runs";

// Role brief calls (FE-7.2). Shapes come only from the generated schema (D-23).
export function getRoleBrief(runId: string): Promise<ApiResult<Schemas["RoleBriefResponse"]>> {
  return apiFetch(`/api/v1/screening-runs/${encodeURIComponent(runId)}/role-brief`);
}

export function approveRoleBrief(
  runId: string,
  roleBriefVersionId: string,
): Promise<ApiResult<Schemas["RoleBriefResponse"]>> {
  const body: Schemas["ApproveRoleBriefRequest"] = { role_brief_version_id: roleBriefVersionId };
  return apiFetch(`/api/v1/screening-runs/${encodeURIComponent(runId)}/approve-role-brief`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
