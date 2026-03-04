"""Backfill: Fix only events with wrong or missing categories."""
import os
import sys
import time

import dotenv
dotenv.load_dotenv()

from supabase import create_client
from groq import Groq

sb = create_client(
    os.environ["NEXT_PUBLIC_SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

# Category map
cats = sb.table("categories").select("id,slug").execute()
cat_id_map = {c["slug"]: c["id"] for c in cats.data}
cat_map = {c["id"]: c["slug"] for c in cats.data}

SOURCE_CONTEXT = {
    "puntos_vuela": "Puntos Vuela - centros de inclusion digital para personas mayores en Andalucia",
    "cemit": "CeMIT - centros de inclusion tecnologica de la Xunta de Galicia",
    "oviedo": "Ayuntamiento de Oviedo - actividades para personas mayores en centros municipales",
    "madrid_datos": "Madrid Datos Abiertos - agenda cultural y social del Ayuntamiento de Madrid",
    "soledadnodeseada": "Soledad No Deseada - programa contra la soledad de personas mayores",
    "consaludmental": "Confederacion Salud Mental Espana - eventos de salud mental",
    "fundacion_telefonica": "Fundacion Telefonica - exposiciones y talleres tecnologicos en Madrid",
    "bcnactiva": "Barcelona Activa - emprendimiento y empleo en Barcelona",
    "tourempleo": "Tourempleo - ferias de empleo y formacion profesional",
    "defensor_pueblo": "Defensor del Pueblo - actos institucionales y derechos civicos",
    "horizonte_europa": "Horizonte Europa - financiacion europea para investigacion e innovacion",
}

SYSTEM_PROMPT = """Eres un clasificador de eventos. Clasifica en UNA categoria segun su PROPOSITO PRINCIPAL.

Considera el contexto del programa:
- Baile/Zumba/Pilates en centros de mayores = SANITARIA (ejercicio)
- Talleres de empleo/CV/finanzas = ECONOMICA aunque sea en centro tecnologico
- Actividades contra la soledad = SOCIAL
- Manualidades/artesania/arte = CULTURAL
- Conciertos, espectaculos de danza y shows musicales = CULTURAL, aunque incluyan baile o tango
- Ferias comerciales y de empleo = ECONOMICA

Categorias (SOLO estas 6):
- cultural: Espectaculos, conciertos, teatro, cine, exposiciones, arte, manualidades, talleres artisticos
- social: Comunidad, voluntariado, ecologia, igualdad, inclusion, combatir soledad
- economica: Empleo, emprendimiento, formacion profesional, finanzas, curriculum
- politica: Gobierno, instituciones, agenda ministerial, derechos civicos
- tecnologia: Informatica, internet, programacion, IA, ciberseguridad, ofimatica, apps
- sanitaria: Salud, nutricion, ejercicio fisico, salud mental, yoga, zumba, pilates, gimnasia

Responde SOLO con el slug."""

ALLOWED = set(cat_id_map.keys())

# =====================================================
# KNOWN MISCLASSIFICATIONS (title patterns -> correct)
# These don't need LLM calls
# =====================================================
TITLE_OVERRIDES = {
    # Puntos Vuela: finance/employment wrongly tagged as tecnologia
    "libertad financiera": "economica",
    "educacion financiera": "economica",
    "mentalidad financiera": "economica",
    "presupuesto inteligente": "economica",
    "tipos de inversion": "economica",
    "tu momento financiero": "economica",
    "mejora tu curriculum": "economica",
    "conocete para encontrar empleo": "economica",
    "busqueda activa de empleo": "economica",
    "ecosistema emprendedor": "economica",
    "chatgpt: busqueda de empleo": "economica",
    "taller de gestiones sae": "economica",
    # Puntos Vuela: health wrongly tagged as tecnologia
    "alzheimer y tecnologia": "sanitaria",
    "elegir bien lo que comes": "sanitaria",
    "comer de temporada": "sanitaria",
    "alimentacion equilibrada": "sanitaria",
    "programas de bienestar": "sanitaria",
    "tu movil, tu centro de salud": "sanitaria",
    "tu salud en un clic": "sanitaria",
    "diabetic": "sanitaria",
    # Puntos Vuela: social wrongly tagged as tecnologia
    "ecologia en tu dia a dia": "social",
    "cuidar el entorno": "social",
    "es tu mundo y es finito": "social",
    "introduccion a la produccion ecologica": "social",
    "pequenos guardianes del planeta": "social",
    # CeMIT: employment wrongly tagged as tecnologia
    "elaboracion de mi cv": "economica",
    "busqueda de empleo": "economica",
    "monitor de tiempo libre": "economica",
    "operaciones basicas en caja": "economica",
    "gestion basica del almacen": "economica",
    "habilidades sociales de atencion al cliente": "economica",
    "proceso de emprender": "economica",
    "coaching desarrollo de personas": "economica",
    "conduccion de carretillas": "economica",
    "acompanante de transporte escolar": "economica",
    "mantenimiento basico de limpieza": "economica",
    # CeMIT: health wrongly tagged as tecnologia
    "tecnicas basicas de primeros auxilios": "sanitaria",
    "exercita a tua memoria": "sanitaria",
    "taller de memoria y estimulacion cognitiva": "sanitaria",
    "el deporte como herramienta dinamizadora": "sanitaria",
    # Oviedo: exercise should be sanitaria
    "baile zumba": "sanitaria",
    "bailoterapia": "sanitaria",
    "baile de salon": "sanitaria",
    "baile de salon avanzado": "sanitaria",
    "baile de salon iniciacion": "sanitaria",
    "baile asturiano": "sanitaria",
    "bailes latinos": "sanitaria",
    "bailes latinos i": "sanitaria",
    "bailes latinos ii": "sanitaria",
    "sevillanas": "sanitaria",
    "sevillanas avanzado": "sanitaria",
    "sevillanas iniciacion": "sanitaria",
    "tango": "sanitaria",
    "yoga": "sanitaria",
    "pilates": "sanitaria",
    "taichi": "sanitaria",
    "taichi i": "sanitaria",
    "taichi ii": "sanitaria",
    "chikung": "sanitaria",
    "aerobic": "sanitaria",
    "gerontogimnasia": "sanitaria",
    "gimnasia de mantenimiento": "sanitaria",
    "escuela de espalda": "sanitaria",
    "yoguilates": "sanitaria",
    "flexibilidad y control postural": "sanitaria",
    "barre y equilibrio": "sanitaria",
    "step": "sanitaria",
    "strenght": "sanitaria",
    "reactivate": "sanitaria",
    "psicomotricidad": "sanitaria",
    "estimulacion mental": "sanitaria",
    "relajacion": "sanitaria",
    # Oviedo: cultural activities
    "taller de teatro": "cultural",
    "coro": "cultural",
    "acuarela avanzado": "cultural",
    "acuarela iniciacion": "cultural",
    "dibujo": "cultural",
    "pintura": "cultural",
    "ceramica": "cultural",
    "cesteria": "cultural",
    "encaje de bolillos": "cultural",
    "encuadernacion artesanal": "cultural",
    "costura creativa": "cultural",
    "cose tu estilo": "cultural",
    "cuero": "cultural",
    "bisuteria con hilos": "cultural",
    "estampacion textil": "cultural",
    "artes florales": "cultural",
    "decoracion del hogar": "cultural",
    "caligrafia": "cultural",
    "club de cine y guiones": "cultural",
    "entre hilos": "cultural",
    "encuadernacion japonesa": "cultural",
    "circo, magia e ilusionismo": "cultural",
}


def normalize_title(t):
    """Normalize title for matching."""
    import unicodedata
    t = t.lower().strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t


def match_override(title):
    """Check if title matches any known override pattern.

    Single-word patterns require EXACT title match to avoid false positives
    (e.g. "tango" should not match "Sótántangó" or "Poesía, Tango y Flamenco").
    Multi-word patterns use substring matching (they're specific enough).
    """
    norm = normalize_title(title)
    for pattern, cat in TITLE_OVERRIDES.items():
        if " " in pattern:
            # Multi-word: substring match (specific enough)
            if pattern in norm:
                return cat
        else:
            # Single-word: exact match only
            if norm == pattern:
                return cat
    return None


def classify_llm(title, source_context=None):
    """Classify via LLM."""
    user_msg = f"Titulo: {title}"
    if source_context:
        user_msg += f"\nFuente: {source_context}"
    try:
        resp = groq_client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=10,
        )
        raw = resp.choices[0].message.content.strip().lower()
        raw = raw.replace('"', "").replace("'", "").replace(".", "").strip()
        return raw if raw in ALLOWED else None
    except Exception as e:
        print(f"  ERROR: {e}")
        time.sleep(2)
        return None


def paginate(table, columns="*"):
    rows = []
    offset = 0
    while True:
        res = sb.table(table).select(columns).range(offset, offset + 999).execute()
        rows.extend(res.data)
        if len(res.data) < 1000:
            break
        offset += 1000
    return rows


def get_source(ext_id):
    for prefix in SOURCE_CONTEXT:
        if ext_id and ext_id.startswith(prefix):
            return prefix
    return "unknown"


def main():
    print("Loading events...")
    all_events = paginate("events", "id,title,external_id")
    all_ec = paginate("event_categories", "event_id,category_id")

    event_current = {}
    for row in all_ec:
        slug = cat_map.get(row["category_id"], "?")
        event_current.setdefault(row["event_id"], []).append(slug)

    print(f"Total events: {len(all_events)}")
    print(f"With category: {len(event_current)}")
    print(f"Without category: {len(all_events) - len(event_current)}")

    # Step 1: Find events needing fixes
    to_fix = []  # (event_id, title, old_cats, new_cat, method)
    llm_needed = []  # events that need LLM classification

    for e in all_events:
        eid = e["id"]
        title = e["title"] or ""
        ext_id = e.get("external_id") or ""
        source = get_source(ext_id)
        current = event_current.get(eid, [])

        # Check pattern override first
        override = match_override(title)
        if override:
            if current != [override]:
                to_fix.append((eid, title, current, override, "pattern", source))
            continue

        # No category at all -> need LLM
        if not current:
            llm_needed.append(e)
            continue

        # Sources known to have issues with "tecnologia" for non-tech events
        if source in ("puntos_vuela", "cemit") and current == ["tecnologia"]:
            llm_needed.append(e)

    print(f"\nPattern-based fixes: {len(to_fix)}")
    print(f"Events needing LLM classification: {len(llm_needed)}")

    # Step 2: Classify remaining via LLM
    # Cache by (title, source) to avoid duplicate calls
    llm_cache = {}
    llm_calls = 0

    for i, e in enumerate(llm_needed):
        title = e["title"] or ""
        ext_id = e.get("external_id") or ""
        source = get_source(ext_id)
        cache_key = (title, source)

        if cache_key in llm_cache:
            new_cat = llm_cache[cache_key]
        else:
            source_ctx = SOURCE_CONTEXT.get(source)
            new_cat = classify_llm(title, source_ctx)
            llm_cache[cache_key] = new_cat
            llm_calls += 1
            if llm_calls % 50 == 0:
                print(f"  LLM calls: {llm_calls}/{len(llm_needed)}...")

        if new_cat:
            current = event_current.get(e["id"], [])
            if current != [new_cat]:
                to_fix.append((e["id"], title, current, new_cat, "llm", source))

    print(f"LLM calls made: {llm_calls}")
    print(f"Total fixes needed: {len(to_fix)}")

    # Show summary
    if to_fix:
        print(f"\n{'='*70}")
        adds = [(eid, t, o, n, m, s) for eid, t, o, n, m, s in to_fix if not o]
        changes = [(eid, t, o, n, m, s) for eid, t, o, n, m, s in to_fix if o]

        if adds:
            print(f"\n--- ADD CATEGORY ({len(adds)}) ---")
            for eid, title, old, new, method, src in adds[:40]:
                print(f"  [{new:12}] ({method:7}) {src:20} | {title[:50]}")
            if len(adds) > 40:
                print(f"  ... and {len(adds) - 40} more")

        if changes:
            print(f"\n--- CHANGE CATEGORY ({len(changes)}) ---")
            for eid, title, old, new, method, src in changes[:60]:
                print(f"  [{','.join(old):12}] -> [{new:12}] ({method:7}) {src:20} | {title[:45]}")
            if len(changes) > 60:
                print(f"  ... and {len(changes) - 60} more")

    total = len(to_fix)
    if total == 0:
        print("\nNo changes needed!")
        return

    print(f"\nReady to apply {total} changes.")
    if "--apply" not in sys.argv:
        print("Run with --apply to execute.")
        return

    # Apply
    print(f"\n=== APPLYING {total} CHANGES ===")
    applied = errors = 0

    for eid, title, old, new, method, src in to_fix:
        try:
            if old:
                sb.table("event_categories").delete().eq("event_id", eid).execute()
            sb.table("event_categories").insert({
                "event_id": eid,
                "category_id": cat_id_map[new],
            }).execute()
            applied += 1
        except Exception as ex:
            errors += 1
            if errors <= 10:
                print(f"  ERROR '{title[:40]}': {ex}")

    print(f"\nDone! Applied: {applied}, Errors: {errors}")


if __name__ == "__main__":
    main()
