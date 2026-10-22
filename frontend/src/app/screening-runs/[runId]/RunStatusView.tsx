"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { completionReasonLabel, errorMessage } from "@/api/messages";
import { getScreeningRun, type Schemas } from "@/api/screening-runs";
import { Alert, Button, Card, KeyValueList, PageShell, StatusBadge } from "@/components/ui";
import { isScreeningRunsEnabled } from "@/features";

// D-24 polling.
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 120_000;
const STOPPING_STATUSES = new Set<string>(["role_brief_draft", "blocked"]);
const STOPPING_ERRORS = new Set<number>([401, 403, 404, 422]);

function statusTone(status: string) {
  if (status === "role_brief_draft") return "success" as const;
  if (status === "blocked") return "error" as const;
  return "info" as const;
}

export function RunStatusView() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<Schemas["ScreeningRunStatusResponse"] | null>(null);
  const [problem, setProblem] = useState<{ variant: "error" | "warning"; text: string } | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const [pollKey, setPollKey] = useState(0);
  const enabled = isScreeningRunsEnabled();

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = Date.now() + POLL_TIMEOUT_MS;

    // One request at a time: the next GET is scheduled only after this one settles.
    async function tick() {
      const result = await getScreeningRun(runId);
      if (cancelled) return;
      let stop: boolean;
      if (result.ok) {
        setRun(result.data);
        setProblem(null);
        stop = STOPPING_STATUSES.has(result.data.status);
      } else {
        stop = STOPPING_ERRORS.has(result.status);
        if (stop) setRun(null);
        setProblem({ variant: stop ? "error" : "warning", text: errorMessage(result, "get") });
      }
      if (stop) return;
      if (Date.now() >= deadline) {
        setTimedOut(true);
        return;
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS);
    }

    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runId, pollKey, enabled]);

  if (!enabled) {
    return (
      <PageShell title="Screening run">
        <Alert variant="info">Screening runs are turned off</Alert>
      </PageShell>
    );
  }

  function refresh() {
    setTimedOut(false);
    setPollKey((k) => k + 1);
  }

  const req = run?.requisition ?? null;
  const missing = run?.status_details?.missing_fields;

  return (
    <PageShell title="Screening run">
      <div className="flex items-center justify-between">
        <Link href="/" className="text-sm text-primary underline">
          Start another run
        </Link>
        <Button variant="secondary" onClick={refresh}>
          Refresh
        </Button>
      </div>
      {problem ? <Alert variant={problem.variant}>{problem.text}</Alert> : null}
      {timedOut ? <Alert variant="warning">Still running — use Refresh</Alert> : null}
      {run ? (
        <>
          <Card title="Status">
            <KeyValueList
              items={[
                { key: "Run ID", value: run.run_id },
                { key: "Status", value: <StatusBadge label={run.status} tone={statusTone(run.status)} /> },
                { key: "Phase 1", value: <StatusBadge label={run.phases.phase_1} tone="info" /> },
                ...(run.completion_reason
                  ? [{ key: "Completion reason", value: completionReasonLabel(run.completion_reason) }]
                  : []),
                ...(Array.isArray(missing) && missing.length > 0
                  ? [{ key: "Missing fields", value: missing.map(String).join(", ") }]
                  : []),
                { key: "Started at", value: run.started_at },
                { key: "Completed at", value: run.completed_at ?? "—" },
                { key: "Correlation ID", value: run.correlation_id },
              ]}
            />
          </Card>
          <Card title="Pinned requisition">
            {req ? (
              <KeyValueList
                items={[
                  { key: "External requisition ID", value: req.external_requisition_id },
                  { key: "HR system key", value: req.hr_system_key },
                  { key: "Requisition ID", value: req.requisition_id },
                  { key: "Snapshot ID", value: req.snapshot_id ?? "—" },
                  { key: "Payload hash", value: req.payload_hash ?? "—" },
                  { key: "Captured at", value: req.captured_at ?? "—" },
                ]}
              />
            ) : (
              <p className="text-sm text-muted">
                {STOPPING_STATUSES.has(run.status) ? "Not pinned" : "Not pinned yet"}
              </p>
            )}
          </Card>
        </>
      ) : null}
    </PageShell>
  );
}
