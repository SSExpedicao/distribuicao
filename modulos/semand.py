import streamlit as st
import pandas as pd
from datetime import datetime
from db_manager import conn, buscar_todos_paginado

# ------------------------------------------------------------------------------
# 1. ABA 1: FILA ATIVA DE MANDADOS E DILIGÊNCIAS
# ------------------------------------------------------------------------------
def renderizar_fila_mandados():
    st.markdown("### 📑 Fila Ativa de Mandados, Citações e Notificações")
    st.caption("Controle de expedição de mandados, diligências externas e monitoramento de retornos de Avisos de Recebimento (AR).")
    
    col_filtro1, col_filtro2 = st.columns([2, 1])
    with col_filtro1:
        filtro_status = st.multiselect(
            "Filtrar por Status Operacional:",
            ["Aguardando Expedição de Mandado", "Em Cumprimento / Diligência", "Aguardando Aviso de Recebimento (AR)"],
            default=["Aguardando Expedição de Mandado", "Em Cumprimento / Diligência", "Aguardando Aviso de Recebimento (AR)"]
        )
    with col_filtro2:
        buscar_num = st.text_input("🔍 Localizar Processo / Alvo:", placeholder="Ex: 00600-... ou SES/DF")

    try:
        dados = buscar_todos_paginado("pauta_semand")
        if not dados:
            st.info("✨ Nenhum mandado pendente na fila da SEMAND no momento. Estrutura pronta e aguardando demandas!")
            return
            
        df_semand = pd.DataFrame(dados)
        
        # Filtra apenas mandados em andamento (exclui arquivados, cancelados e devolvidos)
        df_ativos = df_semand[~df_semand["status"].isin(["Cumprido - Arquivado", "Cancelado / Devolvido"])]
        
        if filtro_status and "status" in df_ativos.columns:
            df_ativos = df_ativos[df_ativos["status"].isin(filtro_status)]
            
        if buscar_num:
            # Permite buscar pelo número do processo ou pelo nome do destinatário
            termo = buscar_num.strip().lower()
            mask_proc = df_ativos["processo"].str.lower().str.contains(termo, na=False)
            mask_dest = df_ativos["destinatario"].str.lower().str.contains(termo, na=False)
            df_ativos = df_ativos[mask_proc | mask_dest]
            
        if df_ativos.empty:
            st.warning("Nenhum mandado encontrado com os filtros selecionados.")
            return

        st.markdown(f"**Mandados em Trâmite Ativo:** `{len(df_ativos)}`")
        
        for idx, row in df_ativos.iterrows():
            with st.container(border=True):
                col_info, col_status, col_acao = st.columns([2.5, 1.5, 1.5])
                
                with col_info:
                    badge_urg = "🚨 **[URGENTE]** | " if row.get("urgente") == 1 else ""
                    st.markdown(f"#### {badge_urg}Mandado — Processo `{row.get('processo', 'S/N')}`")
                    st.markdown(f"**Destinatário/Alvo:** <span style='color: #2C5282; font-weight: 600;'>{row.get('destinatario', 'Não especificado')}</span>", unsafe_allow_html=True)
                    if row.get("observacao"):
                        st.caption(f"📌 *Nota/Diligência:* {row.get('observacao')}")
                    st.caption(f"🕒 Entrada na SEMAND: {row.get('data_entrada', 'N/A')} | Relator: **{row.get('relator', 'GAB')}**")
                    
                with col_status:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(f"**Fase do Cumprimento:**")
                    
                    status_atual = row.get("status", "Aguardando Expedição de Mandado")
                    # Adaptação de cores conforme o avanço da esteira tática
                    cor_bg = "#FEFCBF" if "Aguardando" in status_atual and "AR" not in status_atual else "#EBF8FF" if "Cumprimento" in status_atual else "#E9D8FD"
                    cor_txt = "#744210" if "Aguardando" in status_atual and "AR" not in status_atual else "#2B6CB0" if "Cumprimento" in status_atual else "#553C9A"
                    
                    st.markdown(f"<span style='background-color: {cor_bg}; color: {cor_txt}; padding: 6px 10px; border-radius: 4px; font-weight: bold; font-size: 13px; display: inline-block; margin-bottom: 8px;'>{status_atual}</span>", unsafe_allow_html=True)
                    
                    oficial = row.get("oficial_responsavel")
                    if oficial and oficial != "Não atribuído":
                        st.caption(f"👤 Oficial/Analista: **{oficial}**")
                    else:
                        st.caption("👤 Oficial: *Não assumido*")
                        
                with col_acao:
                    st.markdown("<br>", unsafe_allow_html=True)
                    id_reg = row.get("id")
                    
                    # FASE 1: ASSUMIR E EMITIR MANDADO
                    if status_atual == "Aguardando Expedição de Mandado":
                        if st.button("📨 Emitir Mandado", key=f"btn_emit_{id_reg}_{idx}", type="primary", use_container_width=True):
                            try:
                                conn.table("pauta_semand").update({
                                    "status": "Em Cumprimento / Diligência",
                                    "oficial_responsavel": st.session_state.get("usuario_nome", "Oficial SEMAND")
                                }).eq("id", id_reg).execute()
                                st.success("Mandado emitido e assumido para cumprimento!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao emitir: {e}")
                            
                    # FASE 2: REGISTRO DE DESPACHO EXTERNO E ESPERA DE AR
                    elif status_atual == "Em Cumprimento / Diligência":
                        if st.button("📫 Registrar Envio / AR", key=f"btn_ar_{id_reg}_{idx}", type="primary", use_container_width=True):
                            try:
                                conn.table("pauta_semand").update({
                                    "status": "Aguardando Aviso de Recebimento (AR)"
                                }).eq("id", id_reg).execute()
                                st.success("Envio registrado! Controle de prazo de AR ativado.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao registrar AR: {e}")
                            
                    # FASE 3: CONFIRMAÇÃO DE RECEBIMENTO JURISDICIONADO E FECHAMENTO
                    elif status_atual == "Aguardando Aviso de Recebimento (AR)":
                        if st.button("✨ Atestar Cumprimento", key=f"btn_cump_{id_reg}_{idx}", type="primary", use_container_width=True):
                            try:
                                conn.table("pauta_semand").update({
                                    "status": "Cumprido - Arquivado",
                                    "data_conclusao": datetime.now().strftime("%d/%m/%Y %H:%M")
                                }).eq("id", id_reg).execute()
                                st.success("✨ Aviso de Recebimento confirmado! Mandado arquivado.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao atestar cumprimento: {e}")
                            
                    # VÁLVULA DE SEGURANÇA: CANCELAMENTO/DEVOLUÇÃO
                    if st.button("🚫 Cancelar / Devolver", key=f"btn_canc_{id_reg}_{idx}", type="secondary", use_container_width=True):
                        try:
                            conn.table("pauta_semand").update({
                                "status": "Cancelado / Devolvido",
                                "observacao": "🚫 Cancelado ou devolvido sem cumprimento pelo Oficial."
                            }).eq("id", id_reg).execute()
                            st.warning("Mandado cancelado e removido da fila ativa de trâmite.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao cancelar: {e}")

    except Exception as e:
        st.error(f"🚨 Erro ao carregar a pauta da SEMAND: {e}")

