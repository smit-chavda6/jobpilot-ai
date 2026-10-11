import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import { AppLayout } from "./components/layout/AppLayout";
import { DashboardView } from "./pages/DashboardView";
import { JobsView } from "./pages/JobsView";
import { TrackerView } from "./pages/TrackerView";
import { ResumeStudioView } from "./pages/ResumeStudioView";
import { AnalyticsView } from "./pages/AnalyticsView";
import { SettingsView } from "./pages/SettingsView";
import { ComponentGalleryView } from "./pages/ComponentGalleryView";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<DashboardView />} />
              <Route path="/jobs" element={<JobsView />} />
              <Route path="/tracker" element={<TrackerView />} />
              <Route path="/resumes" element={<ResumeStudioView />} />
              <Route path="/analytics" element={<AnalyticsView />} />
              <Route path="/settings" element={<SettingsView />} />
              <Route path="/gallery" element={<ComponentGalleryView />} />
              <Route path="/interviews" element={<Navigate to="/tracker" replace />} />
              <Route path="/integrations" element={<Navigate to="/settings" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
