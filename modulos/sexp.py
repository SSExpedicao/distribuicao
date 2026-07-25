"""modulos/sexp.py - SEXP: Expedicao (S.A.D.E.)"""

import streamlit as st

def renderizar(usuario: dict, modo_edicao: bool = False):
    st.info("🔧 Modulo SEXP em desenvolvimento.")
    st.markdown(f"**Usuario:** {usuario.get('nome', 'N/A')} | **Cargo:** {usuario.get('cargo', 'N/A')}")
    st.markdown(f"**Modo edicao:** {'Ativo' if modo_edicao else 'Visualizacao'}")
