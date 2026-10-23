import EngineStep from "./EngineStep";

export default function Weather() {
  return (
    <EngineStep
      step={4}
      title="Weather"
      what="See how the bot performs across Bitcoin trend and market volatility, and optionally restrict it to the conditions where it's allowed to fight."
      next="/build/deploy"
      nextLabel="Deploy bot"
    />
  );
}
