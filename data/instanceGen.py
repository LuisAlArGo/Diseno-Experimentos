"""
Generador de instancias para el problema de horarios universitarios.

Plantilla Perfecta   : esqueleto libre de conflictos de aula y currículo
Asignación de Profs  : distribuye profesores al esqueleto (aleatorio sin conflictos de horario)
Factor de Dificultad : ajusta disponibilidad, cursos y max_groups con variante A- o A+

Uso:
    python InstanceGenerator.py --data data --output generated_instances --seeds 42 123 456 --difficulty both
"""

import argparse
import json
import math
import os
import random
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

# ─── Constantes globales ──────────────────────────────────────────────────────

ALL_DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

DAY_PAIRS: Dict[str, List[str]] = {
    "Lunes":     ["Jueves"],
    "Jueves":    ["Lunes"],
    "Martes":    ["Viernes"],
    "Viernes":   ["Martes"],
    "Miércoles": ["Lunes", "Viernes"],
}

START_HOUR = 7
END_HOUR   = 21   # bloques son [h, h+1); el último válido es [22, 23)

# Especializaciones que crean un "track" propio junto a los cursos generales
SPEC_TRACKS = ("software", "computer science", "information technology")


def generate_instances(
    data_path:  str,
    output_path: str,
    seeds:      List[int],
    difficulty: str = "both",   # "A-" | "A+" | "both"
) -> None:
    """Genera una instancia (par de variantes) por cada semilla."""

    courses_data, classrooms_data, all_professors_data = _load_base_data(data_path)

    for idx, seed in enumerate(seeds):
        _banner(f"Instancia {idx + 1}/{len(seeds)}  |  seed = {seed}")

        rng = random.Random(seed)

        # ── Fase 1 ──────────────────────────────────────────────────────────
        print("[Fase 1] Construyendo esqueleto de horario...")
        skeleton = phase1_build_skeleton(courses_data, classrooms_data, rng)

        # ── Fase 2 ──────────────────────────────────────────────────────────
        print("[Fase 2] Asignando profesores al esqueleto...")
        prof_subset, g2p = phase2_assign_professors(
            skeleton, all_professors_data, rng
        )

        # ── Fase 3 ──────────────────────────────────────────────────────────
        variants = ["A-", "A+"] if difficulty == "both" else [difficulty]
        for diff in variants:
            print(f"  [Fase 3] Generando variante {diff}...")
            profs_out = phase3_generate_professors(
                prof_subset, g2p, skeleton, diff, courses_data, rng
            )
            _save_instance(
                output_path, seed, diff,
                courses_data, classrooms_data, profs_out,
                skeleton, g2p, classrooms_data,
            )

    print("\nGeneración finalizada.\n")


# ─── Carga de datos base ─────────────────────────────────────────────────────

def _load_base_data(
    data_path: str,
) -> Tuple[List[dict], List[dict], List[dict]]:
    def _load(fname: str) -> List[dict]:
        path = os.path.join(data_path, fname)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    courses    = [c for c in _load("courses.json")    if c.get("groups", 0) > 0]
    classrooms = _load("classrooms.json")
    professors = _load("professors.json")
    return courses, classrooms, professors


# ─────────────────────────────────────────────────────────────────────────────
# FASE 1 – Plantilla Perfecta
# ─────────────────────────────────────────────────────────────────────────────

