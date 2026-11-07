import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth";

/**
 * Private route that also requires the first-run funnel to be complete. Logged
 * out → sign-in; logged in but `onboarded_at` is null → the onboarding flow.
 * Used on the core app routes (Feed, Fleet, Build); /onboarding itself is behind
 * plain RequireAuth so it can run.
 */
export default function RequireOnboarded({ children }: { children: React.ReactNode }) {
  const { user, loading, profile } = useAuth();
  const loc = useLocation();

  if (loading) return null;
  if (!user) {
    const next = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/?auth=signin&next=${next}`} replace />;
  }
  if (!profile) return null; // wait for the profile row before deciding
  if (!profile.onboarded_at) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}
