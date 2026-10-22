// D-25: screening-run screens are off unless the flag is "true". Inlined at build time.
export function isScreeningRunsEnabled(): boolean {
  return process.env.NEXT_PUBLIC_FEATURE_SCREENING_RUNS === "true";
}
