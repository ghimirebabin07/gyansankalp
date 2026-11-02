import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errMsg } from "../api";
import { useAuth } from "../store";
import { useToast } from "../components/Toast";
import { FadeIn, Card, Skeleton } from "../components/ui";
import type { Course } from "./Courses";

export default function Dashboard() {
  const { user, setUser } = useAuth();
  const [list, setList] = useState<Course[] | null>(null);
  const [sending, setSending] = useState(false);
  const toast = useToast();
  useEffect(() => {
    api.get("/me/courses").then((r) => setList(r.data)).catch(() => setList([]));
    // The confirmation link may be opened elsewhere, so ask rather than trust
    // the copy of the user kept in this browser.
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {});
  }, [setUser]);

  const resend = async () => {
    if (!user) return;
    setSending(true);
    try {
      await api.post("/auth/resend-verification", { email: user.email });
      toast.add("A new confirmation link is on its way.", "success");
    } catch (e) { toast.add(errMsg(e), "error"); } finally { setSending(false); }
  };

  return (
    <div>
      <FadeIn>
        <div className="relative overflow-hidden bg-blue-600 rounded-2xl p-6 sm:p-10 mb-10">
          <div className="absolute top-0 right-0 w-64 h-64 bg-white/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
          <div className="relative">
            <h1 className="text-2xl sm:text-3xl font-bold text-white">Welcome back{user ? `, ${user.full_name}` : ""}!</h1>
            <p className="mt-2 text-blue-100 text-lg">Continue your learning journey.</p>
          </div>
        </div>
      </FadeIn>

      {user && !user.email_verified && (
        <FadeIn delay={120}>
          <Card className="p-5 mb-8 border-blue-200 bg-blue-50/70" hover={false}>
            <div className="flex flex-col sm:flex-row sm:items-center gap-4">
              <span className="w-11 h-11 rounded-xl bg-white border border-blue-200 flex items-center justify-center text-blue-600 shrink-0">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="m2 7 10 6 10-6" />
                </svg>
              </span>
              <div className="flex-1">
                <h3 className="font-bold text-slate-900">Confirm your email address</h3>
                <p className="text-sm text-slate-600 mt-0.5">
                  We sent a link to <span className="font-semibold text-slate-800">{user.email}</span>. Enrolling stays locked until you click it.
                </p>
              </div>
              <button onClick={resend} disabled={sending}
                className="px-5 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 hover:shadow-md hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 transition-all duration-200">
                {sending ? "Sending…" : "Resend link"}
              </button>
            </div>
          </Card>
        </FadeIn>
      )}

      <FadeIn delay={200}>
        <h2 className="text-2xl font-bold mb-6">My Courses</h2>
      </FadeIn>

      {!list ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-2xl border p-6 space-y-4">
              <Skeleton className="w-12 h-12 rounded-xl" />
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          ))}
        </div>
      ) : list.length === 0 ? (
        <FadeIn delay={300}>
          <Card className="text-center py-16" hover={false}>
            <div className="text-6xl mb-4 animate-float">📚</div>
            <h3 className="font-bold text-xl mb-2">No courses yet</h3>
            <p className="text-slate-500 mb-6">Request enrollment in a course to get started.</p>
            <Link to="/courses" className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 hover:scale-105 transition-all">
              Browse Courses <span>→</span>
            </Link>
          </Card>
        </FadeIn>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {list.map((c, i) => (
            <FadeIn key={c.id} delay={i * 100}>
              <Card className="p-6 h-full group">
                <div className="w-14 h-14 bg-blue-100 rounded-2xl flex items-center justify-center text-2xl mb-4 group-hover:scale-110 transition-all duration-300"></div>
                <h3 className="font-bold text-xl mb-2 text-slate-900 group-hover:text-blue-600 transition-colors">{c.title}</h3>
                <p className="text-sm text-slate-500 line-clamp-2 mb-6">{c.description}</p>
                <Link to={`/learn/${c.slug}`} className="inline-flex items-center gap-1 text-blue-600 font-semibold group-hover:gap-2 transition-all">
                  Continue learning <span>→</span>
                </Link>
              </Card>
            </FadeIn>
          ))}
        </div>
      )}
    </div>
  );
}
