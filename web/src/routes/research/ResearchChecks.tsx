import EngineStep from "./EngineStep";

export default function ResearchChecks() {
  return (
    <EngineStep
      step={3}
      title="Validation"
      what="Five checks that confirm the edge is real, not luck: beats random entries, profits spread across many episodes, positive every year, recent performance holds, and the strategy is distinct from your other bots."
      next="/research/weather"
      nextLabel="Review conditions"
    />
  );
}
