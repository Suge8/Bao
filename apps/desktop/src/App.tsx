import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { AppShell } from "@/components/layout/app-shell";
import ChatPage from "@/pages/chat";
import TasksPage from "@/pages/tasks";
import DimsumsPage from "@/pages/dimsums";
import MemoryPage from "@/pages/memory";
import SettingsPage from "@/pages/settings";

function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      className="h-full"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

function AnimatedOutlet({ element, path }: { element: React.ReactNode; path: string }) {
  return (
    <AnimatePresence mode="wait">
      <PageTransition key={path}>{element}</PageTransition>
    </AnimatePresence>
  );
}

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <AnimatedOutlet path="/" element={<ChatPage />} /> },
      {
        path: "/tasks",
        element: <AnimatedOutlet path="/tasks" element={<TasksPage />} />,
      },
      {
        path: "/dimsums",
        element: <AnimatedOutlet path="/dimsums" element={<DimsumsPage />} />,
      },
      {
        path: "/memory",
        element: <AnimatedOutlet path="/memory" element={<MemoryPage />} />,
      },
      {
        path: "/settings",
        element: <AnimatedOutlet path="/settings" element={<SettingsPage />} />,
      },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
