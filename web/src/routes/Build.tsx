import { Route, Routes } from "react-router-dom";
import Hub from "./build/Hub";
import Compose from "./build/Compose";
import Training from "./build/Training";
import Trials from "./build/Trials";
import Weather from "./build/Weather";
import Deploy from "./build/Deploy";
import Report from "./build/Report";

export default function Build() {
  return (
    <Routes>
      <Route index element={<Hub />} />
      <Route path="compose" element={<Compose />} />
      <Route path="training" element={<Training />} />
      <Route path="trials" element={<Trials />} />
      <Route path="weather" element={<Weather />} />
      <Route path="deploy" element={<Deploy />} />
      <Route path="report/:name" element={<Report />} />
      <Route path="report" element={<Report />} />
    </Routes>
  );
}
