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
    st.markdown("### ⚖️ Esteira Ativa de Contas, Acórdãos e Tomadas de Contas (TCE)")
    st.caption("Processos direcionados pela Encruzilhada Lógica do Motor NIP ou inseridos pela Chefia para cálculo, monitoramento de prazos e cobrança de débitos.")
    
    col_filtro1, col_filtro2 = st.columns([2, 1])
    with col_filtro1:
        filtro_status = st.multiselect(
            "Filtrar por Fase Processual / Fiscal:",
            ["Pendente Análise Contábil", "Em Monitoramento de Prazo", "Aguardando Recolhimento / Cobrança", "Em Instrução de Acórdão"],
            default=["Pendente Análise Contábil", "Em Monitoramento de Prazo", "Aguardando Recolhimento / Cobrança", "Em Instrução de Acórdão"]
        )
    with col_filtro2:
        buscar_num = st.text_input("🔍 Localizar Processo / Acórdão:", placeholder="Ex: 00600-...")

    try:
        dados = buscar_todos_paginado("pauta_sercon")
        if not dados:
            st.info("✨ Nenhum processo na esteira da SERCON no momento. O setor está com a pauta limpa!")
            return
            
        df_sercon = pd.DataFrame(dados)
        
        # Filtro de status ativo (exclui os arquivados, concluídos e devolvidos)
        df_ativos = df_sercon[~df_sercon["status"].isin(["Concluído - Arquivado", "Retirado de Pauta", "Devolvido - Não Contábil"])]
        
        if filtro_status and "status" in df_ativos.columns:
            df_ativos = df_ativos[df_ativos["status"].isin(filtro_status)]
        if buscar_num and "processo" in df_ativos.columns:
            df_ativos = df_ativos[df_ativos["processo"].str.contains(buscar_num.strip(), case=False, na=False)]
            
        if df_ativos.empty:
            st.warning("Nenhum processo ativo encontrado com os filtros selecionados.")
            return

        st.markdown(f"**Volume Ativo em Monitoramento Fiscal:** `{len(df_ativos)} processo(s)`")
        
        for idx, row in df_ativos.iterrows():
            with st.container(border=True):
                col_info, col_status, col_acao = st.columns([2.3, 1.7, 1.8])
                
                with col_info:
                    st.markdown(f"#### 📜 `{row.get('processo', 'S/N')}`")
                    st.markdown(f"**Relator:** `{row.get('relator', 'GAB')}`")
                    st.markdown(f"**Origem do Gatilho:** <span style='color: #DD6B20; font-weight: 600;'>{row.get('motivo_gatilho', 'Inclusão Manual')}</span>", unsafe_allow_html=True)
                    if row.get("observacao"):
                        st.caption(f"📌 *Nota/Acórdão:* {row.get('observacao')}")
                    st.caption(f"🕒 Entrada na SERCON: {row.get('data_entrada', 'N/A')}")
                    
                with col_status:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(f"**Fase Fiscal Atual:**")
                    
                    # Cores adaptativas para cada fase da esteira contábil
                    status_atual = row.get("status", "Pendente Análise Contábil")
                    cor_bg = "#FEFCBF" if "Pendente" in status_atual else "#EBF8FF" if "Monitoramento" in status_atual else "#FED7D7"
                    cor_txt = "#744210" if "Pendente" in status_atual else "#2B6CB0" if "Monitoramento" in status_atual else "#9B2C2C"
                    
                    st.markdown(f"<span style='background-color: {cor_bg}; color: {cor_txt}; padding: 6px 10px; border-radius: 4px; font-weight: bold; font-size: 13px; display: inline-block; margin-bottom: 8px;'>{status_atual}</span>", unsafe_allow_html=True)
                    st.caption(f"👤 Analista: **{row.get('analista_responsavel', 'Não atribuído')}**")
                        
                with col_acao:
                    st.markdown("<br>", unsafe_allow_html=True)
                    id_reg = row.get("id")
                    
                    # FASE 1: INICIAR INSTRUÇÃO / CÁLCULO
                    if status_atual == "Pendente Análise Contábil":
                        if st.button("🔎 Iniciar Instrução / Cálculo", key=f"btn_inst_{id_reg}_{idx}", type="primary", use_container_width=True):
                            try:
                                conn.table("pauta_sercon").update({
                                    "status": "Em Monitoramento de Prazo",
                                    "analista_responsavel": st.session_state.get("usuario_nome", "Analista SERCON")
                                }).eq("id", id_reg).execute()
                                st.success("Instrução contábil iniciada! Prazos em monitoramento.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao atualizar: {e}")
                            
                    # FASE 2: EMISSÃO DE COBRANÇA OU ACÓRDÃO
                    elif status_atual == "Em Monitoramento de Prazo":
                        if st.button("💰 Emitir Cobrança / Acórdão", key=f"btn_cob_{id_reg}_{idx}", type="primary", use_container_width=True):
                            try:
                                conn.table("pauta_sercon").update({
                                    "status": "Aguardando Recolhimento / Cobrança"
                                }).eq("id", id_reg).execute()
                                st.success("Fase avançada para cobrança executiva e acompanhamento de recolhimento!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao atualizar: {e}")
                            
                    # FASE 3: ATESTADO DE CUMPRIMENTO E QUITAÇÃO
                    elif status_atual in ["Aguardando Recolhimento / Cobrança", "Em Instrução de Acórdão"]:
                        if st.button("✨ Atestar Quitação (Arquivar)", key=f"btn_arq_{id_reg}_{idx}", type="primary", use_container_width=True):
                            try:
                                conn.table("pauta_sercon").update({
                                    "status": "Concluído - Arquivado",
                                    "data_conclusao": datetime.now().strftime("%d/%m/%Y %H:%M")
                                }).eq("id", id_reg).execute()
                                st.success("✨ Débito quitado ou acórdão cumprido! Processo arquivado com sucesso.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao arquivar: {e}")
                            
                    # TRILHA DE DEVOLUÇÃO RÁPIDA (FALSO POSITIVO DO RADAR NIP)
                    if st.button("↩️ Devolver (Matéria Não Contábil)", key=f"btn_dev_sercon_{id_reg}_{idx}", type="secondary", use_container_width=True):
                        try:
                            conn.table("pauta_sercon").update({
                                "status": "Devolvido - Não Contábil",
                                "motivo_gatilho": "Devolvido pela SERCON - Matéria de natureza puramente administrativa/comum"
                            }).eq("id", id_reg).execute()
                            st.warning("Processo removido da esteira fiscal e catalogado como devolução.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao devolver: {e}")

    except Exception as e:
        st.error(f"🚨 Erro ao carregar a pauta da SERCON: {e}")

