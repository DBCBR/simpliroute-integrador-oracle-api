import json
import os
import sys
from collections import defaultdict

# allow importing project modules
HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from integrations.simpliroute import mapper


def load_sample(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def group_by_atendimento(items):
    groups = defaultdict(list)
    for r in items:
        key = r.get("ID_ATENDIMENTO") or r.get("id_atendimento")
        groups[key].append(r)
    return groups


def build_records(groups):
    records = []
    for aid, rows in groups.items():
        # pick address/name from first row
        first = rows[0] if rows else {}
        # populate keys expected by mapper: ID_ATENDIMENTO, ENDERECO, NOME_PACIENTE, DT_VISITA
        record = {
            "ID_ATENDIMENTO": aid,
            "ENDERECO": first.get("ENDERECO") or first.get("endereco") or "",
            "NOME_PACIENTE": first.get("NOME_PACIENTE") or first.get("nome") or "",
            "DT_VISITA": first.get("DT_VISITA") or first.get("dt_visita") or None,
            "items": rows,
        }
        records.append(record)
    return records


def main():
    sample_path = os.path.join(ROOT, "data", "input", "gnexum_sample.json")
    data = load_sample(sample_path)
    items = data.get("items") or data.get("rows") or []
    groups = group_by_atendimento(items)
    records = build_records(groups)

    out_dir = os.path.join(ROOT, "data", "output", "mapped_samples")
    os.makedirs(out_dir, exist_ok=True)

    for rec in records:
        payload = mapper.build_visit_payload(rec)
        aid = rec.get("ID_ATENDIMENTO") or rec.get("id") or "unknown"
        fname = f"visit-{aid}.json"
        out_path = os.path.join(out_dir, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
