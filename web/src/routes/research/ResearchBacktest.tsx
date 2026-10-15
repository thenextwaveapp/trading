import EngineStep from "./EngineStep";

export default function ResearchBacktest() {
  return (
    <EngineStep
      step={2}
      title="Backtest"
      what="Run the strategy over years of market history to see how it would have performed — equity curve, trade count, win rate, drawdown, all after fees."
      next="/research/checks"
      nextLabel="Run validation"
    />
  );
}
