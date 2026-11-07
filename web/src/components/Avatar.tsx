import { DEFAULT_BOT_COLOR } from "../lib/brand";
import { identicon } from "../lib/format";

// One place for every avatar. People and bots look DIFFERENT on purpose:
//   UserAvatar — an uploaded photo (cropped to the circle) or, failing that,
//     the builder's initials on their colour. A human, not a robot.
//   BotAvatar  — the deterministic pixel identicon, seeded by bot name. Bots
//     are machines; the machine look is theirs to keep.
// Both are perfect circles with the shared #12161D backing, so swapping a raw
// inline <svg>/<img> for one of these never shifts the layout.

const BACKING = "#12161D";

function initials(name?: string | null, handle?: string | null): string {
  const base = (name && name.trim()) || (handle ? handle.replace(/^@/, "") : "");
  if (!base) return "?";
  const parts = base.split(/\s+/).filter(Boolean);
  const chars = parts.length >= 2 ? parts[0][0] + parts[1][0] : parts[0].slice(0, 1);
  return chars.toUpperCase();
}

export function UserAvatar({
  name,
  handle,
  url,
  color = DEFAULT_BOT_COLOR,
  size = 38,
  className,
}: {
  name?: string | null;
  handle?: string | null;
  url?: string | null;
  color?: string;
  size?: number;
  className?: string;
}) {
  const box = { width: size, height: size, flex: "none" as const, display: "block" as const };
  if (url) {
    // standard circle crop: fill the circle, centre the photo, never distort.
    return (
      <img
        src={url}
        alt=""
        width={size}
        height={size}
        className={className}
        style={{ ...box, borderRadius: "50%", objectFit: "cover", objectPosition: "center", background: BACKING }}
      />
    );
  }
  return (
    <span
      className={className}
      aria-hidden
      style={{
        ...box,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "50%",
        background: color,
        color: "#fff",
        fontWeight: 600,
        fontSize: Math.round(size * 0.42),
        lineHeight: 1,
        letterSpacing: 0.2,
        userSelect: "none",
      }}
    >
      {initials(name, handle)}
    </span>
  );
}

export function BotAvatar({
  seed,
  color = DEFAULT_BOT_COLOR,
  size = 38,
  className,
}: {
  seed: string;
  color?: string;
  size?: number;
  className?: string;
}) {
  const inner = Math.round(size * 0.62);
  const off = Math.round((size - inner) / 2);
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={className}
      style={{ flex: "none", display: "block" }}
    >
      <rect width={size} height={size} rx={size / 2} fill={BACKING} />
      <path d={identicon(seed, inner)} fill={color} transform={`translate(${off} ${off})`} />
    </svg>
  );
}
