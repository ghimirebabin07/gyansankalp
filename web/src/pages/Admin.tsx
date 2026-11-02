import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi, errMsg, wakeWorker } from "../adminApi";
import { useAdminAuth } from "../adminStore";
import { FadeIn, Card, Badge, Button, Input } from "../components/ui";
import { useToast } from "../components/Toast";

const MAX_FILE_SIZE = 50 * 1024 * 1024;

const statusColor = (s: string): "green" | "yellow" | "red" | "blue" | "slate" => {
  const map: Record<string, "green" | "yellow" | "red" | "blue" | "slate"> = {
    pending: "yellow", active: "green", revoked: "red", expired: "slate",
    completed: "blue", processing: "yellow", ready: "green", failed: "red",
  };
  return map[s] || "slate";
};

function ConfirmModal({ message, onConfirm, onCancel }: { message: string; onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onCancel}>
      <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-sm w-full mx-4" onClick={(e) => e.stopPropagation()}>
        <p className="text-lg font-semibold text-slate-900 mb-4">{message}</p>
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant="danger" onClick={onConfirm}>Confirm</Button>
        </div>
      </div>
    </div>
  );
}

function useConfirm() {
  const [confirmState, setConfirmState] = useState<{ message: string; resolve: ((v: boolean) => void) } | null>(null);
  const confirm = (message: string) => new Promise<boolean>((resolve) => setConfirmState({ message, resolve }));
  const modal = confirmState ? (
    <ConfirmModal
      message={confirmState.message}
      onConfirm={() => { confirmState.resolve(true); setConfirmState(null); }}
      onCancel={() => { confirmState.resolve(false); setConfirmState(null); }}
    />
  ) : null;
  return { confirm, modal };
}

/* ---------- Courses Tab ---------- */
function CoursesTab() {
  const [list, setList] = useState<any[]>([]);
  const [f, setF] = useState({ title: "", slug: "", description: "", syllabus: "", exam_level: "", price_npr: 0, is_published: false });
  const toast = useToast();
  const { confirm, modal } = useConfirm();

  const load = () => adminApi.get("/admin/courses").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);

  const run = async (fn: () => Promise<any>) => { try { await fn(); await load(); toast.add("Done", "success"); } catch (e) { toast.add(errMsg(e), "error"); } };

  return (
    <div className="space-y-6">
      {modal}
      <FadeIn>
        <Card className="p-6" hover={false}>
          <h3 className="font-bold text-xl mb-5">Create New Course</h3>
          <form className="grid sm:grid-cols-2 gap-4" onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => adminApi.post("/admin/courses", f)); }}>
            <Input placeholder="Course title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required />
            <Input placeholder="slug-like-this" pattern="^[a-z0-9]+(-[a-z0-9]+)*$" value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })} required />
            <Input type="number" placeholder="Price NPR" value={f.price_npr} onChange={(e) => setF({ ...f, price_npr: +e.target.value })} />
            <select className="border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" value={f.exam_level} onChange={(e) => setF({ ...f, exam_level: e.target.value })}>
              <option value="">Select Exam Level</option>
              <option value="kharidar">Kharidar (4th Level)</option>
              <option value="nasu">Na Su (5th Level)</option>
              <option value="officer">Officer (6th Level)</option>
            </select>
            <label className="flex items-center gap-2 px-1 text-sm"><input type="checkbox" checked={f.is_published} onChange={(e) => setF({ ...f, is_published: e.target.checked })} /> Published</label>
            <textarea className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all sm:col-span-2" placeholder="Description" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
            <textarea className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all sm:col-span-2" placeholder="Syllabus (what students will learn)" rows={4} value={f.syllabus} onChange={(e) => setF({ ...f, syllabus: e.target.value })} />
            <Button className="sm:col-span-2">Create Course</Button>
          </form>
        </Card>
      </FadeIn>

      <FadeIn delay={100}>
        <Card className="overflow-hidden" hover={false}>
          <div className="px-6 py-4 border-b border-slate-100"><h3 className="font-bold text-xl">All Courses</h3></div>
          <div className="divide-y divide-slate-100">
            {list.map((c) => (
              <div key={c.id} className="px-6 py-4 flex items-center gap-4 hover:bg-slate-50 transition-colors">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <b className="text-lg text-slate-900">{c.title}</b>
                    {c.is_published && <Badge color="green">Published</Badge>}
                    {c.exam_level && <Badge color="blue">{c.exam_level}</Badge>}
                  </div>
                  <span className="text-xs text-slate-500">#{c.id} · /{c.slug} · NPR {c.price_npr}</span>
                </div>
                <Button variant="ghost" onClick={() => run(() => adminApi.patch(`/admin/courses/${c.id}`, { is_published: !c.is_published }))}>
                  {c.is_published ? "Unpublish" : "Publish"}
                </Button>
                <Button variant="danger" onClick={async () => { if (await confirm("Delete this course? This cannot be undone.")) run(() => adminApi.delete(`/admin/courses/${c.id}`)); }}>Delete</Button>
              </div>
            ))}
            {list.length === 0 && <div className="px-6 py-12 text-center text-slate-500">No courses yet. Create one above.</div>}
          </div>
        </Card>
      </FadeIn>
    </div>
  );
}

