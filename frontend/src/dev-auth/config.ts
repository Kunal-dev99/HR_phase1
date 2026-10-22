// D-21: the dev principal picker and X-Dev-* headers exist only when the flag is on
// and this is not a production build. NEXT_PUBLIC_* values are inlined at build time.
export function isDevAuthEnabled(): boolean {
  return process.env.NEXT_PUBLIC_DEV_AUTH === "true" && process.env.NODE_ENV !== "production";
}
