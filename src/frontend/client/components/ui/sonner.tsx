import { Toaster as Sonner, type ToasterProps } from "sonner";
import { useDark } from "@/lib/theme";
import { Icon } from "./icon";

// Toast jak w mockupie: ciemna "pigułka" z ikoną na dole ekranu (odwrócone kolory motywu).
function Toaster(props: ToasterProps) {
  const dark = useDark();
  return (
    <Sonner
      theme={dark ? "dark" : "light"}
      position="bottom-center"
      // nad dolnym paskiem zakładek na telefonie (components/layout/tab-bar.tsx)
      offset={{ bottom: "calc(80px + env(safe-area-inset-bottom))" }}
      mobileOffset={{ bottom: "calc(80px + env(safe-area-inset-bottom))" }}
      duration={2600}
      icons={{
        success: <Icon name="check_circle" />,
        info: <Icon name="info" />,
        warning: <Icon name="warning" />,
        error: <Icon name="error" />,
      }}
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "flex w-full items-center gap-2 rounded-lg bg-foreground px-4.5 py-3.5 text-base font-semibold text-background shadow-[0_10px_30px_rgb(0_0_0/0.25)]",
          icon: "flex shrink-0 items-center",
          // akcja w toaście (np. „Otwórz” przy nowej wiadomości w czacie ekipy)
          actionButton:
            "ml-auto h-11 shrink-0 cursor-pointer rounded-md bg-background px-3.5 text-sm font-bold text-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
