export interface Lead {
  id: string;
  name: string;
  phone: string;
  email?: string;
  budget?: string;
  property_type?: string;
  region?: string;
  bedrooms?: number;
  status: "novo" | "qualificado" | "visita_agendada" | "perdido" | "convertido";
  score?: number;
  created_at: string;
  updated_at: string;
}

export interface Visit {
  id: string;
  lead_id: string;
  property_id: string;
  broker_id?: string;
  scheduled_date: string;
  scheduled_time: string;
  status: "pendente" | "confirmada" | "realizada" | "cancelada";
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface Property {
  id: string;
  title: string;
  type: string;
  price: number;
  bedrooms: number;
  bathrooms: number;
  area: number;
  region: string;
  address: string;
  images?: string[];
  status: "disponivel" | "vendido" | "alugado";
  created_at: string;
}

export interface Broker {
  id: string;
  name: string;
  creci?: string;
  email: string;
  phone: string;
  status: "ativo" | "inativo";
  performance_score?: number;
  created_at: string;
}

export interface Analytics {
  total_leads: number;
  total_visits: number;
  conversion_rate: number;
  active_brokers: number;
  recent_activity: ActivityLog[];
}

export interface ActivityLog {
  id: string;
  type: "lead" | "visit" | "property" | "broker";
  action: string;
  description: string;
  timestamp: string;
}
