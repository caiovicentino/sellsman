"use client";

import { useState, FormEvent } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { brokersApi, CreateBrokerData, UpdateBrokerData, Broker } from "@/lib/api-brokers";

interface BrokerFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  broker?: Broker | null;
  onSuccess: () => void;
}

export function BrokerFormDialog({ open, onOpenChange, broker, onSuccess }: BrokerFormDialogProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState<CreateBrokerData>({
    name: broker?.name || "",
    phone: broker?.phone || "",
    email: broker?.email || "",
    creci: broker?.creci || "",
  });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (broker) {
        await brokersApi.update(broker.id, formData as UpdateBrokerData);
      } else {
        if (!formData.name || !formData.phone) {
          setError("Nome e telefone são obrigatórios");
          setLoading(false);
          return;
        }
        await brokersApi.create(formData);
      }
      onSuccess();
      onOpenChange(false);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Erro ao salvar corretor";
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {broker ? "Editar Corretor" : "Adicionar Corretor"}
          </DialogTitle>
          <DialogDescription>
            {broker
              ? "Atualize os dados do corretor abaixo."
              : "Preencha os dados do novo corretor."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded text-sm">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="name">Nome *</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="Ex: Reno Alencar"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="phone">Telefone *</Label>
            <Input
              id="phone"
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              placeholder="Ex: 558596227722"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              placeholder="Ex: reno@imob.com"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="creci">CRECI</Label>
            <Input
              id="creci"
              value={formData.creci}
              onChange={(e) => setFormData({ ...formData, creci: e.target.value })}
              placeholder="Ex: 12345-CE"
            />
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Salvando..." : broker ? "Atualizar" : "Adicionar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
