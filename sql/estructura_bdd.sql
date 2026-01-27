-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.audit_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid,
  user_email text,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id text,
  entity_name text,
  details jsonb,
  ip_address text,
  user_agent text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT audit_logs_pkey PRIMARY KEY (id),
  CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.auth_otp_attempts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_email USER-DEFINED NOT NULL,
  ip_address text,
  attempted_at timestamp with time zone NOT NULL DEFAULT now(),
  success boolean NOT NULL DEFAULT false,
  CONSTRAINT auth_otp_attempts_pkey PRIMARY KEY (id)
);
CREATE TABLE public.auth_otp_cooldowns (
  user_email USER-DEFINED NOT NULL,
  next_allowed_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT auth_otp_cooldowns_pkey PRIMARY KEY (user_email)
);
CREATE TABLE public.auth_otp_lockouts (
  user_email USER-DEFINED NOT NULL,
  locked_until timestamp with time zone NOT NULL,
  failure_count integer NOT NULL DEFAULT 0,
  CONSTRAINT auth_otp_lockouts_pkey PRIMARY KEY (user_email)
);
CREATE TABLE public.calendar_shares (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  calendar_id uuid NOT NULL,
  owner_id uuid NOT NULL,
  shared_with_id uuid NOT NULL,
  permission USER-DEFINED DEFAULT 'view'::share_permission,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT calendar_shares_pkey PRIMARY KEY (id),
  CONSTRAINT calendar_shares_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.calendars(id),
  CONSTRAINT calendar_shares_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id),
  CONSTRAINT calendar_shares_shared_with_id_fkey FOREIGN KEY (shared_with_id) REFERENCES public.users(id)
);
CREATE TABLE public.calendars (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_id uuid,
  name character varying NOT NULL,
  description text,
  color character varying DEFAULT '#3B82F6'::character varying,
  is_public boolean DEFAULT false,
  is_default boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  type text DEFAULT 'other'::text,
  parent_id uuid,
  CONSTRAINT calendars_pkey PRIMARY KEY (id),
  CONSTRAINT fk_calendars_user FOREIGN KEY (user_id) REFERENCES public.users(id),
  CONSTRAINT calendars_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.calendars(id)
);
CREATE TABLE public.categories (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  name character varying NOT NULL UNIQUE,
  slug character varying NOT NULL UNIQUE,
  description text,
  color character varying DEFAULT '#3B82F6'::character varying,
  icon character varying,
  sort_order integer DEFAULT 0,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT categories_pkey PRIMARY KEY (id)
);
CREATE TABLE public.event_accessibility (
  event_id uuid NOT NULL,
  wheelchair_accessible boolean DEFAULT false,
  sign_language boolean DEFAULT false,
  hearing_loop boolean DEFAULT false,
  braille_materials boolean DEFAULT false,
  other_facilities text,
  notes text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT event_accessibility_pkey PRIMARY KEY (event_id),
  CONSTRAINT event_accessibility_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id)
);
CREATE TABLE public.event_archive (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  original_event_id uuid NOT NULL,
  title text NOT NULL,
  description text,
  category_id uuid,
  category_name text,
  start_date date NOT NULL,
  end_date date,
  start_time time without time zone,
  end_time time without time zone,
  location_type text,
  venue_name text,
  address text,
  city text,
  province text,
  comunidad_autonoma text,
  country text DEFAULT 'España'::text,
  organizer_name text,
  organizer_type text,
  is_published boolean DEFAULT true,
  is_featured boolean DEFAULT false,
  source text,
  external_id text,
  tags ARRAY,
  calendar_ids ARRAY,
  calendar_names ARRAY,
  original_created_at timestamp with time zone,
  original_updated_at timestamp with time zone,
  archived_at timestamp with time zone DEFAULT now(),
  deleted_reason text DEFAULT 'expired'::text,
  created_by uuid,
  category_ids ARRAY,
  category_names_array ARRAY,
  CONSTRAINT event_archive_pkey PRIMARY KEY (id)
);
CREATE TABLE public.event_calendars (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL,
  calendar_id uuid NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT event_calendars_pkey PRIMARY KEY (id),
  CONSTRAINT event_calendars_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id),
  CONSTRAINT event_calendars_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.calendars(id)
);
CREATE TABLE public.event_categories (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL,
  category_id uuid NOT NULL,
  is_primary boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT event_categories_pkey PRIMARY KEY (id),
  CONSTRAINT event_categories_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id),
  CONSTRAINT event_categories_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id)
);
CREATE TABLE public.event_contact (
  event_id uuid NOT NULL,
  name character varying,
  email character varying,
  phone character varying,
  info text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT event_contact_pkey PRIMARY KEY (event_id),
  CONSTRAINT event_contact_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id)
);
CREATE TABLE public.event_invitations (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  event_id uuid NOT NULL,
  user_id uuid NOT NULL,
  invited_by uuid,
  status USER-DEFINED DEFAULT 'pending'::invitation_status,
  message text,
  invited_at timestamp with time zone DEFAULT now(),
  responded_at timestamp with time zone,
  CONSTRAINT event_invitations_pkey PRIMARY KEY (id),
  CONSTRAINT event_invitations_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id),
  CONSTRAINT event_invitations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id),
  CONSTRAINT event_invitations_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES public.users(id)
);
CREATE TABLE public.event_locations (
  event_id uuid NOT NULL,
  name character varying NOT NULL,
  address text,
  city character varying,
  province character varying,
  postal_code character varying,
  country character varying DEFAULT 'España'::character varying,
  latitude numeric,
  longitude numeric,
  map_url text,
  details text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  comunidad_autonoma text,
  municipio text,
  CONSTRAINT event_locations_pkey PRIMARY KEY (event_id),
  CONSTRAINT event_locations_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id)
);
CREATE TABLE public.event_online (
  event_id uuid NOT NULL,
  url text NOT NULL,
  platform character varying,
  access_info text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT event_online_pkey PRIMARY KEY (event_id),
  CONSTRAINT event_online_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id)
);
CREATE TABLE public.event_organizers (
  event_id uuid NOT NULL,
  name character varying NOT NULL,
  url text,
  logo_url text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  type_other text,
  type USER-DEFINED DEFAULT 'otro'::organizer_type,
  CONSTRAINT event_organizers_pkey PRIMARY KEY (event_id),
  CONSTRAINT event_organizers_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id)
);
CREATE TABLE public.event_registration (
  event_id uuid NOT NULL,
  max_attendees integer,
  current_attendees integer DEFAULT 0,
  requires_registration boolean DEFAULT true,
  registration_url text,
  registration_deadline timestamp with time zone,
  waiting_list boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT event_registration_pkey PRIMARY KEY (event_id),
  CONSTRAINT event_registration_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id)
);
CREATE TABLE public.event_stats_daily (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  date date NOT NULL UNIQUE,
  total_events_active integer DEFAULT 0,
  total_events_published integer DEFAULT 0,
  events_created_today integer DEFAULT 0,
  events_deleted_today integer DEFAULT 0,
  events_expired_today integer DEFAULT 0,
  events_physical integer DEFAULT 0,
  events_online integer DEFAULT 0,
  events_hybrid integer DEFAULT 0,
  events_from_import integer DEFAULT 0,
  events_from_manual integer DEFAULT 0,
  events_from_api integer DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT event_stats_daily_pkey PRIMARY KEY (id)
);
CREATE TABLE public.event_stats_monthly (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  year integer NOT NULL,
  month integer NOT NULL,
  total_events_created integer DEFAULT 0,
  total_events_deleted integer DEFAULT 0,
  total_events_expired integer DEFAULT 0,
  events_by_category jsonb DEFAULT '{}'::jsonb,
  events_by_province jsonb DEFAULT '{}'::jsonb,
  events_by_comunidad jsonb DEFAULT '{}'::jsonb,
  events_physical integer DEFAULT 0,
  events_online integer DEFAULT 0,
  events_hybrid integer DEFAULT 0,
  events_from_import integer DEFAULT 0,
  events_from_manual integer DEFAULT 0,
  events_from_api integer DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT event_stats_monthly_pkey PRIMARY KEY (id)
);
CREATE TABLE public.events (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  calendar_id uuid NOT NULL,
  created_by uuid,
  title character varying NOT NULL,
  slug character varying,
  description text,
  summary character varying,
  image_url text,
  modality USER-DEFINED NOT NULL DEFAULT 'presencial'::event_modality,
  start_date date NOT NULL,
  end_date date,
  start_time time without time zone,
  end_time time without time zone,
  all_day boolean DEFAULT false,
  timezone character varying DEFAULT 'Europe/Madrid'::character varying,
  is_free boolean DEFAULT true,
  price numeric,
  price_info text,
  is_published boolean DEFAULT true,
  is_featured boolean DEFAULT false,
  is_cancelled boolean DEFAULT false,
  cancellation_reason text,
  is_recurring boolean DEFAULT false,
  recurrence_rule jsonb,
  parent_event_id uuid,
  source_id uuid,
  external_id character varying,
  external_url text,
  content_hash character varying,
  search_vector tsvector,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  published_at timestamp with time zone,
  source_image_url text,
  embedding USER-DEFINED,
  embedding_pending boolean DEFAULT true,
  CONSTRAINT events_pkey PRIMARY KEY (id),
  CONSTRAINT events_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.calendars(id),
  CONSTRAINT events_parent_event_id_fkey FOREIGN KEY (parent_event_id) REFERENCES public.events(id),
  CONSTRAINT fk_events_created_by FOREIGN KEY (created_by) REFERENCES public.users(id)
);
CREATE TABLE public.notifications (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL,
  title character varying NOT NULL,
  message text,
  type USER-DEFINED DEFAULT 'system'::notification_type,
  reference_id uuid,
  reference_type character varying,
  action_url text,
  read boolean DEFAULT false,
  read_at timestamp with time zone,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT notifications_pkey PRIMARY KEY (id),
  CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.password_reset_requests (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  email USER-DEFINED NOT NULL,
  ip_address text,
  requested_at timestamp with time zone NOT NULL DEFAULT now() CHECK (requested_at <= now()),
  CONSTRAINT password_reset_requests_pkey PRIMARY KEY (id)
);
CREATE TABLE public.reminders (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL,
  event_id uuid NOT NULL,
  remind_at timestamp with time zone NOT NULL,
  type USER-DEFINED DEFAULT 'both'::reminder_type,
  minutes_before integer NOT NULL,
  sent boolean DEFAULT false,
  sent_at timestamp with time zone,
  error_message text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT reminders_pkey PRIMARY KEY (id),
  CONSTRAINT reminders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id),
  CONSTRAINT reminders_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id)
);
CREATE TABLE public.scraper_sources (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  slug character varying NOT NULL UNIQUE,
  name character varying NOT NULL,
  ccaa character varying,
  ccaa_code character varying,
  source_url text NOT NULL,
  adapter_type character varying DEFAULT 'api'::character varying,
  rate_limit_delay double precision DEFAULT 1.0,
  batch_size integer DEFAULT 20,
  is_active boolean DEFAULT true,
  last_run_at timestamp with time zone,
  last_run_status character varying,
  last_run_count integer,
  last_error text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT scraper_sources_pkey PRIMARY KEY (id)
);
CREATE TABLE public.security_audit_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  user_id uuid,
  action text NOT NULL CHECK (action = ANY (ARRAY['login_success'::text, 'login_failed'::text, 'logout'::text, 'password_change'::text, 'password_reset_request'::text, 'otp_request'::text, 'otp_verify_success'::text, 'otp_verify_failed'::text, 'account_locked'::text, 'suspicious_activity'::text])),
  ip_address text,
  user_agent text,
  details jsonb,
  CONSTRAINT security_audit_log_pkey PRIMARY KEY (id),
  CONSTRAINT security_audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);
