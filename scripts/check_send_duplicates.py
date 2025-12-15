#!/usr/bin/env python3
"""
Analisa data/output/send_history.log e imprime referências enviadas mais de uma vez,
com contagem e timestamps.

Uso:
  .venv\Scripts\python.exe scripts\check_send_duplicates.py --top 50
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
import argparse

LOG = Path("data/output/send_history.log")

def load_entries(path: Path):
    if not path.exists():
        raise SystemExit(f"Arquivo não encontrado: {path}")
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                # ignore malformed lines
                continue


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=50, help="Máximo de referências a mostrar")
    args = p.parse_args()

    refs_counter = Counter()
    refs_times = defaultdict(list)

    for entry in load_entries(LOG):
        refs = entry.get("references") or []
        ts = entry.get("timestamp")
        if isinstance(refs, str):
            refs = [refs]
        for r in refs:
            refs_counter[r] += 1
            refs_times[r].append(ts)

    duplicates = [(r, refs_counter[r], refs_times[r]) for r in refs_counter if refs_counter[r] > 1]
    duplicates.sort(key=lambda x: x[1], reverse=True)

    if not duplicates:
        print("Nenhuma referência com envios múltiplos encontrada no log.")
        return

    print(f"Encontradas {len(duplicates)} referências com envios múltiplos (mostrando até {args.top}):\n")
    for r, count, times in duplicates[: args.top]:
        print(f"{r}: enviado {count} vezes")
        for t in times:
            print(f"  - {t}")
        print()

if __name__ == '__main__':
    main()