/* ---------- Topics Tab ---------- */
function TopicsTab() {
  const [courses, setCourses] = useState<any[]>([]);
  const [topics, setTopics] = useState<Record<number, any[]>>({});
  const [selectedCourse, setSelectedCourse] = useState<number>(0);
  const [newTopic, setNewTopic] = useState("");
  const [uploadTopicId, setUploadTopicId] = useState<number | null>(null);
  const [matTitle, setMatTitle] = useState("");
  const [matFile, setMatFile] = useState<File | null>(null);
  const [topicMaterials, setTopicMaterials] = useState<Record<number, any[]>>({});
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const toast = useToast();
  const { confirm, modal } = useConfirm();
  const fileRef = useRef<HTMLInputElement>(null);

  const loadCourses = () => adminApi.get("/admin/courses").then((r) => setCourses(r.data));
  useEffect(() => { loadCourses(); }, []);

  const loadTopics = (courseId: number) => {
    if (!courseId) return;
    adminApi.get(`/courses/${courses.find((c) => c.id === courseId)?.slug}`).then((r) => {
      const tops = r.data.topics ?? [];
      setTopics((p) => ({ ...p, [courseId]: tops }));
      tops.forEach((t: any) => {
        adminApi.get(`/admin/topics/${t.id}/materials`).then((mr) => setTopicMaterials((p) => ({ ...p, [t.id]: mr.data }))).catch(() => {});
      });
    }).catch(() => {});
  };

  useEffect(() => { if (selectedCourse) loadTopics(selectedCourse); }, [selectedCourse]);

  // A cold worker takes up to a minute to boot before it claims the job, so a
  // fresh upload would otherwise sit at "pending" until the admin reloaded by
  // hand. This refreshes the list while anything is still queued.
  const somethingQueued = Object.values(topicMaterials).some((ms) =>
    ms.some((m) => m.status === "pending" || m.status === "processing"),
  );
  useEffect(() => {
    if (!somethingQueued || !selectedCourse) return;
    const timer = setInterval(() => loadTopics(selectedCourse), 5000);
    return () => clearInterval(timer);
  }, [somethingQueued, selectedCourse]);

  const addTopic = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedCourse || !newTopic) return;
    try {
      const tops = topics[selectedCourse] ?? [];
      await adminApi.post(`/admin/courses/${selectedCourse}/topics`, { title: newTopic, position: tops.length + 1 });
      setNewTopic("");
      loadTopics(selectedCourse);
      toast.add("Topic added", "success");
    } catch (e) { toast.add(errMsg(e), "error"); }
  };

  const deleteTopic = async (topicId: number) => {
    if (!(await confirm("Delete this topic? All materials in it will also be removed."))) return;
    try {
      await adminApi.delete(`/admin/topics/${topicId}`);
      loadTopics(selectedCourse);
      toast.add("Topic deleted", "success");
    } catch (e) { toast.add(errMsg(e), "error"); }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    if (file && file.size > MAX_FILE_SIZE) {
      toast.add(`File too large. Maximum size is ${MAX_FILE_SIZE / (1024 * 1024)} MB.`, "error");
      e.target.value = "";
      return;
    }
    setMatFile(file);
  };

  const uploadPdf = async (e: FormEvent) => {
    e.preventDefault();
    if (!uploadTopicId || !matFile || !matTitle) return;
    if (matFile.size > MAX_FILE_SIZE) {
      toast.add(`File too large. Maximum size is ${MAX_FILE_SIZE / (1024 * 1024)} MB.`, "error");
      return;
    }
    const fd = new FormData();
    fd.append("title", matTitle);
    fd.append("file", matFile);
    setUploading(true);
    setUploadProgress(0);
    try {
      await adminApi.post(`/admin/topics/${uploadTopicId}/materials`, fd, {
        onUploadProgress: (progressEvent) => {
          const pct = progressEvent.total ? Math.round((progressEvent.loaded * 100) / progressEvent.total) : 0;
          setUploadProgress(pct);
        },
      });
      setMatTitle("");
      setMatFile(null);
      setUploadTopicId(null);
      if (fileRef.current) fileRef.current.value = "";
      wakeWorker();
      loadTopics(selectedCourse);
      toast.add("PDF uploaded successfully", "success");
    } catch (e) { toast.add(errMsg(e), "error"); } finally { setUploading(false); setUploadProgress(0); }
  };

  const retryMaterial = async (id: number) => {
    try { await adminApi.post(`/admin/materials/${id}/retry`); wakeWorker(); loadTopics(selectedCourse); toast.add("Retry started", "info"); } catch (e) { toast.add(errMsg(e), "error"); }
  };
  const deleteMaterial = async (id: number) => {
    if (!(await confirm("Delete this material?"))) return;
    try { await adminApi.delete(`/admin/materials/${id}`); loadTopics(selectedCourse); toast.add("Material deleted", "success"); } catch (e) { toast.add(errMsg(e), "error"); }
  };

  const currentTopics = topics[selectedCourse] ?? [];

  return (
    <div className="space-y-6">
      {modal}
      {/* Select Course */}
      <FadeIn>
        <Card className="p-6" hover={false}>
          <h3 className="font-bold text-xl mb-4">Select Course</h3>
          <select className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" value={selectedCourse} onChange={(e) => setSelectedCourse(+e.target.value)}>
            <option value={0}>-- Choose a course --</option>
            {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </Card>
      </FadeIn>

      {/* Add Topic */}
      {selectedCourse > 0 && (
        <FadeIn delay={100}>
          <Card className="p-6" hover={false}>
            <h3 className="font-bold text-xl mb-4">Add Topic</h3>
            <form onSubmit={addTopic} className="flex gap-3">
              <input className="flex-1 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" placeholder="Topic title" value={newTopic} onChange={(e) => setNewTopic(e.target.value)} required />
              <Button>Add Topic</Button>
            </form>
          </Card>
        </FadeIn>
      )}

      {/* Topics List with PDF Upload */}
      {selectedCourse > 0 && currentTopics.length > 0 && (
        <FadeIn delay={200}>
          <div className="space-y-4">
            {currentTopics.map((t: any) => (
              <Card key={t.id} className="p-6" hover={false}>
                <div className="flex items-center gap-3 mb-4">
                  <span className="w-10 h-10 bg-blue-600 text-white rounded-xl flex items-center justify-center text-sm font-bold">{t.position}</span>
                  <div className="flex-1">
                    <h4 className="font-bold text-lg text-slate-900">{t.title}</h4>
                    <span className="text-xs text-slate-500">Topic ID: {t.id} · {topicMaterials[t.id]?.length ?? 0} materials</span>
                  </div>
                  <Button variant="danger" onClick={() => deleteTopic(t.id)}>Delete Topic</Button>
                </div>

                {/* Materials for this topic */}
                <div className="space-y-2 mb-4">
                  {(topicMaterials[t.id] ?? []).map((m: any) => (
                    <div key={m.id} className="flex items-center gap-3 bg-slate-50 rounded-xl px-4 py-3">
                      <span className="text-xl"></span>
                      <div className="flex-1">
                        <div className="font-medium text-sm text-slate-900">{m.title}</div>
                        <div className="text-xs text-slate-500">{m.page_count ?? "..."} pages · {m.attempts} tries</div>
                      </div>
                      <Badge color={statusColor(m.status)}>{m.status}</Badge>
                      {m.status === "failed" && <Button variant="ghost" onClick={() => retryMaterial(m.id)}>Retry</Button>}
                      <Button variant="danger" onClick={() => deleteMaterial(m.id)}>Delete</Button>
                    </div>
                  ))}
                  {(topicMaterials[t.id] ?? []).length === 0 && <p className="text-sm text-slate-500 italic px-2">No materials yet.</p>}
                </div>

                {/* Upload PDF for this topic */}
                {uploadTopicId === t.id ? (
                  <form onSubmit={uploadPdf} className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
                    <input className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" placeholder="Material title" value={matTitle} onChange={(e) => setMatTitle(e.target.value)} required />
                    <div className="flex gap-3 items-center">
                      <input ref={fileRef} type="file" accept="application/pdf" onChange={handleFileSelect} required className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm" />
                      <Button disabled={uploading}>{uploading ? "Uploading..." : "Upload"}</Button>
                      <Button variant="ghost" onClick={() => { setUploadTopicId(null); setMatTitle(""); setMatFile(null); }} disabled={uploading}>Cancel</Button>
                    </div>
                    {uploading && (
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs text-slate-500">
                          <span>Uploading...</span>
                          <span>{uploadProgress}%</span>
                        </div>
                        <div className="w-full bg-blue-100 rounded-full h-2">
                          <div className="bg-blue-600 h-2 rounded-full transition-all duration-300" style={{ width: `${uploadProgress}%` }} />
                        </div>
                      </div>
                    )}
                    <p className="text-xs text-slate-500">Maximum file size: 50 MB</p>
                  </form>
                ) : (
                  <Button variant="secondary" onClick={() => setUploadTopicId(t.id)}>+ Upload PDF</Button>
                )}
              </Card>
            ))}
          </div>
        </FadeIn>
      )}

      {selectedCourse > 0 && currentTopics.length === 0 && (
        <FadeIn delay={200}>
          <Card className="text-center py-12" hover={false}>
            <div className="text-5xl mb-3"></div>
            <p className="text-slate-500">No topics yet. Add your first topic above.</p>
          </Card>
        </FadeIn>
      )}
    </div>
  );
}

