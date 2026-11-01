import { create } from "zustand";

interface Toast { id: number; message: string; type: "success" | "error" | "info"; }

interface ToastStore {
  toasts: Toast[];
  add: (message: string, type?: Toast["type"]) => void;
  remove: (id: number) => void;
}

let nextId = 0;
export const useToast = create<ToastStore>((set) => ({
  toasts: [],
  add: (message, type = "info") => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000);
  },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export function ToastContainer() {
  const { toasts, remove } = useToast();
  const colors = { success: "bg-emerald-500", error: "bg-red-500", info: "bg-blue-600" };
  const icons = { success: "", error: "", info: "ℹ" };
  return (
    <div className="fixed bottom-6 right-6 z-[100] space-y-2">
      {toasts.map((t) => (
        <div key={t.id} className={`${colors[t.type]} text-white px-5 py-3 rounded-xl shadow-2xl flex items-center gap-3 animate-slide-up min-w-[280px]`}>
          <span className="text-lg">{icons[t.type]}</span>
          <span className="flex-1 text-sm font-medium">{t.message}</span>
          <button onClick={() => remove(t.id)} className="text-white/70 hover:text-white text-lg leading-none">×</button>
        </div>
      ))}
    </div>
  );
}
