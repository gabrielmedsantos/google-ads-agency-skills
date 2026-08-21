"""Servidor MCP do workspace de Google Ads.

Expoe tools de leitura (sempre livres) e de mutation (gated por aprovacao
explicita — regra 1 do CLAUDE.md raiz) sobre a Google Ads API, usando as
credenciais do `.env`.

Rodar standalone (smoke test, sem client MCP):
    cd "google ads"
    python mcp/server.py

Registrar no Claude Code: ver `.mcp.json` na raiz deste workspace.
"""

from __future__ import annotations

import hashlib
import json as _json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from mcp.server.mcpserver import MCPServer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

server = MCPServer(
    name="google-ads",
    title="Google Ads (agência)",
    instructions=(
        "Tools de leitura (list_accounts, get_campaign_metrics, get_search_terms, "
        "get_budget_pacing) sempre podem ser chamadas direto. Tools de mutation "
        "(add_negative_keyword, update_campaign_budget, set_campaign_status) exigem "
        "uma segunda chamada com o parametro approval igual à frase de confirmação "
        "retornada no preview da primeira chamada — nunca aplicar sem esse passo."
    ),
)

_client: GoogleAdsClient | None = None


def _read_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        raise RuntimeError(f"{ENV_PATH} não existe.")
    env: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _get_client() -> GoogleAdsClient:
    global _client
    if _client is None:
        env = _read_env()
        required = [
            "GOOGLE_ADS_DEVELOPER_TOKEN",
            "GOOGLE_ADS_CLIENT_ID",
            "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN",
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        ]
        missing = [k for k in required if not env.get(k) or "PENDENTE" in env.get(k, "")]
        if missing:
            raise RuntimeError(f"Faltando no .env: {', '.join(missing)}")
        config = {
            "developer_token": env["GOOGLE_ADS_DEVELOPER_TOKEN"],
            "client_id": env["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": env["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": env["GOOGLE_ADS_REFRESH_TOKEN"],
            "login_customer_id": env["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
            "use_proto_plus": True,
        }
        _client = GoogleAdsClient.load_from_dict(config)
    return _client


def _date_range(days: int) -> tuple[str, str]:
    end = date.today() - timedelta(days=1)  # ontem — hoje costuma vir incompleto
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _previous_range(days: int) -> tuple[str, str]:
    cur_start, _ = _date_range(days)
    prev_end = date.fromisoformat(cur_start) - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return prev_start.isoformat(), prev_end.isoformat()


def _run_gaql(customer_id: str, query: str) -> list[dict[str, Any]]:
    client = _get_client()
    ga_service = client.get_service("GoogleAdsService")
    rows: list[dict[str, Any]] = []
    try:
        stream = ga_service.search_stream(customer_id=customer_id.replace("-", ""), query=query)
        for batch in stream:
            for row in batch.results:
                rows.append(_row_to_dict(row))
    except GoogleAdsException as ex:
        raise RuntimeError(
            "; ".join(f"{e.error_code}: {e.message}" for e in ex.failure.errors)
        ) from ex
    return rows


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Achata um GoogleAdsRow proto-plus nos campos que a gente realmente pediu."""
    import proto

    return proto.Message.to_dict(row)


_CAMPAIGN_STATUS_NAMES = {0: "UNSPECIFIED", 1: "UNKNOWN", 2: "ENABLED", 3: "PAUSED", 4: "REMOVED"}


def client_enum_name(enum_type_name: str, value: Any) -> str | None:
    """Reverse lookup genérico pra qualquer enum do SDK: client.enums.<Nome>(int).name."""
    if value is None:
        return None
    client = _get_client()
    try:
        return getattr(client.enums, enum_type_name)(int(value)).name
    except (ValueError, TypeError):
        return str(value)


def _micros_to_currency(micros: Any) -> float:
    """google-ads-python serializa campos int64 (cost_micros, impressions, clicks) como
    string via proto.Message.to_dict — sem o int() aqui, a divisão quebra com TypeError."""
    return round(int(micros or 0) / 1_000_000, 2)


def _to_int(value: Any) -> int:
    return int(value or 0)


def _to_float(value: Any) -> float:
    return float(value or 0)


# --------------------------------------------------------------------------
# READ tools — sempre livres, sem aprovação
# --------------------------------------------------------------------------


@server.tool()
def list_accounts() -> list[dict[str, str]]:
    """Lista as contas Google Ads acessíveis com as credenciais atuais (inclui a MCC)."""
    client = _get_client()
    customer_service = client.get_service("CustomerService")
    response = customer_service.list_accessible_customers()
    return [{"customer_id": rn.split("/")[-1], "resource_name": rn} for rn in response.resource_names]


@server.tool()
def get_campaign_metrics(customer_id: str, days: int = 7, compare_previous: bool = True) -> dict[str, Any]:
    """Métricas por campanha no período (spend, impressões, clicks, conversões, CPA, impression share).

    Se compare_previous=True, também traz o período anterior de mesma duração pra comparação
    (mesma lógica da skill weekly-review / investigate-campaign).
    """
    start, end = _date_range(days)
    query = f"""
        SELECT
          campaign.id, campaign.name, campaign.status,
          metrics.cost_micros, metrics.impressions, metrics.clicks,
          metrics.conversions, metrics.conversions_value,
          metrics.ctr, metrics.average_cpc,
          metrics.search_impression_share,
          metrics.search_budget_lost_impression_share,
          metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        ORDER BY metrics.cost_micros DESC
    """
    current = _aggregate_by_campaign(_run_gaql(customer_id, query))

    result: dict[str, Any] = {"period": {"start": start, "end": end}, "campaigns": current}

    if compare_previous:
        prev_start, prev_end = _previous_range(days)
        prev_query = query.replace(f"'{start}' AND '{end}'", f"'{prev_start}' AND '{prev_end}'")
        previous = _aggregate_by_campaign(_run_gaql(customer_id, prev_query))
        result["previous_period"] = {"start": prev_start, "end": prev_end}
        result["campaigns_previous"] = previous

    return result


def _aggregate_by_campaign(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        c = r.get("campaign", {})
        m = r.get("metrics", {})
        cid = str(c.get("id"))
        agg = by_id.setdefault(
            cid,
            {
                "campaign_id": cid,
                "campaign_name": c.get("name"),
                "status": _CAMPAIGN_STATUS_NAMES.get(_to_int(c.get("status")), c.get("status")),
                "cost": 0.0,
                "impressions": 0,
                "clicks": 0,
                "conversions": 0.0,
                "conversions_value": 0.0,
                "impression_share_samples": [],
                "lost_is_budget_samples": [],
                "lost_is_rank_samples": [],
            },
        )
        agg["cost"] += _micros_to_currency(m.get("cost_micros"))
        agg["impressions"] += _to_int(m.get("impressions"))
        agg["clicks"] += _to_int(m.get("clicks"))
        agg["conversions"] += _to_float(m.get("conversions"))
        agg["conversions_value"] += _to_float(m.get("conversions_value"))
        if m.get("search_impression_share") is not None:
            agg["impression_share_samples"].append(m["search_impression_share"])
        if m.get("search_budget_lost_impression_share") is not None:
            agg["lost_is_budget_samples"].append(m["search_budget_lost_impression_share"])
        if m.get("search_rank_lost_impression_share") is not None:
            agg["lost_is_rank_samples"].append(m["search_rank_lost_impression_share"])

    out = []
    for agg in by_id.values():
        n_is = len(agg.pop("impression_share_samples")) or 1
        lost_budget = agg.pop("lost_is_budget_samples")
        lost_rank = agg.pop("lost_is_rank_samples")
        agg["cpa"] = round(agg["cost"] / agg["conversions"], 2) if agg["conversions"] else None
        agg["avg_lost_is_budget_pct"] = round(sum(lost_budget) / len(lost_budget) * 100, 1) if lost_budget else None
        agg["avg_lost_is_rank_pct"] = round(sum(lost_rank) / len(lost_rank) * 100, 1) if lost_rank else None
        out.append(agg)
    return sorted(out, key=lambda x: x["cost"], reverse=True)


@server.tool()
def get_search_terms(
    customer_id: str,
    days: int = 30,
    status_filter: Literal["NONE", "ADDED", "EXCLUDED", "ADDED_EXCLUDED", "ALL"] = "NONE",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Search terms ordenadas por custo desc — input pra skill mine-search-terms.

    status_filter='NONE' (default) traz só termos ainda não acionados (nem keyword, nem
    negativa) — é o filtro que a regra global do CLAUDE.md exige antes de minerar.
    """
    start, end = _date_range(days)
    status_clause = "" if status_filter == "ALL" else f"AND search_term_view.status = '{status_filter}'"
    query = f"""
        SELECT
          campaign.name, ad_group.name,
          search_term_view.search_term, search_term_view.status,
          segments.keyword.info.text, segments.keyword.info.match_type,
          metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        {status_clause}
        ORDER BY metrics.cost_micros DESC
        LIMIT {limit}
    """
    rows = _run_gaql(customer_id, query)
    out = []
    for r in rows:
        m = r.get("metrics", {})
        out.append(
            {
                "campaign": r.get("campaign", {}).get("name"),
                "ad_group": r.get("ad_group", {}).get("name"),
                "search_term": r.get("search_term_view", {}).get("search_term"),
                "status": r.get("search_term_view", {}).get("status"),
                "matched_keyword": r.get("segments", {}).get("keyword", {}).get("info", {}).get("text"),
                "matched_keyword_match_type": r.get("segments", {}).get("keyword", {}).get("info", {}).get("match_type"),
                "cost": _micros_to_currency(m.get("cost_micros")),
                "clicks": _to_int(m.get("clicks")),
                "impressions": _to_int(m.get("impressions")),
                "conversions": _to_float(m.get("conversions")),
            }
        )
    return out


@server.tool()
def get_budget_pacing(customer_id: str, days: int = 7) -> list[dict[str, Any]]:
    """Série diária de impression share / lost-to-budget / lost-to-rank por campanha — input pra skill budget-optimize."""
    start, end = _date_range(days)
    query = f"""
        SELECT
          campaign.id, campaign.name, campaign_budget.amount_micros,
          segments.date,
          metrics.cost_micros,
          metrics.search_impression_share,
          metrics.search_budget_lost_impression_share,
          metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        ORDER BY campaign.id, segments.date
    """
    rows = _run_gaql(customer_id, query)
    out = []
    for r in rows:
        c = r.get("campaign", {})
        b = r.get("campaign_budget", {})
        m = r.get("metrics", {})
        out.append(
            {
                "campaign_id": str(c.get("id")),
                "campaign_name": c.get("name"),
                "date": r.get("segments", {}).get("date"),
                "daily_budget": _micros_to_currency(b.get("amount_micros")),
                "cost": _micros_to_currency(m.get("cost_micros")),
                "impression_share_pct": round(m["search_impression_share"] * 100, 1) if m.get("search_impression_share") is not None else None,
                "lost_is_budget_pct": round(m["search_budget_lost_impression_share"] * 100, 1) if m.get("search_budget_lost_impression_share") is not None else None,
                "lost_is_rank_pct": round(m["search_rank_lost_impression_share"] * 100, 1) if m.get("search_rank_lost_impression_share") is not None else None,
            }
        )
    return out


@server.tool()
def list_ad_groups(customer_id: str, campaign_id: str | None = None, days: int = 7) -> list[dict[str, Any]]:
    """Ad groups com métricas agregadas do período — pra ver o que existe antes de pausar/editar,
    ou pra achar o ad_group_id certo pra usar em outras tools."""
    start, end = _date_range(days)
    where_campaign = f"AND campaign.id = {campaign_id} " if campaign_id else ""
    query = f"""
        SELECT
          ad_group.id, ad_group.name, ad_group.status, ad_group.type,
          campaign.id, campaign.name,
          metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions
        FROM ad_group
        WHERE segments.date BETWEEN '{start}' AND '{end}' {where_campaign}
        ORDER BY metrics.cost_micros DESC
    """
    rows = _run_gaql(customer_id, query)
    by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        ag, c, m = r.get("ad_group", {}), r.get("campaign", {}), r.get("metrics", {})
        agg = by_id.setdefault(
            str(ag.get("id")),
            {
                "ad_group_id": str(ag.get("id")),
                "ad_group_name": ag.get("name"),
                "status": client_enum_name("AdGroupStatusEnum", ag.get("status")),
                "campaign_id": str(c.get("id")),
                "campaign_name": c.get("name"),
                "cost": 0.0,
                "impressions": 0,
                "clicks": 0,
                "conversions": 0.0,
            },
        )
        agg["cost"] += _micros_to_currency(m.get("cost_micros"))
        agg["impressions"] += _to_int(m.get("impressions"))
        agg["clicks"] += _to_int(m.get("clicks"))
        agg["conversions"] += _to_float(m.get("conversions"))
    return sorted(by_id.values(), key=lambda x: x["cost"], reverse=True)


@server.tool()
def list_keywords(
    customer_id: str, ad_group_id: str | None = None, campaign_id: str | None = None, days: int = 30
) -> list[dict[str, Any]]:
    """Keywords (positivas) com métricas, quality score e status — inclui o `criterion_id` que
    as tools update_keyword/remove_keyword/set_keyword_status precisam."""
    start, end = _date_range(days)
    where_extra = ""
    if ad_group_id:
        where_extra += f" AND ad_group.id = {ad_group_id}"
    if campaign_id:
        where_extra += f" AND campaign.id = {campaign_id}"
    query = f"""
        SELECT
          ad_group_criterion.criterion_id, ad_group_criterion.keyword.text,
          ad_group_criterion.keyword.match_type, ad_group_criterion.status,
          ad_group_criterion.quality_info.quality_score,
          ad_group.id, ad_group.name, campaign.id, campaign.name,
          metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions
        FROM keyword_view
        WHERE segments.date BETWEEN '{start}' AND '{end}' {where_extra}
        ORDER BY metrics.cost_micros DESC
    """
    rows = _run_gaql(customer_id, query)
    by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        crit, ag, c, m = r.get("ad_group_criterion", {}), r.get("ad_group", {}), r.get("campaign", {}), r.get("metrics", {})
        cid = str(crit.get("criterion_id"))
        agg = by_id.setdefault(
            f"{ag.get('id')}:{cid}",
            {
                "criterion_id": cid,
                "ad_group_id": str(ag.get("id")),
                "ad_group_name": ag.get("name"),
                "campaign_id": str(c.get("id")),
                "campaign_name": c.get("name"),
                "text": crit.get("keyword", {}).get("text"),
                "match_type": client_enum_name("KeywordMatchTypeEnum", crit.get("keyword", {}).get("match_type")),
                "status": client_enum_name("AdGroupCriterionStatusEnum", crit.get("status")),
                "quality_score": crit.get("quality_info", {}).get("quality_score"),
                "cost": 0.0,
                "impressions": 0,
                "clicks": 0,
                "conversions": 0.0,
            },
        )
        agg["cost"] += _micros_to_currency(m.get("cost_micros"))
        agg["impressions"] += _to_int(m.get("impressions"))
        agg["clicks"] += _to_int(m.get("clicks"))
        agg["conversions"] += _to_float(m.get("conversions"))
    return sorted(by_id.values(), key=lambda x: x["cost"], reverse=True)


@server.tool()
def run_gaql(customer_id: str, query: str) -> Any:
    """GAQL arbitrária, escape hatch pra quando os tools prontos (get_campaign_metrics,
    get_search_terms, get_budget_pacing, list_ad_groups, list_keywords) não cobrem o que você
    precisa. Só SELECT — a API não aceita mutation via GAQL, então isso é sempre seguro de rodar.
    Use get_resource_metadata antes pra descobrir os campos válidos de um resource em vez de chutar.
    """
    try:
        return _run_gaql(customer_id, query)
    except RuntimeError as e:
        return {"erro": str(e)}


@server.tool()
def get_resource_metadata(resource_name: str) -> dict[str, Any]:
    """Campos selecionáveis/filtráveis/ordenáveis de um resource Google Ads (ex: 'campaign',
    'ad_group', 'keyword_view', 'search_term_view'), + quais metrics.* e segments.* são
    compatíveis com ele. Rodar antes de escrever uma query em run_gaql — evita campo inventado."""
    client = _get_client()
    service = client.get_service("GoogleAdsFieldService")

    attrs_req = client.get_type("SearchGoogleAdsFieldsRequest")
    attrs_req.query = (
        f"SELECT name, selectable, filterable, sortable, data_type "
        f"WHERE name LIKE '{resource_name}.%' AND category = 'ATTRIBUTE'"
    )
    try:
        attrs_resp = service.search_google_ads_fields(request=attrs_req)
    except GoogleAdsException as ex:
        return {"erro": _ex_detail(ex)}

    attributes = [
        {
            "name": f.name,
            "selectable": f.selectable,
            "filterable": f.filterable,
            "sortable": f.sortable,
            "data_type": client.enums.GoogleAdsFieldDataTypeEnum(f.data_type).name,
        }
        for f in attrs_resp.results
    ]

    compat_req = client.get_type("SearchGoogleAdsFieldsRequest")
    compat_req.query = f"SELECT metrics, segments WHERE name = '{resource_name}'"
    try:
        compat_resp = service.search_google_ads_fields(request=compat_req)
        compat = compat_resp.results[0] if compat_resp.results else None
    except GoogleAdsException:
        compat = None

    return {
        "resource": resource_name,
        "attributes": attributes,
        "compatible_metrics": list(compat.metrics) if compat else [],
        "compatible_segments": list(compat.segments) if compat else [],
    }


@server.tool()
def find_geo_target(query: str, country_code: str = "BR") -> list[dict[str, Any]]:
    """Busca geoTargetConstant IDs por nome de local (cidade/estado/país) — o campo `id`
    retornado é o que vai em `geo_target_ids` de create_search_campaign."""
    client = _get_client()
    service = client.get_service("GeoTargetConstantService")
    request = client.get_type("SuggestGeoTargetConstantsRequest")
    request.locale = "pt"
    request.country_code = country_code
    request.location_names.names.append(query)
    try:
        response = service.suggest_geo_target_constants(request=request)
    except GoogleAdsException as ex:
        return [{"erro": _ex_detail(ex)}]
    return [
        {
            "id": s.geo_target_constant.id,
            "name": s.geo_target_constant.name,
            "country_code": s.geo_target_constant.country_code,
            "target_type": s.geo_target_constant.target_type,
        }
        for s in response.geo_target_constant_suggestions
    ]


@server.tool()
def list_languages() -> dict[str, str]:
    """Idiomas comuns e seus languageConstant ID — usar em `language_id` de create_search_campaign."""
    return {"portugues": "1014", "ingles": "1000", "espanhol": "1003"}


# --------------------------------------------------------------------------
# MUTATION tools — sempre exigem approval explícito (regra 1 do CLAUDE.md)
# --------------------------------------------------------------------------


def _confirm_or_preview(action_id: str, approval: str, preview: dict[str, Any]) -> dict[str, Any] | None:
    """Padrão de aprovação: 1a chamada sem approval (ou errado) devolve preview + a frase
    exata que precisa vir em `approval` na 2a chamada. Retorna None quando aprovado
    (segue pra aplicar), ou o dict de preview quando ainda não."""
    expected = f"CONFIRMO: {action_id}"
    if approval.strip() == expected:
        return None
    return {
        "status": "preview_only — nada foi aplicado",
        "proposed_change": preview,
        "how_to_apply": f'Chame de novo com approval="{expected}" pra aplicar.',
    }


def _action_hash(**kwargs: Any) -> str:
    canonical = _json.dumps(kwargs, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:10]


def _ex_detail(ex: GoogleAdsException) -> str:
    return "; ".join(f"{e.error_code}: {e.message}" for e in ex.failure.errors)


@server.tool()
def add_negative_keyword(
    customer_id: str,
    level: Literal["ad_group", "campaign"],
    scope_id: str,
    text: str,
    match_type: Literal["EXACT", "PHRASE", "BROAD"] = "PHRASE",
    approval: str = "",
) -> dict[str, Any]:
    """Adiciona negative keyword em nível de ad group ou campanha (nível account/lista
    compartilhada continua manual — ver skill search-term-methodology). MUTATION — exige approval.
    """
    action_id = f"add_negative_keyword {level}={scope_id} text='{text}' match={match_type} customer={customer_id}"
    preview = {"level": level, "scope_id": scope_id, "text": text, "match_type": match_type, "customer_id": customer_id}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        if level == "ad_group":
            service = client.get_service("AdGroupCriterionService")
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.create
            criterion.ad_group = client.get_service("AdGroupService").ad_group_path(cid, scope_id)
            criterion.negative = True
            criterion.keyword.text = text
            criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type]
            response = service.mutate_ad_group_criteria(customer_id=cid, operations=[operation])
        else:
            service = client.get_service("CampaignCriterionService")
            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = client.get_service("CampaignService").campaign_path(cid, scope_id)
            criterion.negative = True
            criterion.keyword.text = text
            criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type]
            response = service.mutate_campaign_criteria(customer_id=cid, operations=[operation])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": "; ".join(f"{e.error_code}: {e.message}" for e in ex.failure.errors)}

    return {"status": "aplicado", "resource_name": response.results[0].resource_name}


@server.tool()
def add_positive_keyword(
    customer_id: str,
    ad_group_id: str,
    text: str,
    match_type: Literal["EXACT", "PHRASE", "BROAD"] = "PHRASE",
    cpc_bid_brl: float | None = None,
    approval: str = "",
) -> dict[str, Any]:
    """Adiciona uma keyword positiva a um ad group existente. MUTATION — exige approval."""
    action_id = f"add_positive_keyword ad_group={ad_group_id} text='{text}' match={match_type} bid={cpc_bid_brl} customer={customer_id}"
    preview = {
        "ad_group_id": ad_group_id,
        "text": text,
        "match_type": match_type,
        "cpc_bid_brl": cpc_bid_brl,
        "customer_id": customer_id,
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        service = client.get_service("AdGroupCriterionService")
        operation = client.get_type("AdGroupCriterionOperation")
        criterion = operation.create
        criterion.ad_group = client.get_service("AdGroupService").ad_group_path(cid, ad_group_id)
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = text
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[match_type]
        if cpc_bid_brl is not None:
            criterion.cpc_bid_micros = int(round(cpc_bid_brl * 1_000_000))
        response = service.mutate_ad_group_criteria(customer_id=cid, operations=[operation])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "resource_name": response.results[0].resource_name}


@server.tool()
def update_keyword_bid(
    customer_id: str, ad_group_id: str, criterion_id: str, new_cpc_bid_brl: float, approval: str = ""
) -> dict[str, Any]:
    """Muda o CPC bid de uma keyword específica (positiva). `criterion_id` vem de `list_keywords`.
    MUTATION — exige approval."""
    action_id = f"update_keyword_bid ad_group={ad_group_id} criterion={criterion_id} new_bid={new_cpc_bid_brl} customer={customer_id}"
    preview = {
        "ad_group_id": ad_group_id,
        "criterion_id": criterion_id,
        "new_cpc_bid_brl": new_cpc_bid_brl,
        "customer_id": customer_id,
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        service = client.get_service("AdGroupCriterionService")
        operation = client.get_type("AdGroupCriterionOperation")
        operation.update.resource_name = service.ad_group_criterion_path(cid, ad_group_id, criterion_id)
        operation.update.cpc_bid_micros = int(round(new_cpc_bid_brl * 1_000_000))
        operation.update_mask.paths.append("cpc_bid_micros")
        response = service.mutate_ad_group_criteria(customer_id=cid, operations=[operation])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "resource_name": response.results[0].resource_name}


@server.tool()
def set_keyword_status(
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
    status: Literal["ENABLED", "PAUSED", "REMOVED"],
    approval: str = "",
) -> dict[str, Any]:
    """Ativa, pausa ou remove uma keyword (positiva ou negativa) por `criterion_id`
    (vem de `list_keywords`). MUTATION — exige approval."""
    action_id = f"set_keyword_status ad_group={ad_group_id} criterion={criterion_id} status={status} customer={customer_id}"
    preview = {"ad_group_id": ad_group_id, "criterion_id": criterion_id, "new_status": status, "customer_id": customer_id}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        service = client.get_service("AdGroupCriterionService")
        operation = client.get_type("AdGroupCriterionOperation")
        resource_name = service.ad_group_criterion_path(cid, ad_group_id, criterion_id)
        if status == "REMOVED":
            operation.remove = resource_name
        else:
            operation.update.resource_name = resource_name
            operation.update.status = client.enums.AdGroupCriterionStatusEnum[status]
            operation.update_mask.paths.append("status")
        response = service.mutate_ad_group_criteria(customer_id=cid, operations=[operation])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "resource_name": response.results[0].resource_name}


