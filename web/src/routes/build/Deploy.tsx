import EngineStep from "./EngineStep";

export default function Deploy() {
  return (
    <EngineStep
      step={5}
      title="Deploy to a fleet"
      what="Name the bot, pick a fleet and visibility, and deploy it on $10,000 of paper money. Deploying a new bot needs the write backend; your existing bots are already running."
    />
  );
}
