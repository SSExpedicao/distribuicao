"""modulos/sercon.py - SERCON: Contas, Acordaos e Cobrancas"""

import streamlit as st

def renderizar(usuario: dict):
    st.info("🔧 Modulo SERCON em desenvolvimento.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
