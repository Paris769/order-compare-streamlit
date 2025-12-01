"""
order_compare.py
~~~~~~~~~~~~~~~~~

This module provides a simple utility for comparing two order documents that
have been parsed into structured JSON format.  Each order is expected to be
represented as a dictionary with a top-level key ``"righe"`` containing a
list of line items.  Each line item is a dictionary with the following keys:

- ``codice``: a unique product code (string).
- ``descrizione``: a textual description of the product (string).
- ``quantita``: the quantity ordered (numeric, may be int or float).
- ``unita_misura``: unit of measure, e.g. "PZ", "cartoni" (string or None).
- ``prezzo_unitario``: unit price (numeric or None).
- ``totale_riga``: total amount for the line (numeric or None).

The ``compare_orders`` function will iterate over the line items of each
document and produce a structured result highlighting differences.  It
identifies:

* lines present in the original order but missing in the confirmation;
* lines present in the confirmation but missing in the original order;
* lines present in both documents but with differences in quantity,
  unit price or total amount;
* potential mismatches due to differing units of measure (e.g. pieces vs
  cartons) by comparing the total amounts.

The result is returned as a dictionary which can easily be serialised to
JSON for further processing or fed into another AI model to generate a
natural language report.

Example usage::

    from order_compare import compare_orders

    order_json = {"righe": [...]}      # parsed from the original PDF
    confirm_json = {"righe": [...]}    # parsed from the supplier's PDF

    diff = compare_orders(order_json, confirm_json)
    print(diff)

This script does not perform any IO on its own.  It is designed to be used
as a helper within a Zapier ``Code by Zapier`` step, a standalone Python
service, or integrated into a Streamlit or Flask app.

"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _parse_number(value: Any) -> Optional[float]:
    """Attempt to coerce a value into a float.  Returns None if the value is
    not numeric or is None.

    Parameters
    ----------
    value : Any
        The input value from the JSON.  Strings containing comma as decimal
        separators are also handled.

    Returns
    -------
    Optional[float]
        The numeric value as a float, or None if conversion is not possible.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    # handle strings like "1,234" or "1.234"
    if isinstance(value, str):
        # replace comma decimal separator with dot and remove thousand separators
        cleaned = value.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def compare_orders(
    original: Dict[str, Any], confirmation: Dict[str, Any], *, tolerance: float = 0.05
) -> Dict[str, Any]:
    """Compare two order documents and return a summary of discrepancies.

    Parameters
    ----------
    original : dict
        JSON structure of the original order (parsed from the customer's PDF).
    confirmation : dict
        JSON structure of the supplier's confirmation (parsed from their PDF).
    tolerance : float, optional
        Relative difference threshold used to flag potential unit-of-measure
        mismatches (e.g. piece vs carton).  A value of 0.05 means that if
        the difference in total amounts is within ±5% but quantities differ,
        the function will mark the discrepancy as a possible unit mismatch.

    Returns
    -------
    dict
        A dictionary with three keys:

        ``"differenze"``: list of dicts for items present in both documents but
        with discrepancies; each dict includes the product code and the
        differing values.
        ``"righe_mancanti_nella_conferma"``: list of line items from the
        original order that are absent from the confirmation.
        ``"righe_extra_nella_conferma"``: list of line items from the
        confirmation not found in the original order.
    """
    orig_lines: List[Dict[str, Any]] = original.get("righe", []) or []
    conf_lines: List[Dict[str, Any]] = confirmation.get("righe", []) or []

    # Build dictionaries for quick lookup
    orig_dict: Dict[str, Dict[str, Any]] = {
        (line.get("codice") or "").strip(): line for line in orig_lines
        if line.get("codice") is not None
    }
    conf_dict: Dict[str, Dict[str, Any]] = {
        (line.get("codice") or "").strip(): line for line in conf_lines
        if line.get("codice") is not None
    }

    differences: List[Dict[str, Any]] = []
    missing_in_conf: List[Dict[str, Any]] = []
    extra_in_conf: List[Dict[str, Any]] = []

    # Identify missing items and discrepancies
    for code, o_line in orig_dict.items():
        if code not in conf_dict:
            missing_in_conf.append(o_line)
            continue
        c_line = conf_dict[code]
        discrepancy: Dict[str, Any] = {"codice": code}

        # Compare quantities
        o_qta = _parse_number(o_line.get("quantita"))
        c_qta = _parse_number(c_line.get("quantita"))
        if o_qta is not None and c_qta is not None and o_qta != c_qta:
            discrepancy["quantita"] = (o_qta, c_qta)

        # Compare unit price
        o_price = _parse_number(o_line.get("prezzo_unitario"))
        c_price = _parse_number(c_line.get("prezzo_unitario"))
        if o_price is not None and c_price is not None and o_price != c_price:
            discrepancy["prezzo_unitario"] = (o_price, c_price)

        # Compare total line amounts
        o_total = _parse_number(o_line.get("totale_riga"))
        c_total = _parse_number(c_line.get("totale_riga"))
        if o_total is not None and c_total is not None and o_total != c_total:
            discrepancy["totale_riga"] = (o_total, c_total)

        # Flag potential unit mismatch if quantities differ but totals are close
        if (
            o_qta is not None
            and c_qta is not None
            and o_qta != c_qta
            and o_total is not None
            and c_total is not None
        ):
            # Compute relative difference of totals
            if o_total != 0:
                rel_diff = abs(o_total - c_total) / o_total
                if rel_diff < tolerance:
                    discrepancy.setdefault("nota", []).append(
                        "Possibile differenza unità di misura (pezzi vs cartoni)."
                    )

        # Add discrepancy if any differences were found
        if len(discrepancy) > 1:
            differences.append(discrepancy)

    # Identify extra items in confirmation
    for code, c_line in conf_dict.items():
        if code not in orig_dict:
            extra_in_conf.append(c_line)

    return {
        "differenze": differences,
        "righe_mancanti_nella_conferma": missing_in_conf,
        "righe_extra_nella_conferma": extra_in_conf,
    }


if __name__ == "__main__":  # simple test when run as a script
    import json
    import sys

    if len(sys.argv) != 3:
        print(
            "Usage: python order_compare.py <original_order.json> <confirmation_order.json>",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        orig = json.load(f)
    with open(sys.argv[2], "r", encoding="utf-8") as f:
        conf = json.load(f)
    result = compare_orders(orig, conf)
    print(json.dumps(result, indent=2, ensure_ascii=False))