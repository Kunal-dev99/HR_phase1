import { isDevAuthEnabled } from "./config";
import { DEFAULT_PRESET_ID, DEV_PRINCIPAL_PRESETS, type DevPrincipalPreset } from "./presets";

const STORAGE_KEY = "hr.devPrincipalPreset";
const CHANGE_EVENT = "hr-dev-principal-change";

function findPreset(id: string | null): DevPrincipalPreset {
  return (
    DEV_PRINCIPAL_PRESETS.find((p) => p.id === id) ??
    DEV_PRINCIPAL_PRESETS.find((p) => p.id === DEFAULT_PRESET_ID)!
  );
}

export function getSelectedPresetId(): string {
  if (typeof window === "undefined") return DEFAULT_PRESET_ID;
  return findPreset(window.localStorage.getItem(STORAGE_KEY)).id;
}

export function setSelectedPresetId(id: string): void {
  window.localStorage.setItem(STORAGE_KEY, findPreset(id).id);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

// Headers for the API client. Empty unless dev auth is enabled (D-21).
export function devAuthHeaders(): Record<string, string> {
  if (!isDevAuthEnabled() || typeof window === "undefined") return {};
  const { principal } = findPreset(getSelectedPresetId());
  if (!principal) return {};
  return {
    "X-Dev-Principal-Id": principal.principalId,
    "X-Dev-Permissions": principal.permissions.join(","),
    "X-Dev-Business-Units": principal.businessUnits.join(","),
  };
}
