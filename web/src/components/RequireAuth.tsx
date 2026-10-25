import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth";

/** Gate a private route. Logged out → bounce to /signin with a return path. */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return null; // the app shell already shows a splash while auth hydrates
  if (!user) {
    // No sign-in page — bounce to the landing, which opens the glass auth dialog.
    const next = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/?auth=signin&next=${next}`} replace />;
  }
  return <>{children}</>;
}
