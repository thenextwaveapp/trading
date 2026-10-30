import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import s from "./TopNav.module.css";

/** Marketing top bar for the landing. Transparent while at the top of the
 *  page; fades in a frosted background once the visitor scrolls.
 *
 *  Note: global CSS (`html,body,#root{height:100%}` + `overflow-x:hidden` on
 *  body, which computes overflow-y to auto) makes <body> the scroll container,
 *  not the window — so window.scrollY never moves here. We read body.scrollTop
 *  and listen in the capture phase (scroll events don't bubble). */
export default function TopNav({ onAuth }: { onAuth: (mode: "signin" | "signup") => void }) {
  const nav = useNavigate();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const read = () =>
      Math.max(
        document.body.scrollTop || 0,
        document.documentElement.scrollTop || 0,
        window.scrollY || 0,
      );
    const onScroll = () => setScrolled(read() > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, true);
    return () => window.removeEventListener("scroll", onScroll, true);
  }, []);

  return (
    <header className={`${s.topnav} ${scrolled ? s.scrolled : ""}`}>
      <div className={s.inner}>
        <button
          className={s.brand}
          onClick={() => document.body.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="Paper Fleet home"
        >
          <svg width="22" height="22" viewBox="0 0 200 200" fill="none" aria-hidden>
            <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
            <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
          </svg>
          paper fleet
        </button>
        <nav className={s.links}>
          <button className={s.link} onClick={() => nav("/leaderboard")}>Leaderboard</button>
          <button className={s.link} onClick={() => onAuth("signin")}>Log in</button>
          <button className={s.cta} onClick={() => onAuth("signup")}>Start free</button>
        </nav>
      </div>
    </header>
  );
}
