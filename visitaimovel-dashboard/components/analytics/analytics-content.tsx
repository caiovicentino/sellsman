"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type {
  TimeSeriesDataPoint,
  FunnelStage,
  SourceData,
  NeighborhoodData,
} from "@/lib/api-client";
import { TimeSeriesChart } from "./time-series-chart";
import { FunnelChart } from "./funnel-chart";
import { SourcePieChart } from "./source-pie-chart";
import { NeighborhoodBarChart } from "./neighborhood-bar-chart";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";

interface AnalyticsData {
  timeSeries: TimeSeriesDataPoint[];
  funnel: FunnelStage[];
  sources: SourceData[];
  neighborhoods: NeighborhoodData[];
}

export function AnalyticsContent() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<'7d' | '30d' | '90d'>('30d');

  const fetchAnalyticsData = async (selectedPeriod: '7d' | '30d' | '90d') => {
    try {
      setIsLoading(true);
      setError(null);

      const [timeSeriesResponse, funnelResponse, sourcesResponse, neighborhoodsResponse] = await Promise.all([
        apiClient.analytics.getTimeSeries(selectedPeriod),
        apiClient.analytics.getFunnel(),
        apiClient.analytics.getSources(),
        apiClient.analytics.getNeighborhoods(),
      ]);

      setData({
        timeSeries: timeSeriesResponse.data,
        funnel: funnelResponse.stages,
        sources: sourcesResponse.sources,
        neighborhoods: neighborhoodsResponse.neighborhoods,
      });
    } catch (err) {
      console.error('Error fetching analytics data:', err);
      setError(err instanceof Error ? err.message : 'Erro ao carregar dados de analytics');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalyticsData(period);
  }, [period]);

  const handlePeriodChange = (newPeriod: '7d' | '30d' | '90d') => {
    setPeriod(newPeriod);
  };

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Erro</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Time Series Chart - Full Width */}
      <TimeSeriesChart
        data={data?.timeSeries || []}
        onPeriodChange={handlePeriodChange}
        isLoading={isLoading}
      />

      {/* Funnel and Sources - Side by Side */}
      <div className="grid gap-6 md:grid-cols-2">
        <FunnelChart
          data={data?.funnel || []}
          isLoading={isLoading}
        />
        <SourcePieChart
          data={data?.sources || []}
          isLoading={isLoading}
        />
      </div>

      {/* Neighborhoods - Full Width */}
      <NeighborhoodBarChart
        data={data?.neighborhoods || []}
        isLoading={isLoading}
      />
    </div>
  );
}