# ------------------------------------------------------------------------------
# 2. ABA 2: REGISTRO AVULSO DE MANDADOS (INJEÇÃO MANUAL)
# ------------------------------------------------------------------------------
def renderizar_injecao_semand():
    st.markdown("### 📥 Emissão Manual de Mandados e Citações")
    st.caption("Cadastre mandados de citação, intimação de pauta ou diligências externas solicitadas pelos Relatores.")
    
    with st.container(border=True):
        with st.form("form_avulso_semand"):
            st.markdown("#### 👤 Identificação do Alvo e Processo")
            c1, c2, c3 = st.columns(3)
            with c1:
                num_proc = st.text_input("Nº do Processo:", placeholder="Ex: 00600-00000000/2026-00")
                relator = st.selectbox("Gabinete Solicitante:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT", "GAB"], key="semand_rel")
            with c2:
                destinatario = st.text_input("Destinatário / Jurisdicionado (Alvo):", placeholder="Ex: Secretaria de Saúde - SES/DF")
                tipo_mandado = st.selectbox("Natureza do Documento:", [
                    "Mandado de Citação",
                    "Mandado de Notificação / Intimação",
                    "Diligência de Inspeção / Vistoria",
                    "Comunicado de Urgência"
                ])
            with c3:
                e_urgente = st.checkbox("🚨 Exige Cumprimento Urgente/Prioritário?", value=False)
                obs = st.text_input("Observação / Prazo Legal:", placeholder="Ex: Prazo de 5 dias úteis (Decisão nº 4494)")
                
            if st.form_submit_button("🚀 Emitir e Cadastrar na Fila", type="primary"):
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
                        st.success(f"✨ Mandado para `{destinatario.strip()}` no processo `{num_proc}` registrado na SEMAND com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Erro ao cadastrar mandado: {e}. Verifique a integridade da tabela 'pauta_semand' no Supabase.")
                else:
                    st.warning("⚠️ Os campos 'Nº do Processo' e 'Destinatário/Jurisdicionado' são obrigatórios.")