def phase1_build_skeleton(
    courses_data:    List[dict],
    classrooms_data: List[dict],
    rng:             random.Random,
) -> Dict[str, dict]:
    
    classroom_used: Dict[str, Set[Tuple]] = {
        c["number"]: set() for c in classrooms_data
    }

    curriculum_used: Dict[Tuple[int, int, str], Set[Tuple]] = defaultdict(set)

    skeleton: Dict[str, dict] = {}
    
    all_groups_to_place = []
    for course in courses_data:
        for gnum in range(1, course["groups"] + 1):
            all_groups_to_place.append((course, gnum))
    
    rng.shuffle(all_groups_to_place)

    for course, gnum in all_groups_to_place:
        sem = course["semester"]
        spec = course.get("specialization", "general").lower()
        
        forbidden_slots = set()
        
        if spec == "general" or spec in SPEC_TRACKS:
            # 1. Todo lo que sea de carrera (general o tracks) no puede chocar con las materias "general"
            forbidden_slots |= curriculum_used.get((sem, gnum, "general"), set())
            
            if spec == "general":
                # 2. Si estoy ubicando una "general", me aseguro de no pisar el horario de NINGÚN track
                for other_spec in SPEC_TRACKS:
                    forbidden_slots |= curriculum_used.get((sem, gnum, other_spec), set())
            else:
                # 3. Si estoy ubicando un track (ej. "software"), no piso a las de "software" (ni a las generales, del paso 1)
                forbidden_slots |= curriculum_used.get((sem, gnum, spec), set())
                
        else:
            forbidden_slots = set()

        # El _try_place se encarga de revisar que el AULA esté libre internamente
        result = _try_place(
            course, classrooms_data, classroom_used, forbidden_slots, rng
        )
        
        if result is None:
            print(f"Fallback para {course['id']}-G{gnum} - omitiendo reglas de currículo")
            result = _try_place(
                course, classrooms_data, classroom_used, set(), rng,
                max_attempts=2_000,
            )
        
        if result is None:
            print(f"No se pudo colocar {course['id']}-G{gnum} – omitido")
            continue

        slots, cls_num = result
        gkey = f"{course['id']}-G{gnum}"
        
        skeleton[gkey] = {
            "course":        course,
            "group_number":  gnum,
            "slots":         slots,      
            "classroom":     cls_num,
        }
        
        _occupy(classroom_used[cls_num], slots)
        _occupy(curriculum_used[(sem, gnum, spec)], slots)

    print(f"{len(skeleton)} grupos en el esqueleto")
    return skeleton

def _try_place(
    course:          dict,
    classrooms_data: List[dict],
    classroom_used:  Dict[str, Set[Tuple]],
    forbidden_slots: Set[Tuple],
    rng:             random.Random,
    max_attempts:    int = 1000,
) -> Optional[Tuple[List[Tuple[str, int]], str]]:
    """
    Intenta colocar un curso en el horario respetando aulas y currículo.
    - Cualquier curso se puede asignar a cualquier aula.
    - Cursos > 3 horas se dividen en 2 días.
    - Se usan los DAY_PAIRS.
    - Se alinean los bloques para que inicien o terminen a la misma hora.
    """
    hours = course["hours"]
    
    # Al eliminar el tipo de aula, todas las aulas son válidas
    valid_classrooms = classrooms_data
    
    if not valid_classrooms:
        return None

    # 1. Definir cómo se dividirán las horas
    splits = []
    if hours <= 3:
        splits = [hours]           # 1 a 3 horas en un solo bloque
    elif hours == 4:
        splits = [2, 2]            # 4 horas -> 2 y 2
    elif hours == 5:
        splits = rng.choice([[3, 2], [2, 3]]) # 5 horas -> 3 y 2, o 2 y 3
    else:
        splits = [3, min(hours - 3, 3)]       # 6 horas -> 3 y 3 (límite asumido 6h)

    # 2. Intentar colocar
    for _ in range(max_attempts):
        # Escoger aula aleatoria del total de aulas disponibles
        cls = rng.choice(valid_classrooms)
        cls_num = cls["number"]
        cls_used = classroom_used[cls_num]
        
        slots = []
        is_valid = True
        
        if len(splits) == 1:
            # --- CASO: 1 solo día ---
            h = splits[0]
            day = rng.choice(ALL_DAYS)
            start_h = rng.randint(START_HOUR, END_HOUR - h)
            
            for offset in range(h):
                slot = (day, start_h + offset)
                if slot in forbidden_slots or slot in cls_used:
                    is_valid = False
                    break
                slots.append(slot)
                
        else:
            # --- CASO: 2 días (dividido) ---
            h1, h2 = splits
            
            # Elegir par de días
            day1 = rng.choice(list(DAY_PAIRS.keys()))
            day2 = rng.choice(DAY_PAIRS[day1])
            
            # Decidir si inician a la misma hora o terminan a la misma hora
            alignment = rng.choice(["same_start", "same_end"])
            
            if alignment == "same_start":
                # El inicio máximo está limitado por el bloque más largo
                max_start = END_HOUR - max(h1, h2)
                start_h = rng.randint(START_HOUR, max_start)
                start1 = start_h
                start2 = start_h
            else:
                # El fin mínimo está limitado por el bloque más largo
                min_end = START_HOUR + max(h1, h2)
                end_h = rng.randint(min_end, END_HOUR)
                start1 = end_h - h1
                start2 = end_h - h2
            
            # Generar los slots temporales
            for offset in range(h1):
                slots.append((day1, start1 + offset))
            for offset in range(h2):
                slots.append((day2, start2 + offset))
                
            # Verificar colisiones para todos los slots
            for slot in slots:
                if slot in forbidden_slots or slot in cls_used:
                    is_valid = False
                    break

        # Si no hubo colisiones y se asignaron todas las horas, retornamos el éxito
        if is_valid and len(slots) == hours:
            return slots, cls_num

    # Si se agotan los intentos y no se logra ubicar
    return None

