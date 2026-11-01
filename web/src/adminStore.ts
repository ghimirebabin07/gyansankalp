import { create } from "zustand";
import { persist } from "zustand/middleware";

export type AdminRole = "super_admin" | "content_manager" | "editor";
export type Admin = {
  id: number; email: string; full_name: string;
  role: AdminRole; is_active: boolean; google_linked: boolean;
};

type S = {
  admin: Admin | null; access: string | null; refresh: string | null;
  setTokens: (access: string, refresh: string) => void;
  setAdmin: (admin: Admin) => void;
  logout: () => void;
};

export const useAdminAuth = create<S>()(persist(
  (set) => ({
    admin: null, access: null, refresh: null,
    setTokens: (access, refresh) => set({ access, refresh }),
    setAdmin: (admin) => set({ admin }),
    logout: () => set({ admin: null, access: null, refresh: null }),
  }),
  { name: "admin-auth" }
));
