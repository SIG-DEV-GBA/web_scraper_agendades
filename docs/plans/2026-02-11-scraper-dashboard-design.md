# Diseño: Dashboard Scraper Agendades

**Fecha:** 2026-02-11
**Estado:** Aprobado
**Dominio:** `scraper.agendades.es`

---

## 1. Resumen Ejecutivo

Dashboard de control operativo para el sistema de scraping de eventos culturales de Agendades. Permite a un equipo técnico lanzar scrapes, monitorizar jobs en tiempo real y analizar métricas de calidad.

### Objetivos
- Panel de control para lanzar y monitorizar scrapes
- Visualización de estadísticas y calidad de datos
- Mapa interactivo de España con cobertura por CCAA/Provincia
- Sistema de roles (Admin/Operator/Viewer)

---

## 2. Stack Tecnológico

| Componente | Tecnología |
|------------|------------|
| Framework | Next.js 16.0 (App Router) |
| Lenguaje | TypeScript |
| UI | shadcn/ui + Tailwind CSS |
| Tema | Light mode por defecto, dark mode opcional |
| Auth | Supabase Auth (reutilizado de Agendades) |
| Data Fetching | TanStack Query (React Query) |
| Gráficos | Recharts |
| Mapa | react-simple-maps + GeoJSON España |
| Backend | FastAPI Scraper API (existente) |
| Base de datos | Supabase (PostgreSQL) |

### Colores Corporativos

```js
// tailwind.config.js
colors: {
  primary: {
    DEFAULT: '#FAA035',    // Naranja corporativo
    foreground: '#FFFFFF',
  },
  secondary: {
    DEFAULT: '#1C7F96',    // Azul/teal corporativo
    foreground: '#FFFFFF',
  },
}
```

---

## 3. Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                    scraper.agendades.es                         │
│                      (Next.js 16 App)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │  Supabase   │     │  FastAPI    │     │  Supabase   │       │
│  │    Auth     │     │  Scraper    │     │     DB      │       │
│  │ (compartido)│     │   :8000     │     │ (compartido)│       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Comunicación
- **Dashboard → FastAPI**: Endpoints `/sources`, `/scrape`, `/runs`
- **Dashboard → Supabase**: Estadísticas directas, gestión de usuarios/roles

---

## 4. Sistema de Roles

### Tabla `scraper_user_roles`

```sql
CREATE TABLE scraper_user_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES auth.users(id),

    UNIQUE(user_id)
);

ALTER TABLE scraper_user_roles ENABLE ROW LEVEL SECURITY;

-- Solo admins pueden gestionar roles
CREATE POLICY "Admins can manage roles" ON scraper_user_roles
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM scraper_user_roles
            WHERE user_id = auth.uid() AND role = 'admin'
        )
    );

-- Usuarios pueden ver su propio rol
CREATE POLICY "Users can view own role" ON scraper_user_roles
    FOR SELECT
    USING (user_id = auth.uid());
```

### Funciones Helper

```sql
-- Obtener rol del usuario actual
CREATE OR REPLACE FUNCTION get_scraper_role()
RETURNS TEXT AS $$
BEGIN
    RETURN (
        SELECT role FROM scraper_user_roles
        WHERE user_id = auth.uid()
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Verificar permiso
CREATE OR REPLACE FUNCTION has_scraper_permission(required_role TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    user_role TEXT;
BEGIN
    user_role := get_scraper_role();

    IF user_role IS NULL THEN RETURN FALSE; END IF;
    IF user_role = 'admin' THEN RETURN TRUE; END IF;
    IF user_role = 'operator' AND required_role IN ('operator', 'viewer') THEN RETURN TRUE; END IF;
    IF user_role = 'viewer' AND required_role = 'viewer' THEN RETURN TRUE; END IF;

    RETURN FALSE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

### Permisos por Rol

| Acción | Admin | Operator | Viewer |
|--------|-------|----------|--------|
| Ver Overview | ✅ | ✅ | ✅ |
| Lanzar Scrape | ✅ | ✅ | ❌ |
| Ver Jobs | ✅ | ✅ | ✅ |
| Cancelar Jobs | ✅ | ❌ | ❌ |
| Ver Fuentes | ✅ | ✅ | ✅ |
| Activar/Desactivar Fuentes | ✅ | ❌ | ❌ |
| Ver Estadísticas | ✅ | ✅ | ✅ |
| Gestionar Usuarios | ✅ | ❌ | ❌ |
| Configurar API/Targets | ✅ | ❌ | ❌ |

---

## 5. Estructura de Páginas

```
scraper.agendades.es/
├── /login                    # Login (Supabase Auth)
├── /                         # Redirect a /overview
├── /overview                 # Dashboard principal + Mapa
├── /scrape                   # Lanzar nuevo scrape
├── /jobs                     # Lista de jobs
│   └── /jobs/[id]           # Detalle + logs tiempo real
├── /sources                  # Lista de fuentes
│   └── /sources/[slug]      # Detalle fuente
├── /stats                    # Estadísticas completas
└── /settings                 # Solo Admin
    ├── /settings/users      # Gestión usuarios
    ├── /settings/api        # Config APIs
    └── /settings/targets    # Targets de calidad