def _occupy(used_set: Set[Tuple], slots: List[Tuple]) -> None:
    """
    Marca un conjunto de slots (día, hora) como ocupados en el set indicado.
    """
    for s in slots:
        used_set.add(tuple(s))
# ─────────────────────────────────────────────────────────────────────────────
# FASE 2 – Asignación de Profesores
# ─────────────────────────────────────────────────────────────────────────────
def phase2_assign_professors(
    skeleton:             Dict[str, dict],
    all_professors_data:  List[dict],
    rng:                  random.Random,
    max_classes_per_prof: int = 5    # Límite para balancear la carga
) -> Tuple[List[dict], Dict[str, Optional[str]]]:
    """
    Asigna profesores garantizando que todos reciban al menos un grupo (si hay suficientes),
    y luego distribuye el resto evitando conflictos de horario y balanceando la carga.
    """
    prof_slots: Dict[str, Set[Tuple]] = defaultdict(set)
    prof_counts: Dict[str, int] = defaultdict(int)
    g2p: Dict[str, Optional[str]] = {}

    # Obtenemos todos los grupos y los mezclamos
    unassigned_groups = list(skeleton.keys())
    rng.shuffle(unassigned_groups)

    # Obtenemos todos los profesores y los mezclamos
    candidates = list(all_professors_data)
    rng.shuffle(candidates)

    # ─── PASO 1: Garantizar al menos 1 grupo por profesor ───────────
    # Como es su primera clase, NUNCA habrá conflicto de horario.
    unassigned_profs = list(candidates)
    
    while unassigned_profs and unassigned_groups:
        p = unassigned_profs.pop()
        pid = p["id"]
        gkey = unassigned_groups.pop()
        group = skeleton[gkey]
        g_slots = set(map(tuple, group["slots"]))
        
        g2p[gkey] = pid
        prof_slots[pid] |= g_slots
        prof_counts[pid] += 1

    if unassigned_profs:
        print(f"Hay más profesores ({len(candidates)}) que grupos ({len(skeleton)}). "
              f"{len(unassigned_profs)} profesores quedarán sin clases.")

    # ─── PASO 2: Distribuir los grupos restantes ────────────────────
    for gkey in unassigned_groups:
        group = skeleton[gkey]
        g_slots = set(map(tuple, group["slots"]))

        rng.shuffle(candidates)
        assigned = False

        # Intento A: Asignar respetando el límite máximo de clases por profe
        for p in candidates:
            pid = p["id"]
            
            if prof_counts[pid] >= max_classes_per_prof:
                continue  # Evita que un profe acapare demasiadas clases
                
            if g_slots & prof_slots[pid]:
                continue  # Conflicto de horario
            
            g2p[gkey] = pid
            prof_slots[pid] |= g_slots
            prof_counts[pid] += 1
            assigned = True
            break

        # Intento B (Fallback): Si nadie puede tomarla por el límite, 
        # se ignora el límite (pero se sigue respetando el horario)
        if not assigned:
            for p in candidates:
                pid = p["id"]
                if not (g_slots & prof_slots[pid]):
                    g2p[gkey] = pid
                    prof_slots[pid] |= g_slots
                    prof_counts[pid] += 1
                    assigned = True
                    break

        # Si de verdad nadie puede (todos tienen conflictos a esa hora)
        if not assigned:
            g2p[gkey] = None
            print(f"Sin profesor disponible para {gkey} (conflictos de horario insalvables)")

    ok = sum(1 for v in g2p.values() if v is not None)
    profs_used = sum(1 for c in prof_counts.values() if c > 0)
    
    print(f"{ok}/{len(skeleton)} grupos asignados a profesor")
    print(f"{profs_used}/{len(candidates)} profesores utilizados (Tienen >= 1 clase)")
    
    return all_professors_data, g2p
# ─────────────────────────────────────────────────────────────────────────────
# FASE 3 – Factor de Dificultad
# ─────────────────────────────────────────────────────────────────────────────

