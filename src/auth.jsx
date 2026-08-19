import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { auth } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    restoreSession(setUser, setRestoring);

    const clearUser = () => setUser(null);
    window.addEventListener("pivot:session-expired", clearUser);

    return () => {
      window.removeEventListener("pivot:session-expired", clearUser);
    };
  }, []);

  const context = useMemo(() => createAuthContext(user, restoring, setUser), [user, restoring]);

  return <AuthContext.Provider value={context}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }

  return context;
}


async function restoreSession(setUser, setRestoring) {
  try {
    const restoredUser = await auth.restore();
    setUser(restoredUser);
  } catch {
    setUser(null);
  } finally {
    setRestoring(false);
  }
}


function createAuthContext(user, restoring, setUser) {
  return {
    user,
    restoring,
    login: auth.login,
    logout: async () => {
      await auth.logout();
      setUser(null);
    },
  };
}
