import { Suspense } from "react";
import { RunStatusView } from "./RunStatusView";

// useParams() is runtime data, so the client view streams inside Suspense (Cache Components).
export default function RunStatusPage() {
  return (
    <Suspense fallback={null}>
      <RunStatusView />
    </Suspense>
  );
}
