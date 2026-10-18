import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Siatka kart: 1 kolumna na telefonie, 2 od ~680 px, 3 od 860 px. */
export const GRID = "grid grid-cols-[repeat(auto-fill,minmax(min(320px,100%),1fr))] gap-5 md:grid-cols-3";

// Szkielet karty: ta sama ramka i proporcje co EventCard (pole plakatu + dół z informacjami).
function CardSkeleton() {
  return (
    <Card aria-hidden="true">
      <Skeleton className="h-[200px] border-b-2 border-input" />
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-4 w-[70%]" />
        <Skeleton className="h-4 w-[40%]" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="mt-1 h-12" />
      </div>
    </Card>
  );
}

export function GridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className={GRID}>
      {Array.from({ length: count }, (_, i) => `sk-${i}`).map((key) => (
        <CardSkeleton key={key} />
      ))}
    </div>
  );
}
