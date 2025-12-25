"use client";

import { useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Visits page error:", error);
  }, [error]);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Visitas</h1>
        <p className="text-muted-foreground mt-2">
          Gerencie todas as visitas agendadas
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <CardTitle>Erro ao carregar visitas</CardTitle>
          </div>
          <CardDescription>
            Não foi possível carregar a lista de visitas
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {error.message || "Erro desconhecido"}
          </p>
          <Button onClick={reset} variant="default">
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
