import EngineStep from "./EngineStep";

export default function Trials() {
  return (
    <EngineStep
      step={3}
      title="Trials"
      what="The honesty gauntlet — it proves the edge is real, not luck: the bot survives triple trading costs, survives a late fill, and beats random entries."
      next="/build/weather"
      nextLabel="Check the weather"
    />
  );
}
