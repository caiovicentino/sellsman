# VisitaImóvel Dashboard

Sistema de gerenciamento de visitas imobiliárias com interface moderna e responsiva.

## Tecnologias

- **Next.js 15** - Framework React com App Router
- **TypeScript** - Tipagem estática
- **Tailwind CSS** - Estilização utility-first
- **shadcn/ui** - Componentes UI acessíveis
- **Lucide React** - Ícones
- **Recharts** - Gráficos e visualizações
- **next-themes** - Suporte a tema claro/escuro

## Estrutura do Projeto

```
visitaimovel-dashboard/
├── app/                    # App Router do Next.js
│   ├── layout.tsx         # Layout principal com sidebar e header
│   ├── page.tsx           # Dashboard principal
│   ├── leads/             # Página de gerenciamento de leads
│   ├── visits/            # Página de gerenciamento de visitas
│   ├── analytics/         # Página de analytics e relatórios
│   └── brokers/           # Página de gerenciamento de corretores
├── components/
│   ├── ui/                # Componentes shadcn/ui
│   └── layout/            # Componentes de layout (sidebar, header)
├── lib/
│   ├── utils.ts           # Utilitários (cn helper)
│   └── api.ts             # Cliente API para backend
└── types/
    └── index.ts           # TypeScript types
```

## Configuração

### Variáveis de Ambiente

Crie um arquivo `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:5002
```

### Instalação

```bash
npm install
```

### Desenvolvimento

```bash
npm run dev
```

Acesse [http://localhost:3000](http://localhost:3000)

### Build de Produção

```bash
npm run build
npm run start
```

### Verificação de Tipos

```bash
npm run type-check
```

### Linting

```bash
npm run lint
```

## Funcionalidades

### Implementadas

- Dashboard principal com cards de métricas
- Navegação com sidebar responsiva
- Header com suporte a tema claro/escuro
- Notificações visuais
- Sistema de rotas com App Router
- Cliente API configurado para localhost:5002
- TypeScript types para entidades principais

### Páginas

- **Dashboard (/)** - Visão geral com métricas e atividades recentes
- **/leads** - Gerenciamento de leads (em desenvolvimento)
- **/visits** - Gerenciamento de visitas (em desenvolvimento)
- **/analytics** - Analytics e relatórios (em desenvolvimento)
- **/brokers** - Gerenciamento de corretores (em desenvolvimento)

## API Client

O projeto inclui um cliente API configurado em `lib/api.ts`:

```typescript
import { apiClient } from "@/lib/api";

// GET
const leads = await apiClient.get("/api/leads");

// POST
const newLead = await apiClient.post("/api/leads", { name: "João Silva" });

// PUT
const updated = await apiClient.put("/api/leads/123", { status: "qualificado" });

// DELETE
await apiClient.delete("/api/leads/123");
```

## TypeScript Types

Types principais definidos em `types/index.ts`:

- `Lead` - Lead imobiliário
- `Visit` - Visita agendada
- `Property` - Imóvel
- `Broker` - Corretor
- `Analytics` - Métricas do sistema
- `ActivityLog` - Log de atividades

## Tema

Suporte a tema claro/escuro com next-themes. O tema é persistido no localStorage e sincronizado com as preferências do sistema.

## Responsividade

- Mobile-first design
- Sidebar oculta em mobile (botão de menu no header)
- Layout adaptável para tablet e desktop
- Grid responsivo para cards e conteúdo

## Próximos Passos

1. Implementar páginas de leads com tabela e filtros
2. Criar calendário de visitas
3. Implementar dashboards de analytics com gráficos
4. Adicionar formulários de cadastro
5. Integrar com backend real
6. Implementar autenticação
7. Adicionar testes unitários e E2E