```

---

## 6. Layout Principal

```
┌─────────────────────────────────────────────────────────────────┐
│ 🎯 Scraper Agendades              🔍 Search    🌙/☀️  👤 User ▼│
├──────────────┬──────────────────────────────────────────────────┤
│              │                                                  │
│  📊 Overview │           Contenido Principal                    │
│  ▶️ Scrape   │                                                  │
│  📋 Jobs     │                                                  │
│  🔌 Fuentes  │                                                  │
│  📈 Stats    │                                                  │
│  ──────────  │                                                  │
│  ⚙️ Settings │                                                  │
│              │                                                  │
├──────────────┴──────────────────────────────────────────────────┤
│ © 2026 Agendades                                        v1.0.0  │
└─────────────────────────────────────────────────────────────────┘
```

- **Header**: Logo, búsqueda, toggle tema (derecha), avatar usuario
- **Sidebar**: Navegación principal, Settings solo visible para Admin
- **Footer**: Copyright y versión

---

## 7. Páginas Detalladas

### 7.1 Overview

**Componentes:**
1. **KPI Cards** (4): Total eventos, Insertados hoy, Jobs activos, Errores hoy
2. **Mapa de España**: Toggle CCAA/Provincias, colores por densidad de eventos
3. **Gráfico línea**: Eventos insertados últimos 7 días
4. **Barras calidad**: Métricas vs targets
5. **Jobs recientes**: Últimos 5 jobs

**Mapa:**
- Librería: `react-simple-maps`
- GeoJSON: CCAA y provincias de España
- Interacción: Hover (tooltip), Click (filtra dashboard)
- Colores: Gradiente naranja `#FAA035` según cantidad eventos
- Leyenda: ░ 0-50 | ▒ 51-200 | █ 200+

### 7.2 Lanzar Scrape

**Secciones:**
1. **Selector fuentes**: Radio (Tier/CCAA/Provincia/Manual) + checkboxes
2. **Opciones**: Límite, LLM on/off, Images on/off, Dry run
3. **Resumen**: Fuentes × límite = eventos estimados, tiempo estimado
4. **Botones**: Cancelar, Lanzar

**Comportamiento:**
- POST a `/scrape` con parámetros seleccionados
- Redirect a `/jobs/[job_id]`

### 7.3 Jobs (Lista)

**Columnas:**
- ID (link a detalle)
- Filtro usado
- Estado (badge coloreado)
- Progreso (insertados/skipped)
- Duración/Tiempo

**Filtros:**
- Estado: Todos, Running, Completed, Failed
- Fecha: Últimas 24h, 7 días, 30 días, Todo

### 7.4 Job Detalle

**Secciones:**
1. **KPI Cards**: Fetched, Insertados, Skipped, Errores
2. **Barra progreso**: X/Y fuentes completadas
3. **Panel izquierdo**: Lista fuentes con estado individual
4. **Panel derecho**: Logs en tiempo real (polling 1s)

**Logs:**
- Polling: `GET /scrape/status/{id}/logs?since=X`
- Colores: INFO (gris), SUCCESS (verde), WARN (naranja), ERROR (rojo)
- Auto-scroll con toggle para desactivar

**Acciones:**
- Admin: Botón "Stop" para cancelar

### 7.5 Fuentes (Lista)

**Columnas:**
- Nombre
- Tier (badge: 🥇🥈🥉)
- CCAA
- Eventos en DB
- Estado (🟢/🔴)

**KPI Cards**: Total por tier (Gold/Silver/Bronze)

### 7.6 Fuente Detalle

**Secciones:**
1. **KPI Cards**: Tier, CCAA, Eventos DB, Último scrape
2. **Gráfico**: Eventos insertados últimos 30 días
3. **Panel calidad**: Métricas específicas de esta fuente
4. **Info**: URL API, formato, rate limit
5. **Jobs recientes**: De esta fuente

**Acciones:**
- Admin: Activar/desactivar
- Operator: Lanzar scrape

### 7.7 Estadísticas

**Componentes:**
1. **KPI Cards**: Total eventos, Este mes, CCAAs cubiertas, Provincias cubiertas
2. **Gráfico área**: Eventos por día (30 días)
3. **Pie chart**: Distribución por tier
4. **Barras calidad**: Todas las métricas con actual vs target
5. **Ranking**: Top 10 fuentes por eventos

### 7.8 Settings

**Tabs:**

**Usuarios:**
- Tabla: Usuario, Email, Rol (dropdown editable), Estado
- Botón: Invitar usuario
- Info de roles

**API Config:**
- URL Scraper API + estado conexión
- Estado servicios: Supabase, Groq, Unsplash, Firecrawl

**Targets:**
- Sliders para ajustar targets de calidad (10 métricas)
- Botón guardar

---

## 8. Endpoints API Utilizados

