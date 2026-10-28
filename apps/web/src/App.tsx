import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "@/api/client";
import type { Profile } from "@/api/types";
import { Layout } from "@/components/Layout";
import { Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";

// Route-level code splitting (spec §14 performance budget).
const AuthPages = lazy(() => import("@/pages/AuthPages"));
const Onboarding = lazy(() => import("@/pages/Onboarding"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Jobs = lazy(() => import("@/pages/Jobs"));
const JobDetail = lazy(() => import("@/pages/JobDetail"));
const Documents = lazy(() => import("@/pages/Documents"));
const ResumeStudio = lazy(() => import("@/pages/ResumeStudio"));
const ApplicationWorkspace = lazy(() => import("@/pages/ApplicationWorkspace"));
const Tracker = lazy(() => import("@/pages/Tracker"));
const InboxPage = lazy(() => import("@/pages/Inbox"));
const InterviewPrep = lazy(() => import("@/pages/InterviewPrep"));
const Analytics = lazy(() => import("@/pages/Analytics"));
const ProfilePage = lazy(() => import("@/pages/Profile"));
const Integrations = lazy(() => import("@/pages/Integrations"));
const SettingsPage = lazy(() => import("@/pages/Settings"));
const Notifications = lazy(() => import("@/pages/Notifications"));

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Checking your session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

/** Sends users who have not finished onboarding to the (resumable) wizard. */
function RequireOnboarded({ children }: { children: ReactNode }) {
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => api.get<Profile>("/api/profile") });
  if (profile.isLoading) return <Spinner />;
  if (profile.data && !profile.data.onboarding_completed) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={<AuthPages mode="login" />} />
        <Route path="/register" element={<AuthPages mode="register" />} />
        <Route path="/forgot-password" element={<AuthPages mode="forgot" />} />
        <Route path="/reset-password" element={<AuthPages mode="reset" />} />
        <Route path="/verify-email" element={<AuthPages mode="verify" />} />
        <Route
          path="/onboarding"
          element={
            <RequireAuth>
              <Onboarding />
            </RequireAuth>
          }
        />
        <Route
          element={
            <RequireAuth>
              <RequireOnboarded>
                <Layout />
              </RequireOnboarded>
            </RequireAuth>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="jobs/:jobId" element={<JobDetail />} />
          <Route path="documents" element={<Documents />} />
          <Route path="documents/:docId" element={<ResumeStudio />} />
          <Route path="applications/:appId" element={<ApplicationWorkspace />} />
          <Route path="tracker" element={<Tracker />} />
          <Route path="inbox" element={<InboxPage />} />
          <Route path="interview-prep" element={<InterviewPrep />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="integrations" element={<Integrations />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