@server.tool()
def set_ad_group_status(
    customer_id: str, ad_group_id: str, status: Literal["ENABLED", "PAUSED", "REMOVED"], approval: str = ""
) -> dict[str, Any]:
    """Ativa, pausa ou remove um ad group inteiro. MUTATION — exige approval."""
    action_id = f"set_ad_group_status ad_group={ad_group_id} status={status} customer={customer_id}"
    preview = {"ad_group_id": ad_group_id, "new_status": status, "customer_id": customer_id}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        service = client.get_service("AdGroupService")
        operation = client.get_type("AdGroupOperation")
        resource_name = service.ad_group_path(cid, ad_group_id)
        if status == "REMOVED":
            operation.remove = resource_name
        else:
            operation.update.resource_name = resource_name
            operation.update.status = client.enums.AdGroupStatusEnum[status]
            operation.update_mask.paths.append("status")
        response = service.mutate_ad_groups(customer_id=cid, operations=[operation])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "resource_name": response.results[0].resource_name}


def _link_assets_to_campaign(client: GoogleAdsClient, cid: str, campaign_id: str, asset_resource_names: list[str], field_type: str):
    campaign_resource = client.get_service("CampaignService").campaign_path(cid, campaign_id)
    ca_service = client.get_service("CampaignAssetService")
    ops = []
    for asset_rn in asset_resource_names:
        op = client.get_type("CampaignAssetOperation")
        op.create.asset = asset_rn
        op.create.campaign = campaign_resource
        op.create.field_type = client.enums.AssetFieldTypeEnum[field_type]
        ops.append(op)
    return ca_service.mutate_campaign_assets(customer_id=cid, operations=ops)


