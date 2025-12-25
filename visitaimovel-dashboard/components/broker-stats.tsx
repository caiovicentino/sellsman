"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { brokersApi, BrokerRankingItem } from "@/lib/api-brokers";

export function BrokerStats() {
  const [ranking, setRanking] = useState<BrokerRankingItem[]>([]);
  const [period, setPeriod] = useState<"7d" | "30d" | "90d">("30d");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRanking();
  }, [period]);

  const loadRanking = async () => {
    setLoading(true);
    try {
      const response = await brokersApi.ranking(period);
      setRanking(response.data);
    } catch (error) {
      console.error("Erro ao carregar ranking:", error);
    } finally {
      setLoading(false);
    }
  };

  const getPeriodLabel = () => {
    const labels = {
      "7d": "Últimos 7 dias",
      "30d": "Últimos 30 dias",
      "90d": "Últimos 90 dias",
    };
    return labels[period];
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Ranking de Performance</CardTitle>
            <CardDescription>
              Corretores com melhor desempenho
            </CardDescription>
          </div>
          <div className="flex gap-2">
            {(["7d", "30d", "90d"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1 text-sm rounded ${
                  period === p
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted hover:bg-muted/80"
                }`}
              >
                {p === "7d" ? "7d" : p === "30d" ? "30d" : "90d"}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">
            Carregando...
          </div>
        ) : ranking.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Nenhum corretor com visitas no período
          </div>
        ) : (
          <div className="space-y-4">
            {ranking.slice(0, 5).map((broker) => (
              <div
                key={broker.id}
                className="flex items-center justify-between p-3 rounded-lg border"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold ${
                      broker.rank === 1
                        ? "bg-yellow-500 text-white"
                        : broker.rank === 2
                        ? "bg-gray-400 text-white"
                        : broker.rank === 3
                        ? "bg-orange-600 text-white"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {broker.rank}
                  </div>
                  <div>
                    <p className="font-medium">{broker.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {broker.completed_visits} visitas completadas
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <Badge variant="secondary">
                    {broker.avg_feedback_score.toFixed(1)} ★
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
