"""Annual final HS data with explicit dimensions, raw archives and hard gates."""
from __future__ import annotations
import json
import math
import os
from . import archive, countries
from .sources import http, comtrade


def number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a trade measurement")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"Invalid nonnegative measurement: {value!r}")
    return result


def normalize(payload, query, limit):
    if not isinstance(payload, dict) or payload.get("errorMessage") or payload.get("error"):
        raise ValueError("Comtrade error or changed response schema")
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Comtrade returned no rows: {query}")
    if len(rows) >= limit:
        raise ValueError(f"Comtrade response reached cap {limit}; split query or use a larger subscription limit")
    if payload.get("count") is not None and int(payload["count"]) != len(rows):
        raise ValueError("Comtrade count mismatch: potentially incomplete response")
    required = {"period", "cmdCode", "reporterCode", "reporterISO", "partnerCode", "partnerISO",
                "flowCode", "primaryValue", "netWgt", "qty", "qtyUnitCode",
                "partner2Code", "customsCode", "motCode", "freqCode", "typeCode"}
    seen, result = set(), []
    for row in rows:
        if not isinstance(row, dict) or not required <= row.keys():
            raise ValueError("Comtrade missing required columns")
        for key in ("period", "cmdCode", "flowCode", "partner2Code", "customsCode", "motCode"):
            if str(row[key]) != str(query[key]):
                raise ValueError(f"Unexpected Comtrade dimension {key}: {row[key]}")
        if row["freqCode"] != "A" or row["typeCode"] != "C":
            raise ValueError("Expected annual goods data")
        for key in ("reporterCode", "partnerCode"):
            if query.get(key) not in (None, "") and str(row[key]) != str(query[key]):
                raise ValueError(f"Unexpected requested {key}")
        if int(row["reporterCode"]) in comtrade.NON_COUNTRY_REPORTERS:
            continue
        reporter = countries.normalize(row.get("reporterDesc"), code=row["reporterISO"])
        if int(row["partnerCode"]) == 0:
            partner = "W00"
        elif int(row["partnerCode"]) in comtrade.NON_COUNTRY_REPORTERS:
            continue
        else:
            partner = countries.normalize(row.get("partnerDesc"), code=row["partnerISO"])
        if not reporter or not partner:
            raise ValueError("Country dimension could not be normalized")
        identity = (int(row["period"]), row["cmdCode"], reporter, partner, row["flowCode"])
        if identity in seen:
            raise ValueError(f"Duplicate trade key (including classification overlap): {identity}")
        seen.add(identity)
        net, qty = number(row["netWgt"]), number(row["qty"])
        # Zero is retained as zero, never silently converted into missing.
        weight = net if net is not None else (qty if int(row["qtyUnitCode"]) == 8 else None)
        result.append({"year": identity[0], "hs_code": row["cmdCode"], "reporter": reporter,
                       "partner": partner, "flow": row["flowCode"],
                       "value_usd": number(row["primaryValue"]), "net_weight_kg": net,
                       "quantity": qty, "unit": row.get("qtyUnitAbbr"),
                       "weight_t": None if weight is None else weight / 1000,
                       "weight_source": "netWgt" if net is not None else ("qty_kg" if weight is not None else "missing"),
                       "is_estimated": row.get("isNetWgtEstimated"),
                       "classification": row.get("classificationCode")})
    if not result:
        raise ValueError("No country trade rows remain")
    return result


def fetch(root, hs_code, year, flow, *, reporter="", partner="", max_records=100000):
    key = os.environ.get("COMTRADE_API_KEY", "").strip()
    limit = max_records if key else 500
    query = {"period": str(year), "cmdCode": hs_code, "flowCode": flow,
             "reporterCode": str(reporter), "partnerCode": str(partner),
             "partner2Code": "0", "customsCode": "C00", "motCode": "0",
             "maxRecords": limit, "includeDesc": "true", "breakdownMode": "classic"}
    url = comtrade.FULL_URL if key else comtrade.PREVIEW_URL
    headers = {"Ocp-Apim-Subscription-Key": key} if key else {}
    body = http.get(url, params=query, headers=headers, use_cache=False)
    reference = archive.save(root, "comtrade", body, url=url, query=query)
    rows = normalize(json.loads(body), query, limit)
    for row in rows:
        row["raw_path"] = reference["path"]
        row["retrieved_at"] = reference["retrieved_at"]
    return rows, reference
