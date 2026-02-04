import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "@/components/layout/app-shell";
import ChatPage from "@/pages/chat";
import TasksPage from "@/pages/tasks";
import DimsumsPage from "@/pages/dimsums";
import MemoryPage from "@/pages/memory";
import SettingsPage from "@/pages/settings";

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <ChatPage /> },
      { path: "/tasks", element: <TasksPage /> },
      { path: "/dimsums", element: <DimsumsPage /> },
      { path: "/memory", element: <MemoryPage /> },
      { path: "/settings", element: <SettingsPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
