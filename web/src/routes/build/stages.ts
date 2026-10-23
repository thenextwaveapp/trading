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
