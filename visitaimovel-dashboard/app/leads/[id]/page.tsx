import { Suspense } from "react";
import { LeadDetailContent } from "@/components/leads/lead-detail-content";
import { LeadDetailSkeleton } from "@/components/leads/lead-detail-skeleton";

export const dynamic = 'force-dynamic';

interface LeadDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function LeadDetailPage({ params }: LeadDetailPageProps) {
  const { id } = await params;

  return (
    <div>
      <Suspense fallback={<LeadDetailSkeleton />}>
        <LeadDetailContent leadId={id} />
      </Suspense>
    </div>
  );
}
