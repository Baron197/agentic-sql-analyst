import { Link, Route, Routes } from "react-router";

import { RequireAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AboutPage } from "./pages/AboutPage";
import { AskPage } from "./pages/AskPage";
import { DictionaryPage } from "./pages/DictionaryPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { HistoryPage, RunPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";
import { RecordedRunPage, RecordedRunsPage } from "./pages/RecordedPage";

function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="mt-3 inline-block text-accent hover:underline">
        Back to Ask
      </Link>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* Public: readable without signing in (recorded runs D048, evaluation and about D050). */}
      <Route element={<Layout />}>
        <Route path="recorded" element={<RecordedRunsPage />} />
        <Route path="recorded/:runId" element={<RecordedRunPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="about" element={<AboutPage />} />
      </Route>
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<AskPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="history/:runId" element={<RunPage />} />
        <Route path="dictionary" element={<DictionaryPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
