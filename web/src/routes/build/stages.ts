import type { Stage } from "../../db/types";

// Single source for stage keys, labels and blurbs.
export const STAGES: { key: Stage; label: string; blurb: string }[] = [
  { key: "draft", label: "Draft", blurb: "Composed, not yet run" },
  { key: "training", label: "Training", blurb: "Running over history" },
  { key: "trials", label: "Trials", blurb: "Proving it isn't luck" },
  { key: "weather", label: "Weather", blurb: "When it's allowed to fight" },
  { key: "ready", label: "Ready", blurb: "Passed, awaiting orders" },
  { key: "deployed", label: "Deployed", blurb: "Battling in the fleet" },
];

// Linear build steps (Report follows deploy).
export const FLOW_STEPS = ["Compose", "Training", "Trials", "Weather", "Deploy"] as const;

// Each step's route, in order, so a bot can be carried through the wizard.
export const FLOW_PATHS = [
  "/build/compose",
  "/build/training",
  "/build/trials",
  "/build/weather",
  "/build/deploy",
] as const;

/** Append the bot being built so each step knows which bot it's about. */
export function withBot(path: string, bot: string | null): string {
  return bot ? `${path}?bot=${encodeURIComponent(bot)}` : path;
}

/** Where to resume a bot given the rung it's on. */
export function resumePath(stage: Stage, name: string): string {
  switch (stage) {
    case "deployed":
      return "/bot/" + encodeURIComponent(name);
    case "ready":
      return withBot("/build/deploy", name);
    case "weather":
      return withBot("/build/weather", name);
    case "trials":
      return withBot("/build/trials", name);
    case "training":
      return withBot("/build/training", name);
    default:
      return withBot("/build/compose", name);
  }
}
