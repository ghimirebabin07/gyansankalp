import axios from "axios";
import { useAuth } from "./store";

const base = import.meta.env.VITE_API_URL;
export const api = axios.create({ baseURL: base });

api.interceptors.request.use((c) => {
  const t = useAuth.getState().access;
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});

// Refresh is single-use rotation: share one in-flight call.
let refreshing: Promise<string | null> | null = null;
async function doRefresh(): Promise<string | null> {
  const { refresh, setTokens, logout } = useAuth.getState();
  try {
    const { data } = await axios.post(`${base}/auth/refresh`, { refresh_token: refresh });
    setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch { logout(); return null; }
}

api.interceptors.response.use((r) => r, async (err) => {
  const orig = err.config;
  if (err.response?.status === 401 && !orig._retry && useAuth.getState().refresh) {
    orig._retry = true;
    refreshing ??= doRefresh().finally(() => (refreshing = null));
    const t = await refreshing;
    if (t) { orig.headers.Authorization = `Bearer ${t}`; return api(orig); }
  }
  return Promise.reject(err);
});

export const errMsg = (e: any): string => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  return "Something went wrong";
};
