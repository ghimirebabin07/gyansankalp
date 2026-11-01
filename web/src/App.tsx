import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./store";
import { useAdminAuth } from "./adminStore";
import Layout from "./components/Layout";
import { ToastContainer } from "./components/Toast";
import Home from "./pages/Home";
import Courses from "./pages/Courses";
import CourseDetail from "./pages/CourseDetail";
import Login from "./pages/Login";
import Register from "./pages/Register";
import VerifyEmail from "./pages/VerifyEmail";
import Dashboard from "./pages/Dashboard";
import Reader from "./pages/Reader";
import Admin from "./pages/Admin";
import AdminLogin from "./pages/AdminLogin";

function Guard({ children }: { children: ReactNode }) {
  const { access } = useAuth();
  if (!access) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AdminGuard({ children }: { children: ReactNode }) {
  const { access } = useAdminAuth();
  if (!access) return <Navigate to="/admin/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/courses" element={<Courses />} />
          <Route path="/courses/:slug" element={<CourseDetail />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/dashboard" element={<Guard><Dashboard /></Guard>} />
          <Route path="/learn/:slug" element={<Guard><Reader /></Guard>} />
          <Route path="/admin" element={<AdminGuard><Admin /></AdminGuard>} />
          <Route path="*" element={<Navigate to="/" />} />
        </Route>
      </Routes>
      <ToastContainer />
    </>
  );
}
