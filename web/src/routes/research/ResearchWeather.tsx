import EngineStep from "./EngineStep";

export default function ResearchWeather() {
  return (
    <EngineStep
      step={4}
      title="Market conditions"
      what="See how the strategy performs across Bitcoin trend and market volatility, and optionally restrict it to the conditions where it works best."
      next="/research/graduate"
      nextLabel="Launch bot"
    />
  );
}
