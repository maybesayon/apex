import { AuthGate } from "@/components/auth-gate";

/**
 * Wraps every route in the auth gate and app chrome. A template rather than
 * a layout so it remounts per navigation, which is what lets page
 * transitions animate.
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return <AuthGate>{children}</AuthGate>;
}
