# Quick Start Guide - VisitaImóvel Dashboard

## Installation

```bash
cd /Users/caiovicentino/Desktop/sells/visitaimovel-dashboard
npm install
```

## Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Production Build

```bash
npm run build
npm run start
```

## Testing

```bash
# Type checking
npm run type-check

# Linting
npm run lint
```

## Project Status

✅ **COMPLETE AND READY TO USE**

- Next.js 15 with App Router
- TypeScript strict mode
- Tailwind CSS v3 (stable)
- shadcn/ui components
- Dark/light theme support
- API client configured
- All routes created
- Production build successful

## File Locations

### Key Files
- **Main layout:** `app/layout.tsx`
- **Dashboard:** `app/page.tsx`
- **Global styles:** `app/globals.css`
- **API client:** `lib/api.ts`
- **Types:** `types/index.ts`
- **Sidebar:** `components/layout/sidebar.tsx`
- **Header:** `components/layout/header.tsx`

### Configuration
- **Environment:** `.env.local`
- **TypeScript:** `tsconfig.json`
- **Tailwind:** `tailwind.config.ts`
- **Next.js:** `next.config.ts`

## Routes

- `/` - Dashboard
- `/leads` - Leads management
- `/visits` - Visits management
- `/analytics` - Analytics
- `/brokers` - Brokers management

## API Configuration

The dashboard is configured to connect to a backend at `http://localhost:5002`.

To change this, update `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://your-backend-url
```

## Theme

Toggle between light and dark mode using the button in the header (sun/moon icon).

## Next Steps

1. Start the backend API at `http://localhost:5002`
2. Implement the leads page with data table
3. Create forms for adding/editing leads
4. Build the visits calendar
5. Add charts to analytics page
6. Implement broker management

## Support

Refer to:
- `README.md` - Complete project documentation
- `PROJECT_SUMMARY.md` - Detailed technical summary
- Next.js docs: https://nextjs.org/docs
