import { type ChangeEvent, type FormEvent, type ReactNode, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSaveAccount } from "@/hooks/use-account.mutation";
import { useDeletePhoto, useUploadPhoto } from "@/hooks/use-photo.mutation";
import {
  accountInput,
  ageOn,
  avatarInitials,
  birthDateError,
  fullName,
  MIN_BIRTH_DATE,
  photoFileError,
} from "@/lib/account";
import { warsawDate } from "@/lib/events";
import type { Me } from "@/lib/schemas";
import { plural } from "../../../shared/format";

/**
 * „Twoje dane” na stronie profilu: zdjęcie, imię i nazwisko (z rejestracji albo Google, bez zmian – innym
 * pokazujemy „Ola K.”) i data urodzenia (widzi ją tylko właściciel). Przy koncie Google zdjęcie przychodzi
 * z Google przy pierwszym logowaniu; potem zmienia je już tylko użytkownik.
 */
export function AccountCard({ me }: { me: Me }) {
  const save = useSaveAccount();
  const upload = useUploadPhoto();
  const removePhoto = useDeletePhoto();
  const fileInput = useRef<HTMLInputElement>(null);
  const [birthDate, setBirthDate] = useState(me.account.birthDate ?? "");
  const [error, setError] = useState<string | null>(null);

  const today = warsawDate(new Date());
  const input = accountInput(birthDate);
  const dirty = input.birthDate !== me.account.birthDate;
  const photo = me.account.photoUrl;
  const photoBusy = upload.isPending || removePhoto.isPending;
  const age = birthDate && !birthDateError(birthDate, today) ? ageOn(birthDate, today) : null;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const problem = birthDateError(birthDate, today);
    setError(problem);
    if (problem) return;
    save.mutate(input, {
      onSuccess: () => toast.success("Zapisaliśmy Twoje dane"),
      onError: (err) => setError(err.message),
    });
  }

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // ten sam plik da się wybrać jeszcze raz
    if (!file) return;
    const problem = photoFileError(file);
    setError(problem);
    if (problem) return;
    upload.mutate(file, {
      onSuccess: () => toast.success("Zdjęcie zmienione"),
      onError: (err) => setError(err.message),
    });
  }

  function onRemovePhoto() {
    setError(null);
    removePhoto.mutate(undefined, { onError: (err) => setError(err.message) });
  }

  return (
    <Card className="gap-5 p-5">
      <div className="flex items-center gap-4">
        <Avatar key={photo ?? "brak"} url={photo} first={me.name} last={me.familyName} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="text-xl font-extrabold text-pretty">{fullName(me.name, me.familyName) || "Twoje dane"}</h2>
          <p className="truncate text-meta text-muted-foreground">
            {me.identityProvider === "Google" ? "Konto Google" : "Konto e-mail"}
            {me.email && ` · ${me.email}`}
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" disabled={photoBusy} onClick={() => fileInput.current?.click()}>
              <Icon name="photo_camera" size={20} />
              {upload.isPending ? "Wysyłam…" : photo ? "Zmień zdjęcie" : "Dodaj zdjęcie"}
            </Button>
            {photo && (
              <Button type="button" variant="ghost" size="sm" disabled={photoBusy} onClick={onRemovePhoto}>
                Usuń zdjęcie
              </Button>
            )}
          </div>
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={onFile}
          />
        </div>
      </div>

      <form className="grid gap-4 md:grid-cols-3" onSubmit={onSubmit} noValidate>
        <Field id="account-first-name" label="Imię" hint="Widzą je inni zapisani. Nie zmienisz go.">
          <Input id="account-first-name" value={me.name ?? ""} readOnly disabled />
        </Field>
        <Field
          id="account-last-name"
          label="Nazwisko"
          hint={me.familyName ? "Inni widzą tylko pierwszą literę. Nie zmienisz go." : "Nie podano przy rejestracji."}
        >
          <Input id="account-last-name" value={me.familyName ?? ""} readOnly disabled />
        </Field>
        <Field
          id="account-birth-date"
          label="Data urodzenia"
          hint={age === null ? "Opcjonalnie. Widzisz ją tylko Ty." : `${plural(age, "rok", "lata", "lat")} · widzisz ją tylko Ty.`}
        >
          <Input
            id="account-birth-date"
            type="date"
            autoComplete="bday"
            min={MIN_BIRTH_DATE}
            max={today}
            value={birthDate}
            onChange={(e) => setBirthDate(e.target.value)}
          />
        </Field>

        {error && (
          <Alert variant="destructive" className="md:col-span-3">
            <Icon name="error" size={22} className="mt-px" />
            <AlertTitle className="font-semibold">{error}</AlertTitle>
          </Alert>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 md:col-span-3">
          <Button type="submit" disabled={!dirty || save.isPending} aria-busy={save.isPending}>
            {save.isPending ? "Zapisuję…" : "Zapisz dane"}
          </Button>
          <a
            className="rounded-sm text-meta text-muted-foreground underline underline-offset-4 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring"
            href="/polityka-prywatnosci.html"
          >
            Jak używamy Twoich danych
          </a>
        </div>
      </form>
    </Card>
  );
}

/** Zdjęcie profilowe albo inicjały; zdjęcie, które się nie wczyta (np. wygasłe z Google), też daje inicjały. */
function Avatar({ url, first, last }: { url: string | null; first: string | null; last: string | null }) {
  const [broken, setBroken] = useState(false);
  if (url && !broken) {
    return (
      <img
        src={url}
        alt=""
        width={80}
        height={80}
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
        className="size-20 shrink-0 rounded-full bg-secondary object-cover"
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className="grid size-20 shrink-0 place-items-center rounded-full bg-primary-soft text-2xl font-extrabold text-primary-ink"
    >
      {avatarInitials(first, last)}
    </span>
  );
}

function Field({ id, label, hint, children }: { id: string; label: string; hint: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      <p className="text-meta text-muted-foreground">{hint}</p>
    </div>
  );
}