# ------------------------------------------------------------------------------
# 2. ABA 2: VÁLVULA DE INJEÇÃO AVULSA (CADASTRO MANUAL DE TCE / ACÓRDÃOS)
# ------------------------------------------------------------------------------
def renderizar_injecao_sercon():
    st.markdown("### 📥 Entrada Avulsa de Processos na SERCON (Válvula do Gestor)")
    st.caption("Cadastre Tomadas de Contas Especiais (TCEs), Acórdãos condenatórios legados ou cobranças de multas diretamente no controle do setor.")
    
    with st.container(border=True):
        with st.form("form_avulso_sercon"):
            st.markdown("#### 👤 Identificação do Processo e Matéria Contábil")
            c1, c2, c3 = st.columns(3)
            with c1:
                num_proc = st.text_input("Nº do Processo / Acórdão:", placeholder="Ex: 00600-00014666/2023-71")
                relator = st.selectbox("Relator do Processo:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT", "GAB"], key="sercon_rel")
            with c2:
                tipo_materia = st.selectbox("Natureza da Matéria / Gatilho:", [
                    "Tomada de Contas Especial (TCE)",
                    "Acórdão — Cobrança de Débito / Multa",
                    "Monitoramento de Determinação Contábil",
                    "Recurso de Reconsideração em Contas",
                    "Auditoria de Conformidade Financeira"
                ])
                analista = st.text_input("Analista Responsável:", value=st.session_state.get("usuario_nome", ""), placeholder="Nome do servidor atribuído")
            with c3:
                fase_inicial = st.selectbox("Status Fiscal Inicial:", [
                    "Pendente Análise Contábil",
                    "Em Monitoramento de Prazo",
                    "Aguardando Recolhimento / Cobrança",
                    "Em Instrução de Acórdão"
                ])
                obs = st.text_input("Observação / Referência:", placeholder="Ex: Acórdão nº 1234/2026 - Plenário (Débito solidário)")
                
            if st.form_submit_button("🚀 Injetar no Controle Ativo da SERCON", type="primary"):
                if num_proc.strip():
                    try:
                        novo_sercon = {
                            "processo": num_proc.strip(),
                            "relator": relator,
                            "motivo_gatilho": f"{tipo_materia}",
                            "status": fase_inicial,
                            "analista_responsavel": analista.strip() if analista else "Não atribuído",
                            "observacao": obs.strip(),
                            "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                        }
                        conn.table("pauta_sercon").insert(novo_sercon).execute()
                        st.success(f"✨ Processo `{num_proc}` catalogado com sucesso na base fiscal da SERCON!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Erro ao cadastrar processo: {e}. Verifique se a tabela 'pauta_sercon' possui todas as colunas necessárias no Supabase.")
                else:
                    st.warning("⚠️ O campo 'Nº do Processo' é obrigatório para o cadastro fiscal.")

# ------------------------------------------------------------------------------
# 3. ABA 3: HISTÓRICO DE ACÓRDÃOS CUMPRIDOS E ARQUIVO FISCAL
# ------------------------------------------------------------------------------
def renderizar_historico_sercon():
    st.markdown("### 📜 Histórico Fiscal e Acórdãos Cumpridos")
    st.caption("Repositório de processos que tiveram o recolhimento de débitos atestado, multas quitadas ou obrigações contábeis concluídas.")
    
    try:
        dados = buscar_todos_paginado("pauta_sercon")
        if not dados:
            st.info("Nenhum registro histórico encontrado na base da SERCON.")
            return
            
        df = pd.DataFrame(dados)
        df_hist = df[df["status"].isin(["Concluído - Arquivado", "Retirado de Pauta", "Devolvido - Não Contábil"])]
        
        if df_hist.empty:
            st.info("✨ Nenhum acórdão ou processo de contas arquivado ou devolvido no momento.")
            return
            
        st.markdown(f"**Total Concluído / Arquivado / Devolvido:** `{len(df_hist)} processo(s)`")
        
        cols_show = [c for c in ["processo", "relator", "motivo_gatilho", "analista_responsavel", "status", "data_conclusao", "observacao"] if c in df_hist.columns]
        st.dataframe(df_hist[cols_show], use_container_width=True, hide_index=True)
        
        col_down, _ = st.columns([1, 2])
        with col_down:
            csv_export = df_hist[cols_show].to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Baixar Relatório Fiscal (CSV)", 
                data=csv_export, 
                file_name=f"historico_sercon_{datetime.now().strftime('%Y%m%d')}.csv", 
                mime="text/csv",
                use_container_width=True
            )
    except Exception as e:
        st.error(f"🚨 Erro ao carregar histórico da SERCON: {e}")

