import { useEffect, useState } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { FleetCtx } from "./api/context";
import { useFleet } from "./api/useFleet";
import { useAuth } from "./auth";
import { CandleProvider } from "./components/CandleModal";
import RequireAuth from "./components/RequireAuth";
import Sidebar from "./components/Sidebar";
import FleetView from "./routes/FleetView";
import Roster from "./routes/Roster";
import Landing from "./routes/Landing";
import BotProfile from "./routes/BotProfile";
import Leaderboard from "./routes/Leaderboard";
import Builder from "./routes/Builder";
import Build from "./routes/Build";
import Settings from "./routes/Settings";
import Privacy from "./routes/Privacy";
import SignIn from "./routes/SignIn";
import NotFound from "./routes/NotFound";
import styles from "./App.module.css";

export default function App() {
  const { data, error } = useFleet();
  const { user, loading: authLoading } = useAuth();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sbc") === "1",
  );
  // Off-canvas mobile drawer.
  const [menuOpen, setMenuOpen] = useState(false);

  const toggle = () =>
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem("sbc", next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });

  // Close the drawer on route change.
  useEffect(() => {
    setMenuOpen(false);
  }, [loc.pathname, loc.hash]);

  // Lock background scroll while the drawer is open.
  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  if (authLoading || !data) {
    return (
      <div className={styles.center}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <svg width="34" height="34" viewBox="0 0 200 200" fill="none" aria-hidden style={{ opacity: 0.9 }}>
            <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
            <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
          </svg>
          <span style={{ color: "var(--muted)", fontSize: 14 }}>
            {error ? "Could not reach the fleet. Is the backend / tunnel up?" : "Paper Fleet"}
          </span>
        </div>
      </div>
    );
  }

  const liveOk = data.running && !data.paused;

  return (
    <FleetCtx.Provider value={data}>
      <CandleProvider>
        <div className={styles.app}>
          {/* mobile top app bar */}
          <header className={styles.topbar}>
            <button
              className={styles.hamburger}
              onClick={() => setMenuOpen((o) => !o)}
              aria-label="Open menu"
              aria-expanded={menuOpen}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
                <path d="M3 6h18M3 12h18M3 18h18" />
              </svg>
            </button>
            <span className={styles.brand}>
              <svg width="20" height="20" viewBox="0 0 200 200" fill="none" aria-hidden>
                <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
                <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
              </svg>
              paper fleet
            </span>
            <span
              className={styles.topStatus}
              title={liveOk ? "Fleet is live" : data.paused ? "Fleet paused" : "Fleet is down"}
            >
              <span className={liveOk ? "liveDot" : "downDot"} />
            </span>
          </header>

          {/* drawer backdrop */}
          <div
            className={`${styles.backdrop} ${menuOpen ? styles.backdropOpen : ""}`}
            onClick={() => setMenuOpen(false)}
            aria-hidden
          />

          <Sidebar collapsed={collapsed} onToggle={toggle} mobileOpen={menuOpen} />

          <main className={styles.main}>
            <Routes>
              {/* Adaptive home: your Roster when signed in, the public showcase when not. */}
              <Route path="/" element={user ? <Roster /> : <Landing />} />
              <Route path="/fleet" element={<FleetView />} />
              <Route path="/bot/:name" element={<BotProfile />} />
              <Route path="/leaderboard" element={<Leaderboard />} />
              <Route path="/builder/:handle?" element={<Builder />} />
              <Route path="/build/*" element={<RequireAuth><Build /></RequireAuth>} />
              <Route path="/settings/*" element={<RequireAuth><Settings /></RequireAuth>} />
              <Route path="/signin" element={<SignIn />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
        </div>
      </CandleProvider>
    </FleetCtx.Provider>
  );
}
