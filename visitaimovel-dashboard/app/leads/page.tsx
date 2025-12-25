import { Suspense } from "react";
import { LeadsContent } from "@/components/leads/leads-content";
import { LeadsSkeleton } from "@/components/leads/leads-skeleton";

export const dynamic = 'force-dynamic';

export default function LeadsPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Leads</h1>
        <p className="text-muted-foreground mt-2">
          Gerencie todos os seus leads imobiliários
        </p>
      </div>

      <Suspense fallback={<LeadsSkeleton />}>
        <LeadsContent />
      </Suspense>
    </div>
  );
}
