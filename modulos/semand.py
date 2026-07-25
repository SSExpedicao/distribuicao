"""modulos/semand.py - SEMAND: Mandados e Diligencias"""

import streamlit as st

def renderizar(usuario: dict):
    st.info("🔧 Modulo SEMAND em desenvolvimento.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
