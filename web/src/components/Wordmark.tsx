import { type CSSProperties } from "react";

/** The full brand lockup — plane + "paper fleet" — as one scalable SVG,
 *  geometry copied from the tuned nav lockup (plane ~1.5× cap height, tight
 *  gap, plane's weight 2 units below the text midline). Height-driven: width
 *  follows the viewBox ratio.
 *
 *  The wordmark is live <text> in DM Sans, so it only renders correctly where
 *  the app's fonts are loaded — always true for this inline component. For
 *  contexts outside the app (<img>, READMEs, social), use
 *  public/brand/wordmark.svg and make sure DM Sans is available, or request
 *  an outlined version.
 */
export default function Wordmark({ height = 28, style }: { height?: number; style?: CSSProperties }) {
  return (
    <svg
      height={height}
      viewBox="0 0 142 28"
      overflow="visible"
      fill="none"
      role="img"
      aria-label="Paper Fleet"
      style={style}
    >
      <path d="M23.8 4.2 L4.2 13.3 L13.3 17.5 L23.8 4.2 Z" fill="#E9ECF1" />
      <path d="M23.8 4.2 L14.98 18.34 L17.08 23.8 L19.18 19.18 L23.8 4.2 Z" fill="#5E8FD8" />
      <text
        x="30"
        y="19.1"
        fontFamily="'DM Sans', sans-serif"
        fontWeight="700"
        fontSize="19"
        letterSpacing="-0.035em"
        fill="#E9ECF1"
      >
        paper fleet
      </text>
    </svg>
  );
}
