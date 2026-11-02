import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi, errMsg } from "../adminApi";
import { useAdminAuth } from "../adminStore";
import { googleSignInEnabled, mountStaffGoogleButton, type StaffChallenge } from "../google";
import { useToast } from "../components/Toast";

const CODE_LENGTH = 6;

const clock = (seconds: number) => {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
};

export default function AdminLogin() {
  const [challenge, setChallenge] = useState<StaffChallenge | null>(null);
  const [digits, setDigits] = useState<string[]>(Array(CODE_LENGTH).fill(""));
  const [busy, setBusy] = useState(false);
  const [expiresIn, setExpiresIn] = useState(0);
  const [resendIn, setResendIn] = useState(0);
  const googleRef = useRef<HTMLDivElement>(null);
  const boxes = useRef<(HTMLInputElement | null)[]>([]);
  const { setTokens, setAdmin } = useAdminAuth();
  const nav = useNavigate();
  const toast = useToast();

  useEffect(() => {
    if (challenge || !googleSignInEnabled || !googleRef.current) return;
    return mountStaffGoogleButton(
      googleRef.current,
      (next) => {
        setChallenge(next);
        setExpiresIn(next.code_expires_in);
        setResendIn(next.resend_after);
        toast.add("A sign-in code is on its way to your Gmail", "info");
      },
      (message) => toast.add(message, "error"),
    );
  }, [challenge, toast]);

  // Both countdowns run off one timer so the two numbers cannot disagree.
  useEffect(() => {
    if (!challenge) return;
    const id = setInterval(() => {
      setExpiresIn((s) => Math.max(0, s - 1));
      setResendIn((s) => Math.max(0, s - 1));
    }, 1000);
    return () => clearInterval(id);
  }, [challenge]);

  const startOver = () => {
    setChallenge(null);
    setDigits(Array(CODE_LENGTH).fill(""));
    setExpiresIn(0);
    setResendIn(0);
  };

  const setDigit = (index: number, value: string) => {
    const digit = value.replace(/\D/g, "").slice(-1);
    setDigits((prev) => prev.map((d, i) => (i === index ? digit : d)));
    if (digit && index < CODE_LENGTH - 1) boxes.current[index + 1]?.focus();
  };

  const pasteCode = (text: string) => {
    const codes = text.replace(/\D/g, "").slice(0, CODE_LENGTH).split("");
    if (!codes.length) return false;
    setDigits(Array(CODE_LENGTH).fill("").map((_, i) => codes[i] ?? ""));
    boxes.current[Math.min(codes.length, CODE_LENGTH - 1)]?.focus();
    return true;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!challenge) return;
    setBusy(true);
    try {
      const { data } = await adminApi.post("/admin/auth/otp/verify", {
        challenge: challenge.challenge,
        code: digits.join(""),
      });
      setTokens(data.access_token, data.refresh_token);
      const me = await adminApi.get("/admin/auth/me");
      setAdmin(me.data);
      toast.add(`Welcome back, ${me.data.full_name}`, "success");
      nav("/admin");
    } catch (err) {
      toast.add(errMsg(err), "error");
      setDigits(Array(CODE_LENGTH).fill(""));
      boxes.current[0]?.focus();
    } finally { setBusy(false); }
  };

  const resend = async () => {
    if (!challenge || resendIn > 0) return;
    try {
      await adminApi.post("/admin/auth/otp/resend", { challenge: challenge.challenge });
      setExpiresIn(challenge.code_expires_in);
      setResendIn(challenge.resend_after);
      setDigits(Array(CODE_LENGTH).fill(""));
      boxes.current[0]?.focus();
      toast.add("A new code is on its way", "info");
    } catch (err) { toast.add(errMsg(err), "error"); }
  };

  const inputClass =
    "flex-1 min-w-0 max-w-12 h-14 text-center text-xl sm:text-2xl font-bold bg-white/10 border border-white/20 rounded-xl " +
    "text-white focus:outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-400/30 transition-all";

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900" />
      <div className="absolute top-20 left-[10%] w-72 h-72 bg-blue-500/20 rounded-full blur-3xl animate-float" />
      <div className="absolute bottom-20 right-[10%] w-96 h-96 bg-blue-500/15 rounded-full blur-3xl animate-float" style={{ animationDelay: "1s" }} />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl animate-float" style={{ animationDelay: "2s" }} />

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-6">
            <img src="/logo.png" alt="GyanSankalp" className="h-14 w-auto animate-float" />
          </div>
          <h1 className="text-3xl font-bold text-white">Admin Portal</h1>
          <p className="text-slate-400 mt-2">Staff access only</p>
        </div>

        <div className="bg-white/10 backdrop-blur-xl border border-white/20 rounded-3xl p-6 sm:p-8 shadow-2xl">
          {!challenge && (
            googleSignInEnabled ? (
              <div className="space-y-6">
                <p className="text-sm text-white/70 leading-relaxed">
                  Sign in with the Gmail address we registered for you. We then mail a
                  six digit code to that same inbox, and it is valid for a few minutes.
                </p>
                <div ref={googleRef} className="flex justify-center" />
                <p className="text-xs text-white/40 text-center">
                  There is no password for staff accounts. The code is the second factor.
                </p>
              </div>
            ) : (
              <p className="text-sm text-white/70 text-center leading-relaxed">
                Staff sign-in needs Google to be configured on this server, and it is not
                yet. Nothing here will let you in until it is.
              </p>
            )
          )}

          {challenge && (
            <form onSubmit={submit} className="space-y-6">
              <div className="space-y-1.5">
                <h2 className="text-lg font-bold text-white">Enter your code</h2>
                <p className="text-sm text-white/60">
                  Six digits, mailed to your Gmail. It stops working in{" "}
                  <span className="font-semibold text-white">{clock(expiresIn)}</span>.
                </p>
              </div>

              <div className="flex gap-1.5 sm:gap-2" onPaste={(e) => {
                const text = e.clipboardData.getData("text");
                if (pasteCode(text)) e.preventDefault();
              }}>
                {digits.map((d, i) => (
                  <input
                    key={i}
                    ref={(el) => { boxes.current[i] = el; }}
                    className={inputClass}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={1}
                    aria-label={`Digit ${i + 1}`}
                    value={d}
                    onChange={(e) => setDigit(i, e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Backspace" && !digits[i] && i > 0) {
                        boxes.current[i - 1]?.focus();
                        e.preventDefault();
                      }
                    }}
                  />
                ))}
              </div>

              {expiresIn === 0 && (
                <p className="text-sm text-amber-300">
                  This code has expired. Ask for a new one and sign in again.
                </p>
              )}

              <button
                disabled={busy || digits.join("").length < CODE_LENGTH}
                className="w-full py-3.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 hover:shadow-lg disabled:opacity-50 transition-all duration-200"
              >
                {busy ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Verifying…
                  </span>
                ) : "Verify and sign in"}
              </button>

              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-sm">
                <button type="button" onClick={resend} disabled={resendIn > 0}
                  className="py-2 font-semibold text-blue-300 hover:text-blue-200 disabled:text-white/40 disabled:cursor-not-allowed transition-colors">
                  {resendIn > 0 ? `Resend in ${resendIn}s` : "Send a new code"}
                </button>
                <button type="button" onClick={startOver}
                  className="py-2 text-white/60 hover:text-white transition-colors">
                  Use another account
                </button>
              </div>
            </form>
          )}
        </div>
        <p className="text-center text-xs text-white/40 mt-6">GyanSankalp Admin Panel</p>
      </div>
    </div>
  );
}
