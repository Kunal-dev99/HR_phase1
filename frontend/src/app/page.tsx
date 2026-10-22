"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { errorMessage } from "@/api/messages";
import { createScreeningRun } from "@/api/screening-runs";
import { Alert, Button, Card, PageShell, TextField } from "@/components/ui";
import { isScreeningRunsEnabled } from "@/features";

export default function Home() {
  const router = useRouter();
  const [requisitionId, setRequisitionId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isScreeningRunsEnabled()) {
    return (
      <PageShell title="HR Screening">
        <Alert variant="info">Screening runs are turned off</Alert>
      </PageShell>
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const result = await createScreeningRun(requisitionId);
    if (result.ok) {
      router.push(`/screening-runs/${encodeURIComponent(result.data.run_id)}`);
      return;
    }
    setError(errorMessage(result, "create"));
    setSubmitting(false);
  }

  return (
    <PageShell title="HR Screening">
      <Card title="Start a screening run">
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <TextField
            id="external-requisition-id"
            label="HR requisition ID"
            required
            value={requisitionId}
            onChange={(e) => setRequisitionId(e.target.value)}
          />
          <div>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Starting…" : "Start run"}
            </Button>
          </div>
          {error ? <Alert variant="error">{error}</Alert> : null}
        </form>
      </Card>
    </PageShell>
  );
}
