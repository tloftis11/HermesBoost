import { Route, Routes } from "react-router-dom";
import { IntentChatPage } from "./pages/IntentChatPage";
import { UploadProfilePage } from "./pages/UploadProfilePage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<UploadProfilePage />} />
      <Route path="/datasets/:datasetId/analysis/:specId?" element={<IntentChatPage />} />
    </Routes>
  );
}
