import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { FadeIn, Card } from "../components/ui";

function PageImg({ id, n }: { id: number; n: number }) {
  const box = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string>();
  const [err, setErr] = useState(false);
  useEffect(() => {
    let url: string | undefined, dead = false;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        io.disconnect();
        api.get(`/materials/${id}/pages/${n}`, { responseType: "blob" })
          .then((r) => { if (!dead) { url = URL.createObjectURL(r.data); setSrc(url); setErr(false); } })
          .catch(() => { if (!dead) setErr(true); });
      } else {
        if (url) { URL.revokeObjectURL(url); url = undefined; }
        if (!dead) setSrc(undefined);
      }
    }, { rootMargin: "800px" });
    if (box.current) io.observe(box.current);
    return () => { dead = true; io.disconnect(); if (url) URL.revokeObjectURL(url); };
  }, [id, n]);

  const retry = () => { setErr(false); setSrc(undefined); };

  return (
    <div ref={box} className="aspect-[1/1.414] bg-white rounded-2xl shadow-sm mb-4 flex items-center justify-center border border-slate-100 overflow-hidden">
      {err ? (
        <div className="text-center space-y-3">
          <p className="text-sm text-red-500">Failed to load page {n}</p>
          <button onClick={retry} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">Retry</button>
        </div>
      ) : src ? (
        <img src={src} draggable={false} className="w-full h-full object-contain select-none" alt={`Page ${n}`} />
      ) : (
        <span className="text-sm text-slate-400 flex items-center gap-2">
          <span className="w-4 h-4 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          Loading page {n}…
        </span>
      )}
    </div>
  );
}

export default function Reader() {
  const { slug } = useParams();
  const [course, setCourse] = useState<any>(null);
  const [topic, setTopic] = useState<any>(null);
  const [mats, setMats] = useState<any[]>([]);
  const [mat, setMat] = useState<any>(null);
  const [err, setErr] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => { api.get(`/courses/${slug}`).then((r) => setCourse(r.data)).catch(() => setErr("Course not found")); }, [slug]);

  const openTopic = (t: any) => {
    setTopic(t); setMat(null); setErr(""); setDrawerOpen(false);
    api.get(`/topics/${t.id}/materials`).then((r) => setMats(r.data))
      .catch((e) => { setMats([]); setErr(e.response?.status === 403 ? "You are not enrolled in this course." : "Failed to load materials"); });
  };

  if (!course) return <div className="text-center py-20 text-slate-500">{err || "Loading…"}</div>;

  const topics = [...(course.topics ?? [])].sort((a: any, b: any) => a.position - b.position);

  const sidebar = (
    <Card className="p-5" hover={false}>
      <h2 className="font-bold text-xl mb-1">{course.title}</h2>
      <p className="text-sm text-slate-500 mb-4">{topics.length} topics</p>
      <div className="space-y-1.5">
        {topics.map((t: any, i: number) => (
          <button key={t.id} onClick={() => openTopic(t)}
            className={`block w-full text-left px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200 ${topic?.id === t.id ? "bg-blue-600 text-white shadow-md" : "hover:bg-slate-100 text-slate-700"}`}>
            <span className={`mr-2 ${topic?.id === t.id ? "text-white/70" : "text-slate-400"}`}>{i + 1}.</span>{t.title}
          </button>
        ))}
      </div>
    </Card>
  );

  return (
    <div className="relative" onContextMenu={(e) => e.preventDefault()}>
      {/* Mobile drawer toggle */}
      <button onClick={() => setDrawerOpen(!drawerOpen)} className="lg:hidden fixed bottom-6 left-6 z-50 w-12 h-12 bg-blue-600 text-white rounded-full shadow-lg flex items-center justify-center hover:bg-blue-700 transition-colors">
        <span className="text-xl">{drawerOpen ? "×" : "≡"}</span>
      </button>

      {/* Mobile overlay */}
      {drawerOpen && <div className="lg:hidden fixed inset-0 bg-black/40 z-40" onClick={() => setDrawerOpen(false)} />}

      <div className="grid lg:grid-cols-4 gap-6">
        {/* Desktop sidebar */}
        <div className="hidden lg:block lg:col-span-1">
          <FadeIn><div className="sticky top-20">{sidebar}</div></FadeIn>
        </div>

        {/* Mobile sidebar drawer */}
        <div className={`lg:hidden fixed top-0 left-0 h-full w-[min(20rem,78vw)] z-50 transform transition-transform duration-300 ${drawerOpen ? "translate-x-0" : "-translate-x-full"}`}>
          <div className="h-full overflow-y-auto bg-slate-50 p-4 pt-16">{sidebar}</div>
        </div>

        <section className="lg:col-span-3">
          {err && <div className="bg-red-50 border border-red-200 text-red-600 rounded-2xl px-5 py-4 mb-4 flex items-center gap-2"><span>⚠</span>{err}</div>}
          {!mat ? (
            <div>
              {!topic && <Card className="text-center py-16" hover={false}><div className="text-5xl mb-3 animate-float"></div><p className="text-slate-500">Select a topic to view materials</p></Card>}
              {topic && mats.length === 0 && !err && <Card className="text-center py-16" hover={false}><div className="text-5xl mb-3 animate-float">📭</div><p className="text-slate-500">No materials in this topic yet.</p></Card>}
              <div className="space-y-3">
                {mats.map((m, i) => (
                  <FadeIn key={m.id} delay={i * 100}>
                    <button onClick={() => setMat(m)} className="w-full text-left bg-white border border-slate-200 rounded-2xl p-6 hover:shadow-xl hover:-translate-y-1 hover:border-blue-200 transition-all duration-300 group flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center text-xl group-hover:scale-110 transition-transform"></div>
                        <div>
                          <span className="font-bold text-lg text-slate-900 group-hover:text-blue-600 transition-colors">{m.title}</span>
                          <span className="block text-sm text-slate-500 mt-1">{m.page_count} pages</span>
                        </div>
                      </div>
                      <span className="text-blue-600 text-2xl group-hover:translate-x-2 transition-transform duration-300">→</span>
                    </button>
                  </FadeIn>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto">
              <button onClick={() => setMat(null)} className="flex items-center gap-2 text-blue-600 font-semibold mb-6 hover:gap-3 transition-all group">
                <span className="group-hover:-translate-x-1 transition-transform">←</span> Back to materials
              </button>
              <h2 className="text-3xl font-bold mb-2">{mat.title}</h2>
              <p className="text-sm text-slate-500 mb-8">{mat.page_count} pages</p>
              {Array.from({ length: mat.page_count }, (_, i) => <PageImg key={`${mat.id}-${i}`} id={mat.id} n={i + 1} />)}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