# ------------------------------------------------------------------------------
# 3. ABA 3: HISTÓRICO E ARQUIVO DE MANDADOS CUMPRIDOS
# ------------------------------------------------------------------------------
def renderizar_historico_semand():
    st.markdown("### 📜 Histórico de Mandados e ARs")
    st.caption("Repositório permanente de mandados atestados como cumpridos, com retorno de Aviso de Recebimento, ou cancelados.")
    
    try:
        dados = buscar_todos_paginado("pauta_semand")
        if not dados:
            st.info("Nenhum mandado arquivado no momento.")
            return
            
        df = pd.DataFrame(dados)
        df_hist = df[df["status"].isin(["Cumprido - Arquivado", "Cancelado / Devolvido"])]
        
        if df_hist.empty:
            st.info("✨ Nenhum registro histórico finalizado no momento.")
            return
            
        st.markdown(f"**Total Arquivado / Devolvido:** `{len(df_hist)} mandado(s)`")
        
        cols_show = [c for c in ["processo", "relator", "destinatario", "oficial_responsavel", "status", "data_conclusao", "observacao"] if c in df_hist.columns]
        st.dataframe(df_hist[cols_show], use_container_width=True, hide_index=True)
        
        col_down, _ = st.columns([1, 2])
        with col_down:
            csv_export = df_hist[cols_show].to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Baixar Relatório de Mandados (CSV)", 
                data=csv_export, 
                file_name=f"historico_semand_{datetime.now().strftime('%Y%m%d')}.csv", 
                mime="text/csv",
                use_container_width=True
            )
    except Exception as e:
        st.error(f"🚨 Erro ao carregar histórico: {e}")

# ------------------------------------------------------------------------------
# 4. ABA 4: QUADRO DE AFASTAMENTOS (MODO LEITURA)
# ------------------------------------------------------------------------------
def renderizar_afastamentos_leitura():
    st.markdown("### 🏝️ Quadro de Férias e Afastamentos (Modo Leitura)")
    st.caption("Consulte a disponibilidade da equipe de oficiais e analistas. A gestão e lançamentos são centralizados na Torre do GAB.")
    try:
        afast = buscar_todos_paginado("afastamentos")
        if afast:
            df_af = pd.DataFrame(afast)
            st.dataframe(df_af[["usuario", "motivo", "data_inicio", "data_fim"]], use_container_width=True, hide_index=True)
        else:
            st.success("✨ Toda a equipe tática da SEMAND está 100% ativa e disponível para diligências e plantões!")
    except Exception:
        st.info("Quadro de afastamentos sem registros no momento.")

# ------------------------------------------------------------------------------
# 5. FUNÇÃO PRINCIPAL DO MÓDULO (PONTO DE ENTRADA DO ROTEADOR)
# ------------------------------------------------------------------------------
def run():
    st.markdown("<div class='main-header'>📁 SEMAND — Setor de Mandados e Diligências Externas</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Expedição Tática de Mandados de Citação, Intimação de Pauta e Controle de Avisos de Recebimento (AR)</div>", unsafe_allow_html=True)
    
    t_fila, t_injecao, t_hist, t_ferias = st.tabs([
        "📑 Fila Ativa (Mandados / AR)",
        "📥 Registro de Mandado (Avulso)",
        "📜 Histórico Arquivado",
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
