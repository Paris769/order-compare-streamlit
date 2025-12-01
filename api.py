"""
Flask API for order confirmation comparison.

This module exposes a REST endpoint that accepts two PDF files via
multipart/form-data. The first file should represent the original
order, and the second file should represent the supplier's confirmation.

Upon receiving the files, the API extracts line-item data from each
PDF using the `parse_orders` module, compares the two sets of items
using the `order_compare` module, and returns a JSON response
describing any differences. If the files match exactly, the response
will indicate no discrepancies.

To run this API locally, execute:

    FLASK_APP=api.py flask run --host=0.0.0.0 --port=8000

Ensure that the dependencies listed in requirements.txt are installed.
Note: This API relies on the system `pdftotext` utility via the
`parse_orders` module. When deploying, ensure that Poppler (which
provides `pdftotext`) is available on the server, or adjust
`parse_orders.py` to use a pure-Python PDF parser.
"""

from __future__ import annotations

import os
import tempfile
from flask import Flask, request, jsonify

try:
    from parse_orders import parse_items  # type: ignore
    from order_compare import compare_orders  # type: ignore
except ImportError:
    # Fallback import when the modules are in a different package structure.
    from .parse_orders import parse_items  # type: ignore
    from .order_compare import compare_orders  # type: ignore

app = Flask(__name__)

@app.route("/compare", methods=["POST"])
def compare_files() -> tuple[object, int]:
    """
    Compare two PDF documents via uploaded files.

    Expects a multipart/form-data POST request with two file fields:
      - order: the original order PDF
      - confirm: the supplier's confirmation PDF

    Returns a JSON response with the comparison result or an error
    message if the request is malformed.
    """
    # Validate presence of files
    order_file = request.files.get("order")
    confirm_file = request.files.get("confirm")
    if not order_file or not confirm_file:
        return jsonify({"error": "Both 'order' and 'confirm' files are required."}), 400

    # Save uploaded files to temporary locations
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as order_temp:
        order_file.save(order_temp.name)
        order_path = order_temp.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as confirm_temp:
        confirm_file.save(confirm_temp.name)
        confirm_path = confirm_temp.name

    try:
        # Parse the PDF files into structured data
        order_items = parse_items(order_path)
        confirm_items = parse_items(confirm_path)

        # Package into JSON-like dicts for comparison
        order_json = {"righe": order_items}
        confirm_json = {"righe": confirm_items}

        # Compute differences
        comparison_result = compare_orders(order_json, confirm_json)

        return jsonify(comparison_result), 200
    except Exception as exc:  # noqa: BLE001
        # Catch any unexpected errors and return them as JSON
        return jsonify({"error": str(exc)}), 500
    finally:
        # Clean up temporary files
        for path in (order_path, confirm_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
