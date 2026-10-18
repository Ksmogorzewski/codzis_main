import { type ErrorComponentProps, getRouteApi, Link } from "@tanstack/react-router";
import { type ReactNode, useEffect, useState } from "react";
import { GRID } from "@/components/events/card-skeleton";
import { EventCard } from "@/components/events/event-card";
import { DataRouteError } from "@/components/layout/route-error";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useAcceptFriend, useDeclineFriend, useRemoveFriend } from "@/hooks/use-friend-actions.mutation";
import { useFriends } from "@/hooks/use-friends.query";
import { useFriendsGoing } from "@/hooks/use-friends-going.query";
import { isNameRequired } from "@/lib/api";
import { slotLabel } from "@/lib/events";
import { nearestFor } from "@/lib/friends";
import { startLocation, useLocation } from "@/lib/location";
import { namePrompt } from "@/lib/name-prompt";
import type { Friend, FriendRequest, FriendsGoingCard } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { CodeCard } from "./code-card";
import { CodeInput } from "./code-input";
import { ConfirmSheet } from "./confirm-sheet";

const route = getRouteApi("/_app/znajomi");

/**
 * Zakładka „Znajomi”: u góry wydarzenia, na które idą znajomi („Idę też”), niżej zaproszenia do akceptacji,
 * lista znajomych z najbliższym zapisem, mój kod z QR i pole „Wpisz kod”. Bez znajomych - duży QR.
 */
export function FriendsView() {
  // Loader czeka na pierwszą odpowiedź; potem co 15 s (zaproszenie po zeskanowaniu QR pojawia się samo).
  const initial = route.useLoaderData();
  const friends = useFriends({ live: true });
  const data = friends.data ?? initial;
  useEffect(() => startLocation(), []);

  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-[32px] leading-[1.05] font-extrabold tracking-[-0.03em] md:text-[40px]">Znajomi</h1>
        <p className="text-lg text-muted-foreground">Zobacz, dokąd idą Twoi znajomi, i wybierz się z nimi.</p>
      </header>
      {data.friends.length === 0 ? (
        <div className="mx-auto flex w-full max-w-[440px] flex-col gap-4">
          <Requests items={data.incoming} />
          <p className="text-center text-xl font-extrabold text-balance">Pokaż znajomemu albo wpisz jego kod</p>
          <CodeCard code={data.code} large />
          <CodeInput />
          <Outgoing items={data.outgoing} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
          <div className="flex min-w-0 flex-col gap-6">
            <Going />
            <Requests items={data.incoming} />
            <FriendList friends={data.friends} />
            <Outgoing items={data.outgoing} />
          </div>
          <aside className="flex flex-col gap-4" aria-label="Dodaj znajomego">
            <CodeCard code={data.code} />
            <CodeInput />
          </aside>
        </div>
      )}
    </>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`znajomi-${id}`} className="flex flex-col gap-3">
      <h2 id={`znajomi-${id}`} className="text-xl font-extrabold">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** „Znajomi idą”: nadchodzące wydarzenia znajomych (karta z „Ola idzie” i „Idę też”). */
