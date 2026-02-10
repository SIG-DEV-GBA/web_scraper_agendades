import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  'https://dynlnrhfwjkrwraqmkit.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR5bmxucmhmd2prcndyYXFta2l0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NDMzMzAwMywiZXhwIjoyMDc5OTA5MDAzfQ.j6dVFRink3tcqEpQjU2rlfVuuOchDX17gQS0DIoXuHs'
);

async function createFullEvent() {
  // Obtener IDs necesarios
  const [catsRes, calsRes] = await Promise.all([
    supabase.from('categories').select('id, name').limit(3),
    supabase.from('calendars').select('id').eq('is_default', true).limit(1)
  ]);

  const categories = catsRes.data || [];
  const calendarId = calsRes.data?.[0]?.id;

  if (!calendarId) {
    console.error('No hay calendario por defecto');
    return;
  }

  // 1. Crear evento principal con TODOS los campos
  const { data: event, error: eventError } = await supabase
    .from('events')
    .insert({
      calendar_id: calendarId,
      title: 'Evento Seed Completo - Todos los Campos',
      slug: 'evento-seed-completo-todos-campos',
      description: 'Este es un evento de prueba SEED con absolutamente TODOS los campos de la base de datos rellenados. Sirve como referencia para ver cómo se muestran todos los datos en la interfaz. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam euismod, nisi vel consectetur interdum, nisl nunc egestas nunc, vitae tincidunt nisl nunc euismod nunc.',
      summary: 'Evento seed de referencia con todos los campos completos para testing y demostración.',
      image_url: 'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200',
      external_url: 'https://ejemplo.com/evento-seed-completo',
      start_date: '2026-02-20',
      end_date: '2026-02-21',
      start_time: '09:30',
      end_time: '20:00',
      all_day: false,
      modality: 'hibrido',
      is_free: false,
      price: 35.00,
      price_info: 'Precio general: 35€. Estudiantes y jubilados: 20€. Menores de 12 años: gratis. Precio grupo (+10 personas): 25€/persona. Incluye: acceso completo, material, coffee break y certificado de asistencia.',
      is_published: true,
      is_featured: true,
      is_cancelled: false,
      cancellation_reason: null,
    })
    .select('id')
    .single();

  if (eventError) {
    console.error('Error creando evento:', eventError);
    return;
  }

  const eventId = event.id;
  console.log('✓ Evento principal creado:', eventId);

  // 2. Calendario
  const { error: calError } = await supabase.from('event_calendars').insert({
    event_id: eventId,
    calendar_id: calendarId
  });
  if (calError) console.error('Error calendario:', calError);
  else console.log('✓ Calendario asignado');

  // 3. Categorías (primaria y secundarias)
  if (categories.length > 0) {
    const catInserts = categories.map((cat, i) => ({
      event_id: eventId,
      category_id: cat.id,
      is_primary: i === 0
    }));
    const { error: catError } = await supabase.from('event_categories').insert(catInserts);
    if (catError) console.error('Error categorías:', catError);
    else console.log('✓ Categorías asignadas:', categories.map(c => c.name).join(', '));
  }

  // 4. Ubicación COMPLETA
  const { error: locError } = await supabase.from('event_locations').insert({
    event_id: eventId,
    name: 'Palacio de Congresos y Exposiciones',
    address: 'Paseo de la Castellana, 99',
    city: 'Madrid',
    province: 'Madrid',
    postal_code: '28046',
    country: 'España',
    comunidad_autonoma: 'Comunidad de Madrid',
    municipio: 'Madrid',
    latitude: 40.4514,
    longitude: -3.6925,
    map_url: 'https://maps.google.com/?q=40.4514,-3.6925',
    details: 'Sala principal (Auditorio A). Acceso por entrada norte. Parking subterráneo disponible (3€/hora, máx 15€/día). Metro: Santiago Bernabéu (L10). Autobuses: 14, 27, 40, 43, 120, 147, 150. Punto de encuentro: hall principal junto a recepción.'
  });
  if (locError) console.error('Error ubicación:', locError);
  else console.log('✓ Ubicación completa');

  // 5. Info Online (evento híbrido)
  const { error: onlineError } = await supabase.from('event_online').insert({
    event_id: eventId,
    url: 'https://meet.google.com/abc-defg-hij',
    platform: 'Google Meet',
    access_info: 'El enlace se activará 15 minutos antes del inicio. Se requiere cuenta de Google para acceder. Se enviará enlace alternativo de YouTube para quienes solo quieran ver sin interactuar. La sesión será grabada y estará disponible 48h después para inscritos.'
  });
  if (onlineError) console.error('Error online:', onlineError);
  else console.log('✓ Info online completa');

  // 6. Organizador COMPLETO
  const { error: orgError } = await supabase.from('event_organizers').insert({
    event_id: eventId,
    name: 'Fundación Cultural Metropolitana',
    type: 'institucion',
    type_other: null,
    url: 'https://fundacion-cultural-metropolitana.org',
    logo_url: 'https://images.unsplash.com/photo-1560179707-f14e90ef3623?w=200&h=200&fit=crop'
  });
  if (orgError) console.error('Error organizador:', orgError);
  else console.log('✓ Organizador completo');

  // 7. Contacto COMPLETO
  const { error: contactError } = await supabase.from('event_contact').insert({
    event_id: eventId,
    name: 'Ana Martínez Rodríguez',
    email: 'eventos@fundacion-cultural.org',
    phone: '+34 915 678 901',
    info: 'Horario de atención: L-V de 9:00 a 14:00 y de 16:00 a 19:00. WhatsApp disponible en el mismo número. Para consultas urgentes el día del evento: +34 666 123 456.'
  });
  if (contactError) console.error('Error contacto:', contactError);
  else console.log('✓ Contacto completo');

  // 8. Inscripción COMPLETA
  const { error: regError } = await supabase.from('event_registration').insert({
    event_id: eventId,
    requires_registration: true,
    max_attendees: 250,
    current_attendees: 47,
    registration_url: 'https://fundacion-cultural.org/inscripcion/evento-seed',
    registration_deadline: '2026-02-18',
    waiting_list: true
  });
  if (regError) console.error('Error inscripción:', regError);
  else console.log('✓ Inscripción completa');

  // 9. Accesibilidad COMPLETA
  const { error: accError } = await supabase.from('event_accessibility').insert({
    event_id: eventId,
    wheelchair_accessible: true,
    sign_language: true,
    hearing_loop: true,
    braille_materials: true,
    other_facilities: 'Asientos reservados primera fila, baños adaptados, ascensores, rampas de acceso, zona de descanso con iluminación tenue, personal de apoyo disponible, subtítulos en tiempo real.',
    notes: 'Si necesitas alguna adaptación específica no listada, contacta con nosotros al menos 7 días antes del evento. Perros guía y de asistencia bienvenidos. Servicio de transporte adaptado disponible bajo petición (gratuito).'
  });
  if (accError) console.error('Error accesibilidad:', accError);
  else console.log('✓ Accesibilidad completa');

  console.log('\n========================================');
  console.log('✅ EVENTO SEED CREADO EXITOSAMENTE');
  console.log('========================================');
  console.log('ID:', eventId);
  console.log('URL: https://agendades.es/eventos/evento-seed-completo-todos-campos-' + eventId.substring(0, 8));
  console.log('Admin: https://agendades.es/admin/eventos/' + eventId);
}

createFullEvent().catch(console.error);
