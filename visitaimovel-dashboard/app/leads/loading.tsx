import { LeadsSkeleton } from "@/components/leads/leads-skeleton";

export default function Loading() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Leads</h1>
        <p className="text-muted-foreground mt-2">
          Gerencie todos os seus leads imobiliários
        </p>
      </div>
      <LeadsSkeleton />
    </div>
  );
}
