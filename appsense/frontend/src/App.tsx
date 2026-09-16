import { Navigate, Route, Routes } from "react-router-dom";
import { AboutPresentation } from "./components/AboutPresentation";
import { AppShell } from "./layout/AppShell";
import { ChatPage } from "./pages/ChatPage";
import { LearningPage } from "./pages/LearningPage";
import { SkillsPage } from "./pages/SkillsPage";
import { CodeBasePage } from "./pages/CodeBasePage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/about" element={<AboutPresentation />} />
      <Route element={<AppShell />}>
        <Route path="/" element={<Welcome />} />
        <Route path="/welcome" element={<Navigate to="/" replace />} />
        <Route path="/projects/:projectId/chat" element={<ChatPage />} />
        <Route path="/projects/:projectId/learning" element={<LearningPage />} />
        <Route path="/projects/:projectId/skills" element={<SkillsPage />} />
        <Route path="/projects/:projectId/code" element={<CodeBasePage />} />
        <Route path="/projects/:projectId/knowledge" element={<KnowledgePage />} />
        <Route path="/projects/:projectId/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

function Welcome() {
  return (
    <div className="page page-narrow empty">
      <h3>Welcome to AppSense</h3>
      <p className="lede">
        Create a project in the left sidebar to start chatting, linking repos, and ingesting
        knowledge.
      </p>
    </div>
  );
}
