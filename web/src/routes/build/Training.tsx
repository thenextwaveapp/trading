import EngineStep from "./EngineStep";

export default function Training() {
  return (
    <EngineStep
      step={2}
      title="Training"
      what="Run the bot over years of market history to see how it would have performed — equity curve, trade count, win rate, drawdown, all after fees."
      next="/build/trials"
      nextLabel="Run the trials"
    />
  );
}
