# ==============================================================================
# ARQUIVO: modulos/semand.py
# MISSÃO: Setor de Mandados, Notificações e Diligências Externas (SEMAND)
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from db_manager import conn, buscar_todos_paginado

# ------------------------------------------------------------------------------
# 1. ABA 1: FILA ATIVA DE MANDADOS E DILIGÊNCIAS
# ------------------------------------------------------------------------------
def renderizar_fila_mandados():
    st.markdown("### 📑 Fila Ativa de Mandados e Notificações")
    st.caption("Controle de expedição de mandados de citação, notificação, diligências externas e comunicados urgentes.")
    
    col_filtro1, col_filtro2 = st.columns([2, 1])
    with col_filtro1:
        filtro_status = st.multiselect(
            "Filtrar por Status do Mandado:",
            ["Aguardando Expedição de Mandado", "Em Cumprimento / Diligência", "Aguardando Aviso de Recebimento (AR)"],
            default=["Aguardando Expedição de Mandado", "Em Cumprimento / Diligência"]
        )
    with col_filtro2:
        buscar_num = st.text_input("🔍 Localizar Processo / Mandado:", placeholder="Ex: 00600-...")

    try:
        dados = buscar_todos_paginado("pauta_semand")
        if not dados:
            st.info("✨ Nenhum mandado pendente na fila da SEMAND no momento. Estrutura pronta e aguardando demandas!")
            return
            
        df_semand = pd.DataFrame(dados)
        
        # Filtra apenas mandados em andamento (exclui os arquivados)
        df_ativos = df_semand[~df_semand["status"].isin(["Cumprido - Arquivado", "Cancelado / Devolvido"])]
        
        if filtro_status and "status" in df_ativos.columns:
            df_ativos = df_ativos[df_ativos["status"].isin(filtro_status)]
        if buscar_num and "processo" in df_ativos.columns:
            df_ativos = df_ativos[df_ativos["processo"].str.contains(buscar_num.strip(), case=False, na=False)]
            
        if df_ativos.empty:
            st.warning("Nenhum mandado encontrado com os filtros selecionados.")
            return

        st.markdown(f"**Mandados em Andamento:** `{len(df_ativos)}`")
        
        for idx, row in df_ativos.iterrows():
            with st.container(border=True):
                col_info, col_status, col_acao = st.columns([2.5, 1.5, 1.5])
                
                with col_info:
                    badge_urg = "🚨 **[URGENTE]** | " if row.get("urgente") == 1 else ""
                    st.markdown(f"#### {badge_urg}Mandado — Processo `{row.get('processo', 'S/N')}`")
                    st.markdown(f"**Destinatário/Alvo:** `{row.get('destinatario', 'Não especificado')}`")
                    if row.get("observacao"):
                        st.caption(f"📌 *Nota/Diligência:* {row.get('observacao')}")
                    st.caption(f"🕒 Entrada na SEMAND: {row.get('data_entrada', 'N/A')} | Relator: **{row.get('relator', 'GAB')}**")
                    
                with col_status:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(f"**Fase Atual:**")
                    st.markdown(f"<span style='background-color: #FEFCBF; color: #744210; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 13px;'>{row.get('status', 'Pendente')}</span>", unsafe_allow_html=True)
                    if row.get("oficial_responsavel"):
                        st.caption(f"👤 Oficial/Analista: **{row.get('oficial_responsavel')}**")
                        
                with col_acao:
                    st.markdown("<br>", unsafe_allow_html=True)
                    id_reg = row.get("id")
                    status_atual = row.get("status", "Aguardando Expedição de Mandado")
                    
                    # Botão de progressão de fase do mandado
                    if status_atual == "Aguardando Expedição de Mandado":
                        if st.button("📨 Emitir Mandado", key=f"btn_emit_{id_reg}_{idx}", type="primary", use_container_width=True):
                            conn.table("pauta_semand").update({
                                "status": "Em Cumprimento / Diligência",
                                "oficial_responsavel": st.session_state.get("usuario_nome", "Analista SEMAND")
                            }).eq("id", id_reg).execute()
                            st.success("Mandado emitido para cumprimento!")
                            st.rerun()
                            
                    elif status_atual == "Em Cumprimento / Diligência":
                        if st.button("📫 Registrar Envio / AR", key=f"btn_ar_{id_reg}_{idx}", type="primary", use_container_width=True):
                            conn.table("pauta_semand").update({
                                "status": "Aguardando Aviso de Recebimento (AR)"
                            }).eq("id", id_reg).execute()
                            st.success("Envio registrado! Aguardando retorno do AR.")
                            st.rerun()
                            
                    elif status_atual == "Aguardando Aviso de Recebimento (AR)":
                        if st.button("✨ Atestar Cumprimento", key=f"btn_cump_{id_reg}_{idx}", type="primary", use_container_width=True):
                            conn.table("pauta_semand").update({
                                "status": "Cumprido - Arquivado",
                                "data_conclusao": datetime.now().strftime("%d/%m/%Y %H:%M")
                            }).eq("id", id_reg).execute()
                            st.success("Mandado cumprido e arquivado com sucesso!")
                            st.rerun()
                            
                    if st.button("🚫 Cancelar Mandado", key=f"btn_canc_{id_reg}_{idx}", type="secondary", use_container_width=True):
                        conn.table("pauta_semand").update({
                            "status": "Cancelado / Devolvido",
                            "observacao": "🚫 Cancelado/Devolvido pela SEMAND"
                        }).eq("id", id_reg).execute()
                        st.warning("Mandado cancelado e removido da fila ativa.")
                        st.rerun()

    except Exception as e:
        st.error(f"Erro ao carregar a pauta da SEMAND: {e}")

