import { useNavigate } from "react-router-dom";
import p from "./pages.module.css";

const SECTIONS: [string, string][] = [
  ["What we collect", "Your email address and login method. The strategies and bots you create. The simulated trades and equity your fleet produces. Basic device and usage logs used to keep the service running."],
  ["How we use it", "To run your fleet, send the alerts you turn on, and fix problems. We do not sell your data or use your strategies to trade."],
  ["Who sees it", "Your fleet is private by default. Service providers that host and operate Paper Fleet process data on our behalf."],
  ["Public bots", "If you set a bot to Results only or Public, its name, your handle and its paper results appear on the leaderboard. Its strategy is only visible when set to Public. Setting a bot to Private removes it from the leaderboard."],
  ["Retention", "We keep your data while your account is open, and delete it within a reasonable period after you close it."],
  ["Your choices", "Export or delete your data at any time from settings, or ask us to do it."],
  ["Contact", "Reach us at the support address in your account."],
];

export default function Privacy() {
  const nav = useNavigate();
  return (
    <div className={p.body} style={{ paddingTop: 40, maxWidth: 760 }}>
      <h1 className={p.title} style={{ fontSize: 44 }}>Privacy</h1>
      <p style={{ fontSize: 18, color: "var(--fg-2)", marginTop: 10, lineHeight: 1.6 }}>
        Paper Fleet runs simulated trades. We never hold your money, and we keep only what the product needs to work.
      </p>
      <div className="num lbl" style={{ marginTop: 8 }}>Draft for design. Final text to come from counsel.</div>
      {SECTIONS.map(([h, body]) => (
        <section key={h} style={{ paddingTop: 36, marginTop: 24, borderTop: "1px solid var(--line)" }}>
          <h2 className={p.h2} style={{ fontSize: 20 }}>{h}</h2>
          <p style={{ color: "var(--fg-2)", marginTop: 10, lineHeight: 1.7, fontSize: 15 }}>{body}</p>
        </section>
      ))}
      <button className={`${p.btn} ${p.pri}`} style={{ marginTop: 32 }} onClick={() => nav("/")}>Back to the fleet</button>
    </div>
  );
}
