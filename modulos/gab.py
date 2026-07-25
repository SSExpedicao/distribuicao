"""modulos/gab.py - GAB: Torre de Controle (Gabinete)"""

import streamlit as st

def renderizar(usuario: dict):
    st.info("🔧 Modulo GAB em desenvolvimento.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
