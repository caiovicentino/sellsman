import { Suspense } from "react";
import { AnalyticsContent } from "@/components/analytics/analytics-content";
import { AnalyticsSkeleton } from "@/components/analytics/analytics-skeleton";

export const dynamic = 'force-dynamic';

export const metadata = {
  title: "Analytics | VisitaImovel Dashboard",
  description: "Análise detalhada de leads e visitas",
};

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground mt-2">
          Análise detalhada de leads, conversões e performance
        </p>
      </div>

      <Suspense fallback={<AnalyticsSkeleton />}>
        <AnalyticsContent />
      </Suspense>
    </div>
  );
}
