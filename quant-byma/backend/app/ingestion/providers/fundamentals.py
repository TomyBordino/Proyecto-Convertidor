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
MAX_PERIODS = 6


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
    """Primer concepto con datos → {fecha de cierre: valor}, tomando la presentación anual
    más reciente (las re-expresiones posteriores pisan a las originales)."""
    for cid in concept_ids:
        taxonomy, name = cid.split(":")
        concept = facts.get(taxonomy, {}).get(name)
        if not concept:
            continue
        picked = _unit_facts(concept, currency)
        if not picked:
            continue
        unit, rows = picked
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
        if best:
            return {d: v for d, (_, v) in best.items()}, unit
    return {}, None


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
        return parse_companyfacts(self.http.get_json(self.FACTS_URL.format(cik=cik)))


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
