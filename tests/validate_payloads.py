import sys
import os
import json
from collections import Counter

sys.path.insert(0, os.getcwd())

# Usage: python tests/validate_payloads.py data/output/<file.json>

EXPECTED_KEYS = [
    "id",
    "order",
    "tracking_id",
    "status",
    "title",
    "address",
    "latitude",
    "longitude",
    "load",
    "load_2",
    "load_3",
    "window_start",
    "window_end",
    "window_start_2",
    "window_end_2",
    "duration",
    "contact_name",
    "contact_phone",
    "contact_email",
    "reference",
    "notes",
    "skills_required",
    "skills_optional",
    "tags",
    "planned_date",
    "programmed_date",
    "route",
    "route_estimated_time_start",
    "route_status",
    "estimated_time_arrival",
    "estimated_time_departure",
    "checkin_time",
    "checkout_time",
    "checkout_latitude",
    "checkout_longitude",
    "checkout_comment",
    "checkout_observation",
    "signature",
    "pictures",
    "created",
    "modified",
    "eta_predicted",
    "eta_current",
    "driver",
    "vehicle",
    "priority",
    "has_alert",
    "priority_level",
    "extra_field_values",
    "geocode_alert",
    "visit_type",
    "current_eta",
    "fleet",
    "on_its_way",
    "seller",
    "is_route_completed",
]

TYPE_HINTS = {
    "id": (int, type(None)),
    "order": (int, type(None)),
    "tracking_id": (str, int, type(None)),
    "status": (str, type(None)),
    "title": (str, type(None)),
    "address": (str, type(None)),
    "latitude": (str, float, type(None)),
    "longitude": (str, float, type(None)),
    "load": (int, float, type(None)),
    "load_2": (int, float, type(None)),
    "load_3": (int, float, type(None)),
    "window_start": (str, type(None)),
    "window_end": (str, type(None)),
    "duration": (str, type(None)),
    "contact_name": (str, type(None)),
    "contact_phone": (str, type(None)),
    "reference": (str, int, type(None)),
    "notes": (str, type(None)),
    "skills_required": (list, type(None)),
    "tags": (list, type(None)),
    "planned_date": (str, type(None)),
    "programmed_date": (str, type(None)),
    "route": (str, type(None)),
    "pictures": (list, type(None)),
    "created": (str, type(None)),
    "modified": (str, type(None)),
    "driver": (int, type(None)),
    "vehicle": (int, type(None)),
    "priority": (bool, type(None)),
    "priority_level": (int, float, type(None)),
    "extra_field_values": (dict, type(None)),
    "visit_type": (str, type(None)),
    "is_route_completed": (bool, type(None)),
}


def analyze_file(path):
    print('\nValidating', path)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        print('File does not contain a JSON array')
        return
    total = len(data)
    print('Objects:', total)
    # Keys seen across all objects
    keys = set()
    non_null_counts = Counter()
    type_issues = Counter()
    missing_keys = Counter()
    for obj in data:
        keys.update(obj.keys())
        for k in EXPECTED_KEYS:
            if k not in obj:
                missing_keys[k] += 1
            else:
                v = obj.get(k)
                if v not in (None, '', []):
                    non_null_counts[k] += 1
                # type check when value is not None
                if v is not None and k in TYPE_HINTS:
                    ok = isinstance(v, TYPE_HINTS[k])
                    # numeric strings sometimes present, allow str for numeric fields
                    if not ok:
                        type_issues[k] += 1
    print('\n-- Key presence summary --')
    present_keys = sorted(list(keys))
    print('Keys found in objects (sample):', ', '.join(present_keys[:40]))
    print('\n-- Expected keys missing entirely (count of objects missing key) --')
    for k in EXPECTED_KEYS:
        if missing_keys[k] == total:
            print(f' - {k}: MISSING in all objects')
    print('\n-- Non-null fill rates (expected keys) --')
    for k in EXPECTED_KEYS:
        cnt = non_null_counts.get(k, 0)
        pct = cnt / total * 100 if total else 0
        print(f' - {k}: {cnt}/{total} ({pct:.1f}%)')
    if type_issues:
        print('\n-- Type issues (count of objects with unexpected type for non-null values) --')
        for k, c in type_issues.items():
            print(f' - {k}: {c} objects')
    # quick sample of first object full keys/values
    if data:
        print('\n-- First object (pretty) --')
        print(json.dumps(data[0], ensure_ascii=False, indent=2)[:2000])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python tests/validate_payloads.py <json-file> [<json-file> ...]')
        sys.exit(1)
    for p in sys.argv[1:]:
        if os.path.isdir(p):
            for fname in os.listdir(p):
                if fname.endswith('.json'):
                    analyze_file(os.path.join(p, fname))
        else:
            analyze_file(p)
