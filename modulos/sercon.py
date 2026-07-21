# ==============================================================================
# ARQUIVO: modulos/sercon.py
# MISSÃO: Setor de Contas, Acórdãos, Cobranças e Monitoramento de Prazos (SERCON)
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from db_manager import conn, buscar_todos_paginado

# ------------------------------------------------------------------------------
# 1. ABA 1: ESTEIRA DE CONTAS E ACÓRDÃOS (FILA ATIVA DE TRABALHO)
# ------------------------------------------------------------------------------
def renderizar_esteira_sercon():
    st.markdown("### ⚖️ Esteira Ativa de Contas e Acórdãos")
    st.caption("Processos direcionados pelo radar da SEAT ou inseridos pela Chefia para monitoramento contábil, cobrança de multas e Tomadas de Contas Especiais (TCE).")
    
    col_filtro1, col_filtro2 = st.columns([2, 1])
    with col_filtro1:
        filtro_status = st.multiselect(
            "Filtrar por Fase Processual:",
            ["Pendente Análise Contábil", "Em Monitoramento de Prazo", "Aguardando Recolhimento / Cobrança", "Em Instrução de Acórdão"],
            default=["Pendente Análise Contábil", "Em Monitoramento de Prazo", "Aguardando Recolhimento / Cobrança"]
        )
    with col_filtro2:
        buscar_num = st.text_input("🔍 Localizar Processo:", placeholder="Ex: 00600-...")

    try:
        dados = buscar_todos_paginado("pauta_sercon")
        if not dados:
            st.info("✨ Nenhum processo na esteira da SERCON no momento. O setor está com a pauta limpa!")
            return
            
        df_sercon = pd.DataFrame(dados)
        
        # Filtro de status ativo (exclui os arquivados/concluídos)
        df_ativos = df_sercon[~df_sercon["status"].isin(["Concluído - Arquivado", "Retirado de Pauta"])]
        
        if filtro_status and "status" in df_ativos.columns:
            df_ativos = df_ativos[df_ativos["status"].isin(filtro_status)]
        if buscar_num and "processo" in df_ativos.columns:
            df_ativos = df_ativos[df_ativos["processo"].str.contains(buscar_num.strip(), case=False, na=False)]
            
        if df_ativos.empty:
            st.warning("Nenhum processo ativo encontrado com os filtros selecionados.")
            return

        st.markdown(f"**Volume em Monitoramento:** `{len(df_ativos)} processo(s)`")
        
        for idx, row in df_ativos.iterrows():
            with st.container(border=True):
                col_info, col_status, col_acao = st.columns([2.5, 1.5, 1.5])
                
                with col_info:
                    st.markdown(f"#### 📜 `{row.get('processo', 'S/N')}`")
                    st.markdown(f"**Relator:** `{row.get('relator', 'GAB')}` | **Origem do Gatilho:** <span style='color: #DD6B20; font-weight: 600;'>{row.get('motivo_gatilho', 'Inclusão Manual')}</span>", unsafe_allow_html=True)
                    st.caption(f"🕒 Data de Entrada na SERCON: {row.get('data_entrada', 'N/A')}")
                    
                with col_status:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(f"**Fase Atual:**")
                    st.markdown(f"<span style='background-color: #EBF8FF; color: #2B6CB0; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 13px;'>{row.get('status', 'Pendente')}</span>", unsafe_allow_html=True)
                    if row.get("analista_responsavel"):
                        st.caption(f"👤 Analista: **{row.get('analista_responsavel')}**")
                        
                with col_acao:
                    st.markdown("<br>", unsafe_allow_html=True)
                    id_reg = row.get("id")
                    status_atual = row.get("status", "Pendente Análise Contábil")
                    
                    # Botão de progressão de fase
                    if status_atual == "Pendente Análise Contábil":
                        if st.button("🔎 Iniciar Instrução", key=f"btn_inst_{id_reg}_{idx}", type="primary", use_container_width=True):
                            conn.table("pauta_sercon").update({
                                "status": "Em Monitoramento de Prazo",
                                "analista_responsavel": st.session_state.get("usuario_nome", "Analista SERCON")
                            }).eq("id", id_reg).execute()
                            st.success("Processo em instrução!")
                            st.rerun()
                            
                    elif status_atual == "Em Monitoramento de Prazo":
                        if st.button("💰 Emitir Cobrança / Acórdão", key=f"btn_cob_{id_reg}_{idx}", type="primary", use_container_width=True):
                            conn.table("pauta_sercon").update({
                                "status": "Aguardando Recolhimento / Cobrança"
                            }).eq("id", id_reg).execute()
                            st.success("Fase avançada para cobrança!")
                            st.rerun()
                            
                    elif status_atual == "Aguardando Recolhimento / Cobrança":
                        if st.button("✨ Atestar Cumprimento (Arquivar)", key=f"btn_arq_{id_reg}_{idx}", type="primary", use_container_width=True):
                            conn.table("pauta_sercon").update({
                                "status": "Concluído - Arquivado",
                                "data_conclusao": datetime.now().strftime("%d/%m/%Y %H:%M")
                            }).eq("id", id_reg).execute()
                            st.success("Acórdão cumprido! Processo arquivado com sucesso.")
                            st.rerun()
                            
                    # Opção de devoluçao para GAB ou SEAT caso tenha sido falso positivo
                    if st.button("↩️ Devolver (Não é Contas)", key=f"btn_dev_sercon_{id_reg}_{idx}", type="secondary", use_container_width=True):
                        conn.table("pauta_sercon").update({
                            "status": "Retirado de Pauta",
                            "motivo_gatilho": "Devolvido pela SERCON - Matéria não contábil"
                        }).eq("id", id_reg).execute()
                        st.warning("Processo removido da esteira da SERCON.")
                        st.rerun()

    except Exception as e:
        st.error(f"Erro ao carregar a pauta da SERCON: {e}")

