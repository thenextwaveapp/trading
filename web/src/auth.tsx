import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "./db/supabase";
import type { DbProfile } from "./db/types";

interface AuthState {
  session: Session | null;
  user: User | null;
  profile: DbProfile | null;
  loading: boolean;
  refreshProfile: () => Promise<void>;
  sendMagicLink: (email: string) => Promise<{ error: string | null }>;
  signInGoogle: () => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<DbProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_evt, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  const loadProfile = async (uid: string) => {
    const { data } = await supabase
      .from("pf_profiles")
      .select("*")
      .eq("id", uid)
      .single();
    setProfile((data as DbProfile) ?? null);
  };

  // Profile row is created by the handle_new_user trigger on signup (db/functions.sql).
  useEffect(() => {
    const uid = session?.user?.id;
    if (!uid) {
      setProfile(null);
      return;
    }
    void loadProfile(uid);
  }, [session?.user?.id]);

  // OAuth returns to the same page, stripping the HashRouter fragment.
  const redirectTo =
    typeof window !== "undefined" ? window.location.origin + window.location.pathname : undefined;

  const value: AuthState = {
    session,
    user: session?.user ?? null,
    profile,
    loading,
    refreshProfile: async () => {
      if (session?.user?.id) await loadProfile(session.user.id);
    },
    // Passwordless: email a magic sign-in link. shouldCreateUser signs up new
    // emails (handle_new_user seeds the account on first click), so there is no
    // separate sign-up path.
    sendMagicLink: async (email) => {
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { shouldCreateUser: true, emailRedirectTo: redirectTo },
      });
      return { error: error?.message ?? null };
    },
    signInGoogle: async () => {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo },
      });
      return { error: error?.message ?? null };
    },
    signOut: async () => {
      await supabase.auth.signOut();
    },
  };

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const a = useContext(AuthCtx);
  if (!a) throw new Error("useAuth must be used within <AuthProvider>");
  return a;
}

/** The signed-in user's handle, or null when logged out. */
export function useCurrentHandle(): string | null {
  return useAuth().profile?.handle ?? null;
}
