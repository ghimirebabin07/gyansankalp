import axios from "axios";
import { useAdminAuth } from "./adminStore";

const base = import.meta.env.VITE_API_URL;
export const adminApi = axios.create({ baseURL: base });

declare module "axios" {
  export interface AxiosRequestConfig {
    // Set on the one request a renewal already replayed, so a still-refused call
    // cannot loop into a new renewal.
    retried?: boolean;
  }
}

adminApi.interceptors.request.use((c) => {
  const t = useAdminAuth.getState().access;
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});

// The sign-in endpoints answer 401 for their own reasons - a wrong code, a spent
// challenge - and there is no session to renew yet, so they must not trigger one.
const isAuthCall = (url = "") => url.includes("/admin/auth/");

async function renew(): Promise<string> {
  const refresh = useAdminAuth.getState().refresh;
  if (!refresh) throw new Error("This session has ended");
  const { data } = await axios.post(`${base}/admin/auth/refresh`, {
    refresh_token: refresh,
  });
  useAdminAuth.getState().setTokens(data.access_token, data.refresh_token);
  return data.access_token;
}

// Several requests can age out at the same moment; they share one renewal.
let renewing: Promise<string> | null = null;
const renewOnce = () => (renewing ??= renew().finally(() => { renewing = null; }));

adminApi.interceptors.response.use((r) => r, async (err) => {
  const config = err.config;
  if (err.response?.status === 401 && !isAuthCall(config?.url) && !config?.retried) {
    // An access token lives fifteen minutes and a working day is spanned by the
    // refresh token, so the panel should not ask a person to fetch a new code
    // because a token aged out mid-edit.
    try {
      config.retried = true;
      config.headers.Authorization = `Bearer ${await renewOnce()}`;
      return await adminApi.request(config);
    } catch (renewFailure: any) {
      // A refused renewal is the backend saying this session was revoked.
      const refused = renewFailure?.response?.status === 401;
      if (!refused) return Promise.reject(err);
      useAdminAuth.getState().logout();
      window.location.href = "/admin/login";
      return Promise.reject(err);
    }
  }
  // A 403 is a role answering, not a session failing. The panel shows the reason
  // and stays signed in, because signing out would hide what was refused.
  return Promise.reject(err);
});

export const errMsg = (e: any): string => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  return "Something went wrong";
};
