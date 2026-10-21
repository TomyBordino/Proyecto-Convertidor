"""Fuentes reales de estados contables anuales.

- SecEdgarSource: XBRL "companyfacts" de la SEC (gratis, oficial). Cubre todos los
  subyacentes de CEDEARs que presentan 10-K y los emisores extranjeros con 20-F en XBRL
  (incluidos los ADRs argentinos, que reportan en IFRS y en pesos). Requiere un
  User-Agent con contacto real (política de acceso de la SEC).
- FmpSource: Financial Modeling Prep (QB_FMP_API_KEY), útil como respaldo.

Las acciones locales sin ADR no tienen una API estructurada de calidad (la CNV publica
PDFs); quedan sin fundamentales y el scoring re-normaliza los pesos.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any, Protocol

from app.analytics.fundamental import FinancialStatement
from app.ingestion.providers.base import ProviderError
from app.ingestion.providers.http import HttpClient

log = logging.getLogger(__name__)

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
QUARTERLY_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A"}
MAX_TTM_PERIODS = 48
# Ejercicios a conservar: los balances XBRL de la SEC arrancan en 2009; el modelo los usa
# "point in time" para validar el factor de valuación con historia larga.
MAX_PERIODS = 18


class FundamentalsSource(Protocol):
    name: str

    def fundamentals(self, symbol: str) -> list[FinancialStatement]: ...


# campo → conceptos candidatos en orden de preferencia (us-gaap primero, luego IFRS).
DURATION_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "us-gaap:SalesRevenueNet",
        "ifrs-full:Revenue",
        "ifrs-full:RevenueFromContractsWithCustomers",
    ),
    "ebit": ("us-gaap:OperatingIncomeLoss", "ifrs-full:ProfitLossFromOperatingActivities"),
    "net_income": (
        "us-gaap:NetIncomeLoss",
        "us-gaap:ProfitLoss",
        "ifrs-full:ProfitLossAttributableToOwnersOfParent",
        "ifrs-full:ProfitLoss",
    ),
    "depreciation": (
        "us-gaap:DepreciationDepletionAndAmortization",
        "us-gaap:DepreciationAndAmortization",
        "us-gaap:DepreciationAmortizationAndAccretionNet",
        "ifrs-full:DepreciationAndAmortisationExpense",
        "ifrs-full:DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
    ),
    "operating_cash_flow": (
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        "ifrs-full:CashFlowsFromUsedInOperatingActivities",
    ),
    "capex": (
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquireProductiveAssets",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipment",
    ),
    "tax_rate": ("us-gaap:EffectiveIncomeTaxRateContinuingOperations",),
    # Respaldos cuando no hay un concepto total (ver parse_companyfacts).
    "depreciation_only": (
        "us-gaap:Depreciation",
        "us-gaap:DepreciationNonproduction",
        "us-gaap:DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
    ),
    "amortization_intangibles": ("us-gaap:AmortizationOfIntangibleAssets",),
    "pretax_income": (
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "ifrs-full:ProfitLossBeforeTax",
    ),
    "interest_expense": (
        "us-gaap:InterestExpense",
        "us-gaap:InterestExpenseNonoperating",
        "us-gaap:InterestExpenseDebt",
        "ifrs-full:InterestExpense",
    ),
    "diluted_shares": (
        "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
        "ifrs-full:AdjustedWeightedAverageShares",
        "ifrs-full:WeightedAverageShares",
    ),
}

INSTANT_CONCEPTS: dict[str, tuple[str, ...]] = {
    "total_assets": ("us-gaap:Assets", "ifrs-full:Assets"),
    "total_liabilities": ("us-gaap:Liabilities", "ifrs-full:Liabilities"),
    "current_assets": ("us-gaap:AssetsCurrent", "ifrs-full:CurrentAssets"),
    "current_liabilities": ("us-gaap:LiabilitiesCurrent", "ifrs-full:CurrentLiabilities"),
    "equity": (
        "us-gaap:StockholdersEquity",
        "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "ifrs-full:EquityAttributableToOwnersOfParent",
        "ifrs-full:Equity",
    ),
    "cash": (
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "ifrs-full:CashAndCashEquivalents",
    ),
    "retained_earnings": (
        "us-gaap:RetainedEarningsAccumulatedDeficit",
        "ifrs-full:RetainedEarnings",
    ),
    "liabilities_and_equity": (
        "us-gaap:LiabilitiesAndStockholdersEquity",
        "ifrs-full:EquityAndLiabilities",
    ),
    # Deuda: se suman los componentes disponibles (ver _total_debt).
    "lt_debt_total": ("us-gaap:LongTermDebt",),
    "lt_debt_noncurrent": (
        "us-gaap:LongTermDebtNoncurrent",
        "ifrs-full:NoncurrentPortionOfNoncurrentBorrowings",
        "ifrs-full:NoncurrentBorrowings",
    ),
    "lt_debt_current": (
        "us-gaap:LongTermDebtCurrent",
        "us-gaap:DebtCurrent",
        "ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
        "ifrs-full:CurrentBorrowings",
    ),
    "short_term_borrowings": ("us-gaap:ShortTermBorrowings", "us-gaap:CommercialPaper"),
    "ifrs_borrowings": ("ifrs-full:Borrowings",),
    "shares_outstanding": ("dei:EntityCommonStockSharesOutstanding",),
}


def _days(fact: dict) -> int | None:
    if "start" not in fact:
        return None
    return (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days


def _unit_facts(concept: dict, prefer_currency: str | None) -> tuple[str, list[dict]] | None:
    units: dict[str, list[dict]] = concept.get("units", {})
    if not units:
        return None
    for key in (prefer_currency, "USD", "shares", "pure"):
        if key and key in units:
            return key, units[key]
    key = next(iter(units))
    return key, units[key]


def annual_values(
    facts: dict, concept_ids: tuple[str, ...], duration: bool, currency: str | None
) -> tuple[dict[date, float], str | None]:
    """{fecha de cierre: valor} combinando conceptos por período.

    Las empresas cambian de concepto con el tiempo (p. ej. Apple pasó de `Revenues` a
    `RevenueFromContractWithCustomerExcludingAssessedTax` en 2018), así que cada ejercicio
    toma el primer concepto, en orden de preferencia, que lo informe. Dentro de un concepto
    gana la presentación más reciente (las re-expresiones pisan a las originales).
    """
    merged: dict[date, float] = {}
    unit_used: str | None = currency
    for cid in concept_ids:
        taxonomy, name = cid.split(":")
        concept = facts.get(taxonomy, {}).get(name)
        if not concept:
            continue
        picked = _unit_facts(concept, unit_used)
        if not picked:
            continue
        unit, rows = picked
        if unit_used is not None and unit != unit_used:
            continue  # no mezclar monedas entre conceptos
        best: dict[date, tuple[str, float]] = {}
        for f in rows:
            if f.get("form") not in ANNUAL_FORMS or "end" not in f:
                continue
            days = _days(f)
            if duration and (days is None or not 330 <= days <= 400):
                continue
            if not duration and days is not None:
                continue
            end = date.fromisoformat(f["end"])
            filed = f.get("filed", "")
            if end not in best or filed >= best[end][0]:
                best[end] = (filed, float(f["val"]))
        if not best:
            continue
        unit_used = unit
        for d, (_, v) in best.items():
            merged.setdefault(d, v)
    return merged, (unit_used if merged else None)


def _total_debt(v: dict[str, float | None]) -> float | None:
    parts = [v.get("short_term_borrowings")]
    if v.get("lt_debt_total") is not None:
        parts.append(v["lt_debt_total"])
    else:
        parts += [v.get("lt_debt_noncurrent"), v.get("lt_debt_current")]
    if all(p is None for p in parts) and v.get("ifrs_borrowings") is not None:
        return v["ifrs_borrowings"]
    present = [p for p in parts if p is not None]
    return sum(present) if present else None


def _nearest(series: dict[date, float], target: date, tolerance_days: int = 120) -> float | None:
    """Valor más cercano a `target` (p. ej. acciones en circulación de la portada del 10-K,
    fechadas semanas después del cierre del ejercicio)."""
    candidates = [(abs((d - target).days), v) for d, v in series.items() if d >= target]
    candidates = [c for c in candidates if c[0] <= tolerance_days]
    return min(candidates)[1] if candidates else None


def parse_companyfacts(payload: dict) -> list[FinancialStatement]:
    facts = payload.get("facts", {})
    revenue, currency = annual_values(facts, DURATION_CONCEPTS["revenue"], True, None)
    if currency is None:
        net, currency = annual_values(facts, DURATION_CONCEPTS["net_income"], True, None)
        if currency is None:
            return []
    if currency in ("shares", "pure"):
        return []

    duration = {k: annual_values(facts, c, True, currency)[0] for k, c in DURATION_CONCEPTS.items()}
    instant = {k: annual_values(facts, c, False, currency)[0] for k, c in INSTANT_CONCEPTS.items()}
    # Las acciones vienen en unidad "shares": se buscan sin preferir la moneda.
    duration["diluted_shares"] = annual_values(
        facts, DURATION_CONCEPTS["diluted_shares"], True, "shares"
    )[0]
    cover_shares: dict[date, float] = {}
    concept = facts.get("dei", {}).get("EntityCommonStockSharesOutstanding")
    if concept:
        for f in concept.get("units", {}).get("shares", []):
            if f.get("form") in ANNUAL_FORMS:
                cover_shares[date.fromisoformat(f["end"])] = float(f["val"])

    ends = sorted(set(duration["revenue"]) | set(duration["net_income"]))[-MAX_PERIODS:]
    out = []
    for end in ends:
        v: dict[str, float | None] = {k: s.get(end) for k, s in {**duration, **instant}.items()}
        if (
            v["total_liabilities"] is None
            and v["liabilities_and_equity"] is not None
            and v["equity"] is not None
        ):
            v["total_liabilities"] = v["liabilities_and_equity"] - v["equity"]
        if v["ebit"] is None and v["pretax_income"] is not None:
            # Sin resultado operativo (petroleras, farmacéuticas): EBIT ≈ resultado antes de
            # impuestos + intereses.
            v["ebit"] = v["pretax_income"] + (v["interest_expense"] or 0.0)
        if v["depreciation"] is None and v["depreciation_only"] is not None:
            v["depreciation"] = v["depreciation_only"] + (v["amortization_intangibles"] or 0.0)
        ebitda = None
        if v["ebit"] is not None and v["depreciation"] is not None:
            ebitda = v["ebit"] + v["depreciation"]
        shares = _nearest(cover_shares, end) or v["diluted_shares"]
        out.append(
            FinancialStatement(
                period_end=end,
                currency=currency,
                revenue=v["revenue"],
                ebit=v["ebit"],
                ebitda=ebitda,
                net_income=v["net_income"],
                total_assets=v["total_assets"],
                total_liabilities=v["total_liabilities"],
                current_assets=v["current_assets"],
                current_liabilities=v["current_liabilities"],
                equity=v["equity"],
                total_debt=_total_debt(v),
                cash=v["cash"],
                retained_earnings=v["retained_earnings"],
                operating_cash_flow=v["operating_cash_flow"],
                capex=v["capex"],
                shares_outstanding=shares,
                tax_rate=v["tax_rate"],
            )
        )
    return out


def _quarter_flows(rows: list[dict]) -> dict[date, float]:
    """Valor de cada trimestre (3 meses) por fecha de cierre. Usa los hechos trimestrales
    directos y, si faltan, la diferencia entre acumulados del mismo ejercicio (p. ej. el
    cuarto trimestre = anual − nueve meses)."""
    spans: dict[tuple[date, date], tuple[str, float]] = {}
    for f in rows:
        if f.get("form") not in QUARTERLY_FORMS or "start" not in f or "end" not in f:
            continue
        key = (date.fromisoformat(f["start"]), date.fromisoformat(f["end"]))
        filed = f.get("filed", "")
        if key not in spans or filed >= spans[key][0]:
            spans[key] = (filed, float(f["val"]))
    out: dict[date, float] = {}
    for (start, end), (_, v) in spans.items():
        if 80 <= (end - start).days <= 100:
            out[end] = v
    by_start: dict[date, list[tuple[date, float]]] = {}
    for (start, end), (_, v) in spans.items():
        by_start.setdefault(start, []).append((end, v))
    for lst in by_start.values():
        lst.sort()
        for (e1, v1), (e2, v2) in zip(lst, lst[1:], strict=False):
            if 80 <= (e2 - e1).days <= 100 and e2 not in out:
                out[e2] = v2 - v1
    return out


def _ttm(quarters: dict[date, float]) -> dict[date, float]:
    """Suma de 4 trimestres consecutivos (cierres separados por 70–110 días)."""
    ends = sorted(quarters)
    out = {}
    for i in range(3, len(ends)):
        chain = ends[i - 3 : i + 1]
        if all(70 <= (b - a).days <= 110 for a, b in zip(chain, chain[1:], strict=False)):
            out[ends[i]] = sum(quarters[e] for e in chain)
    return out


def _concept_rows(facts: dict, concept_ids: tuple[str, ...], currency: str) -> list[list[dict]]:
    groups = []
    for cid in concept_ids:
        taxonomy, name = cid.split(":")
        concept = facts.get(taxonomy, {}).get(name)
        if not concept:
            continue
        rows = concept.get("units", {}).get(currency)
        if rows:
            groups.append(rows)
    return groups


def ttm_values(facts: dict, concept_ids: tuple[str, ...], currency: str) -> dict[date, float]:
    merged: dict[date, float] = {}
    for rows in _concept_rows(facts, concept_ids, currency):
        for d, v in _ttm(_quarter_flows(rows)).items():
            merged.setdefault(d, v)
    return merged


def quarter_instants(facts: dict, concept_ids: tuple[str, ...], currency: str) -> dict[date, float]:
    merged: dict[date, float] = {}
    for rows in _concept_rows(facts, concept_ids, currency):
        best: dict[date, tuple[str, float]] = {}
        for f in rows:
            if f.get("form") not in QUARTERLY_FORMS or "start" in f or "end" not in f:
                continue
            end = date.fromisoformat(f["end"])
            filed = f.get("filed", "")
            if end not in best or filed >= best[end][0]:
                best[end] = (filed, float(f["val"]))
        for d, (_, v) in best.items():
            merged.setdefault(d, v)
    return merged


def parse_quarterly_ttm(
    payload: dict, annual: list[FinancialStatement]
) -> list[FinancialStatement]:
    """Últimos 12 meses a cada cierre trimestral posterior al primer ejercicio anual, para
    cierres que no coinciden con un ejercicio ya informado (10-Q de emisores de EE. UU.)."""
    if not annual:
        return []
    facts = payload.get("facts", {})
    currency = annual[-1].currency
    flows: dict[str, dict[date, float]] = {
        k: ttm_values(facts, DURATION_CONCEPTS[k], currency)
        for k in (
            "revenue",
            "ebit",
            "net_income",
            "depreciation",
            "depreciation_only",
            "amortization_intangibles",
            "operating_cash_flow",
            "capex",
            "pretax_income",
            "interest_expense",
        )
        if k in DURATION_CONCEPTS
    }
    inst = {k: quarter_instants(facts, c, currency) for k, c in INSTANT_CONCEPTS.items()}
    cover: dict[date, float] = {}
    concept = facts.get("dei", {}).get("EntityCommonStockSharesOutstanding")
    if concept:
        for f in concept.get("units", {}).get("shares", []):
            if f.get("form") in QUARTERLY_FORMS:
                cover[date.fromisoformat(f["end"])] = float(f["val"])
    annual_ends = {s.period_end for s in annual}
    first = min(annual_ends)
    ends = sorted(
        e
        for e in set(flows.get("revenue", {})) | set(flows.get("net_income", {}))
        if e > first and all(abs((e - a).days) > 20 for a in annual_ends)
    )[-MAX_TTM_PERIODS:]
    out = []
    for end in ends:
        series: dict[str, dict[date, float]] = {**flows, **inst}
        v: dict[str, float | None] = {k: s.get(end) for k, s in series.items()}
        if (
            v.get("total_liabilities") is None
            and v.get("liabilities_and_equity") is not None
            and v.get("equity") is not None
        ):
            v["total_liabilities"] = v["liabilities_and_equity"] - v["equity"]  # type: ignore[operator]
        if v.get("ebit") is None and v.get("pretax_income") is not None:
            v["ebit"] = v["pretax_income"] + (v.get("interest_expense") or 0.0)  # type: ignore[operator]
        if v.get("depreciation") is None and v.get("depreciation_only") is not None:
            v["depreciation"] = v["depreciation_only"] + (v.get("amortization_intangibles") or 0.0)  # type: ignore[operator]
        ebitda = None
        if v.get("ebit") is not None and v.get("depreciation") is not None:
            ebitda = v["ebit"] + v["depreciation"]  # type: ignore[operator]
        out.append(
            FinancialStatement(
                period_end=end,
                currency=currency,
                revenue=v.get("revenue"),
                ebit=v.get("ebit"),
                ebitda=ebitda,
                net_income=v.get("net_income"),
                total_assets=v.get("total_assets"),
                total_liabilities=v.get("total_liabilities"),
                current_assets=v.get("current_assets"),
                current_liabilities=v.get("current_liabilities"),
                equity=v.get("equity"),
                total_debt=_total_debt(v),
                cash=v.get("cash"),
                retained_earnings=v.get("retained_earnings"),
                operating_cash_flow=v.get("operating_cash_flow"),
                capex=v.get("capex"),
                shares_outstanding=_nearest(cover, end),
                period_type="TTM",
            )
        )
    return out


class SecEdgarSource:
    name = "sec_edgar"
    TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

    def __init__(self, http: HttpClient) -> None:
        self.http = http
        self._ciks: dict[str, int] | None = None

    def cik(self, symbol: str) -> int | None:
        if self._ciks is None:
            data = self.http.get_json(self.TICKERS_URL)
            self._ciks = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
        # La SEC usa "BRK-B"; algunos listados usan "BRK.B".
        s = symbol.upper()
        return self._ciks.get(s) or self._ciks.get(s.replace("-", "."))

    def fundamentals(self, symbol: str) -> list[FinancialStatement]:
        cik = self.cik(symbol)
        if cik is None:
            raise ProviderError(f"{symbol} no figura en el listado de emisores de la SEC")
        payload = self.http.get_json(self.FACTS_URL.format(cik=cik))
        annual = parse_companyfacts(payload)
        ttm = parse_quarterly_ttm(payload, annual)
        return sorted(annual + ttm, key=lambda s: s.period_end)


FMP_FIELDS = {
    "revenue": ("income", "revenue"),
    "ebit": ("income", "operatingIncome"),
    "ebitda": ("income", "ebitda"),
    "net_income": ("income", "netIncome"),
    "tax_rate": ("income", "_tax_rate"),
    "total_assets": ("balance", "totalAssets"),
    "total_liabilities": ("balance", "totalLiabilities"),
    "current_assets": ("balance", "totalCurrentAssets"),
    "current_liabilities": ("balance", "totalCurrentLiabilities"),
    "equity": ("balance", "totalStockholdersEquity"),
    "total_debt": ("balance", "totalDebt"),
    "cash": ("balance", "cashAndCashEquivalents"),
    "retained_earnings": ("balance", "retainedEarnings"),
    "operating_cash_flow": ("cash", "operatingCashFlow"),
    "capex": ("cash", "capitalExpenditure"),
    "shares_outstanding": ("income", "weightedAverageShsOutDil"),
}


def parse_fmp(
    income: list[dict], balance: list[dict], cash: list[dict]
) -> list[FinancialStatement]:
    by_date: dict[str, dict[str, dict]] = defaultdict(dict)
    for kind, rows in (("income", income), ("balance", balance), ("cash", cash)):
        for r in rows:
            if r.get("date"):
                by_date[r["date"]][kind] = r
    out = []
    for d in sorted(by_date)[-MAX_PERIODS:]:
        parts = by_date[d]
        inc = parts.get("income", {})
        if inc.get("incomeBeforeTax"):
            inc = {**inc, "_tax_rate": (inc.get("incomeTaxExpense") or 0) / inc["incomeBeforeTax"]}
        parts = {**parts, "income": inc}
        values: dict[str, Any] = {}
        for field, (kind, key) in FMP_FIELDS.items():
            raw = parts.get(kind, {}).get(key)
            values[field] = float(raw) if isinstance(raw, int | float) else None
        currency = (
            inc.get("reportedCurrency") or parts.get("balance", {}).get("reportedCurrency") or "USD"
        )
        out.append(
            FinancialStatement(period_end=date.fromisoformat(d[:10]), currency=currency, **values)
        )
    return out


class FmpSource:
    name = "fmp"
    BASE = "https://financialmodelingprep.com/stable"

    def __init__(self, http: HttpClient, api_key: str) -> None:
        self.http = http
        self.api_key = api_key

    def _get(self, endpoint: str, symbol: str) -> list[dict]:
        data = self.http.get_json(
            f"{self.BASE}/{endpoint}",
            params={
                "symbol": symbol,
                "period": "annual",
                "limit": MAX_PERIODS,
                "apikey": self.api_key,
            },
        )
        if not isinstance(data, list):
            raise ProviderError(f"FMP {endpoint} devolvió un formato inesperado para {symbol}")
        return data

    def fundamentals(self, symbol: str) -> list[FinancialStatement]:
        return parse_fmp(
            self._get("income-statement", symbol),
            self._get("balance-sheet-statement", symbol),
            self._get("cash-flow-statement", symbol),
        )
