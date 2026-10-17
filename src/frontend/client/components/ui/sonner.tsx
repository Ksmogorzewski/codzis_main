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
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