# ------------------------------------------------------------------------------
# 4. ABA 4: QUADRO DE AFASTAMENTOS (MODO LEITURA)
# ------------------------------------------------------------------------------
def renderizar_afastamentos_leitura():
    st.markdown("### 🏝️ Quadro de Férias e Afastamentos (Modo Leitura)")
    st.caption("Consulte a disponibilidade dos analistas contábeis. O controle e lançamento de férias ou licenças é centralizado no módulo GAB.")
    try:
        afast = buscar_todos_paginado("afastamentos")
        if afast:
            df_af = pd.DataFrame(afast)
            st.dataframe(df_af[["usuario", "motivo", "data_inicio", "data_fim"]], use_container_width=True, hide_index=True)
        else:
            st.success("✨ Toda a equipe de analistas da SERCON está 100% ativa e disponível para instrução e monitoramento!")
    except Exception:
        st.info("Quadro de afastamentos sem registros no momento.")

# ------------------------------------------------------------------------------
# 5. FUNÇÃO PRINCIPAL DO MÓDULO (PONTO DE ENTRADA DO ROTEADOR)
# ------------------------------------------------------------------------------
def run():
    st.markdown("<div class='main-header'>⚖️ SERCON — Setor de Contas, Acórdãos e Cobranças</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Monitoramento de Tomadas de Contas Especiais (TCE), Cobrança de Débitos ao Erário e Instrução de Acórdãos</div>", unsafe_allow_html=True)
    
    t_esteira, t_injecao, t_hist, t_ferias = st.tabs([
        "⚖️ Esteira Ativa (Contas / TCE)",
        "📥 Entrada Manual de Acórdãos",
        "📜 Histórico Fiscal / Cumpridos",
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
