import { Skeleton } from "@/components/ui/skeleton";

export function DetailSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-4">
      <Skeleton className="h-60 rounded-2xl md:h-[360px]" />
      <Skeleton className="h-8 w-[80%]" />
      <Skeleton className="h-4 w-[50%]" />
      <Skeleton className="h-4 w-[65%]" />
    </div>
  );
}
