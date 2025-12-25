"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface FunnelStage {
  stage: string;
  count: number;
  percentage: number;
}

interface FunnelChartProps {
  data: FunnelStage[];
  isLoading?: boolean;
}

const stageLabels: Record<string, string> = {
  'landing_leads': 'Leads Captados',
  'contacted': 'Contatados',
  'qualified': 'Qualificados',
  'visit_scheduled': 'Visita Agendada',
  'visit_completed': 'Visita Realizada',
};

const stageColors = [
  '#dbeafe', // blue-100
  '#bfdbfe', // blue-200
  '#93c5fd', // blue-300
  '#60a5fa', // blue-400
  '#3b82f6', // blue-500
];

export function FunnelChart({ data, isLoading }: FunnelChartProps) {
  const formattedData = data.map((item, index) => ({
    ...item,
    label: stageLabels[item.stage] || item.stage,
    displayValue: `${item.count} (${item.percentage.toFixed(1)}%)`,
    color: stageColors[index] || stageColors[stageColors.length - 1],
  }));

  const calculateConversionRate = (currentIndex: number): string => {
    if (currentIndex === 0) return '';
    const current = data[currentIndex];
    const previous = data[currentIndex - 1];
    if (previous.count === 0) return '0%';
    const rate = (current.count / previous.count) * 100;
    return `${rate.toFixed(1)}%`;
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const index = formattedData.findIndex(item => item.stage === data.stage);
      const conversionRate = calculateConversionRate(index);

      return (
        <div className="bg-background border rounded-lg shadow-lg p-3">
          <p className="text-sm font-medium mb-2">{data.label}</p>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Total:</span>
              <span className="font-medium">{data.count}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Do total:</span>
              <span className="font-medium">{data.percentage.toFixed(1)}%</span>
            </div>
            {conversionRate && (
              <div className="flex justify-between gap-4 pt-1 border-t">
                <span className="text-muted-foreground">Conversão:</span>
                <span className="font-medium text-green-600 dark:text-green-400">{conversionRate}</span>
              </div>
            )}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Funil de Conversão</CardTitle>
        <CardDescription>Etapas do processo de vendas e taxas de conversão</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-[400px] flex items-center justify-center">
            <div className="text-sm text-muted-foreground">Carregando dados...</div>
          </div>
        ) : data.length === 0 ? (
          <div className="h-[400px] flex items-center justify-center">
            <div className="text-sm text-muted-foreground">Nenhum dado disponível</div>
          </div>
        ) : (
          <div className="space-y-6">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={formattedData}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 120, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" horizontal={false} />
                <XAxis type="number" className="text-xs" stroke="currentColor" />
                <YAxis
                  type="category"
                  dataKey="label"
                  className="text-xs"
                  stroke="currentColor"
                  width={110}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {formattedData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            {/* Conversion Rates Display */}
            <div className="space-y-2 pt-4 border-t">
              <p className="text-sm font-medium mb-3">Taxa de Conversão entre Etapas</p>
              <div className="grid grid-cols-1 gap-2">
                {formattedData.slice(1).map((item, index) => {
                  const conversionRate = calculateConversionRate(index + 1);
                  return (
                    <div key={item.stage} className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">
                        {formattedData[index].label} → {item.label}
                      </span>
                      <span className="font-medium text-green-600 dark:text-green-400">
                        {conversionRate}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
