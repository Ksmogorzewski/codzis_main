import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttendees } from "@/hooks/use-attendees.query";
import { attendeeLabel, savesLabel } from "@/lib/community";
import { cn } from "@/lib/utils";

/**
 * „Kto się wybiera”: liczba i imiona zapisanych (kolejność z API: ja, znajomi, reszta od najnowszych);
 * znajomi z ikonką. Bez danych z API sekcja znika.
 */
export function AttendeesSection({ id }: { id: string }) {
  const attendees = useAttendees(id);
  if (attendees.isError) return null;
  const data = attendees.data;

  return (
    <Card className="gap-3 p-5">
      <h2 className="flex items-center gap-2 text-xl font-extrabold">
        <Icon name="group" size={24} filled className="text-primary-ink" />
        Kto się wybiera
      </h2>
      {!data ? (
        <div aria-hidden="true" className="flex flex-col gap-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-9 w-[70%] rounded-full" />
        </div>
      ) : (
        <>
          <p className="text-meta font-semibold text-muted-foreground" aria-live="polite">
            {savesLabel(data.saves)}
          </p>
          {data.people.length > 0 ? (
            <ul className="flex flex-wrap gap-2">
              {data.people.map((p, i) => (
                <li
                  // imiona się powtarzają, a lista nie ma id osób - pozycja wystarcza (lista tylko do odczytu)
                  key={`${i}-${p.name ?? ""}`}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1.5 text-base font-semibold",
                    (p.isMe || p.isFriend) && "bg-primary-soft text-primary-ink",
                  )}
                >
                  {p.isFriend && !p.isMe && <Icon name="diversity_3" size={18} filled />}
                  {attendeeLabel(p)}
                  {p.isFriend && !p.isMe && <span className="sr-only">(znajomy)</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-base text-muted-foreground">Jeszcze nikt się nie zapisał — bądź pierwszy.</p>
          )}
          {data.saves > data.people.length && (
            <p className="text-sm text-muted-foreground">Pokazujemy ostatnio zapisanych.</p>
          )}
        </>
      )}
    </Card>
  );
}
