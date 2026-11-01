import { create } from "zustand";
import { persist } from "zustand/middleware";

export type User = {
  id: number | string; full_name: string; email: string;
  phone: string | null; role: "student" | "admin";
  email_verified: boolean;
};
type S = {
  user: User | null; access: string | null; refresh: string | null;
  setTokens: (a: string, r: string) => void;
  setUser: (u: User) => void;
  logout: () => void;
};
export const useAuth = create<S>()(persist(
  (set) => ({
    user: null, access: null, refresh: null,
    setTokens: (access, refresh) => set({ access, refresh }),
    setUser: (user) => set({ user }),
    logout: () => set({ user: null, access: null, refresh: null }),
  }),
  { name: "auth" }
));