CREATE TABLE public.user_personal_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  calendar_id uuid NOT NULL,
  title character varying NOT NULL,
  description text,
  start_date date NOT NULL,
  end_date date,
  start_time time without time zone,
  end_time time without time zone,
  all_day boolean DEFAULT false,
  location_name character varying,
  location_address text,
  color character varying CHECK (color IS NULL OR color::text ~ '^#[0-9A-Fa-f]{6}$'::text),
  reminder_minutes integer,
  notes text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  updated_by uuid,
  CONSTRAINT user_personal_events_pkey PRIMARY KEY (id),
  CONSTRAINT user_personal_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id),
  CONSTRAINT user_personal_events_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.calendars(id),
  CONSTRAINT user_personal_events_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES auth.users(id)
);
CREATE TABLE public.user_preferences (
  user_id uuid NOT NULL,
  timezone character varying DEFAULT 'Europe/Madrid'::character varying,
  email_notifications boolean DEFAULT true,
  push_notifications boolean DEFAULT true,
  reminder_default integer DEFAULT 30,
  calendar_view character varying DEFAULT 'month'::character varying,
  week_starts_on integer DEFAULT 1,
  theme character varying DEFAULT 'system'::character varying,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  default_calendar_view text NOT NULL DEFAULT 'month'::text CHECK (default_calendar_view = ANY (ARRAY['month'::text, 'week'::text, 'day'::text])),
  week_start_day text NOT NULL DEFAULT 'monday'::text CHECK (week_start_day = ANY (ARRAY['monday'::text, 'sunday'::text])),
  default_reminder_minutes integer DEFAULT 60,
  preferred_categories ARRAY DEFAULT '{}'::text[],
  CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id),
  CONSTRAINT user_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.user_saved_events (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL,
  event_id uuid NOT NULL,
  calendar_id uuid NOT NULL,
  notes text,
  color character varying,
  saved_at timestamp with time zone DEFAULT now(),
  saved_by uuid,
  CONSTRAINT user_saved_events_pkey PRIMARY KEY (id),
  CONSTRAINT user_saved_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id),
  CONSTRAINT user_saved_events_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id),
  CONSTRAINT user_saved_events_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.calendars(id),
  CONSTRAINT user_saved_events_saved_by_fkey FOREIGN KEY (saved_by) REFERENCES auth.users(id)
);
CREATE TABLE public.users (
  id uuid NOT NULL,
  email character varying NOT NULL UNIQUE,
  full_name character varying,
  role USER-DEFINED DEFAULT 'user'::user_role,
  is_active boolean DEFAULT true,
  last_login_at timestamp with time zone,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  birth_date date,
  gender character varying,
  avatar_url text,
  location_ccaa_id uuid,
  location_provincia_id uuid,
  CONSTRAINT users_pkey PRIMARY KEY (id),
  CONSTRAINT users_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id),
  CONSTRAINT users_location_ccaa_id_fkey FOREIGN KEY (location_ccaa_id) REFERENCES public.calendars(id),
  CONSTRAINT users_location_provincia_id_fkey FOREIGN KEY (location_provincia_id) REFERENCES public.calendars(id)
);