import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { FadeIn, Card, Skeleton, Badge } from "../components/ui";

export type Course = { id: number; title: string; slug: string; description: string; exam_level: string; price_npr: number };

const LEVELS = [
  { value: "", label: "All Levels" },
  { value: "kharidar", label: "Kharidar (4th)" },
  { value: "nasu", label: "Na Su (5th)" },
  { value: "officer", label: "Officer (6th)" },
];

const levelBadgeColor = (level: string): "blue" | "green" | "purple" | "slate" => {
  const map: Record<string, "blue" | "green" | "purple" | "slate"> = {
    kharidar: "blue", nasu: "green", officer: "purple",
  };
  return map[level.toLowerCase()] || "slate";
};

export function CourseCard({ c }: { c: Course }) {
  const isFree = c.price_npr === 0;
  return (
    <Link to={`/courses/${c.slug}`} className="block h-full">
      <Card className="p-6 h-full group cursor-pointer">
        <div className="flex items-start justify-between mb-4">
          <div className="w-14 h-14 bg-blue-100 rounded-2xl flex items-center justify-center text-2xl group-hover:scale-110 transition-all duration-300"></div>
          <div className="flex gap-2">
            {c.exam_level && <Badge color={levelBadgeColor(c.exam_level)}>{c.exam_level}</Badge>}
            {isFree && <Badge color="green">FREE</Badge>}
          </div>
        </div>
        <h3 className="font-bold text-xl text-slate-900 group-hover:text-blue-600 transition-colors">{c.title}</h3>
        <p className="text-sm text-slate-500 mt-2 line-clamp-2">{c.description}</p>
        <div className="mt-5 flex justify-between items-center pt-4 border-t border-slate-100">
          <span className="font-bold text-xl text-blue-600">{isFree ? "FREE" : `NPR ${c.price_npr}`}</span>
          <span className="text-sm text-blue-600 font-semibold group-hover:translate-x-1 transition-transform flex items-center gap-1">View <span>→</span></span>
        </div>
      </Card>
    </Link>
  );
}

export default function Courses() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeLevel = searchParams.get("level") ?? "";
  const [list, setList] = useState<Course[] | null>(null);

  useEffect(() => {
    setList(null);
    const params = activeLevel ? `?level=${activeLevel}` : "";
    api.get(`/courses${params}`).then((r) => setList(r.data)).catch(() => setList([]));
  }, [activeLevel]);

  const setLevel = (level: string) => {
    if (level) setSearchParams({ level });
    else setSearchParams({});
  };

  return (
    <div>
      <FadeIn>
        <div className="mb-8">
          <h1 className="text-4xl font-bold">All Courses</h1>
          <p className="text-slate-500 mt-2 text-lg">Browse our available courses and start learning.</p>
        </div>
      </FadeIn>

      {/* Filter chips */}
      <FadeIn delay={100}>
        <div className="flex flex-wrap gap-2 mb-8">
          {LEVELS.map((l) => (
            <button
              key={l.value}
              onClick={() => setLevel(l.value)}
              className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 ${
                activeLevel === l.value
                  ? "bg-blue-600 text-white shadow-lg scale-105"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </FadeIn>

      {!list ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="bg-white rounded-2xl border p-6 space-y-4">
              <Skeleton className="w-14 h-14 rounded-2xl" />
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          ))}
        </div>
      ) : list.length === 0 ? (
        <FadeIn delay={200}>
          <Card className="text-center py-16" hover={false}>
            <div className="text-6xl mb-4 animate-float">📚</div>
            <h3 className="font-bold text-xl mb-2">
              {activeLevel ? `No ${activeLevel} courses yet` : "No courses available yet"}
            </h3>
            <p className="text-slate-500">Check back soon for new courses.</p>
          </Card>
        </FadeIn>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {list.map((c, i) => <FadeIn key={c.id} delay={i * 100}><CourseCard c={c} /></FadeIn>)}
        </div>
      )}
    </div>
  );
}