### FastAPI Scraper (existente)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/sources` | Listar fuentes |
| GET | `/sources/by-tier/{tier}` | Filtrar por tier |
| GET | `/sources/by-ccaa/{ccaa}` | Filtrar por CCAA |
| GET | `/sources/{slug}` | Detalle fuente |
| POST | `/scrape` | Lanzar job |
| GET | `/scrape/status/{id}` | Estado job |
| GET | `/scrape/status/{id}/logs` | Logs (polling) |
| GET | `/scrape/jobs` | Listar jobs |
| DELETE | `/scrape/jobs/{id}` | Eliminar job |
| GET | `/scrape/provinces` | Listar provincias |
| GET | `/scrape/ccaas` | Listar CCAAs |
| GET | `/runs/stats` | Estadísticas |
| GET | `/runs/quality` | Métricas calidad |
| GET | `/runs/recent` | Eventos recientes |
| GET | `/runs/by-date` | Eventos por fecha |

### Supabase (directo)

- `scraper_user_roles`: Gestión roles
- `events`: Conteos y estadísticas
- `scraper_sources`: Info fuentes
- `event_locations`: Datos para mapa

---

## 9. Estructura de Carpetas (Next.js)

```
scraper-dashboard/
├── app/
│   ├── (auth)/
│   │   └── login/
│   │       └── page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx           # Layout con sidebar
│   │   ├── overview/
│   │   │   └── page.tsx
│   │   ├── scrape/
│   │   │   └── page.tsx
│   │   ├── jobs/
│   │   │   ├── page.tsx
│   │   │   └── [id]/
│   │   │       └── page.tsx
│   │   ├── sources/
│   │   │   ├── page.tsx
│   │   │   └── [slug]/
│   │   │       └── page.tsx
│   │   ├── stats/
│   │   │   └── page.tsx
│   │   └── settings/
│   │       ├── page.tsx
│   │       ├── users/
│   │       │   └── page.tsx
│   │       ├── api/
│   │       │   └── page.tsx
│   │       └── targets/
│   │           └── page.tsx
│   ├── layout.tsx
│   └── page.tsx                 # Redirect a /overview
├── components/
│   ├── ui/                      # shadcn components
│   ├── layout/
│   │   ├── header.tsx
│   │   ├── sidebar.tsx
│   │   └── footer.tsx
│   ├── dashboard/
│   │   ├── kpi-card.tsx
│   │   ├── spain-map.tsx
│   │   ├── quality-bars.tsx
│   │   └── recent-jobs.tsx
│   ├── scrape/
│   │   ├── source-selector.tsx
│   │   └── scrape-options.tsx
│   ├── jobs/
│   │   ├── job-table.tsx
│   │   ├── job-logs.tsx
│   │   └── job-progress.tsx
│   └── charts/
│       ├── line-chart.tsx
│       ├── pie-chart.tsx
│       └── bar-chart.tsx
├── lib/
│   ├── supabase/
│   │   ├── client.ts
│   │   ├── server.ts
│   │   └── middleware.ts
│   ├── api/
│   │   └── scraper.ts           # Cliente FastAPI
│   └── utils/
│       └── roles.ts
├── hooks/
│   ├── use-role.ts
│   ├── use-job-logs.ts
│   └── use-stats.ts
├── types/
│   ├── job.ts
│   ├── source.ts
│   └── stats.ts
├── data/
│   ├── spain-ccaa.json          # GeoJSON CCAAs
│   └── spain-provinces.json     # GeoJSON provincias
├── middleware.ts                 # Auth + role check
├── tailwind.config.js
└── package.json
```

---

## 10. Dependencias

```json
{
  "dependencies": {
    "next": "^16.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "typescript": "^5.0.0",

    "@supabase/supabase-js": "^2.0.0",
    "@supabase/ssr": "^0.5.0",

    "@tanstack/react-query": "^5.0.0",

    "tailwindcss": "^3.4.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.0.0",

    "recharts": "^2.12.0",
    "react-simple-maps": "^3.0.0",

    "lucide-react": "^0.300.0",
    "next-themes": "^0.3.0",
    "sonner": "^1.0.0",

    "zod": "^3.22.0",
    "date-fns": "^3.0.0"
  }
}
```

---

## 11. Próximos Pasos

1. **Setup proyecto**: `npx create-next-app@latest scraper-dashboard`
2. **Instalar shadcn/ui**: `npx shadcn@latest init`
3. **Configurar Supabase**: Auth + tabla roles
4. **Crear layout**: Header, Sidebar, Footer
5. **Implementar páginas**: Overview → Jobs → Sources → Stats → Settings
6. **Integrar mapa**: GeoJSON + react-simple-maps
7. **Testing**: E2E con Playwright
8. **Deploy**: Vercel con dominio `scraper.agendades.es`

---

## 12. Aprobación

| Aspecto | Estado |
|---------|--------|
| Arquitectura | ✅ Aprobado |
| Stack tecnológico | ✅ Aprobado |
| Sistema de roles | ✅ Aprobado |
| Páginas y navegación | ✅ Aprobado |
| Diseño visual | ✅ Aprobado |

**Listo para implementación.**
