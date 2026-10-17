import { AuthForm } from "./auth-form";

/** Ekran logowania z mockupu: granatowe hero z czerwonym kołem Warszawy po lewej, formularz po prawej. */
export function LoginView() {
  return (
    <div className="grid min-h-dvh grid-cols-1 md:grid-cols-[1.1fr_1fr]">
      <div className="relative flex flex-col justify-between gap-9 overflow-hidden bg-primary-deep px-6 pt-7 pb-10 text-white md:px-14 md:py-12">
        <div
          aria-hidden="true"
          className="absolute -right-[180px] -bottom-[200px] size-[420px] rounded-full bg-brand opacity-90"
        />
        <div
          aria-hidden="true"
          className="absolute right-[60px] bottom-[120px] size-[180px] rounded-full border-2 border-white/20"
        />
        <div className="relative flex items-center gap-2.5">
          <img
            src="/assets/logo.jpg"
            alt=""
            width={49}
            height={49}
            className="size-[49px] rounded-[14px] bg-white object-cover"
          />
          <div className="text-[22px] font-extrabold tracking-[-0.02em]">
            Warsaw<span className="text-brand-on-dark">Now</span>
          </div>
        </div>
        <div className="relative flex max-w-[520px] flex-col gap-4">
          <h1 className="text-[40px] leading-[1.05] font-extrabold tracking-[-0.03em] text-balance md:text-[64px]">
            Wiesz, co robić w Warszawie dziś
          </h1>
          <p className="max-w-[420px] text-lg leading-normal text-white/80">
            Propozycje na wolny czas dopasowane do Ciebie i Twojej okolicy.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-center bg-background px-6 pt-7 pb-10 md:p-12">
        <AuthForm />
      </div>
    </div>
  );
}
