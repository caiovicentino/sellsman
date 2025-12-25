"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { brokersApi, Broker } from "@/lib/api-brokers";
import { BrokerFormDialog } from "@/components/broker-form-dialog";
import { BrokerStats } from "@/components/broker-stats";
import { PlusCircle, Pencil, Trash2, Phone, Mail } from "lucide-react";

export default function BrokersPage() {
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedBroker, setSelectedBroker] = useState<Broker | null>(null);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    loadBrokers();
  }, []);

  const loadBrokers = async () => {
    setLoading(true);
    try {
      const response = await brokersApi.list({ per_page: 50 });
      setBrokers(response.data);
      setTotal(response.total);
    } catch (error) {
      console.error("Erro ao carregar corretores:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = () => {
    setSelectedBroker(null);
    setDialogOpen(true);
  };

  const handleEdit = (broker: Broker) => {
    setSelectedBroker(broker);
    setDialogOpen(true);
  };

  const handleDelete = async (broker: Broker) => {
    if (!confirm(`Deseja realmente desativar o corretor ${broker.name}?`)) {
      return;
    }

    try {
      await brokersApi.delete(broker.id);
      loadBrokers();
    } catch (error) {
      console.error("Erro ao deletar corretor:", error);
      alert("Erro ao desativar corretor");
    }
  };

  const handleSuccess = () => {
    loadBrokers();
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Corretores</h1>
        <p className="text-muted-foreground mt-2">
          Gerencie a equipe de corretores e acompanhe o desempenho
        </p>
      </div>

      <div className="grid gap-6 mb-6">
        <BrokerStats />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Lista de Corretores</CardTitle>
              <CardDescription>
                {total === 0
                  ? "Nenhum corretor cadastrado"
                  : `${total} corretor${total !== 1 ? "es" : ""} cadastrado${total !== 1 ? "s" : ""}`}
              </CardDescription>
            </div>
            <Button onClick={handleAdd}>
              <PlusCircle className="h-4 w-4" />
              Adicionar Corretor
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-12 text-muted-foreground">
              Carregando...
            </div>
          ) : brokers.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground mb-4">
                Nenhum corretor cadastrado ainda
              </p>
              <Button onClick={handleAdd}>
                <PlusCircle className="h-4 w-4" />
                Adicionar Primeiro Corretor
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Contato</TableHead>
                  <TableHead>CRECI</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Visitas</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {brokers.map((broker) => (
                  <TableRow key={broker.id}>
                    <TableCell className="font-medium">{broker.name}</TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        {broker.phone && (
                          <div className="flex items-center gap-1 text-sm">
                            <Phone className="h-3 w-3" />
                            {broker.phone}
                          </div>
                        )}
                        {broker.email && (
                          <div className="flex items-center gap-1 text-sm text-muted-foreground">
                            <Mail className="h-3 w-3" />
                            {broker.email}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>{broker.creci || "-"}</TableCell>
                    <TableCell>
                      <Badge
                        variant={broker.status === "active" ? "default" : "secondary"}
                      >
                        {broker.status === "active" ? "Ativo" : "Inativo"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        <div>{broker.total_visits} total</div>
                        <div className="text-muted-foreground">
                          {broker.completed_visits} concluídas
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {broker.avg_feedback_score.toFixed(1)} ★
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleEdit(broker)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(broker)}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <BrokerFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        broker={selectedBroker}
        onSuccess={handleSuccess}
      />
    </div>
  );
}
