import { Route, Routes } from "react-router-dom";
import ResearchHub from "./research/ResearchHub";
import ResearchBuild from "./research/ResearchBuild";
import ResearchBacktest from "./research/ResearchBacktest";
import ResearchChecks from "./research/ResearchChecks";
import ResearchWeather from "./research/ResearchWeather";
import ResearchGraduate from "./research/ResearchGraduate";
import ResearchReport from "./research/ResearchReport";

export default function Research() {
  return (
    <Routes>
      <Route index element={<ResearchHub />} />
      <Route path="build" element={<ResearchBuild />} />
      <Route path="backtest" element={<ResearchBacktest />} />
      <Route path="checks" element={<ResearchChecks />} />
      <Route path="weather" element={<ResearchWeather />} />
      <Route path="graduate" element={<ResearchGraduate />} />
      <Route path="report/:name" element={<ResearchReport />} />
      <Route path="report" element={<ResearchReport />} />
    </Routes>
  );
}
