"""modulos/semand.py - SEMAND: Mandados e Diligencias"""

import streamlit as st

def renderizar(usuario: dict, modo_edicao: bool = False):
    st.info("🔧 Modulo SEMAND em desenvolvimento.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
    st.markdown(f"**Modo edicao:** {'Ativo' if modo_edicao else 'Visualizacao'}")
