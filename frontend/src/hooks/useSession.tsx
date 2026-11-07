import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, hasToken, post, setToken, setUnauthorizedHandler } from "../services/api";
import type { TokenResponse, User, Workspace } from "../types";

const WORKSPACE_KEY = "visionguard.workspace";

interface Session {
  user: User | null;
  ready: boolean;
  workspaces: Workspace[];
  workspace: Workspace | null;
  selectWorkspace: (id: string) => void;
  reloadWorkspaces: () => Promise<Workspace[]>;
  signIn: (result: TokenResponse) => void;
  signOut: () => Promise<void>;
  setUser: (user: User) => void;
}

const Context = createContext<Session | null>(null);

function remembered(): string | null {
  try {
    return localStorage.getItem(WORKSPACE_KEY);
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(!hasToken());
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(remembered());

  const reloadWorkspaces = useCallback(async () => {
    const list = await api<Workspace[]>("/workspaces");
    setWorkspaces(list);
    return list;
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setWorkspaces([]);
    });
    if (!hasToken()) return;
    Promise.all([api<User>("/users/me"), reloadWorkspaces()])
      .then(([me]) => setUser(me))
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, [reloadWorkspaces]);

  const value = useMemo<Session>(() => {
    const workspace = workspaces.find((w) => w.id === workspaceId) ?? workspaces.find((w) => !w.is_demo) ?? workspaces[0] ?? null;
    return {
      user, ready, workspaces, workspace, reloadWorkspaces, setUser,
      selectWorkspace: (id) => {
        setWorkspaceId(id);
        try { localStorage.setItem(WORKSPACE_KEY, id); } catch { /* A remembered workspace is only a convenience. */ }
      },
      signIn: (result) => {
        setToken(result.access_token);
        setUser(result.user);
        void reloadWorkspaces();
      },
      signOut: async () => {
        try { await post("/auth/logout"); } catch { /* The local session still ends. */ }
        setToken(null);
        setUser(null);
        setWorkspaces([]);
      },
    };
  }, [user, ready, workspaces, workspaceId, reloadWorkspaces]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSession(): Session {
  const session = useContext(Context);
  if (!session) throw new Error("useSession must be used within SessionProvider");
  return session;
}
