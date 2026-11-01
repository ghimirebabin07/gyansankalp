import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { FadeIn, Card } from "../components/ui";
import { useAuth } from "../store";

function AnimatedCounter({ end, label, suffix = "", icon }: { end: number; label: string; suffix?: string; icon: string }) {
  const [count, setCount] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    setReducedMotion(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }, []);

  useEffect(() => {
    if (reducedMotion) { setCount(end); return; }
    let start = 0;
    const duration = 2000;
    const steps = 60;
    const increment = end / steps;
    const timer = setInterval(() => {
      start += increment;
      if (start >= end) { setCount(end); clearInterval(timer); }
      else setCount(Math.floor(start));
    }, duration / steps);
    return () => clearInterval(timer);
  }, [end, reducedMotion]);

  return (
    <FadeIn className="text-center p-8 bg-white rounded-2xl border border-slate-200 shadow-lg hover:shadow-xl transition-all duration-300">
      <div className="text-4xl mb-3">{icon}</div>
      <div className="text-4xl font-bold text-blue-600">{count}{suffix}</div>
      <div className="text-sm text-slate-500 mt-2 uppercase tracking-wider font-medium">{label}</div>
    </FadeIn>
  );
}

function FeatureCard({ icon, title, desc, delay }: { icon: string; title: string; desc: string; delay: number }) {
  return (
    <FadeIn delay={delay}>
      <Card className="p-8 h-full group cursor-default">
        <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center text-3xl mb-5 group-hover:scale-110 transition-all duration-300">
          {icon}
        </div>
        <h3 className="font-bold text-xl mb-3 text-slate-900 group-hover:text-blue-600 transition-colors">{title}</h3>
        <p className="text-slate-500 leading-relaxed">{desc}</p>
      </Card>
    </FadeIn>
  );
}

function FaqItem({ q, a, i }: { q: string; a: string; i: number }) {
  const [open, setOpen] = useState(false);
  return (
    <FadeIn delay={i * 100}>
      <div className="border-b border-slate-200 last:border-0">
        <button onClick={() => setOpen(!open)} aria-expanded={open} className="w-full text-left py-5 flex justify-between items-center font-semibold text-lg text-slate-900 hover:text-blue-600 transition-colors group focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 rounded-lg">
          <span>{q}</span>
          <span className={`w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-xl transition-all duration-300 ${open ? "rotate-45 bg-blue-100 text-blue-600" : "group-hover:bg-blue-50"}`}>+</span>
        </button>
        <div className={`overflow-hidden transition-all duration-500 ${open ? "max-h-48 pb-5" : "max-h-0"}`} role="region">
          <p className="text-slate-600 leading-relaxed pr-12">{a}</p>
        </div>
      </div>
    </FadeIn>
  );
}

function TestimonialCard({ name, role, text, rating, delay }: { name: string; role: string; text: string; rating: number; delay: number }) {
  return (
    <FadeIn delay={delay}>
      <Card className="p-6 h-full" hover={false}>
        <div className="flex gap-1 mb-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} className={`text-xl ${i < rating ? "text-yellow-400" : "text-slate-200"}`}>★</span>
          ))}
        </div>
        <p className="text-slate-600 leading-relaxed mb-6 italic">"{text}"</p>
        <div className="flex items-center gap-3 pt-4 border-t border-slate-100">
          <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-bold text-lg">
            {name.charAt(0)}
          </div>
          <div>
            <div className="font-semibold text-slate-900">{name}</div>
            <div className="text-sm text-slate-500">{role}</div>
          </div>
        </div>
      </Card>
    </FadeIn>
  );
}

function ExamTargetCard({ title, subtitle, desc, delay, level }: { title: string; subtitle: string; desc: string; delay: number; level: string }) {
  return (
    <FadeIn delay={delay} className="h-full">
      <Link to={`/courses?level=${level}`} className="block group h-full">
        <div className="relative overflow-hidden bg-gradient-to-br from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 rounded-3xl p-8 text-white shadow-xl hover:shadow-2xl hover:scale-105 transition-all duration-300 h-full">
          <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="relative h-full flex flex-col">
            <h3 className="text-3xl font-bold mb-2">{title}</h3>
            <p className="text-lg font-semibold mb-4 text-white/90">{subtitle}</p>
            <p className="text-sm text-white/80 leading-relaxed mb-6">{desc}</p>
            <div className="mt-auto flex items-center gap-2 font-semibold group-hover:gap-3 transition-all">
              <span>View Courses</span>
              <span className="group-hover:translate-x-1 transition-transform">→</span>
            </div>
          </div>
        </div>
      </Link>
    </FadeIn>
  );
}

