import { Route, Routes } from "react-router-dom";
import { IntentChatPage } from "./pages/IntentChatPage";
import { ModelResultsPage } from "./pages/ModelResultsPage";
import { UploadProfilePage } from "./pages/UploadProfilePage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<UploadProfilePage />} />
      <Route path="/datasets/:datasetId/analysis/:specId?" element={<IntentChatPage />} />
      <Route path="/models/:modelId" element={<ModelResultsPage />} />
    </Routes>
  );
}
