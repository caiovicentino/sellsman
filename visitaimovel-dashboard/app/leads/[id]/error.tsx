"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertCircle, ArrowLeft } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Lead detail error:", error);
  }, [error]);

  return (
    <div>
      <Link href="/leads">
        <Button variant="ghost" size="sm" className="mb-4">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Voltar para Leads
        </Button>
      </Link>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <CardTitle>Erro ao carregar lead</CardTitle>
          </div>
          <CardDescription>
            Não foi possível carregar os detalhes deste lead
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {error.message || "Erro desconhecido"}
          </p>
          <div className="flex gap-2">
            <Button onClick={reset} variant="default">
              Tentar novamente
            </Button>
            <Link href="/leads">
              <Button variant="outline">
                Voltar para lista
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
