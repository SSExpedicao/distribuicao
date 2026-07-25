"""modulos/gab.py - GAB: Torre de Controle (Gabinete)"""

import streamlit as st

def renderizar(usuario: dict, modo_edicao: bool = False):
    st.info("🔧 Modulo GAB em desenvolvimento.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
    st.markdown(f"**Modo edicao:** {'Ativo' if modo_edicao else 'Visualizacao'}")
