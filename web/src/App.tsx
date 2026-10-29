import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { FleetCtx, EMPTY_PAYLOAD } from "./api/context";
import { useFleet } from "./api/useFleet";
import { useAuth } from "./auth";
import { CandleProvider } from "./components/CandleModal";
import { useTrackNav } from "./components/cells";
import RequireAuth from "./components/RequireAuth";
import TopBar from "./components/TopBar";
import FleetView from "./routes/FleetView";
import Feed from "./routes/Feed";
import LandingLayout from "./routes/LandingLayout";
import BotProfile from "./routes/BotProfile";
import Leaderboard from "./routes/Leaderboard";
import Market from "./routes/Market";
import MarketDetail from "./routes/MarketDetail";
import Challenges from "./routes/Challenges";
import ChallengeDetail from "./routes/ChallengeDetail";
import Builder from "./routes/Builder";
import Build from "./routes/Build";
import Settings from "./routes/Settings";
import Privacy from "./routes/Privacy";
import NotFound from "./routes/NotFound";
import styles from "./App.module.css";

export default function App() {
  const { data, error } = useFleet();
  const { user, loading: authLoading } = useAuth();
  const loc = useLocation();
  useTrackNav();

  if (authLoading || (!data && !error)) {
    return (
      <div className={styles.center}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <svg width="34" height="34" viewBox="0 0 200 200" fill="none" aria-hidden style={{ opacity: 0.9 }}>
            <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
            <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
          </svg>
          <span style={{ color: "var(--muted)", fontSize: 14 }}>Paper Fleet</span>
        </div>
      </div>
    );
  }

  const fleet = data ?? EMPTY_PAYLOAD;

  if (!user && loc.pathname === "/") {
    return (
      <FleetCtx.Provider value={fleet}>
        <CandleProvider>
          <LandingLayout />
        </CandleProvider>
      </FleetCtx.Provider>
    );
  }

  return (
    <FleetCtx.Provider value={fleet}>
      <CandleProvider>
        <div className={styles.app}>
          <TopBar />

          <main className={styles.main}>
            {!data && user && (
              <div style={{ background: "rgba(248,81,73,.1)", color: "var(--muted)", padding: "8px 16px", fontSize: 13, textAlign: "center" }}>
                Live fleet data is temporarily unavailable.
              </div>
            )}
            <Routes>
              <Route path="/" element={<Navigate to="/feed" replace />} />
              <Route path="/feed" element={<RequireAuth><Feed /></RequireAuth>} />
              <Route path="/fleet" element={<RequireAuth><FleetView /></RequireAuth>} />
              <Route path="/bot/:name" element={<BotProfile />} />
              <Route path="/leaderboard" element={<Leaderboard />} />
              <Route path="/market" element={<Market />} />
              <Route path="/market/:symbol" element={<MarketDetail />} />
              <Route path="/challenges" element={<Challenges />} />
              <Route path="/challenge/:slug" element={<ChallengeDetail />} />
              <Route path="/builder/:handle?" element={<Builder />} />
              <Route path="/build/*" element={<RequireAuth><Build /></RequireAuth>} />
              <Route path="/settings/*" element={<RequireAuth><Settings /></RequireAuth>} />
              <Route path="/signin" element={<Navigate to="/?auth=signin" replace />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
        </div>
      </CandleProvider>
    </FleetCtx.Provider>
  );
}
