import { lazy, Suspense } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Spinner } from "./components/ui";
import { useSession } from "./hooks/useSession";
import { AppLayout } from "./layouts/AppLayout";
import { AuthPage } from "./pages/AuthPage";

const Overview = lazy(() => import("./pages/Overview"));
const NewInspection = lazy(() => import("./pages/NewInspection"));
const History = lazy(() => import("./pages/History"));
const InspectionWorkspace = lazy(() => import("./pages/InspectionWorkspace"));
const Comparison = lazy(() => import("./pages/Comparison"));
const DefectAnalysis = lazy(() => import("./pages/DefectAnalysis"));
const Reports = lazy(() => import("./pages/Reports"));
const Analytics = lazy(() => import("./pages/Analytics"));
const ModelInfo = lazy(() => import("./pages/ModelInfo"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function Protected() {
  const { user, ready } = useSession();
  const location = useLocation();
  if (!ready) return <Spinner label="Restoring your session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <AppLayout />;
}

function NotFound() {
  return (
    <div className="p-10 text-center">
      <h1 className="text-lg">Page not found</h1>
      <Link to="/" className="mt-2 inline-block text-sm text-accent">Back to Overview</Link>
    </div>
  );
}

export function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route element={<Protected />}>
          <Route path="/" element={<Overview />} />
          <Route path="/inspections/new" element={<NewInspection />} />
          <Route path="/inspections" element={<History />} />
          <Route path="/inspections/:projectId" element={<InspectionWorkspace />} />
          <Route path="/comparison" element={<Comparison />} />
          <Route path="/comparison/:comparisonId" element={<Comparison />} />
          <Route path="/defects" element={<DefectAnalysis />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/models" element={<ModelInfo />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
