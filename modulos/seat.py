"""
modulos/seat.py - SEAT: Edicao e Triagem
Modulo placeholder. Ser substituido na Fase 1.
"""

import streamlit as st

def renderizar(usuario: dict):
    """
    Funcao principal do modulo SEAT.
    Recebe os dados do usuario logado.
    """
    st.info("🔧 Modulo SEAT em desenvolvimento. Esta sera a nossa proxima fase de construcao.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