# ------------------------------------------------------------------------------
# 2. ABA 2: VÁLVULA DE INJEÇÃO AVULSA (CADASTRO MANUAL DE TCE / ACÓRDÃOS)
# ------------------------------------------------------------------------------
def renderizar_injecao_sercon():
    st.markdown("### 📥 Entrada Avulsa de Processos na SERCON")
    st.caption("Cadastre Tomadas de Contas Especiais (TCEs), Acórdãos condenatórios antigos ou cobranças de multas diretamente no controle do setor.")
    
    with st.container(border=True):
        with st.form("form_avulso_sercon"):
            c1, c2, c3 = st.columns(3)
            with c1:
                num_proc = st.text_input("Nº do Processo / Acórdão:", placeholder="Ex: 00600-00014666/2023-71")
                relator = st.selectbox("Relator do Processo:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT", "GAB"], key="sercon_rel")
            with c2:
                tipo_materia = st.selectbox("Natureza da Matéria:", [
                    "Tomada de Contas Especial (TCE)",
                    "Acórdão - Cobrança de Débito/Multa",
                    "Monitoramento de Determinação Contábil",
                    "Recurso de Reconsideração em Contas"
                ])
                analista = st.text_input("Analista Responsável (Opcional):", value=st.session_state.get("usuario_nome", ""))
            with c3:
                fase_inicial = st.selectbox("Status de Entrada:", [
                    "Pendente Análise Contábil",
                    "Em Monitoramento de Prazo",
                    "Aguardando Recolhimento / Cobrança"
                ])
                obs = st.text_input("Observação / Acórdão nº:", placeholder="Ex: Acórdão nº 1234/2026 - Plenário")
                
            if st.form_submit_button("🚀 Injetar no Controle da SERCON", type="primary"):
                if num_proc.strip():
                    try:
                        novo_sercon = {
                            "processo": num_proc.strip(),
                            "relator": relator,
                            "motivo_gatilho": f"{tipo_materia} - {obs}".strip(" -"),
                            "status": fase_inicial,
                            "analista_responsavel": analista.strip() if analista else "Não atribuído",
                            "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                        }
                        conn.table("pauta_sercon").insert(novo_sercon).execute()
                        st.success(f"Processo {num_proc} catalogado com sucesso na base da SERCON!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao cadastrar processo: {e}. Verifique se a tabela 'pauta_sercon' existe no banco.")
                else:
                    st.warning("O número do processo é obrigatório.")

# ------------------------------------------------------------------------------
# 3. ABA 3: HISTÓRICO DE ACÓRDÃOS CUMPRIDOS E ARQUIVO
# ------------------------------------------------------------------------------
def renderizar_historico_sercon():
    st.markdown("### 📜 Histórico e Acórdãos Cumpridos")
    st.caption("Repositório de processos que tiveram o recolhimento de débitos atestado ou obrigações contábeis cumpridas.")
    
    try:
        dados = buscar_todos_paginado("pauta_sercon")
        if not dados:
            st.info("Nenhum registro histórico encontrado.")
            return
            
        df = pd.DataFrame(dados)
        df_hist = df[df["status"].isin(["Concluído - Arquivado", "Retirado de Pauta"])]
        
        if df_hist.empty:
            st.info("Nenhum acórdão ou processo de contas arquivado no momento.")
            return
            
        st.markdown(f"**Total Concluído / Arquivado:** `{len(df_hist)} processo(s)`")
        
        cols_show = [c for c in ["processo", "relator", "motivo_gatilho", "analista_responsavel", "status", "data_conclusao"] if c in df_hist.columns]
        st.dataframe(df_hist[cols_show], use_container_width=True, hide_index=True)
        
        csv_export = df_hist[cols_show].to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Baixar Relatório de Acórdãos Cumpridos (CSV)", 
            data=csv_export, 
            file_name=f"historico_sercon_{datetime.now().strftime('%Y%m%d')}.csv", 
            mime="text/csv"
        )
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

