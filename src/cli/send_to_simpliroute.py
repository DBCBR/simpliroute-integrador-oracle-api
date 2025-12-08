import argparse
import asyncio
import json
import os
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import httpx

from src.core.config import load_config
from src.integrations.simpliroute.client import post_simpliroute
from src.integrations.simpliroute.mapper import build_visit_payload
from src.integrations.simpliroute.oracle_source import fetch_grouped_records, fetch_view_rows

CONFIG_CACHE: Dict[str, Any] = {}
LOG_PATH = Path("data/output/send_history.log")


def _load_cached_config() -> Dict[str, Any]:
    global CONFIG_CACHE
    if CONFIG_CACHE:
        return CONFIG_CACHE
    try:
        CONFIG_CACHE = load_config()
    except Exception:
        CONFIG_CACHE = {}
    return CONFIG_CACHE


def _default_limit() -> int:
    try:
        return int(os.getenv("ORACLE_FETCH_LIMIT", "25"))
    except ValueError:
        return 25


def _env_default_views() -> List[str]:
    """Retorna views padrão definidas por variáveis de ambiente."""
    views: List[str] = []

    raw = os.getenv("ORACLE_VIEWS") or os.getenv("ORACLE_VIEW_LIST")
    if raw:
        for token in raw.replace(",", " ").replace(";", " ").split():
            token = token.strip()
            if token and token not in views:
                views.append(token)

    for key in (
        "ORACLE_VIEW_VISITAS",
        "ORACLE_VIEW_ENTREGAS",
        "ORACLE_VIEW_VISITA",
        "ORACLE_VIEW_ENTREGA",
    ):
        value = os.getenv(key)
        if value:
            v = value.strip()
            if v and v not in views:
                views.append(v)

    return views


def _simpliroute_base_url() -> str:
    cfg = _load_cached_config().get("integrations", {}) if _load_cached_config() else {}
    return (
        os.getenv("SIMPLIROUTE_API_BASE")
        or os.getenv("SIMPLIR_ROUTE_BASE_URL")
        or os.getenv("SIMPLIROUTE_API_BASE_URL")
        or cfg.get("simpliroute_api_base")
        or "https://api.simpliroute.com"
    )


def _simpliroute_token() -> str:
    return (
        os.getenv("SIMPLIROUTE_TOKEN")
        or os.getenv("SIMPLIR_ROUTE_TOKEN")
        or os.getenv("SIMPLIROUTE_API_TOKEN")
        or ""
    )


def _collect_records(
    use_db: bool,
    file_path: Path | None,
    limit: int,
    where: str | None,
    view_names: Sequence[str] | None,
) -> List[Dict[str, Any]]:
    if use_db:
        targets = list(view_names or []) or [None]
        rows: List[Dict[str, Any]] = []
        for target_view in targets:
            rows.extend(fetch_grouped_records(limit=limit, where_clause=where, view_name=target_view))
        return rows
    if file_path:
        if not file_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "records" in data and isinstance(data["records"], list):
                return data["records"]
            if "data" in data and isinstance(data["data"], list):
                return data["data"]
            return [data]
        raise ValueError("Formato de arquivo inválido: esperado dict ou list")
    raise ValueError("Informe um arquivo via --file para usar dados locais")


