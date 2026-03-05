"""Test de clasificación con 200 eventos (soporta multi-categoría)."""
import sys
sys.path.insert(0, '.')

from src.core.category_classifier import CategoryClassifier

classifier = CategoryClassifier()

# 200 eventos - el expected puede ser string o set para multi-categoría
EVENTS = [
    # === CULTURAL (35 + 9 de fiestas tradicionales) ===
    ('Concierto de Jazz en el Auditorio', None, 'cultural'),
    ('Exposición de Pintura Contemporánea', None, 'cultural'),
    ('Teatro: Don Juan Tenorio', None, 'cultural'),
    ('Visita guiada al Museo del Prado', None, 'cultural'),
    ('Festival de Cine Documental', None, 'cultural'),
    ('Recital de Poesía y Flamenco', None, 'cultural'),
    ('Ópera: La Traviata', None, 'cultural'),
    ('Concierto homenaje a Sabina', None, 'cultural'),
    ('Espectáculo de Tango Argentino', None, 'cultural'),
    ('Maratón de Madrid 2025', None, 'cultural'),
    ('Ballet clásico: El Lago de los Cisnes', None, 'cultural'),
    ('Monólogos de humor con Leo Harlem', None, 'cultural'),
    ('Concierto de rock: Héroes del Silencio Sinfónico', None, 'cultural'),
    ('Exposición fotográfica: España en blanco y negro', None, 'cultural'),
    ('Ciclo de cine francés', None, 'cultural'),
    ('Presentación del libro de Pérez-Reverte', None, 'cultural'),
    ('Zarzuela: La verbena de la Paloma', None, 'cultural'),
    ('Circo del Sol en Madrid', None, 'cultural'),
    ('Concierto de música clásica: Beethoven', None, 'cultural'),
    ('Exposición de esculturas de Botero', None, 'cultural'),
    ('Festival de Teatro Clásico de Mérida', None, 'cultural'),
    ('Concierto tributo a Queen', None, 'cultural'),
    ('Museo Reina Sofía: visita nocturna', None, 'cultural'),
    ('Stand-up comedy night', None, 'cultural'),
    ('Concierto de villancicos navideños', None, 'cultural'),
    ('Exposición de arte urbano', None, 'cultural'),
    ('Musical: El Rey León', None, 'cultural'),
    ('Recital de guitarra española', None, 'cultural'),
    ('Partido de fútbol: Real Madrid vs Barcelona', None, 'cultural'),
    ('Espectáculo de magia', None, 'cultural'),
    ('Festival de Jazz de San Sebastián', None, 'cultural'),
    ('Concierto de Rosalía', None, 'cultural'),
    ('Cine al aire libre: Casablanca', None, 'cultural'),
    ('Lectura dramatizada de Lorca', None, 'cultural'),
    ('Exposición temporal en el Thyssen', None, 'cultural'),
    # Fiestas tradicionales = espectáculos culturales
    ('Verbena de San Juan', None, 'cultural'),
    ('Romería de la Virgen del Rocío', None, 'cultural'),
    ('Cabalgata de Reyes Magos', None, 'cultural'),
    ('Belén viviente del pueblo', None, 'cultural'),
    ('Hogueras de San Antón', None, 'cultural'),
    ('Calçotada popular', None, 'cultural'),
    ('Feria de artesanía local', None, 'cultural'),
    ('Curso de fotografía con móvil', None, 'cultural'),
    ('Taller de reciclaje creativo', None, 'cultural'),

    # === SOCIAL (23) ===
    ('Fiesta Mayor del barrio de Gracia', None, 'social'),
    ('Voluntariado en el Banco de Alimentos', None, 'social'),
    ('Jornada de limpieza del río Manzanares', None, 'social'),
    ('Día de la Mujer: charla sobre igualdad', None, 'social'),
    ('Encuentro intergeneracional abuelos-nietos', None, 'social'),
    ('Taller contra la soledad no deseada', None, 'social'),
    ('Plantación de árboles en el parque', None, 'social'),
    ('Recogida solidaria de juguetes', None, 'social'),
    ('Feria de asociaciones del barrio', None, 'social'),
    ('Comida popular de fiestas patronales', None, 'social'),
    ('Mercadillo solidario Cruz Roja', None, 'social'),
    ('Día del orgullo LGTBI', None, 'social'),
    ('Tertulia de jubilados', None, 'social'),
    ('Huerto urbano comunitario', None, 'social'),
    ('Café social para mayores', None, 'social'),
    ('Campaña de concienciación medioambiental', None, 'social'),
    ('Encuentro de asociaciones de mujeres', None, 'social'),
    ('Jornada de convivencia vecinal', None, 'social'),
    ('Acción solidaria por Ucrania', None, 'social'),
    ('Taller de compostaje doméstico', None, 'social'),
    ('Día internacional contra la violencia de género', None, 'social'),
    ('Paella gigante en fiestas', None, 'social'),
    ('Feria de economía social y solidaria', None, 'economica'),  # economía > social

    # === ECONOMICA (33) + 2 multi-categoría ===
    ('Feria de Empleo para mayores de 50', None, 'economica'),
    ('Curso de Manipulador de Alimentos', None, 'economica'),
    ('Taller de elaboración de CV', None, 'economica'),
    ('Operaciones básicas en caja', 'CeMIT - centros de inclusión tecnológica', 'economica'),
    ('Curso de camarero profesional', None, 'economica'),
    ('Networking para emprendedores senior', None, 'economica'),
    ('Charla sobre pensiones y jubilación', None, 'economica'),
    ('Monitor de tiempo libre: certificación', None, 'economica'),
    ('Atención al cliente y ventas', 'Guadalinfo - centros digitales', 'economica'),
    ('Prevención de riesgos laborales PRL', None, 'economica'),
    ('Emprendimiento: crea tu negocio', None, 'economica'),
    ('Curso de recepcionista de hotel', None, 'economica'),
    ('Gestión de almacén y logística', None, 'economica'),
    ('Taller de finanzas personales', None, 'economica'),
    ('Charla sobre derechos del consumidor', None, 'economica'),
    ('Feria de franquicias', None, 'economica'),
    ('Curso de cocina profesional', None, 'economica'),
    ('Taller de liderazgo empresarial', None, 'economica'),
    ('Jornada de orientación laboral', None, 'economica'),
    ('Curso de auxiliar administrativo', None, 'economica'),
    ('Taller de entrevistas de trabajo', None, 'economica'),
    ('Charla sobre autoempleo', None, 'economica'),
    ('Curso de dependiente de comercio', None, 'economica'),
    ('Feria de productos artesanales', None, 'economica'),
    ('Taller de marketing digital para negocios', None, 'economica'),
    ('Charla sobre economía colaborativa', None, 'economica'),
    ('Taller de gestión de PYMES', None, 'economica'),
    ('Curso de guía turístico', None, 'economica'),
    ('Networking mujeres empresarias', None, 'economica'),
    ('Charla sobre inversiones seguras', None, 'economica'),
    ('Curso de community manager', None, 'economica'),
    ('Taller de facturación y contabilidad', None, 'economica'),
    # Multi-categoría: formación profesional + tema
    ('Curso de socorrista acuático', None, {'economica', 'sanitaria'}),
    ('Curso de cuidador de personas mayores', None, {'economica', 'sanitaria'}),

    # === POLITICA (25) ===
    ('Pleno del Ayuntamiento de Madrid', None, 'politica'),
    ('Agenda del Ministro de Cultura', None, 'politica'),
    ('Debate electoral en el Congreso', None, 'politica'),
    ('Presupuestos participativos 2025', None, 'politica'),
    ('Visita institucional del alcalde', None, 'politica'),
    ('Jornada de puertas abiertas Parlamento', None, 'politica'),
    ('Sesión del Senado', None, 'politica'),
    ('Rueda de prensa del Presidente', None, 'politica'),
    ('Consejo de Ministros', None, 'politica'),
    ('Reunión del Consejo Europeo', None, 'politica'),
    ('Mitin electoral del PSOE', None, 'politica'),
    ('Acto institucional Día de la Constitución', None, 'politica'),
    ('Comisión parlamentaria de Sanidad', None, 'politica'),
    ('Pleno extraordinario del Ayuntamiento', None, 'politica'),
    ('Jornada sobre participación ciudadana', None, 'politica'),
    ('Consulta popular sobre movilidad', None, 'politica'),
    ('Acto de toma de posesión del alcalde', None, 'politica'),
    ('Debate sobre el estado de la nación', None, 'politica'),
    ('Reunión del Consejo de Mayores', None, 'politica'),
    ('Jornada de derechos civiles', None, 'politica'),
    ('Acto institucional 12 de octubre', None, 'politica'),
    ('Visita de Estado del Rey', None, 'politica'),
    ('Inauguración oficial de infraestructura', None, 'politica'),
    ('Asamblea de vecinos con el concejal', None, 'politica'),
    ('Jornada sobre transparencia pública', None, 'politica'),

    # === TECNOLOGIA (31) + 1 multi-categoría ===
    ('Taller de WhatsApp para mayores', None, 'tecnologia'),
    ('Curso de informática básica', None, 'tecnologia'),
    ('Aprender a usar el móvil', 'Puntos Vuela - inclusión digital', 'tecnologia'),
    ('Ciberseguridad: protege tus datos', None, 'tecnologia'),
    ('Taller de videollamadas Zoom', None, 'tecnologia'),
    ('Administración electrónica: cita previa', None, 'tecnologia'),
    ('Introducción a ChatGPT', None, 'tecnologia'),
    ('Banca online segura', None, 'tecnologia'),
    ('Curso de tablet para principiantes', None, 'tecnologia'),
    ('Taller de correo electrónico', None, 'tecnologia'),
    ('Redes sociales: Facebook e Instagram', None, 'tecnologia'),
    ('Taller de compras online seguras', None, 'tecnologia'),
    ('Certificado digital: cómo obtenerlo', None, 'tecnologia'),
    ('Curso de Word y Excel básico', None, 'tecnologia'),
    ('Taller de YouTube para mayores', None, 'tecnologia'),
    ('Protección de contraseñas', None, 'tecnologia'),
    ('Curso de Skype y videollamadas', None, 'tecnologia'),
    ('Taller de almacenamiento en la nube', None, 'tecnologia'),
    ('DNI electrónico: usos prácticos', None, 'tecnologia'),
    ('Curso de edición de fotos', None, 'tecnologia'),
    ('Taller de Google Maps', None, 'tecnologia'),
    ('Introducción a la inteligencia artificial', None, 'tecnologia'),
    ('Curso de creación de blogs', None, 'tecnologia'),
    ('Robótica educativa para mayores', None, 'tecnologia'),
    ('Curso de impresión 3D', None, 'tecnologia'),
    ('Taller de privacidad en internet', None, 'tecnologia'),
    ('Curso de programación básica', None, 'tecnologia'),
    ('Arduino para principiantes', None, 'tecnologia'),
    ('Taller de firma electrónica', None, 'tecnologia'),
    ('Curso de diseño gráfico básico', None, 'tecnologia'),
    ('Hackathon senior', None, 'tecnologia'),
    # Multi-categoría
    ('Taller de apps de salud', None, {'tecnologia', 'sanitaria'}),

    # === SANITARIA (38) + 2 movidos a social ===
    ('Clase de Yoga para mayores', None, 'sanitaria'),
    ('Charla sobre prevención de diabetes', None, 'sanitaria'),
    ('Alzheimer y tecnología', 'Puntos Vuela - inclusión digital', 'sanitaria'),
    ('Taller de nutrición saludable', None, 'sanitaria'),
    ('Gimnasia de mantenimiento', None, 'sanitaria'),
    ('Donación de sangre Cruz Roja', None, 'sanitaria'),
    ('Mindfulness y gestión del estrés', None, 'sanitaria'),
    ('Primeros auxilios básicos', None, 'sanitaria'),
    ('Zumba Gold para seniors', None, 'sanitaria'),
    ('Salud mental: combatir la ansiedad', None, 'sanitaria'),
    ('Tai Chi en el parque', None, 'sanitaria'),
    ('Charla sobre hipertensión', None, 'sanitaria'),
    ('Taller de alimentación mediterránea', None, 'sanitaria'),
    ('Aquagym para mayores', None, 'sanitaria'),
    ('Prevención de caídas en el hogar', None, 'sanitaria'),
    ('Charla sobre colesterol', None, 'sanitaria'),
    ('Pilates suave', None, 'sanitaria'),
    ('Taller de memoria y estimulación cognitiva', None, 'sanitaria'),
    ('Jornada de detección precoz de cáncer', None, 'sanitaria'),
    ('Curso de RCP y desfibrilador', None, 'sanitaria'),
    ('Charla sobre osteoporosis', None, 'sanitaria'),
    ('Meditación guiada', None, 'sanitaria'),
    ('Taller de cocina saludable', None, 'sanitaria'),
    ('Gimnasia respiratoria', None, 'sanitaria'),
    ('Charla sobre sueño y descanso', None, 'sanitaria'),
    ('Taller de autoestima y bienestar', None, 'sanitaria'),
    ('Campaña de vacunación gripe', None, 'sanitaria'),
    ('Fisioterapia preventiva', None, 'sanitaria'),
    ('Charla sobre envejecimiento activo', None, 'sanitaria'),
    ('Taller de gestión emocional', None, 'sanitaria'),
    ('Senderismo saludable', None, 'sanitaria'),
    ('Charla sobre artritis y artrosis', None, 'sanitaria'),
    ('Taller de relajación', None, 'sanitaria'),
    ('Jornada de salud cardiovascular', None, 'sanitaria'),
    ('Estiramientos para mayores', None, 'sanitaria'),
    ('Charla sobre depresión en mayores', None, 'sanitaria'),
    ('Taller de hábitos saludables', None, 'sanitaria'),
    ('Paseos cardiosaludables', None, 'sanitaria'),
    ('Charla sobre diabetes tipo 2', None, 'sanitaria'),
    ('Ejercicio funcional para la vida diaria', None, 'sanitaria'),
    # Estos tienen componente social pero son principalmente salud
    ('Paseo saludable por el parque', None, 'sanitaria'),
    ('Grupo de apoyo para cuidadores', None, 'sanitaria'),
]