# ------------------------------------------------------------------------------
# 2. ABA 2: REGISTRO AVULSO DE MANDADOS (BASE DE ESPERA PARA O FUTURO)
# ------------------------------------------------------------------------------
def renderizar_injecao_semand():
    st.markdown("### 📥 Emissão Manual de Mandados (Módulo Avulso)")
    st.caption("Cadastre mandados de citação, intimação de pauta ou diligências externas diretamente na base da SEMAND.")
    
    with st.container(border=True):
        with st.form("form_avulso_semand"):
            c1, c2, c3 = st.columns(3)
            with c1:
                num_proc = st.text_input("Nº do Processo:", placeholder="Ex: 00600-00000000/2026-00")
                relator = st.selectbox("Relator:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT", "GAB"], key="semand_rel")
            with c2:
                destinatario = st.text_input("Destinatário / Jurisdicionado:", placeholder="Ex: Secretaria de Saúde - SES/DF ou Nome do Gestor")
                tipo_mandado = st.selectbox("Tipo de Documento:", [
                    "Mandado de Citação",
                    "Mandado de Notificação / Intimação",
                    "Diligência de Inspeção / Vistoria",
                    "Comunicado de Urgência"
                ])
            with c3:
                e_urgente = st.checkbox("🚨 Cumprimento Urgente / Prioritário?", value=False)
                obs = st.text_input("Observação / Prazo Legal:", placeholder="Ex: Prazo de 5 dias úteis (Decisão nº 4494)")
                
            if st.form_submit_button("🚀 Emitir e Cadastrar Mandado", type="primary"):
                if num_proc.strip() and destinatario.strip():
                    try:
                        novo_mandado = {
                            "processo": num_proc.strip(),
                            "relator": relator,
                            "destinatario": destinatario.strip(),
                            "status": "Aguardando Expedição de Mandado",
                            "urgente": 1 if e_urgente else 0,
                            "observacao": f"{tipo_mandado} — {obs}".strip(" —"),
                            "oficial_responsavel": "Não atribuído",
                            "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                        }
                        conn.table("pauta_semand").insert(novo_mandado).execute()
                        st.success(f"Mandado para o processo {num_proc} registrado na SEMAND!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao cadastrar mandado: {e}. Verifique se a tabela 'pauta_semand' existe no banco.")
                else:
                    st.warning("Os campos 'Nº do Processo' e 'Destinatário' são obrigatórios.")

# ------------------------------------------------------------------------------
# 3. ABA 3: HISTÓRICO E ARQUIVO DE MANDADOS CUMPRIDOS
# ------------------------------------------------------------------------------
def renderizar_historico_semand():
    st.markdown("### 📜 Histórico de Mandados e Diligências")
    st.caption("Arquivo geral de mandados que já tiveram seus Avisos de Recebimento (AR) confirmados ou diligências concluídas.")
    
    try:
        dados = buscar_todos_paginado("pauta_semand")
        if not dados:
            st.info("Nenhum mandado arquivado no momento.")
            return
            
        df = pd.DataFrame(dados)
        df_hist = df[df["status"].isin(["Cumprido - Arquivado", "Cancelado / Devolvido"])]
        
        if df_hist.empty:
            st.info("Nenhum registro histórico concluído no momento.")
            return
            
        st.markdown(f"**Total Arquivado:** `{len(df_hist)} mandado(s)`")
        
        cols_show = [c for c in ["processo", "relator", "destinatario", "oficial_responsavel", "status", "data_conclusao", "observacao"] if c in df_hist.columns]
        st.dataframe(df_hist[cols_show], use_container_width=True, hide_index=True)
        
        csv_export = df_hist[cols_show].to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Baixar Relatório de Mandados (CSV)", 
            data=csv_export, 
            file_name=f"historico_semand_{datetime.now().strftime('%Y%m%d')}.csv", 
            mime="text/csv"
        )
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

