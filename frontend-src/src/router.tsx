import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/layouts/AppShell";
import { RecordingsList } from "@/pages/app/RecordingsList";
import { RecordingNew } from "@/pages/app/RecordingNew";
import { RecordingDetail } from "@/pages/app/RecordingDetail";
import { Tasks } from "@/pages/app/Tasks";
import { Hotwords } from "@/pages/app/Hotwords";
import { Voiceprints } from "@/pages/app/Voiceprints";
import { Settings } from "@/pages/app/Settings";
import { NotFound } from "@/pages/NotFound";

// Single-user desktop build: no login, no admin console. The app boots straight
// into the workspace; the backend always resolves the one local user.
export const router = createBrowserRouter([
  {
    path: "/",
    element: <Navigate to="/app/recordings/new" replace />,
  },
  {
    path: "/app",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/app/recordings/new" replace /> },
      { path: "workspace", element: <Navigate to="/app/recordings/new" replace /> },
      { path: "recordings", element: <RecordingsList /> },
      { path: "recordings/new", element: <RecordingNew /> },
      { path: "recordings/:id", element: <RecordingDetail /> },
      { path: "tasks", element: <Tasks /> },
      { path: "hotwords", element: <Hotwords /> },
      { path: "voiceprints", element: <Voiceprints /> },
      { path: "settings", element: <Settings /> },
    ],
  },
  {
    path: "*",
    element: <NotFound />,
  },
]);
