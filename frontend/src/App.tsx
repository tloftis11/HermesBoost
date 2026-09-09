import { Route, Routes } from "react-router-dom";
import { DataAcquisitionPage } from "./pages/DataAcquisitionPage";
import { IntentChatPage } from "./pages/IntentChatPage";
import { ModelResultsPage } from "./pages/ModelResultsPage";
import { ModelsListPage } from "./pages/ModelsListPage";
import { RiskScoreResultsPage } from "./pages/RiskScoreResultsPage";
import { RiskScoresPage } from "./pages/RiskScoresPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UploadProfilePage } from "./pages/UploadProfilePage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<UploadProfilePage />} />
      <Route path="/analysis" element={<IntentChatPage />} />
      <Route path="/datasets/:datasetId/analysis/:specId?" element={<IntentChatPage />} />
      <Route path="/data-acquisition" element={<DataAcquisitionPage />} />
      <Route path="/data-acquisition/:sessionId" element={<DataAcquisitionPage />} />
      <Route path="/models" element={<ModelsListPage />} />
      <Route path="/models/:modelId" element={<ModelResultsPage />} />
      <Route path="/risk-scores" element={<RiskScoresPage />} />
      <Route path="/risk-scores/:riskScoreId" element={<RiskScoreResultsPage />} />
      <Route path="/settings" element={<SettingsPage />} />
    </Routes>
  );
}