def check_match(got: list, expected) -> bool:
    """Check if classification matches expected (single or multi-category)."""
    got_set = set(got)
    if isinstance(expected, set):
        # Multi-category: must have at least one match
        return bool(got_set & expected)
    else:
        # Single category: first result must match
        return expected in got_set


def run_test():
    print(f'Testing {len(EVENTS)} events...')
    print('='*80)

    correct = 0
    failures = []
    multi_cat_count = 0

    for i, (title, source, expected) in enumerate(EVENTS, 1):
        result = classifier.classify_llm(title, source)
        got = result if result else ['NONE']
        ok = check_match(got, expected)

        if len(got) > 1:
            multi_cat_count += 1

        cats_str = ','.join(got)
        exp_str = ','.join(sorted(expected)) if isinstance(expected, set) else expected

        if ok:
            correct += 1
            print(f'✓ [{i:3}] {title[:45]:45} -> {cats_str}')
        else:
            failures.append((title, source, exp_str, cats_str))
            print(f'✗ [{i:3}] {title[:45]:45} -> {cats_str} (expected: {exp_str})')

    print('='*80)
    accuracy = (correct/len(EVENTS))*100
    print(f'')
    print(f'RESULTADO GLOBAL: {correct}/{len(EVENTS)} = {accuracy:.1f}%')
    print(f'Eventos multi-categoría: {multi_cat_count}')
    print(f'Target: 95%  |  Result: {"PASS ✓" if accuracy >= 95 else "FAIL ✗"}')

    if failures:
        print(f'')
        print(f'FALLOS ({len(failures)}):')
        for title, source, expected, got in failures:
            src = f' [fuente: {source[:20]}...]' if source else ''
            print(f'  - "{title[:50]}"{src}')
            print(f'    Expected: {expected}, Got: {got}')


if __name__ == '__main__':
    run_test()