def _save_payload(payloads: Sequence[Dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    target = output_dir / f"send_to_sr_{timestamp}.json"
    with open(target, "w", encoding="utf-8") as fp:
        json.dump(payloads, fp, ensure_ascii=False, indent=2)
    return target


def _print_summary(payloads: Sequence[Dict[str, Any]]) -> None:
    total = len(payloads)
    deliveries = sum(1 for p in payloads if p.get("visit_type") == "rota")
    print(f"Payloads gerados: {total} (entregas: {deliveries}, visitas: {total - deliveries})")
    if payloads:
        sample = payloads[0]
        reference = sample.get("reference") or sample.get("tracking_id")
        print(f"Exemplo: title='{sample.get('title')}', reference='{reference}'")


def _append_send_log(entry: Dict[str, Any]) -> None:
    iso_timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    log_entry = {
        "timestamp": iso_timestamp,
        **entry,
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fp:
        json.dump(log_entry, fp, ensure_ascii=False)
        fp.write("\n")


def _extract_response_ids(response: httpx.Response) -> List[str]:
    ids: List[str] = []
    try:
        payload = response.json()
    except ValueError:
        return ids

    def _collect(obj: Any) -> None:
        if isinstance(obj, dict):
            maybe_id = obj.get("id")
            if maybe_id is not None:
                ids.append(str(maybe_id))
            for key in ("items", "visits", "data"):
                value = obj.get(key)
                if isinstance(value, list):
                    for entry in value:
                        _collect(entry)
        elif isinstance(obj, list):
            for entry in obj:
                _collect(entry)

    _collect(payload)
    return ids


def _run_send_flow(args: argparse.Namespace) -> int:
    where = args.where or os.getenv("ORACLE_POLL_WHERE")
    if args.file and (args.view or args.views):
        print("As opções --view/--views não podem ser usadas junto com --file.")
        return 1
    if args.file and args.from_db:
        print("Use --file ou --from-db (padrão) — não ambos.")
        return 1
    use_db = args.from_db or not args.file
    resolved_views: Sequence[str] | None = args.views or ([args.view] if args.view else None)
    if not resolved_views:
        env_views = _env_default_views()
        if env_views:
            resolved_views = env_views
    log_context = {
        "views": list(resolved_views or []),
        "limit": args.limit,
        "where": where,
    }
    try:
        records = _collect_records(
            use_db,
            args.file,
            args.limit,
            where,
            resolved_views,
        )
    except Exception as exc:
        print(f"Erro ao obter registros: {exc}")
        if getattr(args, "send_payloads", False):
            _append_send_log(
                {
                    "status": "failure",
                    "stage": "collect_records",
                    "message": str(exc),
                    **log_context,
                }
            )
        return 1

    if not records:
        print("Nenhum registro retornado pela origem.")
        if getattr(args, "send_payloads", False):
            _append_send_log(
                {
                    "status": "failure",
                    "stage": "collect_records",
                    "message": "Nenhum registro retornado",
                    **log_context,
                }
            )
        return 0

    payloads = [build_visit_payload(record) for record in records]
    _print_summary(payloads)

    if getattr(args, "send_payloads", False):
        response = asyncio.run(post_simpliroute(payloads))
        if response is None:
            print("Falha ao enviar payloads ao SimpliRoute.")
            _append_send_log(
                {
                    "status": "failure",
                    "stage": "http_request",
                    "message": "Resposta vazia do cliente HTTP",
                    **log_context,
                    "payload_count": len(payloads),
                    "references": [p.get("reference") for p in payloads],
                }
            )
            return 1
        print(f"Resposta SimpliRoute: HTTP {response.status_code}")
        body_text = response.text if hasattr(response, "text") else ""
        if body_text:
            print(body_text)
        response_ids = _extract_response_ids(response)
        log_entry = {
            "status": "success" if 200 <= response.status_code < 400 else "failure",
            "stage": "http_request",
            "http_status": response.status_code,
            "response_ids": response_ids,
            "payload_count": len(payloads),
            "references": [p.get("reference") for p in payloads],
            **log_context,
        }
        if body_text:
            log_entry["response_body"] = body_text[:1000]
        _append_send_log(log_entry)
        if response_ids:
            print(f"IDs retornados: {', '.join(response_ids)}")
        return 0 if 200 <= response.status_code < 400 else 2

    if args.no_save:
        print(json.dumps(payloads, ensure_ascii=False, indent=2))
        return 0

    target = _save_payload(payloads, args.output_dir)
    print(f"Payload salvo em: {target}")
    return 0


def _run_preview_flow(args: argparse.Namespace) -> int:
    args.send_payloads = False
    return _run_send_flow(args)


def _cmd_auto(args: argparse.Namespace) -> int:
    raw = args.command_override or os.getenv("SIMPLIROUTE_AUTO_COMMAND") or "send --send"
    auto_args = shlex.split(raw)
    if not auto_args:
        print("Nenhum comando configurado para o modo automático.")
        return 1
    if auto_args[0] == "auto":
        print("O modo automático não pode invocar o subcomando 'auto'.")
        return 1
    print(f"[auto] Executando CLI com: {' '.join(auto_args)}")
    return main(auto_args)


def _cmd_diagnose_sr(args: argparse.Namespace) -> int:
    base = _simpliroute_base_url()
    token = _simpliroute_token()
    print(f"Base SimpliRoute: {base}")
    print(f"Token configurado: {'sim' if token else 'não'}")
    if not args.ping:
        return 0
    url = f"{base.rstrip('/')}/health"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Token {token}"
    try:
        async def _ping() -> httpx.Response:
            async with httpx.AsyncClient(timeout=15.0) as client:
                return await client.get(url, headers=headers)

        resp = asyncio.run(_ping())
        print(f"Ping {url} -> HTTP {resp.status_code}")
        if resp.content:
            print(resp.text)
        return 0 if resp.status_code == 200 else 2
    except httpx.RequestError as exc:
        print(f"Falha ao pingar SimpliRoute: {exc}")
        return 1


def _cmd_diagnose_db(args: argparse.Namespace) -> int:
    where = args.where or os.getenv("ORACLE_POLL_WHERE")
    try:
        rows = fetch_view_rows(limit=args.limit, where_clause=where, view_name=args.view)
    except Exception as exc:
        print(f"Erro ao consultar Oracle: {exc}")
        return 1
    total = len(rows)
    print(f"Linhas retornadas: {total}")
    if rows:
        sample = rows[0]
        print(f"Campos do primeiro registro ({len(sample)} colunas):")
        for key in list(sample.keys())[:10]:
            print(f"  - {key}: {sample[key]}")
        if len(sample) > 10:
            print("  ...")
    return 0


def _cmd_get_visit(args: argparse.Namespace) -> int:
    base = _simpliroute_base_url()
    token = _simpliroute_token()
    if not token:
        print("Token SimpliRoute não configurado.")
        return 1
    url = f"{base.rstrip('/')}/v1/routes/visits/{args.visit_id}/"
    headers = {"Authorization": f"Token {token}", "Accept": "application/json"}

    async def _fetch() -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.get(url, headers=headers)

    try:
        resp = asyncio.run(_fetch())
    except httpx.RequestError as exc:
        print(f"Erro ao consultar visita {args.visit_id}: {exc}")
        return 1

    print(f"GET {url} -> HTTP {resp.status_code}")
    if resp.content:
        try:
            parsed = resp.json()
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        except ValueError:
            print(resp.text)
    return 0 if 200 <= resp.status_code < 400 else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI oficial Integrador SR → SimpliRoute")
    subparsers = parser.add_subparsers(dest="command")

    common_send_args = {
        "--from-db": {
            "action": "store_true",
            "help": "Força leitura direta das views Oracle (padrão quando --file não é usado)",
        },
        "--file": {
            "type": Path,
            "help": "Arquivo JSON contendo registros no formato da view (desativa leitura do Oracle)",
        },
        "--limit": {
            "type": int,
            "default": _default_limit(),
            "help": "Limite de registros ao consultar as views Oracle",
        },
        "--where": {
            "type": str,
            "help": "Cláusula WHERE adicional aplicada à consulta Oracle",
        },
        "--view": {
            "type": str,
            "help": "Nome da view Oracle usada no lugar de ORACLE_VIEW (somente com Oracle)",
        },
        "--views": {
            "nargs": "+",
            "help": "Lista de views Oracle consultadas em sequência (ex.: entregas e visitas)",
        },
        "--output-dir": {
            "type": Path,
            "default": Path("data/output"),
            "help": "Diretório para salvar payloads gerados",
        },
        "--no-save": {
            "action": "store_true",
            "help": "Não gravar arquivo no modo dry-run (imprime no stdout)",
        },
    }

    send_parser = subparsers.add_parser("send", help="Gera payloads e (opcionalmente) envia ao SimpliRoute")
    for flag, opts in common_send_args.items():
        send_parser.add_argument(flag, **opts)
    send_parser.add_argument(
        "--send",
        dest="send_payloads",
        action="store_true",
        help="Quando presente, envia os payloads gerados ao SimpliRoute",
    )
    send_parser.set_defaults(func=_run_send_flow)

    preview_parser = subparsers.add_parser("preview", help="Somente gera payloads e exibe/salva o JSON")
    for flag, opts in common_send_args.items():
        preview_parser.add_argument(flag, **opts)
    preview_parser.set_defaults(func=_run_preview_flow)

    diag_sr = subparsers.add_parser("diagnose-sr", help="Mostra configuração do endpoint SimpliRoute")
    diag_sr.add_argument("--ping", action="store_true", help="Executa um GET /health na base configurada")
    diag_sr.set_defaults(func=_cmd_diagnose_sr)

    diag_db = subparsers.add_parser("diagnose-db", help="Executa uma consulta simples à view Oracle")
    diag_db.add_argument("--limit", type=int, default=5, help="Quantidade de linhas para amostragem")
    diag_db.add_argument("--where", type=str, help="Cláusula WHERE adicional")
    diag_db.add_argument("--view", type=str, help="Nome da view Oracle (padrão=ORACLE_VIEW)")
    diag_db.set_defaults(func=_cmd_diagnose_db)

    get_visit = subparsers.add_parser("get-visit", help="Consulta uma visita existente no SimpliRoute")
    get_visit.add_argument("visit_id", help="ID da visita no SimpliRoute")
    get_visit.set_defaults(func=_cmd_get_visit)

    auto_parser = subparsers.add_parser(
        "auto",
        help="Executa o comando padrão ou o definido via SIMPLIROUTE_AUTO_COMMAND",
    )
    auto_parser.add_argument(
        "--command",
        dest="command_override",
        help="Comando a ser executado automaticamente (padrão='send --send')",
    )
    auto_parser.set_defaults(func=_cmd_auto)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _load_cached_config()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    func = getattr(args, "func", None)
    if not func:
        parser.print_help()
        return 1
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())
