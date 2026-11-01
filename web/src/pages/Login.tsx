import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errMsg } from "../api";
import { googleSignInEnabled, mountGoogleButton } from "../google";
import { useAuth } from "../store";
import { useToast } from "../components/Toast";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const googleRef = useRef<HTMLDivElement>(null);
  const { setTokens, setUser } = useAuth();
  const nav = useNavigate();
  const toast = useToast();

  useEffect(() => {
    if (!googleSignInEnabled || !googleRef.current) return;
    return mountGoogleButton(
      googleRef.current,
      () => { toast.add("Signed in with Google!", "success"); nav("/dashboard"); },
      (message) => toast.add(message, "error"),
    );
  }, [nav, toast]);

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true);
    try {
      const form = new URLSearchParams({ username: email, password });
      const { data } = await api.post("/auth/login", form);
      setTokens(data.access_token, data.refresh_token);
      const me = await api.get("/auth/me");
      setUser(me.data);
      toast.add("Welcome back!", "success");
      // The admin panel is a separate sign-in with its own tokens; a student
      // session has no way into it, so nobody is sent there from here.
      nav("/dashboard");
    } catch (e) { toast.add(errMsg(e), "error"); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50 via-white to-sky-50" />
      <div className="absolute top-20 left-[10%] w-72 h-72 bg-blue-200/30 rounded-full blur-3xl animate-float" />
      <div className="absolute bottom-20 right-[10%] w-96 h-96 bg-sky-200/30 rounded-full blur-3xl animate-float" style={{ animationDelay: "1s" }} />

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2 mb-6 group">
            <img src="/logo.png" alt="GyanSankalp" className="h-12 w-auto group-hover:scale-110 transition-transform duration-300" />
          </Link>
          <h1 className="text-3xl font-bold">Welcome back</h1>
          <p className="text-slate-500 mt-2">Login to continue your learning journey</p>
        </div>

        <div className="bg-white/80 backdrop-blur-xl border border-white/40 rounded-3xl p-8 shadow-2xl">
          <form onSubmit={submit} className="space-y-5">
            <div className="space-y-1.5">
              <label className="block text-sm font-semibold text-slate-700">Email</label>
              <input className="w-full border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <label className="block text-sm font-semibold text-slate-700">Password</label>
              <input className="w-full border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" type="password" placeholder="Enter your password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            <button disabled={busy} className="w-full py-3.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 transition-all duration-200">
              {busy ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Logging in…
                </span>
              ) : "Login"}
            </button>
          </form>
          {googleSignInEnabled && (
            <div className="mt-6 space-y-4">
              <div className="flex items-center gap-3">
                <span className="h-px flex-1 bg-slate-200" />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">or</span>
                <span className="h-px flex-1 bg-slate-200" />
              </div>
              <div ref={googleRef} className="flex justify-center" />
            </div>
          )}
          <p className="text-center text-sm text-slate-500 mt-6">No account? <Link className="text-blue-600 font-semibold hover:underline" to="/register">Sign up</Link></p>
        </div>
      </div>
    </div>
  );
}