@server.tool()
def add_sitelinks(customer_id: str, campaign_id: str, sitelinks: list[dict[str, Any]], approval: str = "") -> dict[str, Any]:
    """Adiciona sitelinks a uma campanha. `sitelinks`: lista de
    {"text": str (até 25 char), "final_url": str, "description1": str opcional (até 35 char),
    "description2": str opcional}. Mínimo recomendado: 4. MUTATION — exige approval."""
    action_id = f"add_sitelinks campaign={campaign_id} n={len(sitelinks)} customer={customer_id}"
    preview = {"campaign_id": campaign_id, "customer_id": customer_id, "sitelinks": sitelinks}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        asset_service = client.get_service("AssetService")
        ops = []
        for sl in sitelinks:
            op = client.get_type("AssetOperation")
            op.create.sitelink_asset.link_text = sl["text"]
            if sl.get("description1"):
                op.create.sitelink_asset.description1 = sl["description1"]
            if sl.get("description2"):
                op.create.sitelink_asset.description2 = sl["description2"]
            op.create.final_urls.append(sl["final_url"])
            ops.append(op)
        asset_resp = asset_service.mutate_assets(customer_id=cid, operations=ops)
        asset_rns = [r.resource_name for r in asset_resp.results]
        link_resp = _link_assets_to_campaign(client, cid, campaign_id, asset_rns, "SITELINK")
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "assets": asset_rns, "links": [r.resource_name for r in link_resp.results]}


@server.tool()
def add_callouts(customer_id: str, campaign_id: str, callout_texts: list[str], approval: str = "") -> dict[str, Any]:
    """Adiciona callouts (texto curto, até 25 char cada) a uma campanha. Mínimo recomendado: 4.
    MUTATION — exige approval."""
    action_id = f"add_callouts campaign={campaign_id} texts={callout_texts} customer={customer_id}"
    preview = {"campaign_id": campaign_id, "customer_id": customer_id, "callout_texts": callout_texts}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        asset_service = client.get_service("AssetService")
        ops = []
        for text in callout_texts:
            op = client.get_type("AssetOperation")
            op.create.callout_asset.callout_text = text
            ops.append(op)
        asset_resp = asset_service.mutate_assets(customer_id=cid, operations=ops)
        asset_rns = [r.resource_name for r in asset_resp.results]
        link_resp = _link_assets_to_campaign(client, cid, campaign_id, asset_rns, "CALLOUT")
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "assets": asset_rns, "links": [r.resource_name for r in link_resp.results]}


@server.tool()
def add_structured_snippet(
    customer_id: str, campaign_id: str, header: str, values: list[str], approval: str = ""
) -> dict[str, Any]:
    """Adiciona um structured snippet a uma campanha. `header` precisa ser um dos valores
    pré-definidos do Google (ex: "Brands", "Types", "Styles", "Models", "Amenities",
    "Service catalog", "Destinations", "Neighborhoods") — a API rejeita header fora dessa lista.
    `values`: 3 a 10 itens curtos. MUTATION — exige approval."""
    action_id = f"add_structured_snippet campaign={campaign_id} header={header} values={values} customer={customer_id}"
    preview = {"campaign_id": campaign_id, "customer_id": customer_id, "header": header, "values": values}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        asset_service = client.get_service("AssetService")
        op = client.get_type("AssetOperation")
        op.create.structured_snippet_asset.header = header
        op.create.structured_snippet_asset.values.extend(values)
        asset_resp = asset_service.mutate_assets(customer_id=cid, operations=[op])
        asset_rns = [r.resource_name for r in asset_resp.results]
        link_resp = _link_assets_to_campaign(client, cid, campaign_id, asset_rns, "STRUCTURED_SNIPPET")
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "assets": asset_rns, "links": [r.resource_name for r in link_resp.results]}


@server.tool()
def list_extensions(customer_id: str, campaign_id: str | None = None) -> list[dict[str, Any]]:
    """Lista sitelinks/callouts/structured snippets já anexados a uma campanha (ou a todas)."""
    where_campaign = f"AND campaign.id = {campaign_id} " if campaign_id else ""
    query = f"""
        SELECT
          campaign.id, campaign.name, campaign_asset.field_type, campaign_asset.status,
          asset.id, asset.type, asset.sitelink_asset.link_text,
          asset.callout_asset.callout_text,
          asset.structured_snippet_asset.header, asset.structured_snippet_asset.values
        FROM campaign_asset
        WHERE campaign_asset.field_type IN ('SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET') {where_campaign}
    """
    rows = _run_gaql(customer_id, query)
    out = []
    for r in rows:
        a = r.get("asset", {})
        ca = r.get("campaign_asset", {})
        out.append(
            {
                "campaign_id": str(r.get("campaign", {}).get("id")),
                "campaign_name": r.get("campaign", {}).get("name"),
                "field_type": client_enum_name("AssetFieldTypeEnum", ca.get("field_type")),
                "status": client_enum_name("AssetLinkStatusEnum", ca.get("status")),
                "sitelink_text": a.get("sitelink_asset", {}).get("link_text"),
                "callout_text": a.get("callout_asset", {}).get("callout_text"),
                "snippet_header": a.get("structured_snippet_asset", {}).get("header"),
                "snippet_values": a.get("structured_snippet_asset", {}).get("values"),
            }
        )
    return out


@server.tool()
def update_campaign_budget(customer_id: str, campaign_id: str, new_budget_brl: float, approval: str = "") -> dict[str, Any]:
    """Muda o orçamento diário de uma campanha (valor em BRL, ex: 85.50). MUTATION — exige approval."""
    action_id = f"update_campaign_budget campaign={campaign_id} new_budget={new_budget_brl} customer={customer_id}"
    preview = {"campaign_id": campaign_id, "new_budget_brl": new_budget_brl, "customer_id": customer_id}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        campaign_rows = _run_gaql(
            customer_id, f"SELECT campaign.campaign_budget FROM campaign WHERE campaign.id = {campaign_id}"
        )
        if not campaign_rows:
            return {"status": "erro", "detail": f"campaign {campaign_id} não encontrada"}
        budget_resource = campaign_rows[0]["campaign"]["campaign_budget"]

        service = client.get_service("CampaignBudgetService")
        operation = client.get_type("CampaignBudgetOperation")
        operation.update.resource_name = budget_resource
        operation.update.amount_micros = int(round(new_budget_brl * 1_000_000))
        operation.update_mask.paths.append("amount_micros")
        response = service.mutate_campaign_budgets(customer_id=cid, operations=[operation])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": "; ".join(f"{e.error_code}: {e.message}" for e in ex.failure.errors)}

    return {"status": "aplicado", "resource_name": response.results[0].resource_name}


@server.tool()
def set_campaign_status(
    customer_id: str, campaign_id: str, status: Literal["ENABLED", "PAUSED", "REMOVED"], approval: str = ""
) -> dict[str, Any]:
    """Ativa, pausa ou remove uma campanha (REMOVED é a forma de 'deletar' — Google Ads não tem
    delete de verdade, só marca como removida e some da UI). MUTATION — exige approval."""
    action_id = f"set_campaign_status campaign={campaign_id} status={status} customer={customer_id}"
    preview = {"campaign_id": campaign_id, "new_status": status, "customer_id": customer_id}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        service = client.get_service("CampaignService")
        operation = client.get_type("CampaignOperation")
        resource_name = service.campaign_path(cid, campaign_id)
        if status == "REMOVED":
            # A API rejeita status=REMOVED via update ("Enum value 'REMOVED' cannot be used") —
            # remoção é um tipo de operação separado, com o campo `remove`, não `update.status`.
            operation.remove = resource_name
        else:
            operation.update.resource_name = resource_name
            operation.update.status = client.enums.CampaignStatusEnum[status]
            operation.update_mask.paths.append("status")
        response = service.mutate_campaigns(customer_id=cid, operations=[operation])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "resource_name": response.results[0].resource_name}


