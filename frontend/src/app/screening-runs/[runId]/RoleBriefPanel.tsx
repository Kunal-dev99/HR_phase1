"use client";

import { useEffect, useState } from "react";
import { roleBriefErrorMessage } from "@/api/messages";
import { approveRoleBrief, getRoleBrief } from "@/api/role-briefs";
import type { Schemas } from "@/api/screening-runs";
import { Alert, Button, Card, KeyValueList, StatusBadge } from "@/components/ui";

// FE-7.4 (D-38). Page-local panel. Every model string is rendered as escaped text (D-35).

function SourceRefs({ refs }: { refs: Schemas["SourceRef"][] }) {
  if (refs.length === 0) return null;
  return (
    <ul className="mt-1 flex flex-col gap-1">
      {refs.map((ref, i) => (
        <li key={`${ref.path}-${i}`} className="text-xs text-muted">
          <code className="rounded-sm bg-background px-1">{ref.path}</code> “{ref.quote}”
        </li>
      ))}
    </ul>
  );
}

function BriefItemValue({ item }: { item: Schemas["BriefItem"] }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <span>{item.text}</span>
        {item.basis === "ai_inference" ? <StatusBadge label="AI suggestion" tone="warning" /> : null}
      </div>
      <SourceRefs refs={item.source_refs} />
    </div>
  );
}

function BriefItemList({ items }: { items: Schemas["BriefItem"][] }) {
  if (items.length === 0) return <span className="text-muted">—</span>;
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item, i) => (
        <li key={i}>
          <BriefItemValue item={item} />
        </li>
      ))}
    </ul>
  );
}

export function RoleBriefPanel({
  runId,
  roleBriefVersionId,
  runStatus,
  onApproved,
}: {
  runId: string;
  roleBriefVersionId: string;
  runStatus: string;
  onApproved: () => void;
}) {
  const [brief, setBrief] = useState<Schemas["RoleBriefResponse"] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const result = await getRoleBrief(runId);
      if (cancelled) return;
      if (result.ok) {
        setBrief(result.data);
        setLoadError(null);
      } else {
        setLoadError(roleBriefErrorMessage(result, "get_brief"));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [runId, roleBriefVersionId, reloadKey]);

  async function approve() {
    if (!brief) return;
    setSubmitting(true);
    setApproveError(null);
    const result = await approveRoleBrief(runId, brief.role_brief_version_id);
    setSubmitting(false);
    if (!result.ok) {
      setApproveError(roleBriefErrorMessage(result, "approve"));
      return;
    }
    setBrief(result.data);
    setReloadKey((k) => k + 1);
    onApproved();
  }

  if (!brief) {
    return (
      <Card title="Role brief">
        {loadError ? <Alert variant="error">{loadError}</Alert> : <p className="text-sm text-muted">Loading…</p>}
      </Card>
    );
  }

  const role = brief.structured_role_data;
  const materialCount = brief.ambiguities.filter((a) => a.severity === "material").length;

  return (
    <>
      {loadError ? <Alert variant="warning">{loadError}</Alert> : null}
      <Card title="Role">
        <KeyValueList
          items={[
            { key: "Title", value: <BriefItemValue item={role.role_title} /> },
            { key: "Purpose", value: <BriefItemValue item={role.role_purpose} /> },
            { key: "Seniority", value: <BriefItemValue item={role.seniority} /> },
            { key: "Employment constraints", value: <BriefItemList items={role.employment_constraints} /> },
            { key: "Location constraints", value: <BriefItemList items={role.location_constraints} /> },
          ]}
        />
      </Card>
      <Card title="From the requisition (facts)">
        {brief.explicit_source_facts.length === 0 ? (
          <p className="text-sm text-muted">None</p>
        ) : (
          <ul className="flex flex-col gap-3 text-sm">
            {brief.explicit_source_facts.map((fact, i) => (
              <li key={i}>
                <p>{fact.statement}</p>
                <SourceRefs refs={fact.source_refs} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="AI inferences">
        {brief.ai_inferences.length === 0 ? (
          <p className="text-sm text-muted">None</p>
        ) : (
          <ul className="flex flex-col gap-3 text-sm">
            {brief.ai_inferences.map((inf, i) => (
              <li key={i}>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge label="AI suggestion" tone="warning" />
                  <span>{inf.statement}</span>
                </div>
                <p className="mt-1 text-muted">Rationale: {inf.rationale}</p>
                <SourceRefs refs={inf.source_refs} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Ambiguities">
        {brief.ambiguities.length === 0 ? (
          <p className="text-sm text-muted">None</p>
        ) : (
          <ul className="flex flex-col gap-3 text-sm">
            {brief.ambiguities.map((amb, i) => (
              <li key={i}>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge label={amb.severity} tone={amb.severity === "material" ? "error" : "neutral"} />
                  <span className="font-medium">{amb.topic}</span>
                </div>
                <p className="mt-1">{amb.description}</p>
                <p className="mt-1 text-muted">Suggested question: {amb.suggested_question}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Provenance">
        <KeyValueList
          items={[
            { key: "Version", value: String(brief.version_number) },
            {
              key: "Status",
              value: (
                <StatusBadge label={brief.status} tone={brief.status === "approved" ? "success" : "warning"} />
              ),
            },
            { key: "Model", value: `${brief.model_provider} / ${brief.model_name}` },
            { key: "Prompt version", value: brief.prompt_version },
            { key: "Schema version", value: brief.schema_version },
            { key: "Snapshot ID", value: brief.source_snapshot_id },
            { key: "Snapshot hash", value: brief.source_payload_hash },
            { key: "Approved by", value: brief.approved_by ?? "—" },
            { key: "Approved at", value: brief.approved_at ?? "—" },
          ]}
        />
      </Card>
      {runStatus === "awaiting_role_approval" ? (
        <Card title="Approval">
          <div className="flex flex-col gap-4">
            {approveError ? <Alert variant="error">{approveError}</Alert> : null}
            <div>
              <Button onClick={() => void approve()} disabled={submitting}>
                {materialCount > 0 ? "Approve (accepts listed ambiguities)" : "Approve role brief"}
              </Button>
            </div>
          </div>
        </Card>
      ) : null}
    </>
  );
}
