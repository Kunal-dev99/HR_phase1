export type DevPrincipalPreset = {
  id: string;
  label: string;
  // null = send no X-Dev-* headers.
  principal: { principalId: string; permissions: string[]; businessUnits: string[] } | null;
};

export const DEV_PRINCIPAL_PRESETS: readonly DevPrincipalPreset[] = [
  { id: "none", label: "No principal", principal: null },
  {
    id: "recruiter-bu-1",
    label: "Recruiter bu-1",
    principal: {
      principalId: "dev-recruiter-bu-1",
      permissions: ["screening_run:create", "screening_run:read"],
      businessUnits: ["bu-1"],
    },
  },
  {
    id: "viewer-bu-1",
    label: "Viewer bu-1",
    principal: {
      principalId: "dev-viewer-bu-1",
      permissions: ["screening_run:read"],
      businessUnits: ["bu-1"],
    },
  },
  {
    id: "recruiter-bu-other",
    label: "Recruiter bu-other",
    principal: {
      principalId: "dev-recruiter-bu-other",
      permissions: ["screening_run:create", "screening_run:read"],
      businessUnits: ["bu-other"],
    },
  },
];

export const DEFAULT_PRESET_ID = "none";
