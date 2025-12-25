"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface NeighborhoodData {
  neighborhood: string;
  count: number;
}

interface NeighborhoodBarChartProps {
  data: NeighborhoodData[];
  isLoading?: boolean;
}

const COLORS = [
  '#3b82f6', // blue-500
  '#60a5fa', // blue-400
  '#93c5fd', // blue-300
  '#bfdbfe', // blue-200
  '#dbeafe', // blue-100
];

export function NeighborhoodBarChart({ data, isLoading }: NeighborhoodBarChartProps) {
  // Sort by count and take top 10
  const top10Data = [...data]
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
    .reverse(); // Reverse to show highest at top in horizontal chart

  const maxCount = Math.max(...top10Data.map(item => item.count), 0);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const totalLeads = top10Data.reduce((sum, item) => sum + item.count, 0);
      const percentage = totalLeads > 0 ? (data.count / totalLeads * 100) : 0;

      return (
        <div className="bg-background border rounded-lg shadow-lg p-3">
          <p className="text-sm font-medium mb-2">{data.neighborhood}</p>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Leads:</span>
              <span className="font-medium">{data.count}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Do Top 10:</span>
              <span className="font-medium">{percentage.toFixed(1)}%</span>
            </div>
          </div>
        </div>
      );
    }
    return null;
  };

  const getBarColor = (count: number): string => {
    const percentage = maxCount > 0 ? count / maxCount : 0;
    if (percentage > 0.8) return COLORS[0];
    if (percentage > 0.6) return COLORS[1];
    if (percentage > 0.4) return COLORS[2];
    if (percentage > 0.2) return COLORS[3];
    return COLORS[4];
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Top Bairros</CardTitle>
        <CardDescription>10 bairros com maior número de leads</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-[500px] flex items-center justify-center">
            <div className="text-sm text-muted-foreground">Carregando dados...</div>
          </div>
        ) : data.length === 0 ? (
          <div className="h-[500px] flex items-center justify-center">
            <div className="text-sm text-muted-foreground">Nenhum dado disponível</div>
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={500}>
              <BarChart
                data={top10Data}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" horizontal={false} />
                <XAxis type="number" className="text-xs" stroke="currentColor" />
                <YAxis
                  type="category"
                  dataKey="neighborhood"
                  className="text-xs"
                  stroke="currentColor"
                  width={150}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {top10Data.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={getBarColor(entry.count)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            {/* Summary Stats */}
            <div className="grid grid-cols-3 gap-4 pt-6 border-t mt-4">
              <div className="text-center">
                <p className="text-2xl font-bold">
                  {top10Data.length > 0 ? top10Data[top10Data.length - 1].count : 0}
                </p>
                <p className="text-xs text-muted-foreground mt-1">Bairro líder</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold">
                  {top10Data.reduce((sum, item) => sum + item.count, 0)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">Total Top 10</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold">
                  {Math.round(top10Data.reduce((sum, item) => sum + item.count, 0) / Math.max(top10Data.length, 1))}
                </p>
                <p className="text-xs text-muted-foreground mt-1">Média por bairro</p>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
