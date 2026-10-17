import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Siatka kart: 1 kolumna na telefonie, 2 od ~620 px, 3 od 860 px. */
export const GRID = "grid grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))] gap-4 md:grid-cols-3";

// Szkielet karty: ta sama ramka i proporcje co EventCard.
function CardSkeleton() {
  return (
    <Card aria-hidden="true">
      <Skeleton className="h-[168px] rounded-none" />
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-5 w-[90%]" />
        <Skeleton className="h-3.5 w-[70%]" />
        <Skeleton className="h-3.5 w-[40%]" />
        <Skeleton className="mt-1.5 h-12 rounded-lg" />
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
