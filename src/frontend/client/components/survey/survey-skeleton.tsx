import { Skeleton } from "@/components/ui/skeleton";

export function SurveySkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-9 w-[80%] max-w-xl" />
        <Skeleton className="h-4 w-[60%] max-w-md" />
      </div>
      <Skeleton className="h-3 rounded-full" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {["a", "b", "c", "d"].map((k) => (
          <Skeleton key={k} className="h-[190px] md:h-[220px]" />
        ))}
      </div>
    </div>
  );
}