def phase3_generate_professors(
    prof_subset:  List[dict],
    g2p:          Dict[str, Optional[str]],
    skeleton:     Dict[str, dict],
    difficulty:   str,              # "A-" | "A+"
    courses_data: List[dict],
    rng:          random.Random,
) -> List[dict]:
    
    prof_assigned_slots: Dict[str, List[Tuple]] = defaultdict(list)
    prof_assigned_courses: Dict[str, Set[str]]  = defaultdict(set)
    prof_assigned_counts: Dict[str, int]        = defaultdict(int)

    for gkey, pid in g2p.items():
        if pid is None: continue
        group = skeleton[gkey]
        cid   = group["course"]["id"]
        
        prof_assigned_counts[pid] += 1
        prof_assigned_courses[pid].add(cid)
        for s in group["slots"]:
            prof_assigned_slots[pid].append(tuple(s))

    # Lista de todos los cursos disponibles en la data
    all_course_ids = [c["id"] for c in courses_data]

    result = []
    for p in prof_subset:
        pid = p["id"]
        assigned_slots   = prof_assigned_slots.get(pid, [])
        assigned_count   = prof_assigned_counts.get(pid, 0)
        assigned_courses = prof_assigned_courses.get(pid, set())

        # Definir cuántos grupos EXTRA tendrá el profesor
        if difficulty == "A+":
            extra_groups = rng.choice([2, 3]) # Holgado: 2 o 3 grupos extra
        else:
            extra_groups = 1                  # Estricto: exactamente 1 grupo extra

        max_groups = assigned_count + extra_groups

        # Generar horarios en base a la proporción
        avail_ranges, pref_ranges = _generate_proportional_availability(
            assigned_slots, extra_groups, rng
        )

        # Ajuste de preferencias de horario según la dificultad
        if difficulty == "A+":
            # A+: Prefiere todos los horarios en los que está disponible (incluyendo los extra)
            pref_ranges = list(avail_ranges)
        else:
            # A-: Sus preferencias son estrictamente los horarios del esqueleto base (sin el tiempo extra)
            pref_ranges = _slots_to_ranges(set(assigned_slots))

        # Configurar can_teach y course_preferences
        can_teach_set = set(assigned_courses)
        pref_teach_set = set(assigned_courses)

        if not can_teach_set:
            # Fallback: si no tiene cursos en el skeleton, le damos todos
            can_teach_set = set(all_course_ids)
            pref_teach_set = set(all_course_ids)
        else:
            # Buscar un curso random que el profesor AÚN NO tenga asignado
            unassigned_courses = [cid for cid in all_course_ids if cid not in can_teach_set]
            if unassigned_courses:
                random_extra_course = rng.choice(unassigned_courses)
                
                # Siempre lo puede enseñar
                can_teach_set.add(random_extra_course)
                
                # Si es holgado (A+), también prefiere enseñarlo
                if difficulty == "A+":
                    pref_teach_set.add(random_extra_course)

        result.append({
            "id":                   pid,
            "name":                 p["name"],
            "courses":              list(can_teach_set),
            "max_groups":           max_groups,
            "course_preferences":   list(pref_teach_set),
            "schedule_preferences": pref_ranges,
            "available_blocks":     avail_ranges,
        })
        
    return result