# ------------------------------------------------------------------------------
# 4. ABA 4: QUADRO DE AFASTAMENTOS (MODO LEITURA)
# ------------------------------------------------------------------------------
def renderizar_afastamentos_leitura():
    st.markdown("### 🏝️ Quadro de Férias e Afastamentos (Modo Leitura)")
    st.caption("Consulte a disponibilidade da equipe. O controle e lançamento de férias é realizado pela Chefia no módulo GAB.")
    try:
        afast = buscar_todos_paginado("afastamentos")
        if afast:
            df_af = pd.DataFrame(afast)
            st.dataframe(df_af[["usuario", "motivo", "data_inicio", "data_fim"]], use_container_width=True, hide_index=True)
        else:
            st.success("✨ Toda a equipe da SERCON está ativa e disponível!")
    except Exception:
        st.info("Quadro de afastamentos sem registros no momento.")

# ------------------------------------------------------------------------------
# 5. FUNÇÃO PRINCIPAL DO MÓDULO (PONTO DE ENTRADA DO ROTEADOR)
# ------------------------------------------------------------------------------
def run():
    st.markdown("<div style='font-size: 26px; font-weight: bold; color: #1E3A8A;'>⚖️ SERCON — Setor de Contas e Acórdãos</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size: 14px; color: #4B5563; margin-bottom: 20px; border-bottom: 2px solid #E5E7EB; padding-bottom: 8px;'>Monitoramento de Tomadas de Contas Especiais (TCE), Cobrança de Débitos e Prazos de Acórdãos</div>", unsafe_allow_html=True)
    
    t_esteira, t_injecao, t_hist, t_ferias = st.tabs([
        "⚖️ Esteira Ativa (Contas/Acórdãos)",
        "📥 Entrada Manual de TCE",
        "📜 Histórico / Cumpridos",
        "🏝️ Afastamentos (Leitura)"
    ])
    
    with t_esteira:
        renderizar_esteira_sercon()
    with t_injecao:
        renderizar_injecao_sercon()
    with t_hist:
        renderizar_historico_sercon()
    with t_ferias:
        renderizar_afastamentos_leitura()

if __name__ == "__main__":
    run()
