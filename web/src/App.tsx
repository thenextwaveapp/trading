import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import PaperLoader from "./components/PaperLoader";
import { FleetCtx, EMPTY_PAYLOAD } from "./api/context";
import { useFleet } from "./api/useFleet";
import { useAuth } from "./auth";
import { CandleProvider } from "./components/CandleModal";
import { AssistantProvider } from "./assistant/AssistantProvider";
import { CurrentFleetProvider } from "./fleets/CurrentFleetProvider";
import Assistant from "./assistant/Assistant";
import { useTrackNav } from "./components/cells";
import RequireAuth from "./components/RequireAuth";
import RequireOnboarded from "./components/RequireOnboarded";
import { UpgradeProvider } from "./components/UpgradeModal";
import TopBar from "./components/TopBar";
import FleetView from "./routes/FleetView";
import Feed from "./routes/Feed";
import LandingLayout from "./routes/LandingLayout";
import BotProfile from "./routes/BotProfile";
import Leaderboard from "./routes/Leaderboard";
import Market from "./routes/Market";
import MarketDetail from "./routes/MarketDetail";
import SearchPage from "./routes/SearchPage";
import Challenges from "./routes/Challenges";
import ChallengeDetail from "./routes/ChallengeDetail";
import Builder from "./routes/Builder";
import Trade from "./routes/Trade";
import Build from "./routes/Build";
import Settings from "./routes/Settings";
import Upgrade from "./routes/Upgrade";
import Onboarding from "./routes/Onboarding";
import Privacy from "./routes/Privacy";
import NotFound from "./routes/NotFound";
import styles from "./App.module.css";

export default function App() {
  const { data, error } = useFleet();
  const { user, loading: authLoading } = useAuth();
  const loc = useLocation();
  useTrackNav();

  // A minimum display floor, not a fixed hold: the app appears as soon as data
  // is ready AND this short beat has passed. Fast loads glimpse the plane; slow
  // loads see the animation until data lands. ~800ms kills the flash-frame
  // glitch without making a returning user wait.
  const [minElapsed, setMinElapsed] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setMinElapsed(true), 800);
    return () => clearTimeout(t);
  }, []);

  if (!minElapsed || authLoading || (!data && !error)) {
    return (
      <div className={styles.center}>
        <div className={styles.splash}>
          <div className={styles.splashPaper}><PaperLoader size={72} /></div>
          <div className={styles.splashWord}>paper fleet</div>
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
       <CurrentFleetProvider>
       <UpgradeProvider>
       <AssistantProvider>
        <div className={styles.app}>
          <TopBar />

          <main className={`${styles.main} ${loc.pathname.startsWith("/fleet") ? styles.wide : ""}`}>
            {!data && user && (
              <div style={{ background: "rgba(248,81,73,.1)", color: "var(--muted)", padding: "8px 16px", fontSize: 13, textAlign: "center" }}>
                Live fleet data is temporarily unavailable.
              </div>
            )}
            <Routes>
              <Route path="/" element={<Navigate to="/feed" replace />} />
              <Route path="/feed" element={<RequireOnboarded><Feed /></RequireOnboarded>} />
              <Route path="/fleet" element={<RequireOnboarded><FleetView /></RequireOnboarded>} />
              <Route path="/bot/:name" element={<BotProfile />} />
              <Route path="/trade/:bot/:ticker/:t?" element={<Trade />} />
              <Route path="/leaderboard" element={<Leaderboard />} />
              <Route path="/market" element={<Market />} />
              <Route path="/market/:symbol" element={<MarketDetail />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/challenges" element={<Challenges />} />
              <Route path="/challenge/:slug" element={<ChallengeDetail />} />
              <Route path="/builder/:handle?" element={<Builder />} />
              <Route path="/build/*" element={<RequireOnboarded><Build /></RequireOnboarded>} />
              <Route path="/settings/*" element={<RequireAuth><Settings /></RequireAuth>} />
              <Route path="/onboarding" element={<RequireAuth><Onboarding /></RequireAuth>} />
              <Route path="/upgrade" element={<Upgrade />} />
              <Route path="/signin" element={<Navigate to="/?auth=signin" replace />} />
              <Route path="/privacy" element={<Privacy />} />
              {/* readable canonical paths: /@handle, /@handle/bot-slug,
                  /@handle/bot-slug/TICKER/:t — components 404 non-@ handles */}
              <Route path="/:handle" element={<Builder />} />
              <Route path="/:handle/:botSlug" element={<BotProfile />} />
              <Route path="/:handle/:botSlug/:ticker/:t?" element={<Trade />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
          {/* the search page is its own full-screen search surface — the
              Strategy Navigator composer would just compete with it */}
          {loc.pathname !== "/search" && <Assistant />}
        </div>
       </AssistantProvider>
       </UpgradeProvider>
       </CurrentFleetProvider>
      </CandleProvider>
    </FleetCtx.Provider>
  );
}
