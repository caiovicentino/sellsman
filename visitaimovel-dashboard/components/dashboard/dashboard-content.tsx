"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Users, Calendar, TrendingUp, Target, CheckCircle } from "lucide-react";

interface DashboardMetrics {
  total_leads: number;
  leads_today: number;
  pending_visits: number;
  confirmed_visits: number;
  completed_visits: number;
  total_visits: number;
  conversion_rate: number;
  leads_by_status: Record<string, number>;
  visits_by_status: Record<string, number>;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5002";

export function DashboardContent() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchMetrics() {
      try {
        const response = await fetch(`${API_URL}/api/v1/dashboard/metrics`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setMetrics(data);
      } catch (err) {
        console.error("Failed to fetch metrics:", err);
        setError(err instanceof Error ? err.message : "Erro ao carregar dados");
      } finally {
        setLoading(false);
      }
    }

    fetchMetrics();
  }, []);

  if (loading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16 mb-2" />
              <Skeleton className="h-3 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6">
          <p className="text-destructive text-center">
            Erro ao carregar dashboard: {error}
          </p>
          <p className="text-muted-foreground text-center text-sm mt-2">
            Verifique se o backend está rodando em {API_URL}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!metrics) {
    return null;
  }

  const stats = [
    {
      name: "Total de Leads",
      value: metrics.total_leads.toString(),
      description: "leads cadastrados",
      icon: Users,
    },
    {
      name: "Leads Hoje",
      value: metrics.leads_today.toString(),
      description: "novos leads hoje",
      icon: Target,
    },
    {
      name: "Visitas Pendentes",
      value: metrics.pending_visits.toString(),
      description: `${metrics.confirmed_visits} confirmadas`,
      icon: Calendar,
    },
    {
      name: "Taxa de Conversão",
      value: `${(metrics.conversion_rate || 0).toFixed(1)}%`,
      description: `${metrics.completed_visits} visitas concluídas`,
      icon: TrendingUp,
    },
  ];

  const leadStatusLabels: Record<string, string> = {
    pending: "Pendentes",
    contacted: "Contatados",
    qualified: "Qualificados",
    scheduled: "Agendados",
    completed: "Convertidos",
  };

  const visitStatusLabels: Record<string, string> = {
    pending: "Pendentes",
    confirmed: "Confirmadas",
    completed: "Concluídas",
    cancelled: "Canceladas",
  };

  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.name}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {stat.name}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {stat.description}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Leads por Status</CardTitle>
            <CardDescription>
              Distribuição de leads por status atual
            </CardDescription>
          </CardHeader>
          <CardContent>
            {Object.keys(metrics.leads_by_status).length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                Nenhum lead cadastrado ainda
              </p>
            ) : (
              <div className="space-y-4">
                {Object.entries(metrics.leads_by_status).map(([status, count]) => (
                  <div key={status} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-primary" />
                      <span className="text-sm font-medium">
                        {leadStatusLabels[status] || status}
                      </span>
                    </div>
                    <span className="text-sm font-bold">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Visitas por Status</CardTitle>
            <CardDescription>
              Distribuição de visitas agendadas
            </CardDescription>
          </CardHeader>
          <CardContent>
            {metrics.total_visits === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                Nenhuma visita agendada ainda
              </p>
            ) : (
              <div className="space-y-4">
                {Object.entries(metrics.visits_by_status).map(([status, count]) => (
                  <div key={status} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">
                        {visitStatusLabels[status] || status}
                      </span>
                    </div>
                    <span className="text-sm font-bold">{count}</span>
                  </div>
                ))}
                {Object.keys(metrics.visits_by_status).length === 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Total de visitas</span>
                    <span className="text-sm font-bold">{metrics.total_visits}</span>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
