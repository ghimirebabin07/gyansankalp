import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errMsg } from "../api";
import { googleSignInEnabled, mountGoogleButton } from "../google";
import { useAuth } from "../store";
import { useToast } from "../components/Toast";

export default function Register() {
  const [f, setF] = useState({ full_name: "", email: "", phone: "", password: "" });
  const [busy, setBusy] = useState(false);
  const googleRef = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  const toast = useToast();
  const { setTokens, setUser, logout } = useAuth();
  const passwordRef = useRef("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    if (k === "password") passwordRef.current = e.target.value;
    setF({ ...f, [k]: e.target.value });
  };
  // Google only signs this student up once they have chosen a password, so a
  // Gmail-only account can also be entered by typing the address.
  const hasPassword = f.password.trim().length >= 8;

  useEffect(() => {
    if (!googleSignInEnabled || !hasPassword || !googleRef.current) return;
    return mountGoogleButton(
      googleRef.current,
      ({ created }) => {
        if (created) { toast.add("Welcome! You are signed in.", "success"); nav("/dashboard"); return; }
        logout();
        toast.add("This Gmail is already registered. Please login.", "error");
        nav("/login");
      },
      (message) => toast.add(message, "error"),
      () => passwordRef.current,
    );
  }, [nav, toast, logout, hasPassword]);

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true);
    try {
      await api.post("/auth/register", { ...f, phone: f.phone || null });
      // Signed in straight away so the "confirm your email" notice can appear
      // on the dashboard instead of leaving the student at a login screen.
      const form = new URLSearchParams({ username: f.email, password: f.password });
      const { data } = await api.post("/auth/login", form);
      setTokens(data.access_token, data.refresh_token);
      const me = await api.get("/auth/me");
      setUser(me.data);
      toast.add("Account created! Check your email to confirm your address.", "success");
      nav("/dashboard");
    } catch (e) { toast.add(errMsg(e), "error"); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-sky-50 via-white to-blue-50" />
      <div className="absolute top-20 right-[10%] w-72 h-72 bg-sky-200/30 rounded-full blur-3xl animate-float" />
      <div className="absolute bottom-20 left-[10%] w-96 h-96 bg-blue-200/30 rounded-full blur-3xl animate-float" style={{ animationDelay: "1s" }} />

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2 mb-6 group">
            <img src="/logo.png" alt="GyanSankalp" className="h-12 w-auto group-hover:scale-110 transition-transform duration-300" />
          </Link>
          <h1 className="text-3xl font-bold">Create your account</h1>
          <p className="text-slate-500 mt-2">Start your learning journey today</p>
        </div>

        <div className="bg-white/80 backdrop-blur-xl border border-white/40 rounded-3xl p-8 shadow-2xl">
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-sm font-semibold text-slate-700">Full Name</label>
              <input className="w-full border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" placeholder="Your full name" value={f.full_name} onChange={set("full_name")} required />
            </div>
            <div className="space-y-1.5">
              <label className="block text-sm font-semibold text-slate-700">Email</label>
              <input className="w-full border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" type="email" placeholder="you@example.com" value={f.email} onChange={set("email")} required />
            </div>
            <div className="space-y-1.5">
              <label className="block text-sm font-semibold text-slate-700">Phone <span className="font-normal text-slate-400">(optional)</span></label>
              <input className="w-full border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" placeholder="98XXXXXXXX" value={f.phone} onChange={set("phone")} />
            </div>
            <div className="space-y-1.5">
              <label className="block text-sm font-semibold text-slate-700">Password</label>
              <input className="w-full border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" type="password" placeholder="Min 8 characters" value={f.password} onChange={set("password")} required minLength={8} />
            </div>
            <button disabled={busy} className="w-full py-3.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 transition-all duration-200">
              {busy ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Creating…
                </span>
              ) : "Create Account"}
            </button>
          </form>
          {googleSignInEnabled && (
            <div className="mt-6 space-y-4">
              <div className="flex items-center gap-3">
                <span className="h-px flex-1 bg-slate-200" />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">or</span>
                <span className="h-px flex-1 bg-slate-200" />
              </div>
              {hasPassword ? (
                <div ref={googleRef} className="flex justify-center" />
              ) : (
                <p className="text-center text-xs text-slate-500">
                  Choose a password above to sign up with Google.
                </p>
              )}
            </div>
          )}
          <p className="text-center text-sm text-slate-500 mt-6">Have an account? <Link className="text-blue-600 font-semibold hover:underline" to="/login">Login</Link></p>
        </div>
      </div>
    </div>
  );
}
