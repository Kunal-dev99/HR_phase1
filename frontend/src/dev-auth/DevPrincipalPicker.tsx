"use client";

import { useSyncExternalStore } from "react";
import { DEFAULT_PRESET_ID, DEV_PRINCIPAL_PRESETS } from "./presets";
import { getSelectedPresetId, setSelectedPresetId, subscribe } from "./store";

export function DevPrincipalPicker() {
  const selected = useSyncExternalStore(subscribe, getSelectedPresetId, () => DEFAULT_PRESET_ID);
  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor="dev-principal" className="font-medium text-muted">
        Dev principal
      </label>
      <select
        id="dev-principal"
        value={selected}
        onChange={(e) => setSelectedPresetId(e.target.value)}
        className="rounded-md border border-border bg-surface px-2 py-1"
      >
        {DEV_PRINCIPAL_PRESETS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>
    </div>
  );
}