def _generate_proportional_availability(
    assigned_slots: List[Tuple[str, int]],
    extra_groups: int,
    rng: random.Random
) -> Tuple[List[dict], List[dict]]:
    """
    Genera rangos de disponibilidad añadiendo 6 horas por cada 'extra_group'.
    Reconoce si el profe ya tiene bloques en días pares (ej. Lunes y Jueves)
    para pegar las horas justo antes o justo después de los horarios de ese curso.
    Si el ancla es de un solo día, replica la misma hora de inicio en su día par.
    """
    avail_slots = set(assigned_slots)
    MAX_SLOT = 22  # Bloques son [h, h+1). Hora de inicio máxima válida es las 22:00.

    for _ in range(extra_groups):
        placed = False
        duration = 3

        # Extraer bloques contiguos actuales por día
        by_day: Dict[str, List[int]] = defaultdict(list)
        for d, h in avail_slots:
            by_day[d].append(h)

        blocks = []
        for d, hours in by_day.items():
            if not hours:
                continue
            sorted_h = sorted(hours)
            start_h = sorted_h[0]
            prev = start_h
            for h in sorted_h[1:]:
                if h == prev + 1:
                    prev = h
                else:
                    blocks.append((d, start_h, prev + 1))
                    start_h = prev = h
            blocks.append((d, start_h, prev + 1))

        # Identificar cuáles bloques pertenecen a un mismo "curso" (Días Pares)
        # Un curso se empareja si está en DAY_PAIRS y comparten hora de inicio o de fin.
        paired_anchors = []
        single_anchors = []
        used_blocks = set()

        for i, b1 in enumerate(blocks):
            if i in used_blocks: continue
            d1, s1, e1 = b1
            
            paired_days = DAY_PAIRS.get(d1, [])
            matched = False
            
            for j, b2 in enumerate(blocks):
                if j in used_blocks or j == i: continue
                d2, s2, e2 = b2
                # Si es un día par y tienen la misma hora de inicio o de fin, asumimos que es el mismo curso
                if d2 in paired_days and (s1 == s2 or e1 == e2):
                    paired_anchors.append((b1, b2))
                    used_blocks.add(i)
                    used_blocks.add(j)
                    matched = True
                    break
            
            if not matched:
                single_anchors.append(b1)
                used_blocks.add(i)

        rng.shuffle(paired_anchors)
        rng.shuffle(single_anchors)

        def is_free(day1: str, st1: int, day2: str, st2: int) -> bool:
            if st1 < START_HOUR or (st1 + duration - 1) > MAX_SLOT: return False
            if st2 < START_HOUR or (st2 + duration - 1) > MAX_SLOT: return False
            for offset in range(duration):
                if (day1, st1 + offset) in avail_slots: return False
                if (day2, st2 + offset) in avail_slots: return False
            return True

        def register_slots(day1: str, st1: int, day2: str, st2: int):
            for offset in range(duration):
                avail_slots.add((day1, st1 + offset))
                avail_slots.add((day2, st2 + offset))

        # Intentar pegar a "Bloques Emparejados" (Ej. Lunes 16-19 y Jueves 16-18)
        for (d1, s1, e1), (d2, s2, e2) in paired_anchors:
            # Opciones: ANTES (s-3 en ambos) o DESPUÉS (el final respectivo de cada bloque)
            options = [
                (s1 - duration, s2 - duration),  # Antes
                (e1, e2)                         # Después
            ]
            rng.shuffle(options)
            
            for st1, st2 in options:
                if is_free(d1, st1, d2, st2):
                    register_slots(d1, st1, d2, st2)
                    placed = True
                    break
            if placed: break

        # Si falló o no tenía bloques emparejados, intentar con "Bloques Simples" (Cursos de 1 día)
        if not placed:
            for d1, s1, e1 in single_anchors:
                paired_opts = DAY_PAIRS.get(d1, [])
                d2 = rng.choice(paired_opts) if paired_opts else rng.choice([d for d in ALL_DAYS if d != d1])
                
                # Opciones: ANTES (s-3) o DESPUÉS (e). En el día par se replica la misma hora de inicio.
                options = [
                    (s1 - duration, s1 - duration), # Antes
                    (e1, e1)                        # Después
                ]
                rng.shuffle(options)
                
                for st1, st2 in options:
                    if is_free(d1, st1, d2, st2):
                        register_slots(d1, st1, d2, st2)
                        placed = True
                        break
                if placed: break

        # Fallback total: Buscar espacios de 3 horas aleatorios con la misma hora de inicio en días pares
        if not placed:
            days_list = list(ALL_DAYS)
            for _fallback in range(100):
                d1 = rng.choice(days_list)
                paired_opts = DAY_PAIRS.get(d1, [])
                d2 = rng.choice(paired_opts) if paired_opts else rng.choice([d for d in days_list if d != d1])
                
                max_start = MAX_SLOT - duration + 1
                if max_start >= START_HOUR:
                    rand_start = rng.randint(START_HOUR, max_start)
                    if is_free(d1, rand_start, d2, rand_start):
                        register_slots(d1, rand_start, d2, rand_start)
                        break

    avail_ranges = _slots_to_ranges(avail_slots)
    pref_ranges = list(avail_ranges)

    return avail_ranges, pref_ranges


# Utilidades