# ------------------------------------------------------------------------------
# 4. ABA 4: QUADRO DE AFASTAMENTOS (MODO LEITURA)
# ------------------------------------------------------------------------------
def renderizar_afastamentos_leitura():
    st.markdown("### 🏝️ Quadro de Férias e Afastamentos (Modo Leitura)")
    st.caption("Consulte a disponibilidade dos oficiais e analistas. A gestão e alteração de afastamentos fica centralizada no painel do GAB.")
    try:
        afast = buscar_todos_paginado("afastamentos")
        if afast:
            df_af = pd.DataFrame(afast)
            st.dataframe(df_af[["usuario", "motivo", "data_inicio", "data_fim"]], use_container_width=True, hide_index=True)
        else:
            st.success("✨ Toda a equipe da SEMAND está ativa e disponível!")
    except Exception:
        st.info("Quadro de afastamentos sem registros no momento.")

# ------------------------------------------------------------------------------
# 5. FUNÇÃO PRINCIPAL DO MÓDULO (PONTO DE ENTRADA DO ROTEADOR)
# ------------------------------------------------------------------------------
def run():
    st.markdown("<div style='font-size: 26px; font-weight: bold; color: #1E3A8A;'>📁 SEMAND — Setor de Mandados e Diligências</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size: 14px; color: #4B5563; margin-bottom: 20px; border-bottom: 2px solid #E5E7EB; padding-bottom: 8px;'>Expedição de Mandados de Citação, Intimação de Pauta e Controle de Avisos de Recebimento (AR)</div>", unsafe_allow_html=True)
    
    t_fila, t_injecao, t_hist, t_ferias = st.tabs([
        "📑 Fila de Mandados (Ativos)",
        "📥 Registro de Mandado (Avulso)",
        "📜 Histórico / Arquivo",
        "🏝️ Afastamentos (Leitura)"
    ])
    
    with t_fila:
        renderizar_fila_mandados()
    with t_injecao:
        renderizar_injecao_semand()
    with t_hist:
        renderizar_historico_semand()
    with t_ferias:
        renderizar_afastamentos_leitura()

if __name__ == "__main__":
    run()
