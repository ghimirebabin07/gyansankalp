import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, errMsg } from "../api";
import { useAuth } from "../store";
import { FadeIn, Card } from "../components/ui";
import { useToast } from "../components/Toast";

export default function CourseDetail() {
  const { slug } = useParams();
  const { access } = useAuth();
  const [c, setC] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  useEffect(() => { api.get(`/courses/${slug}`).then((r) => setC(r.data)).catch(() => setC(null)); }, [slug]);

  const isFree = c.price_npr === 0;

  const enroll = async () => {
    setBusy(true);
    try {
      await api.post("/enrollments", null, { params: { course_id: c.id } });
      toast.add(isFree ? "Enrolled! Start learning now." : "Enrollment request sent! Admin will review shortly.", "success");
    } catch (e) { toast.add(errMsg(e), "error"); } finally { setBusy(false); }
  };

  if (!c) return (
    <div className="text-center py-20">
      <div className="text-6xl mb-4 animate-float">😕</div>
      <h2 className="text-2xl font-bold mb-2">Course not found</h2>
      <Link to="/courses" className="inline-flex items-center gap-1 text-blue-600 font-semibold hover:gap-2 transition-all">← Back to courses</Link>
    </div>
  );

  const topics = [...(c.topics ?? [])].sort((a: any, b: any) => a.position - b.position);

  return (
    <div className="grid lg:grid-cols-3 gap-8">
      <FadeIn className="lg:col-span-2">
        <Card className="p-8" hover={false}>
          <h1 className="text-4xl font-bold">{c.title}</h1>
          <p className="mt-4 text-slate-600 leading-relaxed text-lg whitespace-pre-line">{c.description}</p>

          {c.syllabus && (
            <div className="mt-10">
              <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
                <span className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center">📚</span>
                Syllabus
              </h2>
              <div className="bg-blue-50 border border-blue-100 rounded-2xl p-6">
                <p className="text-slate-700 leading-relaxed whitespace-pre-line">{c.syllabus}</p>
              </div>
            </div>
          )}

          <div className="mt-10">
            <h2 className="text-2xl font-bold mb-6 flex items-center gap-3">
              <span className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center">📋</span>
              Course Topics
            </h2>
            {topics.length === 0 ? (
              <p className="text-slate-500 italic">Topics will be added soon.</p>
            ) : (
              <ol className="space-y-3">
                {topics.map((t: any, i: number) => (
                  <li key={t.id} className="flex items-center gap-4 bg-slate-50 rounded-2xl px-5 py-4 border border-slate-100 hover:border-blue-200 hover:shadow-md transition-all duration-300 group">
                    <span className="w-10 h-10 bg-blue-600 text-white rounded-xl flex items-center justify-center text-sm font-bold shadow-md group-hover:scale-110 transition-transform">{i + 1}</span>
                    <span className="font-semibold text-lg">{t.title}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </Card>
      </FadeIn>

      <FadeIn delay={200} className="lg:col-span-1">
        <div className="sticky top-20 space-y-4">
          <Card className="p-6" hover={false}>
            <div className="text-center pb-5 border-b border-slate-100">
              <p className="text-sm text-slate-500 font-medium">Course Price</p>
              <p className="text-5xl font-bold text-blue-600 mt-2">{isFree ? "FREE" : `NPR ${c.price_npr}`}</p>
            </div>

            <div className="mt-5 space-y-3">
              {access ? (
                <button onClick={enroll} disabled={busy}
                  className="w-full py-3.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 hover:shadow-lg transition-all duration-200 flex items-center justify-center gap-2">
                  {busy ? <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Sending…</> : <>{isFree ? "Enroll Now" : "Request Enrollment"} <span>→</span></>}
                </button>
              ) : (
                <Link to="/login" className="block w-full text-center py-3.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 transition-all duration-200">
                  Login to Enroll
                </Link>
              )}

              <Link to={access ? `/learn/${c.slug}` : "/login"}
                className="block w-full text-center py-3.5 rounded-xl border-2 border-blue-600 text-blue-600 font-semibold hover:bg-blue-50 transition-all duration-200">
                {access ? "Open Course" : "Login to Continue"}
              </Link>
            </div>

            <div className="mt-5 pt-4 border-t border-slate-100">
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <span className={isFree ? "text-green-500" : "text-blue-500"}>{isFree ? "✓" : "⏳"}</span>
                {isFree ? "Free course — instant access" : "Access granted after admin approval"}
              </div>
            </div>
          </Card>
        </div>
      </FadeIn>
    </div>
  );
}
