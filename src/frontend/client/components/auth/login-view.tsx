import { getRouteApi } from "@tanstack/react-router";
import { dayLine } from "@/lib/events";
import { AuthForm } from "./auth-form";

const route = getRouteApi("/login");

/** Ekran logowania: czerwony plakat z wielkim hasłem (na telefonie u góry, na desktopie po lewej), formularz na papierze. */
export function LoginView() {
  const { googleError } = route.useLoaderData();
  return (
    <div className="grid min-h-dvh grid-cols-1 md:grid-cols-[1.15fr_1fr]">
      <div className="flex flex-col justify-between gap-8 border-b-2 border-input bg-poster-kultura px-5 pt-5 pb-7 text-poster-kultura-foreground md:border-r-2 md:border-b-0 md:px-12 md:py-10">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1.5">
          <span className="font-display text-[22px] leading-none font-black tracking-[-0.02em] [font-stretch:130%] md:text-[28px]">
            WarsawNow
          </span>
          <span className="text-[13px] font-bold tracking-[0.1em] whitespace-nowrap uppercase">{dayLine(new Date())}</span>
        </div>
        <div className="flex flex-col gap-4">
          <h1 className="font-display text-[clamp(52px,17vw,76px)] leading-[0.84] font-black tracking-[-0.01em] uppercase [font-stretch:58%] md:text-[124px]">
            Wiesz,
            <br />
            co robić
            <br />w Warszawie
            <br />
            <span className="text-poster-highlight">dziś</span>
          </h1>
          <p className="max-w-[420px] text-[17px] leading-normal md:text-lg">
            Propozycje na wolny czas dopasowane do Ciebie i Twojej okolicy.
          </p>
        </div>
      </div>

      <div className="flex items-start justify-center bg-background px-5 pt-6 pb-10 md:items-center md:p-12">
        <AuthForm initialError={googleError} />
      </div>
    </div>
  );
}
