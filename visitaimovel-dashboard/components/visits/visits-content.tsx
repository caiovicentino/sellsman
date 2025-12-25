"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select } from "@/components/ui/select";
import { apiClient, type Visit, type VisitsResponse } from "@/lib/api-client";
import { Calendar as CalendarIcon, List, MapPin, User, Clock } from "lucide-react";

const STATUS_LABELS: Record<string, string> = {
  pendente: "Pendente",
  confirmada: "Confirmada",
  realizada: "Realizada",
  cancelada: "Cancelada",
};

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  pendente: "outline",
  confirmada: "default",
  realizada: "secondary",
  cancelada: "destructive",
};

function formatDate(dateString: string): string {
  if (!dateString) return "-";

  // Handle date format "2025-12-25 02:24:24" by replacing space with T
  const isoString = dateString.replace(" ", "T");
  const date = new Date(isoString);

  if (isNaN(date.getTime())) return "-";

  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}

function formatTime(timeString: string): string {
  return timeString.slice(0, 5);
}

function groupVisitsByDate(visits: Visit[]): Record<string, Visit[]> {
  const grouped: Record<string, Visit[]> = {};

  visits.forEach((visit) => {
    const date = visit.scheduled_date;
    if (!grouped[date]) {
      grouped[date] = [];
    }
    grouped[date].push(visit);
  });

  // Sort each group by time
  Object.keys(grouped).forEach((date) => {
    grouped[date].sort((a, b) => a.scheduled_time.localeCompare(b.scheduled_time));
  });

  return grouped;
}

export function VisitsContent() {
  const [data, setData] = useState<VisitsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [view, setView] = useState<"calendar" | "list">("list");

  const fetchVisits = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.visits.getAll({
        status: status ? (status as "pendente" | "confirmada" | "realizada" | "cancelada") : undefined,
      });
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar visitas");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    fetchVisits();
  }, [fetchVisits]);

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatus(e.target.value);
  };

  const groupedVisits = data ? groupVisitsByDate(data.visits) : {};
  const sortedDates = Object.keys(groupedVisits).sort();

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <CardTitle>Agenda de Visitas</CardTitle>
            <CardDescription>
              {data ? `${data.total} visitas registradas` : "Carregando..."}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={status}
              onChange={handleStatusChange}
              className="w-40"
            >
              <option value="">Todos os status</option>
              <option value="pendente">Pendente</option>
              <option value="confirmada">Confirmada</option>
              <option value="realizada">Realizada</option>
              <option value="cancelada">Cancelada</option>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="list" value={view} onValueChange={(v) => setView(v as "calendar" | "list")}>
          <TabsList className="mb-6">
            <TabsTrigger value="list">
              <List className="h-4 w-4 mr-2" />
              Lista
            </TabsTrigger>
            <TabsTrigger value="calendar">
              <CalendarIcon className="h-4 w-4 mr-2" />
              Calendário
            </TabsTrigger>
          </TabsList>

          {error ? (
            <div className="text-center py-12">
              <p className="text-sm text-destructive">{error}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchVisits}
                className="mt-4"
              >
                Tentar novamente
              </Button>
            </div>
          ) : loading ? (
            <div className="text-center py-12">
              <p className="text-sm text-muted-foreground">Carregando visitas...</p>
            </div>
          ) : !data || data.visits.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-sm text-muted-foreground">
                Nenhuma visita encontrada
              </p>
            </div>
          ) : (
            <>
              <TabsContent value="list" className="mt-0">
                <div className="space-y-6">
                  {data.visits
                    .sort((a, b) => {
                      const dateCompare = a.scheduled_date.localeCompare(b.scheduled_date);
                      if (dateCompare !== 0) return dateCompare;
                      return a.scheduled_time.localeCompare(b.scheduled_time);
                    })
                    .map((visit) => (
                      <div
                        key={visit.id}
                        className="flex flex-col sm:flex-row sm:items-center gap-4 p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                      >
                        <div className="flex h-14 w-14 flex-shrink-0 flex-col items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <span className="text-xs font-medium">
                            {formatDate(visit.scheduled_date).split('/')[0]}
                          </span>
                          <span className="text-lg font-bold">
                            {formatTime(visit.scheduled_time)}
                          </span>
                        </div>

                        <div className="flex-1 space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="flex items-center gap-2 mb-1">
                                <User className="h-4 w-4 text-muted-foreground" />
                                <p className="font-medium">{visit.lead_name}</p>
                              </div>
                              {visit.property_address && (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                  <MapPin className="h-3 w-3" />
                                  <span>{visit.property_address}</span>
                                </div>
                              )}
                              {visit.property_type && (
                                <p className="text-sm text-muted-foreground mt-1">
                                  {visit.property_type}
                                </p>
                              )}
                            </div>
                            <Badge variant={STATUS_VARIANTS[visit.status]}>
                              {STATUS_LABELS[visit.status]}
                            </Badge>
                          </div>

                          {visit.notes && (
                            <p className="text-sm text-muted-foreground">
                              {visit.notes}
                            </p>
                          )}

                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3" />
                            <span>Criada em {formatDate(visit.created_at)}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                </div>
              </TabsContent>

              <TabsContent value="calendar" className="mt-0">
                <div className="space-y-8">
                  {sortedDates.map((date) => (
                    <div key={date}>
                      <h3 className="text-lg font-semibold mb-4">
                        {formatDate(date)}
                      </h3>
                      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {groupedVisits[date].map((visit) => (
                          <div
                            key={visit.id}
                            className="p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                          >
                            <div className="flex items-start justify-between mb-3">
                              <div className="flex items-center gap-2 text-lg font-bold text-primary">
                                <Clock className="h-5 w-5" />
                                {formatTime(visit.scheduled_time)}
                              </div>
                              <Badge variant={STATUS_VARIANTS[visit.status]} className="text-xs">
                                {STATUS_LABELS[visit.status]}
                              </Badge>
                            </div>

                            <div className="space-y-2">
                              <div className="flex items-center gap-2">
                                <User className="h-4 w-4 text-muted-foreground" />
                                <p className="font-medium text-sm">{visit.lead_name}</p>
                              </div>

                              {visit.property_address && (
                                <div className="flex items-start gap-2">
                                  <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                                  <p className="text-sm text-muted-foreground">
                                    {visit.property_address}
                                  </p>
                                </div>
                              )}

                              {visit.property_type && (
                                <p className="text-sm text-muted-foreground">
                                  {visit.property_type}
                                </p>
                              )}

                              {visit.notes && (
                                <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
                                  {visit.notes}
                                </p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>
            </>
          )}
        </Tabs>
      </CardContent>
    </Card>
  );
}
