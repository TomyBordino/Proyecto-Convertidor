"""Importación de la cartera desde archivos.

Formatos aceptados:
- Excel o CSV de **Movimientos de Balanz** (columnas Concertación, Tipo, Descripción, Ticker,
  Cantidad, Precio, Liquidación, Moneda, Importe): se reconstruyen las tenencias y su costo
  promedio ponderado en dólares MEP a partir de las operaciones.
- CSV simple de tenencias: ticker, cantidad, precio (promedio), moneda (ARS/USD) y fecha
  opcional.
"""

from __future__ import annotations

import io
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

# (monto, moneda, fecha) → (usd_mep, ars)
Converter = Callable[[float, str, date | None], tuple[float, float]]


def _norm(text: object) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_number(v: object) -> float | None:
    """Números en formato argentino ("1.234,56") o estándar."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, int | float):
        return float(v)
    s = str(v).strip().replace("$", "").replace("US", "").replace(" ", "")
    if not s or s in ("-", "--"):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(v: object) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def currency_of(text: object) -> str:
    """ARS, MEP o CABLE según la descripción de moneda de Balanz."""
    t = _norm(text)
    if "cable" in t or "u$s" in t or "7000" in t or "exterior" in t:
        return "CABLE"
    if "dolar" in t or "usd" in t or t in ("us$", "u$d", "mep"):
        return "MEP"
    return "ARS"


@dataclass
class Position:
    quantity: float = 0.0
    cost_usd: float = 0.0
    cost_ars: float = 0.0
    income_usd: float = 0.0
    opened_at: date | None = None


@dataclass
class ImportResult:
    kind: str  # "balanz" | "tenencias"
    positions: dict[str, Position]
    rows_used: int = 0
    rows_skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Lee Excel o CSV y ubica la fila de encabezados (Balanz agrega filas de título)."""
    if filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raw = pd.read_excel(io.BytesIO(content), header=None, dtype=object)
    else:
        text = content.decode("utf-8-sig", errors="replace")
        raw = pd.read_csv(io.StringIO(text), header=None, sep=None, engine="python", dtype=object)
    for i in range(min(len(raw), 30)):
        cells = {_norm(c) for c in raw.iloc[i].tolist()}
        if "ticker" in cells or "especie" in cells:
            df = raw.iloc[i + 1 :].copy()
            df.columns = [_norm(c) for c in raw.iloc[i].tolist()]
            return df.dropna(how="all")
    raise ValueError("No se encontró la fila de encabezados (se esperaba una columna Ticker)")


def _col(df: pd.DataFrame, *names: str) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


def import_file(content: bytes, filename: str, convert: Converter) -> ImportResult:
    df = read_table(content, filename)
    if _col(df, "importe") and _col(df, "concertacion", "fecha"):
        return _from_movements(df, convert)
    return _from_holdings(df, convert)


def _from_holdings(df: pd.DataFrame, convert: Converter) -> ImportResult:
    tcol = _col(df, "ticker", "especie")
    qcol = _col(df, "cantidad", "nominales", "quantity")
    pcol = _col(df, "precio", "precio promedio", "ppc", "costo")
    mcol = _col(df, "moneda")
    dcol = _col(df, "fecha")
    if not tcol or not qcol:
        raise ValueError("El archivo de tenencias necesita columnas Ticker y Cantidad")
    out = ImportResult("tenencias", {})
    for _, r in df.iterrows():
        ticker = str(r[tcol] or "").strip().upper()
        qty = parse_number(r[qcol])
        if not ticker or ticker == "NAN" or not qty:
            out.rows_skipped += 1
            continue
        pos = Position(quantity=qty, opened_at=parse_date(r[dcol]) if dcol else None)
        price = parse_number(r[pcol]) if pcol else None
        if price:
            cur = currency_of(r[mcol]) if mcol else "ARS"
            pos.cost_usd, pos.cost_ars = convert(qty * price, cur, pos.opened_at)
        out.positions[ticker] = pos
        out.rows_used += 1
    return out


SKIP = ("suscripcion desde balanz", "rescate a balanz", "operacion diferida", "caucion")
NO_COST = ("dividendo en acciones", "split", "reverse", "cambio de ratio")
INCOME = ("dividendo", "renta")


def _from_movements(df: pd.DataFrame, convert: Converter) -> ImportResult:
    c = {
        "date": _col(df, "concertacion", "fecha"),
        "tipo": _col(df, "tipo"),
        "desc": _col(df, "descripcion"),
        "ticker": _col(df, "ticker", "especie"),
        "qty": _col(df, "cantidad"),
        "price": _col(df, "precio"),
        "cur": _col(df, "moneda"),
        "amount": _col(df, "importe"),
    }
    if not c["ticker"] or not c["qty"]:
        raise ValueError("El Excel de movimientos necesita columnas Ticker y Cantidad")
    df = df.assign(_d=df[c["date"]].map(parse_date)).sort_values("_d", kind="stable")
    out = ImportResult("balanz", {})
    pos = out.positions
    for _, r in df.iterrows():
        ticker = str(r[c["ticker"]] or "").strip().upper()
        text = _norm(f"{r[c['tipo']] if c['tipo'] else ''} {r[c['desc']] if c['desc'] else ''}")
        qty = parse_number(r[c["qty"]]) or 0.0
        amount = parse_number(r[c["amount"]]) if c["amount"] else None
        cur = currency_of(r[c["cur"]]) if c["cur"] else "ARS"
        day = r["_d"]
        if not ticker or ticker == "NAN" or any(k in text for k in SKIP):
            out.rows_skipped += 1
            continue
        p = pos.setdefault(ticker, Position())
        if any(k in text for k in NO_COST) and qty:
            p.quantity += qty  # cambia la cantidad sin costo
        elif any(k in text for k in INCOME) and not qty:
            if amount and amount > 0:
                p.income_usd += convert(amount, cur, day)[0]
        elif qty > 0:
            # Compra o transferencia recibida: el costo es lo pagado (o cantidad × precio).
            gross = abs(amount) if amount else qty * (parse_number(r[c["price"]]) or 0.0)
            usd, ars = convert(gross, cur, day)
            if p.quantity <= 1e-9:
                p.opened_at, p.cost_usd, p.cost_ars = day, 0.0, 0.0
            p.quantity += qty
            p.cost_usd += usd
            p.cost_ars += ars
            if not amount and "transferencia" in text:
                out.warnings.append(
                    f"{ticker}: transferencia recibida valuada al precio informado "
                    "(no es el costo original)"
                )
        elif qty < 0:
            if p.quantity <= 1e-9:
                out.warnings.append(f"{ticker}: venta sin tenencia previa en el archivo ({day})")
                out.rows_skipped += 1
                continue
            frac = min(1.0, -qty / p.quantity)
            p.cost_usd *= 1 - frac
            p.cost_ars *= 1 - frac
            p.quantity += qty
        else:
            out.rows_skipped += 1
            continue
        out.rows_used += 1
    out.positions = {t: p for t, p in pos.items() if p.quantity > 1e-9}
    return out
