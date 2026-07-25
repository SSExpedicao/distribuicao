"""modulos/sexp.py - SEXP: Expedicao (S.A.D.E.)"""

import streamlit as st

def renderizar(usuario: dict):
    st.info("🔧 Modulo SEXP em desenvolvimento.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
