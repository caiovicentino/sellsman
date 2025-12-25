import { VisitsSkeleton } from "@/components/visits/visits-skeleton";

export default function Loading() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Visitas</h1>
        <p className="text-muted-foreground mt-2">
          Gerencie todas as visitas agendadas
        </p>
      </div>
      <VisitsSkeleton />
    </div>
  );
}
