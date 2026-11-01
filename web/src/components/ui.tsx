import { useEffect, useRef, useState } from "react";

export function useInView(threshold = 0.1) {
  const ref = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setIsVisible(true); obs.disconnect(); } }, { threshold });
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, isVisible };
}

export function FadeIn({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  const { ref, isVisible } = useInView();
  return (
    <div ref={ref} className={`transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-slate-200 rounded-lg ${className}`} />;
}

export function Card({ children, className = "", hover = true, glass = false }: { children: React.ReactNode; className?: string; hover?: boolean; glass?: boolean }) {
  return (
    <div className={`rounded-2xl shadow-sm ${glass ? "bg-white/80 backdrop-blur-sm border border-white/40" : "bg-white border border-slate-200"} ${hover ? "hover:shadow-xl hover:-translate-y-1 hover:border-blue-200" : ""} transition-all duration-300 ${className}`}>
      {children}
    </div>
  );
}

export function Button({ children, variant = "primary", className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const styles = {
    primary: "bg-blue-600 text-white hover:bg-blue-700 shadow-md hover:shadow-lg",
    secondary: "bg-white text-blue-600 border-2 border-blue-600 hover:bg-blue-50",
    danger: "bg-red-50 text-red-600 border border-red-200 hover:bg-red-100",
    ghost: "text-slate-600 hover:bg-slate-100",
  };
  return (
    <button className={`px-5 py-2.5 rounded-xl font-medium transition-all duration-200 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed ${styles[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Input({ label, error, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { label?: string; error?: string }) {
  return (
    <div className="space-y-1.5">
      {label && <label className="block text-sm font-medium text-slate-700">{label}</label>}
      <input className={`w-full border rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 transition-all ${error ? "border-red-300" : "border-slate-200"}`} {...props} />
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

export function Badge({ children, color = "slate" }: { children: React.ReactNode; color?: "green" | "yellow" | "red" | "blue" | "slate" | "purple" }) {
  const colors = {
    green: "bg-emerald-100 text-emerald-700 border-emerald-200",
    yellow: "bg-amber-100 text-amber-700 border-amber-200",
    red: "bg-red-100 text-red-700 border-red-200",
    blue: "bg-blue-100 text-blue-700 border-blue-200",
    slate: "bg-slate-100 text-slate-600 border-slate-200",
    purple: "bg-purple-100 text-purple-700 border-purple-200",
  };
  return <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-semibold border ${colors[color]}`}>{children}</span>;
}
