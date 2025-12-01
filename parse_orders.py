"""
parse_orders.py
================

This module provides a utility function to extract structured data from an
order or confirmation PDF.  It uses the ``pdftotext`` command‑line tool
available in the container to convert the PDF into a fixed‑width text
representation and then parses each line to identify product rows.

The parser assumes that the PDF has a table with a header containing
"Codice Fornitore" and "Descrizione".  After this header, each product
row begins with a four‑digit article code followed by a supplier code,
then various fields including unit of measure, quantity, unit price,
discount, line total and tax.  The parser extracts the following
information for each row:

``codice``
    Four digit article code.

``codice_fornitore``
    The supplier’s internal code for the article.

``descrizione``
    A brief description of the article.  In many cases the description
    may be empty because multi‑line descriptions in the original PDF are
    difficult to align with the row on which the numeric data appears.

``unita_misura``
    Unit of measure (for example ``PZ`` for pieces).

``quantita``
    Quantity ordered or confirmed, as a float.

``prezzo_unitario``
    Unit price, converted from the comma/period notation used in
    European PDF exports.

``importo``
    Line total (quantity * price), converted to a float.

The module exposes a single function ``parse_items(pdf_path: str) -> list``
which returns a list of dictionaries in the format described above.  It is
intended to be used as part of a larger pipeline—for example, reading
both the original order and the supplier confirmation, comparing the
rows using ``order_compare.compare_orders`` and generating a report.

Example::

    from parse_orders import parse_items
    from order_compare import compare_orders

    order_items = parse_items("357_madal_28.11.25.pdf")
    confirm_items = parse_items("confirmation.pdf")
    result = compare_orders({'righe': order_items}, {'righe': confirm_items})
    print(result)

Note
----
This parser relies on ``pdftotext`` being installed and accessible in
the system’s PATH.  The container used for this project includes
``pdftotext``, but if you run this script elsewhere you may need to
install Poppler (which provides ``pdftotext``) for your platform.
"""

from __future__ import annotations

import re
import subprocess
from typing import List, Dict

__all__ = ["parse_items"]


def _parse_number(token: str) -> float:
    """Convert a number from European format (with commas as decimal
    separator and optional dots as thousand separators) to a float.

    Parameters
    ----------
    token : str
        The token extracted from the PDF.

    Returns
    -------
    float
        The numeric value of the token.
    """
    return float(token.replace(".", "").replace(",", "."))


def parse_items(pdf_path: str) -> List[Dict[str, object]]:
    """Parse an order or confirmation PDF and return a list of row
    dictionaries.

    This function uses the ``pdftotext`` command‑line utility to convert
    the PDF into a text representation with fixed column widths.  It
    scans for the table header containing "Codice Fornitore" and
    "Descrizione" to detect the start of the items table.  Each row of
    the table is expected to begin with a four‑digit article code.  The
    function extracts the numeric fields by splitting on whitespace and
    assumes the following layout for each row::

        [codice] [codice_fornitore] [description words ...] [UM] [qty]
        [unit_price] [discount] [importo] [iva]

    Since discount and tax (IVA) are not needed for the comparison, they
    are parsed but discarded.  The remaining values are converted to
    floats using the helper function ``_parse_number``.

    Parameters
    ----------
    pdf_path : str
        Absolute or relative path to the PDF file.

    Returns
    -------
    List[Dict[str, object]]
        A list of dictionaries, each representing one product line with
        keys ``codice``, ``codice_fornitore``, ``descrizione``,
        ``unita_misura``, ``quantita``, ``prezzo_unitario`` and
        ``importo``.
    """
    # Run pdftotext and capture the output.  The '-layout' option
    # preserves the visual alignment of columns, which makes it easier
    # to split on whitespace.
    raw_text = subprocess.check_output(["pdftotext", "-layout", pdf_path, "-"]).decode("utf-8")
    lines = raw_text.split("\n")

    items: List[Dict[str, object]] = []
    table_started = False

    for line in lines:
        # Look for the header row signalling the start of the table
        if not table_started:
            if "Codice Fornitore" in line and "Descrizione" in line:
                table_started = True
            continue
        # Stop reading rows when the totals section begins
        if "Totale Merce" in line:
            break
        stripped = line.strip()
        if not stripped:
            continue
        # Each data row starts with a 4‑digit article code
        if re.match(r"^\d{4}\b", stripped):
            parts = re.split(r"\s+", stripped)
            if len(parts) < 8:
                # Skip malformed rows
                continue
            code = parts[0]
            supplier_code = parts[1]
            remainder = parts[2:]
            if len(remainder) < 6:
                continue
            # The last six tokens are: UM, quantity, unit price, discount,
            # importo, IVA.  The description may be empty.
            unita_misura = remainder[-6]
            quantity_token = remainder[-5]
            price_token = remainder[-4]
            discount_token = remainder[-3]  # Unused
            importo_token = remainder[-2]
            iva_token = remainder[-1]      # Unused
            description = " ".join(remainder[:-6]).strip()
            try:
                quantity = _parse_number(quantity_token)
                price_unit = _parse_number(price_token)
                importo = _parse_number(importo_token)
            except ValueError:
                # Skip rows with invalid numeric values
                continue
            items.append({
                "codice": code,
                "codice_fornitore": supplier_code,
                "descrizione": description,
                "unita_misura": unita_misura,
                "quantita": quantity,
                "prezzo_unitario": price_unit,
                "importo": importo,
            })
    return items


if __name__ == "__main__":
    import json
    import argparse

    parser = argparse.ArgumentParser(description="Parse a PDF order or confirmation file into JSON")
    parser.add_argument("pdf", help="Path to the PDF file to parse")
    parser.add_argument("output", help="Output JSON file path")
    args = parser.parse_args()

    data = parse_items(args.pdf)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"righe": data}, f, ensure_ascii=False, indent=2)
    print(f"Extracted {len(data)} rows from {args.pdf} and wrote to {args.output}")