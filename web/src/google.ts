// Google Identity Services in the browser, for both doors.
//
// Google returns a signed ID token here and we hand it straight to our API, which
// verifies it against Google's own keys. Nothing in this file decides whether a
// sign-in is trusted - it only moves Google's word to the backend.
//
// Students finish in one call. Staff finish in two (the backend then mails a code),
// so the two entry points below differ only in where the credential goes.
import { adminApi } from "./adminApi";
import { api, errMsg } from "./api";
import { useAuth } from "./store";

const clientId: string | undefined = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const SCRIPT_URL = "https://accounts.google.com/gsi/client";

// No client id means no button. Students still have passwords; staff have
// nothing else, so the admin door stays shut without it.
export const googleSignInEnabled = Boolean(clientId);

type GoogleId = {
  initialize: (config: {
    client_id: string;
    auto_select: boolean;
    callback: (response: { credential?: string }) => void;
  }) => void;
  renderButton: (el: HTMLElement, options: Record<string, string | number>) => void;
};

declare global {
  interface Window {
    google?: { accounts?: { id?: GoogleId } };
  }
}

let loading: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  loading ??= new Promise<void>((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = SCRIPT_URL;
    tag.async = true;
    tag.onload = () => resolve();
    tag.onerror = () => {
      loading = null;
      tag.remove();
      reject(new Error("Google could not be reached"));
    };
    document.head.appendChild(tag);
  });
  return loading;
}

async function studentSignIn(credential: string, password?: string) {
  const body: { id_token: string; password?: string } = { id_token: credential };
  if (password) body.password = password;
  const { data } = await api.post("/auth/google", body);
  useAuth.getState().setTokens(data.access_token, data.refresh_token);
  const me = await api.get("/auth/me");
  useAuth.getState().setUser(me.data);
  return { created: Boolean(data.created), user: me.data };
}

/** Google's button, painted into `el` and wired to one exchange function. */
function renderButton<T>(
  el: HTMLElement,
  exchange: (credential: string) => Promise<T>,
  onSuccess: (value: T) => void,
  onFailure: (message: string) => void,
): () => void {
  if (!clientId) return () => {};

  let stopped = false;
  loadScript()
    .then(() => {
      const id = window.google?.accounts?.id;
      if (stopped || !id) return;
      el.innerHTML = "";
      id.initialize({
        client_id: clientId,
        auto_select: false,
        callback: (response) => {
          if (!response.credential) {
            onFailure("Google did not give us a sign-in token. Please try again.");
            return;
          }
          exchange(response.credential)
            .then((value) => !stopped && onSuccess(value))
            .catch((e) => !stopped && onFailure(errMsg(e)));
        },
      });
      // Google paints the button; width follows the card so it never overflows.
      id.renderButton(el, {
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "pill",
        width: Math.round(el.clientWidth) || 320,
      });
      // Google renders the label in the visitor's detected language - Nepali for
      // most of our users - and no initialization option changes that. This
      // interface is English-only, so the label and its screen-reader twin get
      // Google's own approved English wording.
      el.querySelectorAll<HTMLElement>("span").forEach((span) => {
        if (!span.textContent?.trim()) return;
        span.textContent = span.id === "button-label"
          ? "Continue with Google. Opens in new tab."
          : "Continue with Google";
      });
    })
    .catch(() => {
      if (!stopped) onFailure("Google sign-in is unavailable right now.");
    });

  return () => { stopped = true; };
}

/**
 * Renders Google's button into `el` and returns a cleanup function.
 * Call it from a useEffect; the element must already have its final width.
 * `created` says whether this sign-in made the student or found one waiting.
 * `readPassword` is the register door's way of handing the password it collected
 * along with the token; the login door leaves it out and Google stays a
 * password-free entry.
 */
export function mountGoogleButton(
  el: HTMLElement,
  onSignedIn: (result: { created: boolean; user: { email_verified: boolean } }) => void,
  onFailure: (message: string) => void,
  readPassword?: () => string,
): () => void {
  return renderButton(
    el,
    (credential) => studentSignIn(credential, readPassword?.().trim()),
    onSignedIn,
    onFailure,
  );
}

export type StaffChallenge = {
  challenge: string;
  code_expires_in: number;
  resend_after: number;
};

/**
 * The staff button: Google proves the account, then the backend mails a code to
 * it. This hands the browser the waiting-room pass and nothing else - no session
 * exists until the code is typed.
 */
export function mountStaffGoogleButton(
  el: HTMLElement,
  onChallenge: (challenge: StaffChallenge) => void,
  onFailure: (message: string) => void,
): () => void {
  return renderButton(
    el,
    async (credential) => {
      const { data } = await adminApi.post("/admin/auth/google", { id_token: credential });
      return data as StaffChallenge;
    },
    onChallenge,
    onFailure,
  );
}
