"""Predeclared synthetic suite. Saved JSON, not RNG alone, identifies each input."""
import random

from capacity_planner.examples import load_example, with_outage
from capacity_planner.schema import Scenario

SUITE_VERSION = 1
SCALES = [(2, 2, 4), (4, 3, 8), (6, 4, 12), (8, 6, 20)]
PROFILES = [('balanced', 1729), ('disrupted', 2718)]


def generated_case(products: int, cells: int, shifts: int, profile: str, seed: int) -> Scenario:
    if profile not in {'balanced', 'disrupted'}:
        raise ValueError('Unknown generation profile')
    rng = random.Random(seed)
    ps = [f'P{i+1}' for i in range(products)]
    cs = [f'C{i+1}' for i in range(cells)]
    ts = [f'T{i+1}' for i in range(shifts)]
    crews = {c: rng.randint(1, 3) for c in cs}
    rates = []
    for p in ps:
        # Largest scale deliberately dense to exercise the schema/model ceiling.
        eligible = [c for c in cs if rng.random() < .65 or (products, cells, shifts) == (8, 6, 20)]
        if not eligible:
            eligible = [rng.choice(cs)]
        rates.extend({'product_id': p, 'cell_id': c, 'minutes_per_unit': rng.randint(3, 9)} for c in eligible)
    staffing = sum(crews.values()) if profile == 'balanced' else max(min(crews.values()), int(sum(crews.values()) * .6))
    capacity = []
    for i, t in enumerate(ts):
        for j, c in enumerate(cs):
            minutes = rng.randint(85, 120)
            if profile == 'disrupted' and ((i + j) % 5 == 2 or (j == cells - 1 and shifts // 3 <= i < 2 * shifts // 3)):
                minutes = 0
            capacity.append({'cell_id': c, 'shift_id': t, 'available_machine_minutes': minutes})
    demand_level = max(2, int(cells * 100 / (6 * products) * (.5 if profile == 'balanced' else .9)))
    demand = [{'product_id': p, 'shift_id': t, 'due_units': rng.randint(max(0, demand_level - 3), demand_level + 3)}
              for p in ps for t in ts]
    return Scenario.model_validate({
        'schema_version': 1, 'name': f'Synthetic {profile} {products}p-{cells}c-{shifts}t seed {seed}',
        'data_origin': 'synthetic',
        'products': [{'id': p, 'initial_inventory_units': rng.randint(0, 3)} for p in ps],
        'cells': [{'id': c, 'crew_operators': crews[c]} for c in cs],
        'processing_times': rates,
        'shifts': [{'id': t, 'index': i + 1, 'duration_minutes': 120,
                    'available_operators': staffing if profile == 'balanced' or i % 7 != 3 else max(0, staffing - 1)}
                   for i, t in enumerate(ts)],
        'capacity': capacity, 'demand': demand})


def cases():
    base = load_example('base')
    result = {'base': base, 'short_outage': with_outage(base, 'C3', 5, 6),
              'full_outage': with_outage(base, 'C3', 1, 10),
              'lookahead': load_example('lookahead'), 'tiny': load_example('tiny')}
    for p, c, t in SCALES:
        for profile, seed in PROFILES:
            name = f'{profile}-{p}p-{c}c-{t}t'
            result[name] = generated_case(p, c, t, profile, seed)
    return result


def model_size(s):
    """Exact counts for current model.py before presolve, including zero-UB x."""
    p, c, t, e = len(s.products), len(s.cells), len(s.shifts), len(s.processing_times)
    return {'products': p, 'cells': c, 'shifts': t, 'eligible_pairs': e,
            'variables': e*t + c*t + 3*p*t,
            'constraints': 2*c*t + e*t + t + p + 3*p*t}
