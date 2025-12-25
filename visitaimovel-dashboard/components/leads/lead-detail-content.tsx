import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { apiClient } from "@/lib/api-client";
import {
  ArrowLeft,
  User,
  Phone,
  Mail,
  MapPin,
  Bed,
  DollarSign,
  Calendar,
  MessageSquare,
} from "lucide-react";

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
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function formatPhone(phone: string): string {
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 11) {
    return `(${cleaned.slice(0, 2)}) ${cleaned.slice(2, 7)}-${cleaned.slice(7)}`;
  }
  return phone;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

interface LeadDetailContentProps {
  leadId: string;
}

export async function LeadDetailContent({ leadId }: LeadDetailContentProps) {
  const [lead, conversation] = await Promise.all([
    apiClient.leads.getById(leadId),
    apiClient.leads.getConversation(leadId),
  ]);

  return (
    <div>
      <div className="mb-6">
        <Link href="/leads">
          <Button variant="ghost" size="sm" className="mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Voltar para Leads
          </Button>
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{lead.name}</h1>
            <p className="text-muted-foreground mt-2">
              Cadastrado em {formatDate(lead.created_at)}
            </p>
          </div>
          <Badge variant={STATUS_VARIANTS[lead.status]}>
            {STATUS_LABELS[lead.status]}
          </Badge>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Lead Information Card */}
        <Card>
          <CardHeader>
            <CardTitle>Informações do Lead</CardTitle>
            <CardDescription>Dados de contato e informações pessoais</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <User className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Nome</p>
                <p className="text-sm text-muted-foreground">{lead.name}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Phone className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Telefone</p>
                <p className="text-sm text-muted-foreground">{formatPhone(lead.phone)}</p>
              </div>
            </div>
            {lead.email && (
              <div className="flex items-center gap-3">
                <Mail className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">Email</p>
                  <p className="text-sm text-muted-foreground">{lead.email}</p>
                </div>
              </div>
            )}
            {lead.score !== undefined && (
              <div className="flex items-center gap-3">
                <MessageSquare className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">Score</p>
                  <p className="text-sm text-muted-foreground">{lead.score}/100</p>
                </div>
              </div>
            )}
            <div className="flex items-center gap-3">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Última atualização</p>
                <p className="text-sm text-muted-foreground">{formatDate(lead.updated_at)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Property Interest Card */}
        <Card>
          <CardHeader>
            <CardTitle>Interesse em Imóvel</CardTitle>
            <CardDescription>Preferências e requisitos do cliente</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {lead.preferences.property_type && (
              <div className="flex items-center gap-3">
                <MapPin className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">Tipo de Imóvel</p>
                  <p className="text-sm text-muted-foreground">{lead.preferences.property_type}</p>
                </div>
              </div>
            )}
            {lead.preferences.bedrooms && (
              <div className="flex items-center gap-3">
                <Bed className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">Quartos</p>
                  <p className="text-sm text-muted-foreground">{lead.preferences.bedrooms}</p>
                </div>
              </div>
            )}
            {(lead.preferences.min_price || lead.preferences.max_price) && (
              <div className="flex items-center gap-3">
                <DollarSign className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">Faixa de Preço</p>
                  <p className="text-sm text-muted-foreground">
                    {lead.preferences.min_price
                      ? formatCurrency(lead.preferences.min_price)
                      : "Sem mínimo"}{" "}
                    -{" "}
                    {lead.preferences.max_price
                      ? formatCurrency(lead.preferences.max_price)
                      : "Sem máximo"}
                  </p>
                </div>
              </div>
            )}
            {lead.preferences.neighborhoods && lead.preferences.neighborhoods.length > 0 && (
              <div className="flex items-start gap-3">
                <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                <div>
                  <p className="text-sm font-medium">Bairros de Interesse</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {lead.preferences.neighborhoods.map((neighborhood, index) => (
                      <Badge key={index} variant="outline">
                        {neighborhood}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {lead.preferences.additional_notes && (
              <div>
                <p className="text-sm font-medium mb-1">Observações Adicionais</p>
                <p className="text-sm text-muted-foreground">
                  {lead.preferences.additional_notes}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Conversation Timeline */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Histórico de Conversas</CardTitle>
            <CardDescription>
              {conversation.messages.length} mensagens trocadas
            </CardDescription>
          </CardHeader>
          <CardContent>
            {conversation.messages.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                Nenhuma conversa registrada
              </p>
            ) : (
              <ScrollArea className="h-[600px] pr-4">
                <div className="space-y-4">
                  {conversation.messages.map((message) => (
                    <div
                      key={message.id}
                      className={`flex ${
                        message.role === "user" ? "justify-end" : "justify-start"
                      }`}
                    >
                      <div
                        className={`max-w-[80%] rounded-lg px-4 py-3 ${
                          message.role === "user"
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted"
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <p className="text-xs font-medium">
                            {message.role === "user" ? lead.name : "VisitaImóvel"}
                          </p>
                          <p className="text-xs opacity-70">
                            {formatDate(message.timestamp)}
                          </p>
                        </div>
                        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                        {message.metadata?.intent && (
                          <p className="text-xs mt-2 opacity-70">
                            Intent: {message.metadata.intent}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
