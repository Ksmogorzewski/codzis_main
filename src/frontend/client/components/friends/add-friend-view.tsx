import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { errorText } from "@/components/layout/route-error";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useInviteFriend } from "@/hooks/use-friend-actions.mutation";
import { useFriendCodePreview } from "@/hooks/use-friend-code-preview.query";
import { useFriends } from "@/hooks/use-friends.query";
import { ApiRequestError, isNameRequired } from "@/lib/api";
import { normalizeCode } from "@/lib/friends";
import type { FriendPreview, FriendsOverview } from "@/lib/schemas";
import { NameNeeded } from "./friends-view";

const route = getRouteApi("/_app/znajomi_/dodaj/$code");

/**
 * Ekran z linku w QR (albo po wpisaniu kodu): „Wysłać zaproszenie do <Imię>?” -> Wyślij. Własny kod -
 * „To Twój kod”; zły - „Nie ma takiego kodu”. Bez sesji trasa prowadzi przez logowanie i tu wraca.
 */
export function AddFriendView() {
  const { code: raw } = route.useParams();
  const code = normalizeCode(raw);
  const overview = useFriends();
  const preview = useFriendCodePreview(code);

  if (!code) return <NoSuchCode />;
  if (overview.data?.code === code) return <OwnCode />;
  if (preview.isError) return <PreviewError error={preview.error} />;
  if (!preview.data) return <Skeleton className="mx-auto h-[320px] w-full max-w-[440px]" />;
  return <Invite code={code} person={preview.data} overview={overview.data} />;
}

function Invite({ code, person, overview }: { code: string; person: FriendPreview; overview?: FriendsOverview }) {
  const navigate = useNavigate();
  const invite = useInviteFriend();
  const isFriend = overview?.friends.some((f) => f.userId === person.userId) ?? false;
  const pending = overview?.outgoing.some((r) => r.userId === person.userId) ?? false;

  if (isFriend) {
    return (
      <Message icon="diversity_3" title={`${person.name} jest już Twoim znajomym`}>
        <BackToFriends />
      </Message>
    );
  }

  return (
    <Message
      icon="person_add"
      title={`Wysłać zaproszenie do użytkownika ${person.name}?`}
      description={
        pending
          ? "Zaproszenie już wysłane — czeka na akceptację."
          : `${person.name} zobaczy Twoje imię i zdecyduje, czy przyjąć zaproszenie. Potem zobaczycie nawzajem, na co się wybieracie.`
      }
    >
      {!pending && (
        <Button
          variant="brand"
          size="lg"
          className="w-full"
          aria-busy={invite.isPending || undefined}
          onClick={() => {
            if (invite.isPending) return;
            invite.mutate(code, { onSuccess: () => void navigate({ to: "/znajomi" }) });
          }}
        >
          <Icon name="send" />
          Wyślij
        </Button>
      )}
      <BackToFriends secondary={!pending} />
    </Message>
  );
}

function PreviewError({ error }: { error: unknown }) {
  if (isNameRequired(error)) return <NameNeeded />;
  const status = error instanceof ApiRequestError ? error.status : 0;
  if (status === 404) return <NoSuchCode />;
  if (status === 400) return <OwnCode />; // backend: „Nie możesz dodać siebie”
  return (
    <Message icon="error" title={errorText(error, "Nie udało się sprawdzić kodu.")}>
      <BackToFriends />
    </Message>
  );
}

const NoSuchCode = () => (
  <Message icon="search_off" title="Nie ma takiego kodu" description="Sprawdź kod u znajomego i wpisz go jeszcze raz.">
    <BackToFriends />
  </Message>
);

const OwnCode = () => (
  <Message icon="qr_code_2" title="To Twój kod" description="Pokaż go znajomemu, żeby mógł Cię dodać.">
    <BackToFriends />
  </Message>
);

function BackToFriends({ secondary = false }: { secondary?: boolean }) {
  return (
    <Button asChild variant={secondary ? "ghost" : "default"} size="lg" className="w-full">
      <Link to="/znajomi">{secondary ? "Anuluj" : "Przejdź do znajomych"}</Link>
    </Button>
  );
}

type MessageProps = { icon: string; title: string; description?: string; children: ReactNode };

function Message({ icon, title, description, children }: MessageProps) {
  return (
    <Card className="mx-auto w-full max-w-[440px] items-center gap-4 p-6 text-center">
      <span className="grid size-16 place-items-center bg-foreground text-background">
        <Icon name={icon} size={32} />
      </span>
      <h1 className="text-[25px] leading-tight font-extrabold tracking-[-0.02em] text-balance">{title}</h1>
      {description && <p className="text-base text-muted-foreground text-pretty">{description}</p>}
      <div className="flex w-full flex-col gap-2">{children}</div>
    </Card>
  );
}
