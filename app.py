import streamlit as st
import json
from parse_orders import parse_items
from order_compare import compare_orders

st.title("Confronto Ordini")

order_file = st.file_uploader("Carica il PDF dell'ordine originale", type="pdf")
confirm_file = st.file_uploader("Carica il PDF della conferma", type="pdf")

if order_file and confirm_file:
    # Save uploaded files to temporary files
    with open("order_temp.pdf", "wb") as f:
        f.write(order_file.getvalue())
    with open("confirm_temp.pdf", "wb") as f:
        f.write(confirm_file.getvalue())

    order_items = parse_items("order_temp.pdf")
    confirm_items = parse_items("confirm_temp.pdf")

    result = compare_orders({"righe": order_items}, {"righe": confirm_items})

    st.header("Risultato del confronto")
    st.json(result)
