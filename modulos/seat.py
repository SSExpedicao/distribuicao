"""modulos/seat.py - SEAT: Edicao e Triagem"""

import streamlit as st

def renderizar(usuario: dict, modo_edicao: bool = False):
    st.info("🔧 Modulo SEAT em desenvolvimento. Esta sera a nossa proxima fase de construcao.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
    st.markdown(f"**Modo edicao:** {'Ativo' if modo_edicao else 'Visualizacao'}")