@server.tool()
def create_search_campaign(
    customer_id: str,
    campaign_name: str,
    daily_budget_brl: float,
    geo_target_ids: list[str],
    language_id: str,
    ad_groups: list[dict[str, Any]],
    bidding: Literal["MANUAL_CPC", "MAXIMIZE_CLICKS"] = "MANUAL_CPC",
    max_cpc_brl: float = 2.0,
    approval: str = "",
) -> dict[str, Any]:
    """Cria uma campanha Search completa: budget + campanha + geo + idioma + ad groups + keywords + RSA.
    Sempre nasce PAUSED, nunca ativa sozinha — ver skill launch-campaign pra metodologia completa
    (settings, fórmula de keyword, mix de headline).

    geo_target_ids: IDs numéricos de find_geo_target (ex: ["20089"] pra Ceará).
    language_id: ID de list_languages (ex: "1014" português).
    ad_groups: lista de dicts, um por ad group:
        {
          "name": str,
          "keywords": [{"text": str, "match_type": "EXACT"|"PHRASE"|"BROAD"}, ...],
          "headlines": [str, ...]        # 3 a 15, até 30 caracteres cada
          "descriptions": [str, ...]     # 2 a 4, até 90 caracteres cada
          "final_url": str
        }

    Não cria sitelinks/callouts/negativas nesta chamada — negativas via add_negative_keyword
    depois; extensions ainda não têm tool própria (ver mcp/README.md).

    MUTATION composta — exige approval. Se um passo no meio falhar (ex: RSA de um ad group),
    os passos anteriores já aplicados NÃO são desfeitos automaticamente — o retorno mostra
    exatamente o que foi criado e o que falhou, pra revisão manual.
    """
    errors: list[str] = []
    if not ad_groups:
        errors.append("ad_groups vazio — precisa de pelo menos 1 ad group")
    for i, ag in enumerate(ad_groups):
        label = f"ad_groups[{i}] '{ag.get('name', '?')}'"
        n_h, n_d = len(ag.get("headlines", [])), len(ag.get("descriptions", []))
        if not ag.get("name"):
            errors.append(f"{label}: sem name")
        if not (3 <= n_h <= 15):
            errors.append(f"{label}: precisa de 3 a 15 headlines, tem {n_h}")
        if not (2 <= n_d <= 4):
            errors.append(f"{label}: precisa de 2 a 4 descriptions, tem {n_d}")
        if not ag.get("keywords"):
            errors.append(f"{label}: sem keywords")
        if not ag.get("final_url"):
            errors.append(f"{label}: sem final_url")
    if errors:
        return {"status": "erro_validacao", "erros": errors}

    action_id = (
        "create_search_campaign:"
        + _action_hash(
            customer_id=customer_id,
            campaign_name=campaign_name,
            daily_budget_brl=daily_budget_brl,
            geo_target_ids=geo_target_ids,
            language_id=language_id,
            bidding=bidding,
            max_cpc_brl=max_cpc_brl,
            ad_groups=ad_groups,
        )
    )
    preview = {
        "customer_id": customer_id,
        "campaign_name": campaign_name,
        "daily_budget_brl": daily_budget_brl,
        "geo_target_ids": geo_target_ids,
        "language_id": language_id,
        "bidding": bidding,
        "max_cpc_brl": max_cpc_brl,
        "status_inicial": "PAUSED (sempre)",
        "ad_groups": [
            {
                "name": ag["name"],
                "n_keywords": len(ag.get("keywords", [])),
                "n_headlines": len(ag.get("headlines", [])),
                "n_descriptions": len(ag.get("descriptions", [])),
                "final_url": ag.get("final_url"),
            }
            for ag in ad_groups
        ],
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    max_cpc_micros = int(round(max_cpc_brl * 1_000_000))
    created: dict[str, Any] = {"budget": None, "campaign": None, "criteria": [], "ad_groups": []}

    try:
        budget_service = client.get_service("CampaignBudgetService")
        budget_op = client.get_type("CampaignBudgetOperation")
        budget_op.create.name = f"{campaign_name} — Budget — {int(time.time())}"
        budget_op.create.amount_micros = int(round(daily_budget_brl * 1_000_000))
        budget_op.create.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget_op.create.explicitly_shared = False
        budget_resp = budget_service.mutate_campaign_budgets(customer_id=cid, operations=[budget_op])
        budget_resource = budget_resp.results[0].resource_name
        created["budget"] = budget_resource
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "budget", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        campaign_service = client.get_service("CampaignService")
        campaign_op = client.get_type("CampaignOperation")
        camp = campaign_op.create
        camp.name = campaign_name
        camp.status = client.enums.CampaignStatusEnum.PAUSED
        camp.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
        camp.campaign_budget = budget_resource
        camp.network_settings.target_google_search = True
        camp.network_settings.target_search_network = False
        camp.network_settings.target_content_network = False
        camp.network_settings.target_partner_search_network = False
        # Campo obrigatório desde 2025 (compliance de transparência de ads políticos da UE) —
        # sem isso a API recusa o create com "field_error: REQUIRED" sem apontar o campo no erro.
        camp.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )
        if bidding == "MANUAL_CPC":
            camp.manual_cpc.enhanced_cpc_enabled = False
        else:
            camp.target_spend.cpc_bid_ceiling_micros = max_cpc_micros
        campaign_resp = campaign_service.mutate_campaigns(customer_id=cid, operations=[campaign_op])
        campaign_resource = campaign_resp.results[0].resource_name
        created["campaign"] = campaign_resource
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "campaign", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        crit_service = client.get_service("CampaignCriterionService")
        ops = []
        for gid in geo_target_ids:
            op = client.get_type("CampaignCriterionOperation")
            op.create.campaign = campaign_resource
            op.create.location.geo_target_constant = f"geoTargetConstants/{gid}"
            ops.append(op)
        lang_op = client.get_type("CampaignCriterionOperation")
        lang_op.create.campaign = campaign_resource
        lang_op.create.language.language_constant = f"languageConstants/{language_id}"
        ops.append(lang_op)
        crit_resp = crit_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
        created["criteria"] = [r.resource_name for r in crit_resp.results]
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "geo_idioma", "detail": _ex_detail(ex), "created_so_far": created}

    ag_service = client.get_service("AdGroupService")
    ag_crit_service = client.get_service("AdGroupCriterionService")
    ad_service = client.get_service("AdGroupAdService")

    for ag in ad_groups:
        ag_result: dict[str, Any] = {"name": ag["name"]}
        try:
            ag_op = client.get_type("AdGroupOperation")
            ag_op.create.name = ag["name"]
            ag_op.create.campaign = campaign_resource
            ag_op.create.status = client.enums.AdGroupStatusEnum.ENABLED
            ag_op.create.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
            if bidding == "MANUAL_CPC":
                ag_op.create.cpc_bid_micros = max_cpc_micros
            ag_resp = ag_service.mutate_ad_groups(customer_id=cid, operations=[ag_op])
            ag_resource = ag_resp.results[0].resource_name
            ag_result["resource_name"] = ag_resource
        except GoogleAdsException as ex:
            ag_result["erro_ad_group"] = _ex_detail(ex)
            created["ad_groups"].append(ag_result)
            continue

        try:
            kw_ops = []
            for kw in ag.get("keywords", []):
                op = client.get_type("AdGroupCriterionOperation")
                op.create.ad_group = ag_resource
                op.create.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                op.create.keyword.text = kw["text"]
                op.create.keyword.match_type = client.enums.KeywordMatchTypeEnum[kw.get("match_type", "PHRASE")]
                kw_ops.append(op)
            kw_resp = ag_crit_service.mutate_ad_group_criteria(customer_id=cid, operations=kw_ops)
            ag_result["keywords_criadas"] = len(kw_resp.results)
        except GoogleAdsException as ex:
            ag_result["erro_keywords"] = _ex_detail(ex)

        try:
            ad_op = client.get_type("AdGroupAdOperation")
            ad_op.create.ad_group = ag_resource
            ad_op.create.status = client.enums.AdGroupAdStatusEnum.ENABLED
            ad_op.create.ad.final_urls.append(ag["final_url"])
            for h in ag["headlines"]:
                asset = client.get_type("AdTextAsset")
                asset.text = h
                ad_op.create.ad.responsive_search_ad.headlines.append(asset)
            for d in ag["descriptions"]:
                asset = client.get_type("AdTextAsset")
                asset.text = d
                ad_op.create.ad.responsive_search_ad.descriptions.append(asset)
            ad_resp = ad_service.mutate_ad_group_ads(customer_id=cid, operations=[ad_op])
            ag_result["rsa_resource_name"] = ad_resp.results[0].resource_name
        except GoogleAdsException as ex:
            ag_result["erro_rsa"] = _ex_detail(ex)

        created["ad_groups"].append(ag_result)

    any_error = any(
        "erro_ad_group" in r or "erro_keywords" in r or "erro_rsa" in r for r in created["ad_groups"]
    )
    created["status"] = "aplicado_com_erros — revisar campos 'erro_*'" if any_error else "aplicado"
    created["campanha_status"] = "PAUSED — revisar tudo e ativar manualmente quando pronto"
    return created