export default function Home() {
  const { access } = useAuth();
  const [stats, setStats] = useState({ courses: 0, topics: 0, materials: 0 });

  useEffect(() => {
    api.get("/stats").then((r) => setStats(r.data)).catch(() => {});
  }, []);

  const features = [
    { icon: "", title: "Quality Content", desc: "Well-structured courses designed by experts to help you master any subject effectively." },
    { icon: "🎓", title: "Expert Teachers", desc: "Learn from experienced instructors with proven teaching methods and real-world knowledge." },
    { icon: "♾️", title: "Lifetime Access", desc: "Study anytime, anywhere with unlimited access to all materials and future updates." },
    { icon: "💬", title: "Dedicated Support", desc: "Get help whenever you need it from our committed support team via WhatsApp or email." },
  ];

  const faqs = [
    { q: "How do I enroll in a course?", a: "Browse our courses, click 'Request Enrollment' on any course, and our admin will review and approve your access within 24 hours." },
    { q: "What payment methods do we accept?", a: "We accept eSewa, Khalti, bank transfer, and cash payment. Contact us for payment details after enrollment approval." },
    { q: "How long do I have access to a course?", a: "Once enrolled, you get lifetime access to all course materials including future updates and additions." },
    { q: "Can I access courses on mobile?", a: "Yes! Our platform works on any device — phone, tablet, or computer. Study wherever you are, whenever you want." },
    { q: "What if I have questions about the content?", a: "Contact us through WhatsApp or email. Our support team is ready to help with any doubts or questions." },
  ];

  const testimonials = [
    { name: "Sita Sharma", role: "Kharidar 2025", text: "GyanSankalp helped me clear my Kharidar exam on the first attempt. The study materials were comprehensive and well-organized.", rating: 5 },
    { name: "Ram Thapa", role: "Na Su 2024", text: "The quality of content and expert guidance made my preparation much easier. Highly recommend for all Lok Sewa aspirants.", rating: 5 },
    { name: "Anita Poudel", role: "Officer 2025", text: "Lifetime access to materials meant I could study at my own pace. The platform is easy to use and the support team is always helpful.", rating: 5 },
  ];

  return (
    <div className="space-y-0">
      {/* Hero with image like TeamSandesh */}
      <section className="relative overflow-hidden bg-gradient-to-br from-blue-50 to-white py-16">
        <div className="max-w-7xl mx-auto px-4 grid lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <FadeIn>
              <h1 className="text-5xl md:text-6xl font-bold text-slate-900 leading-tight">
                Best Exam<br />
                <span className="text-blue-600">Preparation Class</span>
              </h1>
            </FadeIn>
            <FadeIn delay={200}>
              <p className="text-xl text-slate-600 leading-relaxed">
                GyanSankalp is Nepal's trusted platform for quality education. Access expert-led courses and study materials at your own pace.
              </p>
            </FadeIn>
            <FadeIn delay={400}>
              <div className="flex flex-wrap gap-4">
                <Link to="/courses" className="px-8 py-4 bg-blue-600 text-white font-bold rounded-xl hover:bg-blue-700 hover:shadow-lg transition-all duration-300 flex items-center gap-2">
                  Browse Courses <span>→</span>
                </Link>
                {!access && (
                  <Link to="/register" className="px-8 py-4 border-2 border-blue-600 text-blue-600 font-bold rounded-xl hover:bg-blue-50 transition-all duration-300">
                    Get Started
                  </Link>
                )}
              </div>
            </FadeIn>
          </div>
          <FadeIn delay={300}>
            <img src="/FRONT IMG.png" alt="Student preparing for exams" className="w-full h-auto rounded-2xl shadow-2xl" width={600} height={400} />
          </FadeIn>
        </div>
      </section>

      {/* Stats */}
      <section className="max-w-5xl mx-auto px-4 -mt-8 relative z-10">
        <div className="grid grid-cols-3 gap-6">
          <AnimatedCounter end={stats.courses} suffix="+" label="Courses" icon="" />
          <AnimatedCounter end={stats.topics} suffix="+" label="Topics" icon="" />
          <AnimatedCounter end={stats.materials} suffix="+" label="Materials" icon="" />
        </div>
      </section>

      {/* Exam Targets */}
      <section className="max-w-6xl mx-auto px-4 py-24">
        <FadeIn>
          <div className="text-center mb-16">
            <span className="text-blue-600 font-semibold text-sm uppercase tracking-wider">Your Goal</span>
            <h2 className="text-4xl md:text-5xl font-bold mt-3 text-slate-900">Choose Your Exam Target</h2>
            <p className="text-slate-500 mt-4 text-lg max-w-2xl mx-auto">Prepare for Lok Sewa Aayog exams and achieve your career dreams with expert guidance</p>
          </div>
        </FadeIn>
        <div className="grid md:grid-cols-3 gap-8">
          <ExamTargetCard
            title="Kharidar"
            subtitle="4th Level"
            desc="Comprehensive preparation for Kharidar position. Quality education following Nepal Lok Sewa Aayog approved curriculum."
            delay={0}
            level="kharidar"
          />
          <ExamTargetCard
            title="Na Su"
            subtitle="5th Level"
            desc="Extensive preparation for Na Su position. Deep knowledge of all subjects with practice materials and mock tests."
            delay={150}
            level="nasu"
          />
          <ExamTargetCard
            title="Officer"
            subtitle="6th Level"
            desc="High-level preparation for senior positions. Special focus on leadership ability and management skill development."
            delay={300}
            level="officer"
          />
        </div>
      </section>

      {/* Why Choose Us */}
      <section className="max-w-6xl mx-auto px-4 py-24">
        <FadeIn>
          <div className="text-center mb-16">
            <span className="text-blue-600 font-semibold text-sm uppercase tracking-wider">Why Choose Us</span>
            <h2 className="text-4xl md:text-5xl font-bold mt-3 text-slate-900">Everything you need to succeed</h2>
            <p className="text-slate-500 mt-4 text-lg max-w-2xl mx-auto">We provide the best learning experience with quality content, expert guidance, and lifetime access.</p>
          </div>
        </FadeIn>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f, i) => <FeatureCard key={f.title} {...f} delay={i * 150} />)}
        </div>
      </section>

      {/* Testimonials */}
      <section className="max-w-6xl mx-auto px-4 py-24">
        <FadeIn>
          <div className="text-center mb-16">
            <span className="text-blue-600 font-semibold text-sm uppercase tracking-wider">Testimonials</span>
            <h2 className="text-4xl md:text-5xl font-bold mt-3 text-slate-900">What our students say</h2>
            <p className="text-slate-500 mt-4 text-lg max-w-2xl mx-auto">Real stories from students who achieved their goals with GyanSankalp</p>
          </div>
        </FadeIn>
        <div className="grid md:grid-cols-3 gap-6">
          {testimonials.map((t, i) => <TestimonialCard key={t.name} {...t} delay={i * 150} />)}
        </div>
      </section>

      {/* FAQ */}
      <section className="max-w-3xl mx-auto px-4 py-24">
        <FadeIn>
          <div className="text-center mb-12">
            <span className="text-blue-600 font-semibold text-sm uppercase tracking-wider">FAQ</span>
            <h2 className="text-4xl md:text-5xl font-bold mt-3 text-slate-900">Frequently Asked Questions</h2>
            <p className="text-slate-500 mt-4 text-lg">Got questions? We've got answers.</p>
          </div>
        </FadeIn>
        <FadeIn delay={200}>
          <Card className="p-8" hover={false}>
            {faqs.map((f, i) => <FaqItem key={f.q} {...f} i={i} />)}
          </Card>
        </FadeIn>
      </section>

      {/* CTA */}
      {!access && (
        <section className="bg-blue-600 py-24 px-4">
          <div className="max-w-3xl mx-auto text-center">
            <FadeIn>
              <h2 className="text-4xl md:text-5xl font-bold text-white">Ready to start learning?</h2>
              <p className="mt-4 text-xl text-blue-100">Join GyanSankalp today and unlock your full potential.</p>
              <Link to="/register" className="inline-flex items-center gap-2 mt-10 px-10 py-4 bg-white text-blue-600 font-bold rounded-xl hover:shadow-2xl hover:scale-105 transition-all duration-300">
                Create Free Account <span>→</span>
              </Link>
            </FadeIn>
          </div>
        </section>
      )}
    </div>
  );
}
