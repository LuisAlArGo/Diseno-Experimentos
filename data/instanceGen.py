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
END_HOUR   = 21   # bloques son [h, h+1); el inicio máximo válido es 20.

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
        result = _try_place(course, classrooms_data, classroom_used, forbidden_slots, rng)
        
        if result is None:
            print(f"Fallback para {course['id']}-G{gnum} - omitiendo reglas de currículo")
            result = _try_place(
                course, classrooms_data, classroom_used, set(), rng, max_attempts=2_000
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
                slots.append((day, start_h + offset))
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
                start1 = start2 = start_h
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
                
        # Validar colisiones
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

    # PASO 1: Garantizar al menos 1 grupo por profesor
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

    # PASO 2: Distribuir los grupos restantes
    for gkey in unassigned_groups:
        group = skeleton[gkey]
        g_slots = set(map(tuple, group["slots"]))

        rng.shuffle(candidates)
        assigned = False

        def assign_prof(p_id: str):
            g2p[gkey] = p_id
            prof_slots[p_id] |= g_slots
            prof_counts[p_id] += 1

        # Intento A: Asignar respetando el límite máximo de clases por profe
        for p in candidates:
            pid = p["id"]
            if prof_counts[pid] < max_classes_per_prof and not (g_slots & prof_slots[pid]):
                assign_prof(pid)
                assigned = True
                break

        # Intento B (Fallback): Ignorar límite de carga máxima
        if not assigned:
            for p in candidates:
                pid = p["id"]
                if not (g_slots & prof_slots[pid]):
                    assign_prof(pid)
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
    
    prof_assigned_groups: Dict[str, List[dict]] = defaultdict(list)
    prof_assigned_courses: Dict[str, Set[str]]  = defaultdict(set)

    for gkey, pid in g2p.items():
        if pid is None: continue
        group = skeleton[gkey]
        prof_assigned_courses[pid].add(group["course"]["id"])
        prof_assigned_groups[pid].append(group)

    all_course_ids = [c["id"] for c in courses_data]
    result = []
    for p in prof_subset:
        pid = p["id"]
        assigned_groups  = prof_assigned_groups.get(pid, [])
        assigned_count   = len(assigned_groups)
        assigned_courses = prof_assigned_courses.get(pid, set())

        extra_groups = rng.choice([2, 3]) if difficulty == "A+" else 1
        max_groups = assigned_count + extra_groups

        # Generar horarios en base a la proporción
        avail_ranges, pref_ranges = _generate_proportional_availability(
            assigned_groups, extra_groups, rng
        )

        # Ajuste de preferencias de horario según la dificultad
        if difficulty == "A+":
            # A+: Prefiere todos los horarios en los que está disponible (incluyendo los extra)
            pref_ranges = list(avail_ranges)

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
    assigned_groups: List[dict],
    extra_groups: int,
    rng: random.Random
) -> Tuple[List[dict], List[dict]]:
    
    base_slots = set()
    group_extents = []

    for g in assigned_groups:
        g_slots = g["slots"]
        base_slots.update(g_slots)

        day_hours = defaultdict(list)
        for d, h in g_slots:
            day_hours[d].append(h)

        if len(day_hours) == 2:
            extent = {}
            for d, hs in day_hours.items():
                extent[d] = {"min": min(hs), "max": max(hs)}
            group_extents.append(extent)

    available_slots = set(base_slots)
    work_days = {d for d, h in base_slots}

    def get_free_blocks(day: str, size: int) -> List[int]:
        blocks = []
        for start_h in range(START_HOUR, END_HOUR - size + 1):
            valid = True
            for offset in range(size):
                if (day, start_h + offset) in available_slots:
                    valid = False
                    break
            if valid:
                blocks.append(start_h)
        return blocks

    for _ in range(extra_groups):
        hours_to_add = 6
        
        rng.shuffle(group_extents)
        extended = False
        
        for extent in group_extents:
            d1, d2 = list(extent.keys())

            before_slots = [(d, h) for d in [d1, d2] for h in range(extent[d]["min"] - 3, extent[d]["min"])]
            after_slots  = [(d, h) for d in [d1, d2] for h in range(extent[d]["max"] + 1, extent[d]["max"] + 4)]

            valid_before = all(START_HOUR <= h < END_HOUR and (d, h) not in available_slots for d, h in before_slots) if before_slots else False
            valid_after  = all(START_HOUR <= h < END_HOUR and (d, h) not in available_slots for d, h in after_slots) if after_slots else False

            options = []
            if valid_before: options.append(before_slots)
            if valid_after: options.append(after_slots)

            if options:
                chosen = rng.choice(options)
                available_slots.update(chosen)
                hours_to_add -= 6
                
                for d, h in chosen:
                    extent[d]["min"] = min(extent[d]["min"], h)
                    extent[d]["max"] = max(extent[d]["max"], h)
                
                extended = True
                break

        if extended: continue

        all_pairs = []
        for day1, paired_days in DAY_PAIRS.items():
            for day2 in paired_days:
                if (day1, day2) not in all_pairs and (day2, day1) not in all_pairs:
                    all_pairs.append((day1, day2))

        rng.shuffle(all_pairs)
        all_pairs.sort(key=lambda p: (p[0] in work_days) + (p[1] in work_days), reverse=True)

        placed_pair = False
        for d1, d2 in all_pairs:
            blocks1 = get_free_blocks(d1, 3)
            blocks2 = get_free_blocks(d2, 3)

            if blocks1 and blocks2:
                st1 = rng.choice(blocks1)
                st2 = rng.choice(blocks2)
                slots_to_add = [(d1, st1 + i) for i in range(3)] + [(d2, st2 + i) for i in range(3)]
                available_slots.update(slots_to_add)
                hours_to_add -= 6
                work_days.update([d1, d2])
                placed_pair = True
                break
                
        if placed_pair: continue

        for size in [3, 2, 1]:
            if hours_to_add == 0: break
                
            while hours_to_add >= size:
                possible_placements = [(d, b) for d in ALL_DAYS for b in get_free_blocks(d, size)]
                if not possible_placements:
                    break

                d, st = rng.choice(possible_placements)
                for i in range(size):
                    available_slots.add((d, st + i))
                
                hours_to_add -= size
                work_days.add(d)

        if hours_to_add > 0:
            print(f"  [Advertencia] No se pudieron ubicar {hours_to_add} horas extra para un profesor. Horario saturado.")

    pref_ranges = _group_consecutive_hours(base_slots, "start_time", "end_time")
    avail_ranges = _group_consecutive_hours(available_slots, "start_time", "end_time")

    return avail_ranges, pref_ranges


def _group_consecutive_hours(
    slots: Set[Tuple[str, int]], 
    start_key: str, 
    end_key: str
) -> List[dict]:
    """Agrupa tuplas de horas individuales en rangos continuos según los parámetros de dict pasados."""
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
                result.append({"day": day, start_key: start, end_key: prev + 1})
                start = prev = h
        result.append({"day": day, start_key: start, end_key: prev + 1})
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

        schedules = _group_consecutive_hours(
            [tuple(s) for s in group["slots"]], "start_hour", "end_hour"
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