@server.tool()
def create_pmax_campaign(
    customer_id: str,
    campaign_name: str,
    daily_budget_brl: float,
    geo_target_ids: list[str],
    language_id: str,
    final_url: str,
    headlines: list[str],
    long_headlines: list[str],
    descriptions: list[str],
    business_name: str,
    marketing_image_path: str | None = None,
    square_marketing_image_path: str | None = None,
    logo_path: str | None = None,
    target_cpa_brl: float | None = None,
    approval: str = "",
) -> dict[str, Any]:
    """Cria uma campanha Performance Max: budget + campanha + geo + idioma + 1 asset group +
    assets de texto (headlines, long headlines, descriptions, business name) + imagens (opcional,
    mas praticamente obrigatório — ver aviso abaixo). Sempre nasce PAUSED.

    headlines: 3 a 15 itens, até 30 caracteres cada.
    long_headlines: 1 a 5 itens, até 90 caracteres cada.
    descriptions: 2 a 5 itens, até 90 caracteres cada.
    business_name: até 25 caracteres.
    marketing_image_path: caminho local pra imagem 1.91:1 (landscape, ex: 1200x628).
    square_marketing_image_path: caminho local pra imagem 1:1 (ex: 1200x1200).
    logo_path: caminho local pra imagem 1:1 (logo, mín. 128x128).
    target_cpa_brl: opcional — se ausente, bidding fica em Maximize Conversions sem meta de CPA.

    AVISO: a API do Google **recusa criar o asset group** (`NOT_ENOUGH_MARKETING_IMAGE_ASSET` /
    `NOT_ENOUGH_SQUARE_MARKETING_IMAGE_ASSET` / `NOT_ENOUGH_LOGO_ASSET`) se as 3 imagens não
    forem enviadas — não é um "nice to have", é bloqueante de verdade (validado contra a API real).
    As 3 imagens + todos os assets de texto são enviados numa única operação atômica
    (`GoogleAdsService.mutate` com resource names temporários) — é assim que a API exige pra
    asset group, não dá pra criar vazio e popular depois como em Search.

    MUTATION composta — exige approval. Se falhar no passo de budget/campanha/geo, mesmo padrão
    de `created_so_far` que create_search_campaign. Se falhar no lote atômico de assets, a
    campanha e o budget já foram criados (ficam órfãos, sem asset group) — reportado em erro.
    """
    errors: list[str] = []
    if not (3 <= len(headlines) <= 15):
        errors.append(f"headlines: precisa de 3 a 15, tem {len(headlines)}")
    if not (1 <= len(long_headlines) <= 5):
        errors.append(f"long_headlines: precisa de 1 a 5, tem {len(long_headlines)}")
    if not (2 <= len(descriptions) <= 5):
        errors.append(f"descriptions: precisa de 2 a 5, tem {len(descriptions)}")
    if not business_name:
        errors.append("business_name: obrigatório")
    if not final_url:
        errors.append("final_url: obrigatório")
    if errors:
        return {"status": "erro_validacao", "erros": errors}

    action_id = "create_pmax_campaign:" + _action_hash(
        customer_id=customer_id,
        campaign_name=campaign_name,
        daily_budget_brl=daily_budget_brl,
        geo_target_ids=geo_target_ids,
        language_id=language_id,
        final_url=final_url,
        headlines=headlines,
        long_headlines=long_headlines,
        descriptions=descriptions,
        business_name=business_name,
        target_cpa_brl=target_cpa_brl,
        marketing_image_path=marketing_image_path,
        square_marketing_image_path=square_marketing_image_path,
        logo_path=logo_path,
    )
    preview = {
        "customer_id": customer_id,
        "campaign_name": campaign_name,
        "daily_budget_brl": daily_budget_brl,
        "geo_target_ids": geo_target_ids,
        "language_id": language_id,
        "final_url": final_url,
        "n_headlines": len(headlines),
        "n_long_headlines": len(long_headlines),
        "n_descriptions": len(descriptions),
        "business_name": business_name,
        "target_cpa_brl": target_cpa_brl,
        "marketing_image_path": marketing_image_path,
        "square_marketing_image_path": square_marketing_image_path,
        "logo_path": logo_path,
        "status_inicial": "PAUSED (sempre)",
        "aviso": None
        if (marketing_image_path and square_marketing_image_path and logo_path)
        else "faltam imagens — asset group vai FALHAR (API exige as 3: marketing, square, logo)",
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    created: dict[str, Any] = {"budget": None, "campaign": None, "criteria": [], "asset_group": None, "assets": {}}

    try:
        budget_service = client.get_service("CampaignBudgetService")
        budget_op = client.get_type("CampaignBudgetOperation")
        budget_op.create.name = f"{campaign_name} — Budget — {int(time.time())}"
        budget_op.create.amount_micros = int(round(daily_budget_brl * 1_000_000))
        budget_op.create.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget_op.create.explicitly_shared = False
        budget_resp = budget_service.mutate_campaign_budgets(customer_id=cid, operations=[budget_op])
        budget_resource = budget_resp.results[0].resource_name
        created["budget"] = budget_resource
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "budget", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        campaign_service = client.get_service("CampaignService")
        campaign_op = client.get_type("CampaignOperation")
        camp = campaign_op.create
        camp.name = campaign_name
        camp.status = client.enums.CampaignStatusEnum.PAUSED
        camp.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
        camp.campaign_budget = budget_resource
        camp.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )
        # "Brand Guidelines" (feature 2026) exige logo (imagem) linkado antes de criar a
        # campanha se ficar ligado — como não temos upload de imagem, desligamos aqui.
        # Sem isso: campaign_error REQUIRED_LOGO_ASSET_NOT_LINKED / REQUIRED_BUSINESS_NAME_ASSET_NOT_LINKED.
        camp.brand_guidelines_enabled = False
        if target_cpa_brl is not None:
            camp.maximize_conversions.target_cpa_micros = int(round(target_cpa_brl * 1_000_000))
        else:
            camp.maximize_conversions.target_cpa_micros = 0
        campaign_resp = campaign_service.mutate_campaigns(customer_id=cid, operations=[campaign_op])
        campaign_resource = campaign_resp.results[0].resource_name
        created["campaign"] = campaign_resource
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "campaign", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        crit_service = client.get_service("CampaignCriterionService")
        ops = []
        for gid in geo_target_ids:
            op = client.get_type("CampaignCriterionOperation")
            op.create.campaign = campaign_resource
            op.create.location.geo_target_constant = f"geoTargetConstants/{gid}"
            ops.append(op)
        lang_op = client.get_type("CampaignCriterionOperation")
        lang_op.create.campaign = campaign_resource
        lang_op.create.language.language_constant = f"languageConstants/{language_id}"
        ops.append(lang_op)
        crit_resp = crit_service.mutate_campaign_criteria(customer_id=cid, operations=ops)
        created["criteria"] = [r.resource_name for r in crit_resp.results]
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "geo_idioma", "detail": _ex_detail(ex), "created_so_far": created}

    # AssetGroupService valida os mínimos de asset NA CRIAÇÃO — não dá pra criar o asset group
    # vazio e linkar assets depois (diferente de Search). Por isso tudo aqui vira uma única
    # operação atômica via GoogleAdsService.mutate, usando resource names temporários (IDs
    # negativos) pra cross-referenciar asset -> asset group dentro do mesmo lote.
    next_temp_id = [-1]

    def _temp_asset_rn() -> str:
        rn = f"customers/{cid}/assets/{next_temp_id[0]}"
        next_temp_id[0] -= 1
        return rn

    mutate_ops: list[Any] = []
    asset_rns_by_type: dict[str, list[str]] = {}

    text_groups = {
        "HEADLINE": headlines,
        "LONG_HEADLINE": long_headlines,
        "DESCRIPTION": descriptions,
        "BUSINESS_NAME": [business_name],
    }
    for field_type, texts in text_groups.items():
        asset_rns_by_type[field_type] = []
        for t in texts:
            rn = _temp_asset_rn()
            op = client.get_type("MutateOperation")
            op.asset_operation.create.resource_name = rn
            op.asset_operation.create.text_asset.text = t
            mutate_ops.append(op)
            asset_rns_by_type[field_type].append(rn)

    image_groups = {
        "MARKETING_IMAGE": marketing_image_path,
        "SQUARE_MARKETING_IMAGE": square_marketing_image_path,
        "LOGO": logo_path,
    }
    for field_type, path in image_groups.items():
        if not path:
            continue
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            return {"status": "erro", "step": f"ler imagem {field_type}", "detail": str(e), "created_so_far": created}
        rn = _temp_asset_rn()
        op = client.get_type("MutateOperation")
        op.asset_operation.create.resource_name = rn
        op.asset_operation.create.name = f"{campaign_name} — {field_type} — {int(time.time())}"
        op.asset_operation.create.image_asset.data = data
        mutate_ops.append(op)
        asset_rns_by_type[field_type] = [rn]

    asset_group_rn = f"customers/{cid}/assetGroups/{next_temp_id[0]}"
    next_temp_id[0] -= 1
    ag_op = client.get_type("MutateOperation")
    ag_op.asset_group_operation.create.resource_name = asset_group_rn
    ag_op.asset_group_operation.create.name = f"{campaign_name} — Asset Group"
    ag_op.asset_group_operation.create.campaign = campaign_resource
    ag_op.asset_group_operation.create.final_urls.append(final_url)
    ag_op.asset_group_operation.create.status = client.enums.AssetGroupStatusEnum.ENABLED
    mutate_ops.append(ag_op)

    for field_type, rns in asset_rns_by_type.items():
        for rn in rns:
            op = client.get_type("MutateOperation")
            op.asset_group_asset_operation.create.asset_group = asset_group_rn
            op.asset_group_asset_operation.create.asset = rn
            op.asset_group_asset_operation.create.field_type = client.enums.AssetFieldTypeEnum[field_type]
            mutate_ops.append(op)

    try:
        ga_service = client.get_service("GoogleAdsService")
        batch_resp = ga_service.mutate(customer_id=cid, mutate_operations=mutate_ops)
    except GoogleAdsException as ex:
        return {
            "status": "erro",
            "step": "asset_group_e_assets (lote atômico)",
            "detail": _ex_detail(ex),
            "created_so_far": created,
            "aviso": "budget e campanha já existem, órfãos sem asset group — considerar remover com set_campaign_status REMOVED",
        }

    temp_to_real: dict[str, str] = {}
    for op, resp_item in zip(mutate_ops, batch_resp.mutate_operation_responses):
        if op.asset_operation.create.resource_name:
            temp_to_real[op.asset_operation.create.resource_name] = resp_item.asset_result.resource_name
        elif op.asset_group_operation.create.resource_name:
            temp_to_real[op.asset_group_operation.create.resource_name] = resp_item.asset_group_result.resource_name

    created["asset_group"] = temp_to_real.get(asset_group_rn, asset_group_rn)
    created["assets"] = {k: [temp_to_real.get(rn, rn) for rn in v] for k, v in asset_rns_by_type.items()}
    created["status"] = "aplicado"
    created["campanha_status"] = "PAUSED — revisar tudo e ativar manualmente quando pronto"
    return created


