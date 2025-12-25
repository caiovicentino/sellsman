import { Suspense } from "react";
import { VisitsContent } from "@/components/visits/visits-content";
import { VisitsSkeleton } from "@/components/visits/visits-skeleton";

export const dynamic = 'force-dynamic';

export default function VisitsPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Visitas</h1>
        <p className="text-muted-foreground mt-2">
          Gerencie todas as visitas agendadas
        </p>
      </div>

      <Suspense fallback={<VisitsSkeleton />}>
        <VisitsContent />
      </Suspense>
    </div>
  );
}
