import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errMsg } from "../api";
import { useAuth } from "../store";
import { useToast } from "../components/Toast";

type State = { kind: "working" } | { kind: "done" } | { kind: "failed", message: string };

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState<State>(() => token
    ? { kind: "working" }
    : { kind: "failed", message: "This link does not carry a confirmation code." });
  const { user, setUser } = useAuth();
  const toast = useToast();

  useEffect(() => {
    if (!token) return;
    let active = true;
    api.post("/auth/verify-email", { token })
      .then((r) => active && (setUser(r.data), setState({ kind: "done" })))
      .catch((e) => active && setState({ kind: "failed", message: errMsg(e) }));
    return () => { active = false; };
  }, [token, setUser]);

  const resend = async () => {
    if (!user) return;
    try {
      await api.post("/auth/resend-verification", { email: user.email });
      toast.add("A new confirmation link is on its way.", "success");
    } catch (e) { toast.add(errMsg(e), "error"); }
  };

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50 via-white to-sky-50 -z-10" />
      <div className="absolute top-16 left-[15%] w-72 h-72 bg-blue-200/30 rounded-full blur-3xl animate-float -z-10" />

      <div className="relative w-full max-w-md bg-white/80 backdrop-blur-xl border border-white/40 rounded-3xl p-8 shadow-2xl text-center">
        {state.kind === "working" && (
          <>
            <span className="mx-auto mb-5 block w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            <h1 className="text-2xl font-bold">Confirming your email…</h1>
            <p className="text-slate-500 mt-2">This only takes a moment.</p>
          </>
        )}

        {state.kind === "done" && (
          <>
            <div className="mx-auto mb-5 w-16 h-16 rounded-2xl bg-emerald-100 flex items-center justify-center text-3xl">✓</div>
            <h1 className="text-2xl font-bold">Email confirmed</h1>
            <p className="text-slate-500 mt-2">Your address is verified. Courses are unlocked for you.</p>
            <Link to="/dashboard" className="mt-6 inline-flex w-full items-center justify-center gap-2 py-3.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-all duration-200">
              Go to my courses <span>→</span>
            </Link>
          </>
        )}

        {state.kind === "failed" && (
          <>
            <div className="mx-auto mb-5 w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center text-3xl">!</div>
            <h1 className="text-2xl font-bold">We could not confirm it</h1>
            <p className="text-slate-500 mt-2">{state.message}</p>
            <div className="mt-6 space-y-3">
              {user && (
                <button onClick={resend} className="w-full py-3.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-all duration-200">
                  Send me a new link
                </button>
              )}
              <Link to={user ? "/dashboard" : "/login"} className="block text-sm text-slate-500 hover:text-blue-600 transition-colors">
                {user ? "Back to my courses" : "Login first"}
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
