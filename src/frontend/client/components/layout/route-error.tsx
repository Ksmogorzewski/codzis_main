import { type ErrorComponentProps, useRouter } from "@tanstack/react-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";

type Props = { message: string; onRetry?: () => void; retryable?: boolean };

/** Wspólny błąd tras: komunikat i przycisk ponowienia (przeładowuje loadery trasy). */
export function RouteError({ message, onRetry, retryable = true }: Props) {
  const router = useRouter();
  return (
    <Alert variant="destructive">
      <Icon name="error" size={22} className="mt-px" />
      <AlertTitle>{message}</AlertTitle>
      {retryable && (
        <AlertDescription>
          <Button
            variant="link"
            size="inline"
            className="font-bold text-brand-ink"
            onClick={() => {
              onRetry?.();
              router.invalidate();
            }}
          >
            Spróbuj ponownie
          </Button>
        </AlertDescription>
      )}
    </Alert>
  );
}

/** errorComponent tras bez własnego komunikatu: błąd renderowania to nie brak serwera. */
export function GenericRouteError({ reset }: ErrorComponentProps) {
  return <RouteError message="Coś poszło nie tak" onRetry={reset} />;
}

/** Jak wyżej, ale dla tras poza layoutem (logowanie, sam layout): z własnym marginesem strony. */
export function PageRouteError(props: ErrorComponentProps) {
  return (
    <main className="mx-auto w-full max-w-[1160px] px-4 pt-[18px] pb-10 md:px-8 md:pt-8">
      <GenericRouteError {...props} />
    </main>
  );
}
