"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiClient, type Lead, type LeadsResponse } from "@/lib/api-client";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";

const STATUS_LABELS: Record<string, string> = {
  novo: "Novo",
  qualificado: "Qualificado",
  visita_agendada: "Visita Agendada",
  negociando: "Negociando",
  convertido: "Convertido",
  perdido: "Perdido",
};

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  novo: "outline",
  qualificado: "default",
  visita_agendada: "secondary",
  negociando: "default",
  convertido: "default",
  perdido: "destructive",
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

function formatPhone(phone: string): string {
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 11) {
    return `(${cleaned.slice(0, 2)}) ${cleaned.slice(2, 7)}-${cleaned.slice(7)}`;
  }
  return phone;
}

export function LeadsContent() {
  const router = useRouter();
  const [data, setData] = useState<LeadsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1); // Reset to first page on new search
    }, 500);

    return () => clearTimeout(timer);
  }, [search]);

  const fetchLeads = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.leads.getAll({
        page,
        page_size: 20,
        search: debouncedSearch || undefined,
        status: status || undefined,
      });
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar leads");
    } finally {
      setLoading(false);
    }
  }, [page, debouncedSearch, status]);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatus(e.target.value);
    setPage(1);
  };

  const handleRowClick = (leadId: string) => {
    router.push(`/leads/${leadId}`);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Lista de Leads</CardTitle>
        <CardDescription>
          {data ? `${data.total} leads cadastrados no sistema` : "Carregando..."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-6 flex flex-col sm:flex-row gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar por nome, telefone..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select
            value={status}
            onChange={handleStatusChange}
            className="sm:w-48"
          >
            <option value="">Todos os status</option>
            <option value="novo">Novo</option>
            <option value="qualificado">Qualificado</option>
            <option value="visita_agendada">Visita Agendada</option>
            <option value="negociando">Negociando</option>
            <option value="convertido">Convertido</option>
            <option value="perdido">Perdido</option>
          </Select>
        </div>

        {error ? (
          <div className="text-center py-12">
            <p className="text-sm text-destructive">{error}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchLeads}
              className="mt-4"
            >
              Tentar novamente
            </Button>
          </div>
        ) : loading ? (
          <div className="text-center py-12">
            <p className="text-sm text-muted-foreground">Carregando leads...</p>
          </div>
        ) : !data || data.leads.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-sm text-muted-foreground">
              Nenhum lead encontrado
            </p>
          </div>
        ) : (
          <>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>Telefone</TableHead>
                    <TableHead>Bairro</TableHead>
                    <TableHead className="text-center">Quartos</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Data</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.leads.map((lead) => (
                    <TableRow
                      key={lead.id}
                      className="cursor-pointer"
                      onClick={() => handleRowClick(lead.id)}
                    >
                      <TableCell className="font-medium">{lead.name}</TableCell>
                      <TableCell>{formatPhone(lead.phone)}</TableCell>
                      <TableCell>
                        {lead.preferences.neighborhoods?.[0] || "-"}
                      </TableCell>
                      <TableCell className="text-center">
                        {lead.preferences.bedrooms || "-"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_VARIANTS[lead.status]}>
                          {STATUS_LABELS[lead.status]}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDate(lead.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {data.total_pages > 1 && (
              <div className="flex items-center justify-between mt-6">
                <p className="text-sm text-muted-foreground">
                  Página {data.page} de {data.total_pages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1 || loading}
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Anterior
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
                    disabled={page === data.total_pages || loading}
                  >
                    Próxima
                    <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