function Going() {
  const going = useFriendsGoing();
  const { position } = useLocation();
  const now = new Date();
  const items = going.data?.items;

  return (
    <Section id="going" title="Znajomi idą">
      {going.isError ? (
        <p className="text-meta text-muted-foreground">Nie udało się wczytać wydarzeń znajomych.</p>
      ) : !items ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-hidden="true">
          <Skeleton className="h-[360px] rounded-2xl" />
          <Skeleton className="hidden h-[360px] rounded-2xl sm:block" />
        </div>
      ) : items.length > 0 ? (
        <ul className={cn(GRID, "md:grid-cols-2")}>
          {items.map((c) => (
            <li key={c.id} className="flex">
              <EventCard card={c} position={position} now={now} saveLabel="Idę też" />
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-2xl border-[1.5px] border-dashed border-input px-5 py-6 text-center text-meta text-muted-foreground">
          Twoi znajomi nie mają jeszcze zapisów na najbliższe dni.{" "}
          <Link to="/" className="font-bold text-brand-ink underline-offset-4 hover:underline">
            Zaproponuj coś
          </Link>
        </p>
      )}
    </Section>
  );
}

const Initial = ({ name }: { name: string }) => (
  <span
    aria-hidden="true"
    className="grid size-11 shrink-0 place-items-center rounded-full bg-primary-soft text-lg font-extrabold text-primary-ink"
  >
    {name.trim().charAt(0).toUpperCase() || "?"}
  </span>
);

/** Zaproszenia do mnie: Akceptuj / Odrzuć (odrzucenie jest ciche dla zapraszającego). */
function Requests({ items }: { items: FriendRequest[] }) {
  const accept = useAcceptFriend();
  const decline = useDeclineFriend();
  // jedno zapytanie naraz (podwójne stuknięcie nie wysyła drugiego)
  const busy = accept.isPending || decline.isPending;
  if (items.length === 0) return null;

  return (
    <Section id="requests" title="Zaproszenia">
      <ul className="flex flex-col gap-2">
        {items.map((r) => (
          <li key={r.userId}>
            <Card className="flex-row flex-wrap items-center gap-3 p-4">
              <Initial name={r.name} />
              <p className="min-w-0 flex-1">
                <span className="block font-bold">{r.name}</span>
                <span className="text-meta text-muted-foreground">chce dodać Cię do znajomych</span>
              </p>
              <div className="flex w-full gap-2 sm:w-auto">
                <Button
                  className="flex-1"
                  disabled={busy}
                  aria-busy={(accept.isPending && accept.variables === r.userId) || undefined}
                  onClick={() => accept.mutate(r.userId)}
                >
                  Akceptuj
                </Button>
                <Button variant="secondary" className="flex-1" disabled={busy} onClick={() => decline.mutate(r.userId)}>
                  Odrzuć
                </Button>
              </div>
            </Card>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** Lista znajomych z najbliższym zapisem (z „Znajomi idą”) i usuwaniem z potwierdzeniem. */
function FriendList({ friends }: { friends: Friend[] }) {
  const going = useFriendsGoing();
  const remove = useRemoveFriend();
  const [removing, setRemoving] = useState<Friend | null>(null);
  const items = going.data?.items ?? [];
  const now = new Date();

  return (
    <Section id="list" title="Twoi znajomi">
      <ul className="flex flex-col gap-2">
        {friends.map((f) => (
          <li key={f.userId}>
            <Card className="flex-row items-center gap-3 p-4">
              <Initial name={f.name} />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="font-bold">{f.name}</span>
                <NextSave card={nearestFor(f.userId, items)} now={now} loading={!going.data && !going.isError} />
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Usuń ze znajomych: ${f.name}`}
                title="Usuń ze znajomych"
                onClick={() => setRemoving(f)}
              >
                <Icon name="person_remove" size={22} />
              </Button>
            </Card>
          </li>
        ))}
      </ul>
      <ConfirmSheet
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Usunąć ze znajomych: ${removing?.name ?? ""}?`}
        description="Przestaniecie widzieć swoje zapisy. Możecie dodać się ponownie kodem."
        confirm="Usuń"
        onConfirm={() => removing && remove.mutate(removing.userId)}
      />
    </Section>
  );
}

function NextSave({ card, now, loading }: { card: FriendsGoingCard | null; now: Date; loading: boolean }) {
  if (loading) return <Skeleton className="mt-1 h-4 w-40" />;
  if (!card) return <span className="text-meta text-muted-foreground">Brak zapisów na najbliższe dni</span>;
  const when = slotLabel(card.slot, now);
  return (
    <>
      <Link
        to="/wydarzenie/$id"
        params={{ id: card.id }}
        className="truncate rounded-sm text-meta font-semibold text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
      >
        {card.title}
      </Link>
      {when && <span className="text-meta text-muted-foreground">{when}</span>}
    </>
  );
}

/** Wysłane zaproszenia, które czekają na akceptację (odrzucenia nie widać - zostają do wygaśnięcia). */
function Outgoing({ items }: { items: FriendRequest[] }) {
  if (items.length === 0) return null;
  return (
    <Section id="outgoing" title="Wysłane zaproszenia">
      <ul className="flex flex-col gap-1.5 text-meta">
        {items.map((r) => (
          <li key={r.userId} className="flex items-center gap-2">
            <Icon name="schedule_send" size={18} className="text-muted-foreground" />
            <span className="font-semibold">{r.name}</span>
            <span className="text-muted-foreground">czeka na akceptację</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** Szkielet na czas pierwszego ładowania. */
export function FriendsSkeleton() {
  return (
    <>
      <Skeleton className="h-10 w-[40%]" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-hidden="true">
        <Skeleton className="h-[360px] rounded-2xl" />
        <Skeleton className="h-[360px] rounded-2xl" />
      </div>
    </>
  );
}

/** Błąd trasy: konto bez imienia (409 name_required) prosi o imię; inne błędy jak zwykle. */
export function FriendsRouteError(props: ErrorComponentProps) {
  if (!isNameRequired(props.error)) return <DataRouteError {...props} />;
  return <NameNeeded />;
}

export function NameNeeded() {
  return (
    <div className="flex flex-col items-center gap-2.5 rounded-2xl border-[1.5px] border-dashed border-input px-5 py-8 text-center">
      <Icon name="badge" size={40} className="text-muted-foreground" />
      <p className="text-lg font-bold">Podaj imię, żeby dodawać znajomych</p>
      <p className="max-w-md text-meta text-muted-foreground">Znajomi zobaczą tylko Twoje imię — nigdy e-mail.</p>
      <Button size="sm" onClick={() => namePrompt.open()}>
        Podaj imię
      </Button>
    </div>
  );
}
