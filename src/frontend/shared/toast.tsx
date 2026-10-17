import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Icon } from "./Icon";

type Kind = "ok" | "error";
type ShowToast = (text: string, kind?: Kind) => void;

const ToastContext = createContext<ShowToast>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ text: string; kind: Kind } | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const show = useCallback<ShowToast>((text, kind = "ok") => {
    setToast({ text, kind });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), 3200);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <div className={`toast${toast.kind === "error" ? " error" : ""}`} role="status">
          <Icon name={toast.kind === "error" ? "error" : "check_circle"} />
          <span>{toast.text}</span>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