def _slots_to_ranges(slots: Set[Tuple]) -> List[dict]:
    by_day: Dict[str, List[int]] = defaultdict(list)
    for d, h in slots:
        by_day[d].append(h)

    ranges = []
    for day in ALL_DAYS:
        hours = sorted(by_day.get(day, []))
        if not hours:
            continue
        start = prev = hours[0]
        for h in hours[1:]:
            if h == prev + 1:
                prev = h
            else:
                ranges.append({"day": day, "start_time": start, "end_time": prev + 1})
                start = prev = h
        ranges.append({"day": day, "start_time": start, "end_time": prev + 1})
    return ranges


def _consolidate_slots(slots) -> List[dict]:
    by_day: Dict[str, List[int]] = defaultdict(list)
    for d, h in slots:
        by_day[d].append(h)

    result = []
    for day in ALL_DAYS:
        hours = sorted(by_day.get(day, []))
        if not hours:
            continue
        start = prev = hours[0]
        for h in hours[1:]:
            if h == prev + 1:
                prev = h
            else:
                result.append({"day": day, "start_hour": start, "end_hour": prev + 1})
                start = prev = h
        result.append({"day": day, "start_hour": start, "end_hour": prev + 1})
    return result


def _save_instance(
    out_path:        str,
    seed:            int,
    difficulty:      str,
    courses:         List[dict],
    classrooms:      List[dict],
    professors:      List[dict],
    skeleton:        Dict[str, dict],
    g2p:             Dict[str, Optional[str]],
    classrooms_data: List[dict],
) -> None:
    folder = os.path.join(out_path, f"seed_{seed}", difficulty)
    os.makedirs(folder, exist_ok=True)

    def dump(obj: Any, fname: str) -> None:
        with open(os.path.join(folder, fname), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    dump(courses,    "courses.json")
    dump(classrooms, "classrooms.json")
    dump(professors, "professors.json")
    dump(
        _build_solution(skeleton, g2p, professors, classrooms_data),
        "solution.json",
    )
    print(f"Guardado en {folder}/")


def _build_solution(
    skeleton:        Dict[str, dict],
    g2p:             Dict[str, Optional[str]],
    professors_list: List[dict],
    classrooms_data: List[dict],
) -> dict:
    prof_map = {p["id"]: p for p in professors_list}
    cls_map  = {c["number"]: c for c in classrooms_data}

    groups_out = []
    for gkey, group in skeleton.items():
        pid = g2p.get(gkey)

        prof_info = (
            {"id": pid, "name": prof_map[pid]["name"]}
            if pid and pid in prof_map else None
        )
        cls_num  = group["classroom"]
        cls_info = (
            {"number": cls_num, "type": cls_map[cls_num]["type"]}
            if cls_num and cls_num in cls_map else None
        )

        schedules = _consolidate_slots(
            tuple(s) for s in group["slots"]
        )

        groups_out.append({
            "id":           gkey,
            "course": {
                "id":             group["course"]["id"],
                "name":           group["course"]["name"],
                "semester":       group["course"]["semester"],
                "hours":          group["course"]["hours"],
                "lab":            group["course"]["lab"],
                "specialization": group["course"]["specialization"],
            },
            "group_number": group["group_number"],
            "professor":    prof_info,
            "classroom":    cls_info,
            "schedules":    schedules,
        })

    return {
        "metadata": {
            "total_groups":          len(groups_out),
            "groups_with_professor": sum(1 for g in groups_out if g["professor"]),
            "groups_unassigned":     sum(1 for g in groups_out if not g["professor"]),
        },
        "groups": groups_out,
    }


def _banner(msg: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {msg}")
    print("─" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generador de instancias de horarios universitarios"
    )
    parser.add_argument(
        "--data",
        default="data",
        help="Carpeta con courses.json, classrooms.json y professors.json",
    )
    parser.add_argument(
        "--output",
        default="generated_instances",
        help="Carpeta de salida para las instancias generadas",
    )
    parser.add_argument(
        "--start-seed",
        type=int,
        default=42,
        help="La primera semilla para la generación.",
    )
    parser.add_argument(
        "--num-seeds",
        type=int,
        default=5,
        help="Número de instancias (semillas consecutivas) a generar a partir de la inicial.",
    )
    parser.add_argument(
        "--difficulty",
        choices=["A-", "A+", "both"],
        default="both",
        help="Variante de dificultad a generar",
    )

    args = parser.parse_args()
    seeds_to_generate = list(range(args.start_seed, args.start_seed + args.num_seeds))
    
    generate_instances(args.data, args.output, seeds_to_generate, args.difficulty)