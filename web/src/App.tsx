import { Link, Route, Routes } from "react-router";

import { RequireAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AboutPage } from "./pages/AboutPage";
import { AskPage } from "./pages/AskPage";
import { DictionaryPage } from "./pages/DictionaryPage";
import { HistoryPage, RunPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";

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
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
