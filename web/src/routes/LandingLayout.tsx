import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Landing from "./Landing";
import TopNav from "../components/TopNav";
import AuthModal from "./AuthModal";
import styles from "../App.module.css";

type Mode = "signin" | "signup";

/** The logged-out marketing shell: top nav, the landing, and a glass auth
 *  dialog floated over it. Opened by the nav/CTA buttons, or by a `?auth=`
 *  query when a guarded route bounces someone here. */
export default function LandingLayout() {
  const loc = useLocation();
  const nav = useNavigate();
  const [auth, setAuth] = useState<Mode | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(loc.search).get("auth");
    if (q === "signin" || q === "signup") setAuth(q);
  }, [loc.search]);

  const close = () => {
    setAuth(null);
    if (loc.search) nav("/", { replace: true }); // strip ?auth from the url
  };

  return (
    <div className={styles.app}>
      <TopNav onAuth={setAuth} />
      <main className={styles.landingMain}>
        <Landing onAuth={setAuth} />
      </main>
      {auth && <AuthModal mode={auth} setMode={setAuth} onClose={close} />}
    </div>
  );
}