@server.tool()
def research_keywords(
    customer_id: str, seed_keywords: list[str], geo_target_ids: list[str], language_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Pesquisa keyword ideas com dado real (Keyword Planner): volume médio mensal de busca,
    nível de competição e faixa de CPC estimado — pra alimentar a fórmula de keyword do
    launch-campaign com dado em vez de intuição. Não é mutation nem cria Keyword Plan salvo,
    é geração direta (read-only, sempre livre)."""
    client = _get_client()
    try:
        service = client.get_service("KeywordPlanIdeaService")
        request = client.get_type("GenerateKeywordIdeasRequest")
        request.customer_id = customer_id.replace("-", "")
        request.language = f"languageConstants/{language_id}"
        for gid in geo_target_ids:
            request.geo_target_constants.append(f"geoTargetConstants/{gid}")
        request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
        request.keyword_seed.keywords.extend(seed_keywords)
        response = service.generate_keyword_ideas(request=request)
    except GoogleAdsException as ex:
        return [{"erro": _ex_detail(ex)}]

    out = []
    for idea in response:
        m = idea.keyword_idea_metrics
        out.append(
            {
                "keyword": idea.text,
                "avg_monthly_searches": m.avg_monthly_searches,
                "competition": client.enums.KeywordPlanCompetitionLevelEnum(m.competition).name,
                "low_top_of_page_bid_brl": _micros_to_currency(m.low_top_of_page_bid_micros),
                "high_top_of_page_bid_brl": _micros_to_currency(m.high_top_of_page_bid_micros),
            }
        )
        if len(out) >= limit:
            break
    return sorted(out, key=lambda x: x["avg_monthly_searches"] or 0, reverse=True)


@server.tool()
def list_negative_keyword_lists(customer_id: str) -> list[dict[str, Any]]:
    """Lista as listas de negativas compartilhadas (shared sets) da conta, com membros e
    quais campanhas cada uma está anexada."""
    sets = _run_gaql(
        customer_id,
        "SELECT shared_set.id, shared_set.name, shared_set.status, shared_set.member_count "
        "FROM shared_set WHERE shared_set.type = 'NEGATIVE_KEYWORDS'",
    )
    out = []
    for r in sets:
        ss = r["shared_set"]
        set_id = str(ss["id"])
        members = _run_gaql(
            customer_id,
            f"SELECT shared_criterion.keyword.text, shared_criterion.keyword.match_type "
            f"FROM shared_criterion WHERE shared_criterion.shared_set = 'customers/{customer_id.replace('-', '')}/sharedSets/{set_id}'",
        )
        attached = _run_gaql(
            customer_id,
            f"SELECT campaign.id, campaign.name FROM campaign_shared_set "
            f"WHERE campaign_shared_set.shared_set = 'customers/{customer_id.replace('-', '')}/sharedSets/{set_id}'",
        )
        out.append(
            {
                "shared_set_id": set_id,
                "name": ss["name"],
                "status": client_enum_name("SharedSetStatusEnum", ss.get("status")),
                "member_count": _to_int(ss.get("member_count")),
                "keywords": [
                    {
                        "text": m["shared_criterion"]["keyword"]["text"],
                        "match_type": client_enum_name(
                            "KeywordMatchTypeEnum", m["shared_criterion"]["keyword"]["match_type"]
                        ),
                    }
                    for m in members
                ],
                "attached_campaigns": [
                    {"campaign_id": str(a["campaign"]["id"]), "campaign_name": a["campaign"]["name"]} for a in attached
                ],
            }
        )
    return out


@server.tool()
def create_negative_keyword_list(
    customer_id: str, list_name: str, keywords: list[dict[str, str]], approval: str = ""
) -> dict[str, Any]:
    """Cria uma lista de negativas compartilhada (shared set) com os termos já dentro.
    `keywords`: [{"text": str, "match_type": "EXACT"|"PHRASE"|"BROAD"}]. Anexar a campanhas
    depois com `attach_negative_keyword_list`. MUTATION — exige approval."""
    if not keywords:
        return {"status": "erro_validacao", "erros": ["keywords vazio"]}

    action_id = f"create_negative_keyword_list name={list_name} n={len(keywords)} customer={customer_id}"
    preview = {"list_name": list_name, "customer_id": customer_id, "keywords": keywords}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        ss_service = client.get_service("SharedSetService")
        ss_op = client.get_type("SharedSetOperation")
        ss_op.create.name = list_name
        ss_op.create.type_ = client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
        ss_resp = ss_service.mutate_shared_sets(customer_id=cid, operations=[ss_op])
        shared_set_resource = ss_resp.results[0].resource_name
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "shared_set", "detail": _ex_detail(ex)}

    try:
        sc_service = client.get_service("SharedCriterionService")
        ops = []
        for kw in keywords:
            op = client.get_type("SharedCriterionOperation")
            op.create.shared_set = shared_set_resource
            op.create.keyword.text = kw["text"]
            op.create.keyword.match_type = client.enums.KeywordMatchTypeEnum[kw.get("match_type", "PHRASE")]
            ops.append(op)
        sc_resp = sc_service.mutate_shared_criteria(customer_id=cid, operations=ops)
    except GoogleAdsException as ex:
        return {
            "status": "erro",
            "step": "shared_criteria",
            "detail": _ex_detail(ex),
            "aviso": f"shared_set {shared_set_resource} já foi criado (vazio) — pode reaproveitar ou remover",
        }

    return {
        "status": "aplicado",
        "shared_set": shared_set_resource,
        "keywords_criadas": len(sc_resp.results),
    }


@server.tool()
def attach_negative_keyword_list(
    customer_id: str, shared_set_id: str, campaign_ids: list[str], approval: str = ""
) -> dict[str, Any]:
    """Anexa uma lista de negativas compartilhada (já criada) a uma ou mais campanhas.
    MUTATION — exige approval."""
    if not campaign_ids:
        return {"status": "erro_validacao", "erros": ["campaign_ids vazio"]}

    action_id = f"attach_negative_keyword_list set={shared_set_id} campaigns={campaign_ids} customer={customer_id}"
    preview = {"shared_set_id": shared_set_id, "campaign_ids": campaign_ids, "customer_id": customer_id}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        css_service = client.get_service("CampaignSharedSetService")
        campaign_service = client.get_service("CampaignService")
        shared_set_service = client.get_service("SharedSetService")
        ops = []
        for campaign_id in campaign_ids:
            op = client.get_type("CampaignSharedSetOperation")
            op.create.campaign = campaign_service.campaign_path(cid, campaign_id)
            op.create.shared_set = shared_set_service.shared_set_path(cid, shared_set_id)
            ops.append(op)
        resp = css_service.mutate_campaign_shared_sets(customer_id=cid, operations=ops)
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "links": [r.resource_name for r in resp.results]}


@server.tool()
def list_bidding_strategies(customer_id: str) -> list[dict[str, Any]]:
    """Lista as portfolio bidding strategies da conta e quantas campanhas cada uma usa."""
    rows = _run_gaql(
        customer_id,
        "SELECT bidding_strategy.id, bidding_strategy.name, bidding_strategy.type, "
        "bidding_strategy.status, bidding_strategy.campaign_count, "
        "bidding_strategy.non_removed_campaign_count FROM bidding_strategy "
        "WHERE bidding_strategy.status != 'REMOVED'",
    )
    out = []
    for r in rows:
        bs = r["bidding_strategy"]
        out.append(
            {
                "bidding_strategy_id": str(bs["id"]),
                "name": bs["name"],
                "type": client_enum_name("BiddingStrategyTypeEnum", bs.get("type_")),
                "status": client_enum_name("BiddingStrategyStatusEnum", bs.get("status")),
                "campaign_count": _to_int(bs.get("campaign_count")),
            }
        )
    return out


@server.tool()
def create_portfolio_bidding_strategy(
    customer_id: str,
    name: str,
    strategy_type: Literal[
        "TARGET_CPA", "TARGET_ROAS", "TARGET_IMPRESSION_SHARE", "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE"
    ],
    target_cpa_brl: float | None = None,
    target_roas: float | None = None,
    target_impression_share_pct: float | None = None,
    max_cpc_brl: float | None = None,
    approval: str = "",
) -> dict[str, Any]:
    """Cria uma portfolio bidding strategy (compartilhável entre campanhas — diferente do bidding
    inline de create_search_campaign, que vale só pra uma campanha). Depois de criada, usar
    `assign_bidding_strategy` pra aplicar numa ou mais campanhas.

    - TARGET_CPA: precisa de `target_cpa_brl`.
    - TARGET_ROAS: precisa de `target_roas` (ex: 4.0 = 400%, retorno de R$4 pra cada R$1 gasto).
    - TARGET_IMPRESSION_SHARE: precisa de `target_impression_share_pct` (ex: 65.0) — usa
      ANYWHERE_ON_PAGE como local alvo por padrão; `max_cpc_brl` vira o teto de CPC.
    - MAXIMIZE_CONVERSIONS / MAXIMIZE_CONVERSION_VALUE: `target_cpa_brl`/`max_cpc_brl` são opcionais.

    MUTATION — exige approval."""
    action_id = f"create_portfolio_bidding_strategy name={name} type={strategy_type} customer={customer_id}"
    preview = {
        "name": name,
        "strategy_type": strategy_type,
        "target_cpa_brl": target_cpa_brl,
        "target_roas": target_roas,
        "target_impression_share_pct": target_impression_share_pct,
        "max_cpc_brl": max_cpc_brl,
        "customer_id": customer_id,
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        service = client.get_service("BiddingStrategyService")
        op = client.get_type("BiddingStrategyOperation")
        bs = op.create
        bs.name = name
        max_cpc_micros = int(round(max_cpc_brl * 1_000_000)) if max_cpc_brl else None

        if strategy_type == "TARGET_CPA":
            bs.target_cpa.target_cpa_micros = int(round(target_cpa_brl * 1_000_000))
        elif strategy_type == "TARGET_ROAS":
            bs.target_roas.target_roas = target_roas
        elif strategy_type == "TARGET_IMPRESSION_SHARE":
            bs.target_impression_share.location = client.enums.TargetImpressionShareLocationEnum.ANYWHERE_ON_PAGE
            bs.target_impression_share.location_fraction_micros = int(round(target_impression_share_pct * 10_000))
            if max_cpc_micros:
                bs.target_impression_share.cpc_bid_ceiling_micros = max_cpc_micros
        elif strategy_type == "MAXIMIZE_CONVERSIONS":
            if target_cpa_brl:
                bs.maximize_conversions.target_cpa_micros = int(round(target_cpa_brl * 1_000_000))
        elif strategy_type == "MAXIMIZE_CONVERSION_VALUE":
            pass

        resp = service.mutate_bidding_strategies(customer_id=cid, operations=[op])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "resource_name": resp.results[0].resource_name}


@server.tool()
def assign_bidding_strategy(customer_id: str, campaign_id: str, bidding_strategy_id: str, approval: str = "") -> dict[str, Any]:
    """Aplica uma portfolio bidding strategy (já criada) numa campanha existente — substitui
    qualquer bidding inline que a campanha tinha antes. MUTATION — exige approval."""
    action_id = f"assign_bidding_strategy campaign={campaign_id} strategy={bidding_strategy_id} customer={customer_id}"
    preview = {"campaign_id": campaign_id, "bidding_strategy_id": bidding_strategy_id, "customer_id": customer_id}
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    try:
        campaign_service = client.get_service("CampaignService")
        bs_service = client.get_service("BiddingStrategyService")
        op = client.get_type("CampaignOperation")
        op.update.resource_name = campaign_service.campaign_path(cid, campaign_id)
        op.update.bidding_strategy = bs_service.bidding_strategy_path(cid, bidding_strategy_id)
        op.update_mask.paths.append("bidding_strategy")
        resp = campaign_service.mutate_campaigns(customer_id=cid, operations=[op])
    except GoogleAdsException as ex:
        return {"status": "erro", "detail": _ex_detail(ex)}

    return {"status": "aplicado", "resource_name": resp.results[0].resource_name}


def _create_budget_campaign_shell(
    client: GoogleAdsClient,
    cid: str,
    campaign_name: str,
    daily_budget_brl: float,
    channel_type: str,
    geo_target_ids: list[str],
    language_id: str | None,
    configure_campaign: Any,
    skip_geo_lang: bool = False,
) -> tuple[dict[str, Any], str | None, dict[str, Any] | None]:
    """Boilerplate comum a Search/PMax/Display/Demand Gen: budget -> campanha (PAUSED, EU
    political declarado) -> geo + idioma. `configure_campaign(camp)` seta o que é específico
    do tipo (bidding, network_settings, etc.) antes do create. `skip_geo_lang=True` pula o passo
    de geo/idioma (usado por Demand Gen — ver gotcha #12 no mcp/README.md). Retorna
    (created_parcial, campaign_resource_ou_None, erro_dict_ou_None) — se erro_dict não é None,
    parar e devolver ele."""
    created: dict[str, Any] = {"budget": None, "campaign": None, "criteria": []}

    try:
        budget_service = client.get_service("CampaignBudgetService")
        budget_op = client.get_type("CampaignBudgetOperation")
        budget_op.create.name = f"{campaign_name} — Budget — {int(time.time())}"
        budget_op.create.amount_micros = int(round(daily_budget_brl * 1_000_000))
        budget_op.create.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget_op.create.explicitly_shared = False
        budget_resp = budget_service.mutate_campaign_budgets(customer_id=cid, operations=[budget_op])
        budget_resource = budget_resp.results[0].resource_name
        created["budget"] = budget_resource
    except GoogleAdsException as ex:
        return created, None, {"status": "erro", "step": "budget", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        campaign_service = client.get_service("CampaignService")
        campaign_op = client.get_type("CampaignOperation")
        camp = campaign_op.create
        camp.name = campaign_name
        camp.status = client.enums.CampaignStatusEnum.PAUSED
        camp.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum[channel_type]
        camp.campaign_budget = budget_resource
        camp.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )
        if channel_type == "PERFORMANCE_MAX":
            # "Brand Guidelines" só existe pra PMax — em outro channel_type a API rejeita
            # com BRAND_GUIDELINES_UNSUPPORTED_CHANNEL mesmo setando como False.
            camp.brand_guidelines_enabled = False
        configure_campaign(camp)
        campaign_resp = campaign_service.mutate_campaigns(customer_id=cid, operations=[campaign_op])
        campaign_resource = campaign_resp.results[0].resource_name
        created["campaign"] = campaign_resource
    except GoogleAdsException as ex:
        return created, None, {"status": "erro", "step": "campaign", "detail": _ex_detail(ex), "created_so_far": created}

    if skip_geo_lang:
        created["criteria"] = "pulado — ver aviso"
        return created, campaign_resource, None

    try:
        crit_service = client.get_service("CampaignCriterionService")
        ops = []
        for gid in geo_target_ids:
            op = client.get_type("CampaignCriterionOperation")
            op.create.campaign = campaign_resource
            op.create.location.geo_target_constant = f"geoTargetConstants/{gid}"
            ops.append(op)
        if language_id:
            lang_op = client.get_type("CampaignCriterionOperation")
            lang_op.create.campaign = campaign_resource
            lang_op.create.language.language_constant = f"languageConstants/{language_id}"
            ops.append(lang_op)
        crit_resp = crit_service.mutate_campaign_criteria(customer_id=cid, operations=ops) if ops else None
        created["criteria"] = [r.resource_name for r in crit_resp.results] if crit_resp else []
    except GoogleAdsException as ex:
        return created, None, {"status": "erro", "step": "geo_idioma", "detail": _ex_detail(ex), "created_so_far": created}

    return created, campaign_resource, None


@server.tool()
def create_display_campaign(
    customer_id: str,
    campaign_name: str,
    daily_budget_brl: float,
    geo_target_ids: list[str],
    language_id: str,
    final_url: str,
    headlines: list[str],
    long_headline: str,
    descriptions: list[str],
    business_name: str,
    marketing_image_path: str,
    square_marketing_image_path: str,
    max_cpc_brl: float = 2.0,
    approval: str = "",
) -> dict[str, Any]:
    """Cria uma campanha Display: budget + campanha + geo + idioma + 1 ad group + 1 Responsive
    Display Ad (com imagens). Sempre nasce PAUSED.

    headlines: 1 a 5, até 30 caracteres. long_headline: 1, até 90 caracteres.
    descriptions: 1 a 5, até 90 caracteres. business_name: até 25 caracteres.
    marketing_image_path: imagem 1.91:1 local. square_marketing_image_path: imagem 1:1 local.

    Diferente de PMax: aqui a validação de mínimo de asset é só no momento do anúncio (RSA-like),
    não no ad group — passos sequenciais funcionam (cria as imagens primeiro, depois o anúncio
    referenciando elas), sem precisar do lote atômico.

    MUTATION composta — exige approval."""
    errors: list[str] = []
    if not (1 <= len(headlines) <= 5):
        errors.append(f"headlines: precisa de 1 a 5, tem {len(headlines)}")
    if not long_headline:
        errors.append("long_headline: obrigatório")
    if not (1 <= len(descriptions) <= 5):
        errors.append(f"descriptions: precisa de 1 a 5, tem {len(descriptions)}")
    if not business_name:
        errors.append("business_name: obrigatório")
    if errors:
        return {"status": "erro_validacao", "erros": errors}

    action_id = "create_display_campaign:" + _action_hash(
        customer_id=customer_id,
        campaign_name=campaign_name,
        daily_budget_brl=daily_budget_brl,
        geo_target_ids=geo_target_ids,
        language_id=language_id,
        final_url=final_url,
        headlines=headlines,
        long_headline=long_headline,
        descriptions=descriptions,
        business_name=business_name,
        marketing_image_path=marketing_image_path,
        square_marketing_image_path=square_marketing_image_path,
        max_cpc_brl=max_cpc_brl,
    )
    preview = {
        "customer_id": customer_id,
        "campaign_name": campaign_name,
        "daily_budget_brl": daily_budget_brl,
        "geo_target_ids": geo_target_ids,
        "language_id": language_id,
        "final_url": final_url,
        "n_headlines": len(headlines),
        "long_headline": long_headline,
        "n_descriptions": len(descriptions),
        "business_name": business_name,
        "marketing_image_path": marketing_image_path,
        "square_marketing_image_path": square_marketing_image_path,
        "max_cpc_brl": max_cpc_brl,
        "status_inicial": "PAUSED (sempre)",
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    max_cpc_micros = int(round(max_cpc_brl * 1_000_000))

    def _configure(camp: Any) -> None:
        camp.manual_cpc.enhanced_cpc_enabled = False

    created, campaign_resource, err = _create_budget_campaign_shell(
        client, cid, campaign_name, daily_budget_brl, "DISPLAY", geo_target_ids, language_id, _configure
    )
    if err:
        return err

    try:
        marketing_data = Path(marketing_image_path).read_bytes()
        square_data = Path(square_marketing_image_path).read_bytes()
    except OSError as e:
        return {"status": "erro", "step": "ler imagem", "detail": str(e), "created_so_far": created}

    try:
        asset_service = client.get_service("AssetService")
        img_ops = []
        for label, data in [("marketing", marketing_data), ("square", square_data)]:
            op = client.get_type("AssetOperation")
            op.create.name = f"{campaign_name} — {label} — {int(time.time())}"
            op.create.image_asset.data = data
            img_ops.append(op)
        img_resp = asset_service.mutate_assets(customer_id=cid, operations=img_ops)
        marketing_image_rn, square_image_rn = [r.resource_name for r in img_resp.results]
        created["images"] = {"marketing": marketing_image_rn, "square": square_image_rn}
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "imagens", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        ag_service = client.get_service("AdGroupService")
        ag_op = client.get_type("AdGroupOperation")
        ag_op.create.name = f"{campaign_name} — Ad Group"
        ag_op.create.campaign = campaign_resource
        ag_op.create.status = client.enums.AdGroupStatusEnum.ENABLED
        ag_op.create.type_ = client.enums.AdGroupTypeEnum.DISPLAY_STANDARD
        ag_op.create.cpc_bid_micros = max_cpc_micros
        ag_resp = ag_service.mutate_ad_groups(customer_id=cid, operations=[ag_op])
        ad_group_resource = ag_resp.results[0].resource_name
        created["ad_group"] = ad_group_resource
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "ad_group", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        ad_service = client.get_service("AdGroupAdService")
        ad_op = client.get_type("AdGroupAdOperation")
        ad_op.create.ad_group = ad_group_resource
        ad_op.create.status = client.enums.AdGroupAdStatusEnum.ENABLED
        ad_op.create.ad.final_urls.append(final_url)
        rda = ad_op.create.ad.responsive_display_ad
        for h in headlines:
            asset = client.get_type("AdTextAsset")
            asset.text = h
            rda.headlines.append(asset)
        rda.long_headline.text = long_headline
        for d in descriptions:
            asset = client.get_type("AdTextAsset")
            asset.text = d
            rda.descriptions.append(asset)
        rda.business_name = business_name
        rda.marketing_images.append(client.get_type("AdImageAsset"))
        rda.marketing_images[0].asset = marketing_image_rn
        rda.square_marketing_images.append(client.get_type("AdImageAsset"))
        rda.square_marketing_images[0].asset = square_image_rn
        ad_resp = ad_service.mutate_ad_group_ads(customer_id=cid, operations=[ad_op])
        created["ad"] = ad_resp.results[0].resource_name
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "ad", "detail": _ex_detail(ex), "created_so_far": created}

    created["status"] = "aplicado"
    created["campanha_status"] = "PAUSED — revisar tudo e ativar manualmente quando pronto"
    return created


@server.tool()
def create_demand_gen_campaign(
    customer_id: str,
    campaign_name: str,
    daily_budget_brl: float,
    geo_target_ids: list[str],
    language_id: str,
    final_url: str,
    headlines: list[str],
    descriptions: list[str],
    business_name: str,
    marketing_image_path: str,
    square_marketing_image_path: str,
    logo_path: str,
    approval: str = "",
) -> dict[str, Any]:
    """Cria uma campanha Demand Gen (o antigo "Discovery" — feeds do Discover/Gmail/YouTube).
    Diferente de PMax: **não** usa AssetGroup (a API recusa com `CANNOT_ADD_ASSET_GROUP_FOR_
    CAMPAIGN_TYPE`, confirmado testando). Estrutura real: budget + campanha + 1 ad group + 1
    anúncio `demand_gen_multi_asset_ad` (mesmo formato de asset do ResponsiveDisplayAd —
    headlines, descriptions, business name, imagens). Sempre nasce PAUSED.

    headlines: 1 a 5 itens, até 40 caracteres. descriptions: 1 a 5, até 90 caracteres.
    business_name: até 25 caracteres. marketing_image_path (1.91:1), square_marketing_image_path
    (1:1) e logo_path (1:1) são obrigatórios.

    LIMITAÇÃO CONHECIDA (validada contra a API real, testado com e sem AssetGroup, geo de
    estado e de país, sozinho e em lote — sempre o mesmo erro): `CampaignCriterionService` pra
    campanha Demand Gen retorna `request_error: UNKNOWN — The error code is not in this
    version` de forma consistente. Por isso `geo_target_ids`/`language_id` **não são
    aplicados** — configurar manualmente pela UI antes de ativar. Ver gotcha #12 no
    `mcp/README.md`.

    MUTATION composta — exige approval."""
    errors: list[str] = []
    if not (1 <= len(headlines) <= 5):
        errors.append(f"headlines: precisa de 1 a 5, tem {len(headlines)}")
    if not (1 <= len(descriptions) <= 5):
        errors.append(f"descriptions: precisa de 1 a 5, tem {len(descriptions)}")
    if not business_name:
        errors.append("business_name: obrigatório")
    if errors:
        return {"status": "erro_validacao", "erros": errors}

    action_id = "create_demand_gen_campaign:" + _action_hash(
        customer_id=customer_id,
        campaign_name=campaign_name,
        daily_budget_brl=daily_budget_brl,
        geo_target_ids=geo_target_ids,
        language_id=language_id,
        final_url=final_url,
        headlines=headlines,
        descriptions=descriptions,
        business_name=business_name,
        marketing_image_path=marketing_image_path,
        square_marketing_image_path=square_marketing_image_path,
        logo_path=logo_path,
    )
    preview = {
        "customer_id": customer_id,
        "campaign_name": campaign_name,
        "daily_budget_brl": daily_budget_brl,
        "geo_target_ids": geo_target_ids,
        "language_id": language_id,
        "final_url": final_url,
        "n_headlines": len(headlines),
        "n_descriptions": len(descriptions),
        "business_name": business_name,
        "status_inicial": "PAUSED (sempre)",
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")

    def _configure(camp: Any) -> None:
        camp.maximize_conversions.target_cpa_micros = 0

    created, campaign_resource, err = _create_budget_campaign_shell(
        client, cid, campaign_name, daily_budget_brl, "DEMAND_GEN", geo_target_ids, language_id, _configure,
        skip_geo_lang=True,
    )
    if err:
        return err

    try:
        marketing_data = Path(marketing_image_path).read_bytes()
        square_data = Path(square_marketing_image_path).read_bytes()
        logo_data = Path(logo_path).read_bytes()
    except OSError as e:
        return {"status": "erro", "step": "ler imagem", "detail": str(e), "created_so_far": created}

    try:
        asset_service = client.get_service("AssetService")
        img_ops = []
        for label, data in [("marketing", marketing_data), ("square", square_data), ("logo", logo_data)]:
            op = client.get_type("AssetOperation")
            op.create.name = f"{campaign_name} — {label} — {int(time.time())}"
            op.create.image_asset.data = data
            img_ops.append(op)
        img_resp = asset_service.mutate_assets(customer_id=cid, operations=img_ops)
        marketing_rn, square_rn, logo_rn = [r.resource_name for r in img_resp.results]
        created["images"] = {"marketing": marketing_rn, "square": square_rn, "logo": logo_rn}
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "imagens", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        ag_service = client.get_service("AdGroupService")
        ag_op = client.get_type("AdGroupOperation")
        ag_op.create.name = f"{campaign_name} — Ad Group"
        ag_op.create.campaign = campaign_resource
        ag_op.create.status = client.enums.AdGroupStatusEnum.ENABLED
        ag_resp = ag_service.mutate_ad_groups(customer_id=cid, operations=[ag_op])
        ad_group_resource = ag_resp.results[0].resource_name
        created["ad_group"] = ad_group_resource
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "ad_group", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        ad_service = client.get_service("AdGroupAdService")
        ad_op = client.get_type("AdGroupAdOperation")
        ad_op.create.ad_group = ad_group_resource
        ad_op.create.status = client.enums.AdGroupAdStatusEnum.ENABLED
        ad_op.create.ad.final_urls.append(final_url)
        dma = ad_op.create.ad.demand_gen_multi_asset_ad
        for h in headlines:
            asset = client.get_type("AdTextAsset")
            asset.text = h
            dma.headlines.append(asset)
        for d in descriptions:
            asset = client.get_type("AdTextAsset")
            asset.text = d
            dma.descriptions.append(asset)
        dma.business_name = business_name
        dma.marketing_images.append(client.get_type("AdImageAsset"))
        dma.marketing_images[0].asset = marketing_rn
        dma.square_marketing_images.append(client.get_type("AdImageAsset"))
        dma.square_marketing_images[0].asset = square_rn
        dma.logo_images.append(client.get_type("AdImageAsset"))
        dma.logo_images[0].asset = logo_rn
        ad_resp = ad_service.mutate_ad_group_ads(customer_id=cid, operations=[ad_op])
        created["ad"] = ad_resp.results[0].resource_name
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "ad", "detail": _ex_detail(ex), "created_so_far": created}

    created["status"] = "aplicado"
    created["campanha_status"] = "PAUSED — revisar tudo e ativar manualmente quando pronto"
    created["aviso"] = (
        "geo/idioma NÃO foram aplicados (limitação da API pra Demand Gen — ver docstring/mcp/README.md). "
        "Configurar manualmente pela UI antes de ativar."
    )
    return created


@server.tool()
def create_video_campaign(
    customer_id: str,
    campaign_name: str,
    daily_budget_brl: float,
    geo_target_ids: list[str],
    language_id: str,
    final_url: str,
    youtube_video_id: str,
    headlines: list[str],
    long_headlines: list[str],
    descriptions: list[str],
    business_name: str,
    approval: str = "",
) -> dict[str, Any]:
    """Cria uma campanha Video (YouTube): budget + campanha + geo + idioma + 1 ad group + 1
    Video Responsive Ad. Sempre nasce PAUSED.

    youtube_video_id: ID de um vídeo do YouTube JÁ PUBLICADO e de propriedade do
    anunciante (o trecho depois de `v=` na URL, ex: `dQw4w9WgXcQ`) — o Google Ads não hospeda
    vídeo, só referencia um público existente. Vídeo tem que existir e ser acessível, senão a
    criação do asset falha.
    headlines: 1 a 5, até 30 caracteres. long_headlines: 1 a 5, até 90 caracteres.
    descriptions: 1 a 5, até 90 caracteres. business_name: até 25 caracteres.

    ⚠️ NÃO TESTADA end-to-end ainda (precisa de um youtube_video_id real de algum cliente —
    a estrutura foi validada via introspecção do SDK, mesmo padrão de campos que
    create_display_campaign, mas nunca rodou contra a API de verdade). Testar antes de confiar
    em produção.

    MUTATION composta — exige approval."""
    errors: list[str] = []
    if not youtube_video_id:
        errors.append("youtube_video_id: obrigatório")
    if not (1 <= len(headlines) <= 5):
        errors.append(f"headlines: precisa de 1 a 5, tem {len(headlines)}")
    if not (1 <= len(long_headlines) <= 5):
        errors.append(f"long_headlines: precisa de 1 a 5, tem {len(long_headlines)}")
    if not (1 <= len(descriptions) <= 5):
        errors.append(f"descriptions: precisa de 1 a 5, tem {len(descriptions)}")
    if not business_name:
        errors.append("business_name: obrigatório")
    if errors:
        return {"status": "erro_validacao", "erros": errors}

    action_id = "create_video_campaign:" + _action_hash(
        customer_id=customer_id,
        campaign_name=campaign_name,
        daily_budget_brl=daily_budget_brl,
        geo_target_ids=geo_target_ids,
        language_id=language_id,
        final_url=final_url,
        youtube_video_id=youtube_video_id,
        headlines=headlines,
        long_headlines=long_headlines,
        descriptions=descriptions,
        business_name=business_name,
    )
    preview = {
        "customer_id": customer_id,
        "campaign_name": campaign_name,
        "daily_budget_brl": daily_budget_brl,
        "geo_target_ids": geo_target_ids,
        "language_id": language_id,
        "final_url": final_url,
        "youtube_video_id": youtube_video_id,
        "n_headlines": len(headlines),
        "n_long_headlines": len(long_headlines),
        "n_descriptions": len(descriptions),
        "business_name": business_name,
        "status_inicial": "PAUSED (sempre)",
        "aviso": "tool ainda não testada end-to-end contra a API real",
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")

    def _configure(camp: Any) -> None:
        camp.maximize_conversions.target_cpa_micros = 0

    created, campaign_resource, err = _create_budget_campaign_shell(
        client, cid, campaign_name, daily_budget_brl, "VIDEO", geo_target_ids, language_id, _configure
    )
    if err:
        return err

    try:
        asset_service = client.get_service("AssetService")
        video_op = client.get_type("AssetOperation")
        video_op.create.youtube_video_asset.youtube_video_id = youtube_video_id
        video_resp = asset_service.mutate_assets(customer_id=cid, operations=[video_op])
        video_rn = video_resp.results[0].resource_name
        created["video_asset"] = video_rn
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "video_asset", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        ag_service = client.get_service("AdGroupService")
        ag_op = client.get_type("AdGroupOperation")
        ag_op.create.name = f"{campaign_name} — Ad Group"
        ag_op.create.campaign = campaign_resource
        ag_op.create.status = client.enums.AdGroupStatusEnum.ENABLED
        ag_op.create.type_ = client.enums.AdGroupTypeEnum.VIDEO_RESPONSIVE
        ag_resp = ag_service.mutate_ad_groups(customer_id=cid, operations=[ag_op])
        ad_group_resource = ag_resp.results[0].resource_name
        created["ad_group"] = ad_group_resource
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "ad_group", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        ad_service = client.get_service("AdGroupAdService")
        ad_op = client.get_type("AdGroupAdOperation")
        ad_op.create.ad_group = ad_group_resource
        ad_op.create.status = client.enums.AdGroupAdStatusEnum.ENABLED
        ad_op.create.ad.final_urls.append(final_url)
        vra = ad_op.create.ad.video_responsive_ad
        for h in headlines:
            asset = client.get_type("AdTextAsset")
            asset.text = h
            vra.headlines.append(asset)
        for lh in long_headlines:
            asset = client.get_type("AdTextAsset")
            asset.text = lh
            vra.long_headlines.append(asset)
        for d in descriptions:
            asset = client.get_type("AdTextAsset")
            asset.text = d
            vra.descriptions.append(asset)
        vra.business_name = business_name
        vra.videos.append(client.get_type("AdVideoAsset"))
        vra.videos[0].asset = video_rn
        ad_resp = ad_service.mutate_ad_group_ads(customer_id=cid, operations=[ad_op])
        created["ad"] = ad_resp.results[0].resource_name
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "ad", "detail": _ex_detail(ex), "created_so_far": created}

    created["status"] = "aplicado"
    created["campanha_status"] = "PAUSED — revisar tudo e ativar manualmente quando pronto"
    return created


@server.tool()
def create_shopping_campaign(
    customer_id: str,
    campaign_name: str,
    daily_budget_brl: float,
    geo_target_ids: list[str],
    merchant_id: str,
    max_cpc_brl: float = 2.0,
    campaign_priority: int = 0,
    approval: str = "",
) -> dict[str, Any]:
    """Cria uma campanha Shopping: budget + campanha (com shopping_setting apontando pro
    Merchant Center) + geo + 1 ad group + 1 Shopping Product Ad (sem conteúdo manual — os
    anúncios vêm automaticamente do feed de produtos do Merchant Center). Sempre nasce PAUSED.

    merchant_id: ID da conta do Google Merchant Center **já linkada** a esta conta Google Ads
    (Ferramentas → Contas vinculadas → Merchant Center). Pré-requisito que a API não cria —
    precisa existir uma conta Merchant Center de verdade com feed de produto configurado.
    campaign_priority: 0 (baixa), 1 (média), 2 (alta) — usado quando há mais de uma campanha
    Shopping competindo pelos mesmos produtos.

    ⚠️ NÃO TESTADA end-to-end — a conta usada pra validar as outras tools não tem
    Merchant Center linkado (não vende por e-commerce), então não existe merchant_id
    real pra testar contra. Estrutura validada via introspecção do SDK (mesmo rigor das outras),
    mas nunca rodou contra a API de verdade. Testar antes de confiar em produção — primeiro erro
    provável é algo específico de conta com Merchant Center real conectado.

    MUTATION composta — exige approval."""
    if not merchant_id:
        return {"status": "erro_validacao", "erros": ["merchant_id: obrigatório"]}

    action_id = "create_shopping_campaign:" + _action_hash(
        customer_id=customer_id,
        campaign_name=campaign_name,
        daily_budget_brl=daily_budget_brl,
        geo_target_ids=geo_target_ids,
        merchant_id=merchant_id,
        max_cpc_brl=max_cpc_brl,
        campaign_priority=campaign_priority,
    )
    preview = {
        "customer_id": customer_id,
        "campaign_name": campaign_name,
        "daily_budget_brl": daily_budget_brl,
        "geo_target_ids": geo_target_ids,
        "merchant_id": merchant_id,
        "max_cpc_brl": max_cpc_brl,
        "campaign_priority": campaign_priority,
        "status_inicial": "PAUSED (sempre)",
        "aviso": "tool ainda não testada end-to-end contra a API real (precisa de Merchant Center real)",
    }
    pending = _confirm_or_preview(action_id, approval, preview)
    if pending:
        return pending

    client = _get_client()
    cid = customer_id.replace("-", "")
    max_cpc_micros = int(round(max_cpc_brl * 1_000_000))

    def _configure(camp: Any) -> None:
        camp.shopping_setting.merchant_id = int(merchant_id)
        camp.shopping_setting.campaign_priority = campaign_priority
        camp.manual_cpc.enhanced_cpc_enabled = False

    created, campaign_resource, err = _create_budget_campaign_shell(
        client, cid, campaign_name, daily_budget_brl, "SHOPPING", geo_target_ids, None, _configure
    )
    if err:
        return err

    try:
        ag_service = client.get_service("AdGroupService")
        ag_op = client.get_type("AdGroupOperation")
        ag_op.create.name = f"{campaign_name} — Ad Group"
        ag_op.create.campaign = campaign_resource
        ag_op.create.status = client.enums.AdGroupStatusEnum.ENABLED
        ag_op.create.type_ = client.enums.AdGroupTypeEnum.SHOPPING_PRODUCT_ADS
        ag_op.create.cpc_bid_micros = max_cpc_micros
        ag_resp = ag_service.mutate_ad_groups(customer_id=cid, operations=[ag_op])
        ad_group_resource = ag_resp.results[0].resource_name
        created["ad_group"] = ad_group_resource
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "ad_group", "detail": _ex_detail(ex), "created_so_far": created}

    try:
        ad_service = client.get_service("AdGroupAdService")
        ad_op = client.get_type("AdGroupAdOperation")
        ad_op.create.ad_group = ad_group_resource
        ad_op.create.status = client.enums.AdGroupAdStatusEnum.ENABLED
        ad_op.create.ad.shopping_product_ad.SetInParent()
        ad_resp = ad_service.mutate_ad_group_ads(customer_id=cid, operations=[ad_op])
        created["ad"] = ad_resp.results[0].resource_name
    except GoogleAdsException as ex:
        return {"status": "erro", "step": "ad", "detail": _ex_detail(ex), "created_so_far": created}

    created["status"] = "aplicado"
    created["campanha_status"] = "PAUSED — revisar tudo e ativar manualmente quando pronto"
    return created


if __name__ == "__main__":
    server.run(transport="stdio")
