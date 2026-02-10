-- Add registration_info field to event_registration table
-- For storing registration instructions when there's no URL (e.g., phone, email)

ALTER TABLE event_registration
ADD COLUMN IF NOT EXISTS registration_info TEXT;

COMMENT ON COLUMN event_registration.registration_info IS
'Free text with registration instructions when no URL available (e.g., "Inscripción por teléfono 974 243 760 o email inscripciones@ejemplo.es")';