/* ---------- Materials Tab (mapping view) ---------- */
function MaterialsTab() {
  const [allMaterials, setAllMaterials] = useState<{ topic: any; course: any; material: any }[]>([]);
  const [search, setSearch] = useState("");
  const toast = useToast();
  const { confirm, modal } = useConfirm();

  const load = async () => {
    const cs = await adminApi.get("/admin/courses").then((r) => r.data);
    const mats: { topic: any; course: any; material: any }[] = [];
    for (const c of cs) {
      try {
        const courseData = await adminApi.get(`/courses/${c.slug}`).then((r) => r.data);
        for (const t of (courseData.topics ?? [])) {
          try {
            const ms = await adminApi.get(`/admin/topics/${t.id}/materials`).then((r) => r.data);
            for (const m of ms) mats.push({ topic: t, course: c, material: m });
          } catch {}
        }
      } catch {}
    }
    setAllMaterials(mats);
  };
  useEffect(() => { load(); }, []);

  const somethingQueued = allMaterials.some(
    ({ material: m }) => m.status === "pending" || m.status === "processing",
  );
  useEffect(() => {
    if (!somethingQueued) return;
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [somethingQueued]);

  const retryMaterial = async (id: number) => {
    try { await adminApi.post(`/admin/materials/${id}/retry`); wakeWorker(); load(); toast.add("Retry started", "info"); } catch (e) { toast.add(errMsg(e), "error"); }
  };
  const deleteMaterial = async (id: number) => {
    if (!(await confirm("Delete this material?"))) return;
    try { await adminApi.delete(`/admin/materials/${id}`); load(); toast.add("Material deleted", "success"); } catch (e) { toast.add(errMsg(e), "error"); }
  };

  const filtered = allMaterials.filter(({ material: m, topic: t, course: c }) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return m.title.toLowerCase().includes(q) || t.title.toLowerCase().includes(q) || c.title.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-6">
      {modal}
      <FadeIn>
        <Card className="overflow-hidden" hover={false}>
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-4 flex-wrap">
            <h3 className="font-bold text-xl">All Materials</h3>
            <div className="flex items-center gap-3">
              <input className="border border-slate-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all w-64" placeholder="Search materials..." value={search} onChange={(e) => setSearch(e.target.value)} />
              <Badge color="blue">{filtered.length} total</Badge>
            </div>
          </div>
          {filtered.length === 0 ? (
            <div className="px-6 py-12 text-center text-slate-500">{allMaterials.length === 0 ? "No materials uploaded yet." : "No materials match your search."}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left border-b border-slate-100 bg-slate-50/50"><th className="px-6 py-3 font-semibold text-slate-500">Material</th><th className="px-6 py-3 font-semibold text-slate-500">Topic</th><th className="px-6 py-3 font-semibold text-slate-500">Course</th><th className="px-6 py-3 font-semibold text-slate-500">Pages</th><th className="px-6 py-3 font-semibold text-slate-500">Status</th><th className="px-6 py-3 font-semibold text-slate-500">Actions</th></tr></thead>
                <tbody>{filtered.map(({ topic, course, material: m }) => (
                  <tr key={m.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium text-slate-900">{m.title}</div>
                      {m.error && <div className="text-xs text-red-500 mt-1">{m.error}</div>}
                    </td>
                    <td className="px-6 py-4 text-slate-600">{topic.title}</td>
                    <td className="px-6 py-4 text-slate-600">{course.title}</td>
                    <td className="px-6 py-4 text-slate-500">{m.page_count ?? "—"}</td>
                    <td className="px-6 py-4"><Badge color={statusColor(m.status)}>{m.status}</Badge></td>
                    <td className="px-6 py-4 space-x-2">
                      {m.status === "failed" && <Button variant="ghost" onClick={() => retryMaterial(m.id)}>Retry</Button>}
                      <Button variant="danger" onClick={() => deleteMaterial(m.id)}>Delete</Button>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>
      </FadeIn>
    </div>
  );
}

/* ---------- Enrollments Tab ---------- */
function EnrollTab() {
  const [courses, setCourses] = useState<any[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [f, setF] = useState({ email: "", course_id: 0, days: 365 });
  const [search, setSearch] = useState("");
  const toast = useToast();
  const { confirm, modal } = useConfirm();
  const load = () => adminApi.get("/admin/enrollments", { params: { limit: 100 } }).then((r) => setRows(r.data));
  useEffect(() => { adminApi.get("/admin/courses").then((r) => { setCourses(r.data); if (r.data[0]) setF((p) => ({ ...p, course_id: r.data[0].id })); }); load(); }, []);
  const grant = async (e: FormEvent) => { e.preventDefault(); try { await adminApi.post("/admin/enrollments", f); await load(); toast.add("Access granted", "success"); } catch (e) { toast.add(errMsg(e), "error"); } };
  const approve = async (id: number) => { try { await adminApi.post(`/admin/enrollments/${id}/approve`); await load(); toast.add("Enrollment approved", "success"); } catch (e) { toast.add(errMsg(e), "error"); } };
  const revoke = async (id: number) => { if (!(await confirm("Revoke this enrollment? The student will lose access."))) return; try { await adminApi.post(`/admin/enrollments/${id}/revoke`); await load(); toast.add("Enrollment revoked", "info"); } catch (e) { toast.add(errMsg(e), "error"); } };

  const pending = rows.filter((r) => r.status === "pending").length;

  const filtered = rows.filter((r) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return String(r.user_id).includes(q) || String(r.course_id).includes(q) || r.status.includes(q);
  });

  return (
    <div className="space-y-6">
      {modal}
      <FadeIn>
        <Card className="p-6" hover={false}>
          <h3 className="font-bold text-xl mb-5">Grant Direct Access</h3>
          <form onSubmit={grant} className="flex flex-wrap gap-3">
            <input className="flex-1 min-w-[200px] border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" type="email" placeholder="Student email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required />
            <select className="w-48 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" value={f.course_id} onChange={(e) => setF({ ...f, course_id: +e.target.value })}>{courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select>
            <input className="w-24 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" type="number" value={f.days} onChange={(e) => setF({ ...f, days: +e.target.value })} />
            <Button>Grant Access</Button>
          </form>
        </Card>
      </FadeIn>

      <FadeIn delay={100}>
        <Card className="overflow-hidden" hover={false}>
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <h3 className="font-bold text-xl">Enrollments</h3>
              {pending > 0 && <Badge color="yellow">{pending} pending</Badge>}
            </div>
            <input className="border border-slate-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all w-64" placeholder="Search enrollments..." value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left border-b border-slate-100 bg-slate-50/50"><th className="px-6 py-3 font-semibold text-slate-500">ID</th><th className="px-6 py-3 font-semibold text-slate-500">User</th><th className="px-6 py-3 font-semibold text-slate-500">Course</th><th className="px-6 py-3 font-semibold text-slate-500">Status</th><th className="px-6 py-3 font-semibold text-slate-500">Expires</th><th className="px-6 py-3 font-semibold text-slate-500">Actions</th></tr></thead>
              <tbody>{filtered.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/50 transition-colors">
                  <td className="px-6 py-4 font-mono text-xs">{r.id}</td>
                  <td className="px-6 py-4">{r.user_id}</td>
                  <td className="px-6 py-4">{r.course_id}</td>
                  <td className="px-6 py-4"><Badge color={statusColor(r.status)}>{r.status}</Badge></td>
                  <td className="px-6 py-4 text-slate-500">{r.expires_at ? new Date(r.expires_at).toLocaleDateString() : "Lifetime"}</td>
                  <td className="px-6 py-4 space-x-2">
                    {r.status === "pending" && <Button variant="primary" onClick={() => approve(r.id)}>Approve</Button>}
                    {r.status === "active" && <Button variant="danger" onClick={() => revoke(r.id)}>Revoke</Button>}
                  </td>
                </tr>))}</tbody>
            </table>
          </div>
          {filtered.length === 0 && <div className="px-6 py-12 text-center text-slate-500">No enrollments found.</div>}
        </Card>
      </FadeIn>
    </div>
  );
}

/* ---------- Staff Tab (Super Admin only) ---------- */
const ROLES = [
  { id: "super_admin", label: "Super Admin", hint: "Everything, including this page" },
  { id: "content_manager", label: "Content Manager", hint: "Courses, topics, materials, student access" },
  { id: "editor", label: "Editor", hint: "Only the courses assigned to them" },
];
const roleLabel = (role: string) => ROLES.find((r) => r.id === role)?.label ?? role;

function StaffTab() {
  const [rows, setRows] = useState<any[]>([]);
  const [courses, setCourses] = useState<any[]>([]);
  const [f, setF] = useState({ full_name: "", email: "", role: "editor" });
  const [picking, setPicking] = useState<number | null>(null);
  const [assigned, setAssigned] = useState<number[]>([]);
  const [activity, setActivity] = useState<{ id: number; rows: any[] } | null>(null);
  const me = useAdminAuth((s) => s.admin);
  const toast = useToast();
  const { confirm, modal } = useConfirm();

  const load = () => adminApi.get("/admin/staff").then((r) => setRows(r.data));
  useEffect(() => {
    load();
    adminApi.get("/admin/courses").then((r) => setCourses(r.data));
  }, []);

  const run = async (fn: () => Promise<any>, message = "Done") => {
    try { await fn(); await load(); toast.add(message, "success"); }
    catch (e) { toast.add(errMsg(e), "error"); }
  };

  const openCourses = async (id: number) => {
    try {
      const { data } = await adminApi.get(`/admin/staff/${id}/courses`);
      setPicking(id); setAssigned(data);
    } catch (e) { toast.add(errMsg(e), "error"); }
  };

  const toggleCourse = (courseId: number) =>
    setAssigned((prev) => prev.includes(courseId) ? prev.filter((c) => c !== courseId) : [...prev, courseId]);

  const openActivity = async (id: number) => {
    try {
      const { data } = await adminApi.get(`/admin/staff/${id}/activity`);
      setActivity({ id, rows: data });
    } catch (e) { toast.add(errMsg(e), "error"); }
  };

  const setRole = (id: number, role: string) =>
    run(() => adminApi.patch(`/admin/staff/${id}`, { role }), "Role updated, their sessions were ended");

  const setActive = async (id: number, active: boolean) => {
    if (!active && !(await confirm("Deactivate this account? They are signed out immediately."))) return;
    run(() => adminApi.patch(`/admin/staff/${id}`, { is_active: active }), active ? "Account reactivated" : "Account deactivated");
  };

  return (
    <div className="space-y-6">
      {modal}
      <FadeIn>
        <Card className="p-6" hover={false}>
          <h3 className="font-bold text-xl mb-2">Add a staff member</h3>
          <p className="text-sm text-slate-500 mb-5">
            Use the Gmail address they will sign in with. There is no password to hand
            out: they pick Google, then we mail a six digit code to that inbox.
          </p>
          <form className="flex flex-wrap gap-3" onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => adminApi.post("/admin/staff", f), "Staff account created"); setF({ full_name: "", email: "", role: f.role }); }}>
            <div className="flex-1 min-w-[180px]"><Input placeholder="Full name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} required /></div>
            <div className="flex-1 min-w-[220px]"><Input type="email" placeholder="name@gmail.com" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required /></div>
            <select className="w-48 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
              {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
            <Button>Add Staff</Button>
          </form>
          <p className="text-xs text-slate-500 mt-3">{ROLES.find((r) => r.id === f.role)?.hint}</p>
        </Card>
      </FadeIn>

      <FadeIn delay={100}>
        <Card className="overflow-hidden" hover={false}>
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-3 flex-wrap">
            <h3 className="font-bold text-xl">Staff</h3>
            <Badge color="blue">{rows.filter((r) => r.is_active).length} active</Badge>
          </div>
          <div className="divide-y divide-slate-100">
            {rows.map((s) => (
              <div key={s.id} className="px-6 py-4 hover:bg-slate-50 transition-colors">
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex-1 min-w-[220px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <b className="text-lg text-slate-900">{s.full_name}</b>
                      {s.id === me?.id && <Badge color="blue">You</Badge>}
                      {!s.is_active && <Badge color="red">Deactivated</Badge>}
                      {s.google_linked
                        ? <Badge color="green">Google linked</Badge>
                        : <Badge color="yellow">Waiting for first sign-in</Badge>}
                    </div>
                    <span className="text-xs text-slate-500">{s.email}</span>
                  </div>
                  <select
                    className="w-44 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-all"
                    value={s.role}
                    onChange={(e) => setRole(s.id, e.target.value)}
                  >
                    {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                  </select>
                  <Button variant="ghost" onClick={() => openCourses(s.id)}>Courses</Button>
                  <Button variant="ghost" onClick={() => openActivity(s.id)}>Activity</Button>
                  <Button variant={s.is_active ? "danger" : "secondary"} onClick={() => setActive(s.id, !s.is_active)}>
                    {s.is_active ? "Deactivate" : "Reactivate"}
                  </Button>
                </div>

                {picking === s.id && (
                  <div className="mt-4 bg-blue-50 border border-blue-200 rounded-xl p-4">
                    <p className="text-sm font-semibold text-slate-700 mb-3">
                      Assigned courses — an Editor can only open these
                    </p>
                    <div className="grid sm:grid-cols-2 gap-2 mb-4">
                      {courses.map((c) => (
                        <label key={c.id} className="flex items-center gap-2 text-sm text-slate-700">
                          <input type="checkbox" checked={assigned.includes(c.id)} onChange={() => toggleCourse(c.id)} />
                          {c.title}
                        </label>
                      ))}
                      {courses.length === 0 && <p className="text-sm text-slate-500 italic">No courses yet.</p>}
                    </div>
                    <div className="flex gap-3">
                      <Button onClick={() => run(() => adminApi.put(`/admin/staff/${s.id}/courses`, { course_ids: assigned }).then(() => setPicking(null)), "Assignments saved")}>Save</Button>
                      <Button variant="ghost" onClick={() => setPicking(null)}>Cancel</Button>
                    </div>
                  </div>
                )}

                {activity && activity.id === s.id && (
                  <div className="mt-4 bg-slate-50 border border-slate-200 rounded-xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-sm font-semibold text-slate-700">Recent actions</p>
                      <Button variant="ghost" onClick={() => setActivity(null)}>Close</Button>
                    </div>
                    {activity.rows.length === 0 ? (
                      <p className="text-sm text-slate-500 italic">Nothing recorded for this account yet.</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {activity.rows.map((row) => (
                          <li key={row.id} className="flex items-center gap-3 text-sm">
                            <span className="font-mono text-xs text-slate-500">{new Date(row.created_at).toLocaleString()}</span>
                            <span className="text-slate-800">{row.action}</span>
                            {row.target && <span className="text-slate-500 truncate">{row.target}</span>}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      </FadeIn>

      <FadeIn delay={200}>
        <Card className="p-6" hover={false}>
          <h3 className="font-bold text-lg mb-3">How the three roles differ</h3>
          <ul className="space-y-2 text-sm text-slate-600">
            {ROLES.map((r) => (
              <li key={r.id}><b className="text-slate-900">{r.label}</b> — {r.hint}</li>
            ))}
          </ul>
          <p className="text-sm text-slate-500 mt-4">
            Changing a role or deactivating an account signs that person out of the panel
            on their next request. The last active Super Admin cannot be removed, so the
            panel can never be locked.
          </p>
        </Card>
      </FadeIn>
    </div>
  );
}

/* ---------- Shell ---------- */
export default function Admin() {
  const [tab, setTab] = useState<"courses" | "topics" | "materials" | "enroll" | "staff">("courses");
  const { admin, refresh, setAdmin, logout } = useAdminAuth();
  const nav = useNavigate();
  const toast = useToast();

  useEffect(() => {
    // A session saved before roles existed has no role to read, so it is refreshed.
    if (admin?.role) return;
    adminApi.get("/admin/auth/me").then((r) => setAdmin(r.data)).catch(() => {});
  }, [admin, setAdmin]);

  // Which tabs exist follows the role, and the backend answers 403 for anything
  // else, so a hidden tab is a convenience rather than the actual gate.
  const tabs: { id: typeof tab; label: string; icon: string }[] = [
    { id: "courses", label: "Courses", icon: "🗂" },
    { id: "topics", label: "Topics", icon: "🧭" },
    { id: "materials", label: "Materials", icon: "📄" },
  ];
  if (admin?.role !== "editor") tabs.push({ id: "enroll", label: "Enrollments", icon: "🎓" });
  if (admin?.role === "super_admin") tabs.push({ id: "staff", label: "Staff", icon: "👥" });

  const signOut = async () => {
    try {
      if (refresh) await adminApi.post("/admin/auth/logout", { refresh_token: refresh });
    } catch { /* the session is cleared locally either way */ }
    logout();
    toast.add("Signed out", "info");
    nav("/admin/login");
  };

  const onTab = tabs.some((t) => t.id === tab);

  return (
    <div>
      <FadeIn>
        <div className="flex items-end justify-between gap-4 flex-wrap mb-6">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Admin Panel</h1>
            {admin && (
              <p className="text-sm text-slate-500 mt-1">
                {admin.full_name} · {roleLabel(admin.role)}
              </p>
            )}
          </div>
          <Button variant="ghost" onClick={signOut}>Sign out</Button>
        </div>
      </FadeIn>
      <FadeIn delay={100}>
        <div className="flex gap-2 mb-8 flex-wrap">
          {tabs.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 ${tab === t.id ? "bg-blue-600 text-white shadow-lg scale-105" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
              <span className="mr-1.5">{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
      </FadeIn>
      {!onTab && (
        <Card className="text-center py-12" hover={false}>
          <p className="text-slate-500">Your role changed. Pick a tab above.</p>
        </Card>
      )}
      {tab === "courses" ? <CoursesTab />
        : tab === "topics" ? <TopicsTab />
        : tab === "materials" ? <MaterialsTab />
        : tab === "enroll" ? <EnrollTab />
        : tab === "staff" ? <StaffTab /> : null}
    </div>
  );
}
