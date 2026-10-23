import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth";

/** Gate a private route. Logged out → bounce to /signin with a return path. */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return null; // the app shell already shows a splash while auth hydrates
  if (!user) {
    const next = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/signin?next=${next}`} replace />;
  }
  return <>{children}</>;
}
