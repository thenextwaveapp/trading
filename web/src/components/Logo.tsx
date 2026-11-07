import { type CSSProperties } from "react";

/** The brand mark: the original paper plane, componentized so every lockup
 *  (nav, footer, auth, loading) renders the same glyph from one place.
 *  `mono` fills it in currentColor for use inside tinted controls. */
export default function Logo({
  size = 24,
  style,
  mono = false,
}: {
  size?: number;
  style?: CSSProperties;
  mono?: boolean;
}) {
  if (mono) {
    return (
      <svg width={size} height={size} viewBox="0 0 200 200" fill="none" aria-hidden style={style}>
        <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="currentColor" />
        <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="currentColor" opacity="0.55" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 200 200" fill="none" aria-hidden style={style}>
      <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
      <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
    </svg>
  );
}
