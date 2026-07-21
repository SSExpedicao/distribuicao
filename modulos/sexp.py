# ==============================================================================
# ARQUIVO: modulos/sexp.py
# MISSÃO: Setor de Expedição (S.A.D.E. - Homologação, Esteira e Expedição)
# ==============================================================================

import streamlit as st
import pandas as pd
import random
from datetime import datetime
from db_manager import conn, buscar_todos_paginado, carregar_equipes, obter_colaboradores_ausentes_hoje

# ------------------------------------------------------------------------------
# 1. COMPONENTE REUTILIZÁVEL: CARTÕES DE TRABALHO (ESTEIRA A EXPEDE / B REVISA)
# ------------------------------------------------------------------------------
def renderizar_cartoes_expedicao(df_processos, tipo_painel="geral"):
    """Renderiza os cartões de trabalho iterativos com fluxo sequencial sem burocracia."""
    if df_processos.empty:
        st.info("✨ Nenhum processo pendente de expedição nesta esteira no momento.")
        return

    st.markdown(f"**Volume Operacional na Fila:** `{len(df_processos)} processo(s)`")
    
    for idx, row in df_processos.iterrows():
        status_atual = row.get("status", "Em Expedição")
        e_urgente = row.get("urgente", 0) == 1
        id_reg = row.get("id")
        
        with st.container(border=True):
            col_info, col_responsaveis, col_acao = st.columns([2.2, 1.8, 1.5])
            
            with col_info:
                badge_urg = "🚨 **[URGENTE]** " if e_urgente and tipo_painel == "misto" else ""
                st.markdown(f"#### {badge_urg}`{row.get('processo', 'S/N')}`")
                st.markdown(f"**Relator:** `{row.get('relator', 'GAB')}` | **Sessão:** {row.get('sessao', 'Ordinária')}")
                if row.get("observacao"):
                    st.caption(f"📌 *Nota/Motivo:* {row.get('observacao')}")
                st.caption(f"🕒 Entrada na SEXP: {row.get('data_entrada', 'N/A')}")
                
            with col_responsaveis:
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(f"**Expedidor (A):** 👤 `{row.get('expedidor', 'N/A')}`")
                st.markdown(f"**Revisor (B):** 🛡️ `{row.get('revisor', 'N/A')}`")
                
                # Cores de status adaptativas para guiar o olhar do operador
                cor_status = "#2B6CB0" if status_atual == "Liberado p/ Expedição" else "#DD6B20" if "Revisão" in status_atual else "#319795"
                st.markdown(f"**Status:** <span style='color: {cor_status}; font-weight: 600;'>{status_atual}</span>", unsafe_allow_html=True)
                
            with col_acao:
                st.markdown("<br>", unsafe_allow_html=True)
                
                # FASE 1: EXPEDIÇÃO DO OFÍCIO (Colaborador A)
                if status_atual in ["Em Expedição", "Aguardando Expedição", "Liberado p/ Expedição"]:
                    if st.button("📝 Marcar Expedido", key=f"btn_exp_{id_reg}_{idx}", type="primary", use_container_width=True):
                        try:
                            conn.table("pauta_sexp").update({
                                "status": "Expedido - Aguardando Revisão",
                                "data_expedicao": datetime.now().strftime("%d/%m/%Y %H:%M")
                            }).eq("id", id_reg).execute()
                            st.success("Ofício expedido! Enviado para a revisão do Colega B.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar: {e}")
                            
                # FASE 2: REVISÃO DO OFÍCIO E ARQUIVAMENTO (Colaborador B)
                elif status_atual == "Expedido - Aguardando Revisão":
                    if st.button("🛡️ Validar Revisão (Concluir)", key=f"btn_rev_sexp_{id_reg}_{idx}", type="primary", use_container_width=True):
                        try:
                            conn.table("pauta_sexp").update({
                                "status": "Concluído",
                                "data_conclusao": datetime.now().strftime("%d/%m/%Y %H:%M")
                            }).eq("id", id_reg).execute()
                            st.success("✨ Processo finalizado e arquivado no Histórico do S.A.D.E.!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao arquivar: {e}")
                    
                    # Botão secundário para quarentena de erro (devolver para o expedidor A)
                    if st.button("⚠️ Devolver c/ Correção", key=f"btn_dev_{id_reg}_{idx}", type="secondary", use_container_width=True):
                        try:
                            conn.table("pauta_sexp").update({
                                "status": "Liberado p/ Expedição",
                                "observacao": "⚠️ Devolvido pela revisão para ajustes no ofício."
                            }).eq("id", id_reg).execute()
                            st.warning("Processo devolvido para a mesa do Expedidor.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao devolver: {e}")
                else:
                    st.success("✔️ Concluído")

# ------------------------------------------------------------------------------
# 2. ABA 1: HOMOLOGAÇÃO DA CHEFIA (MESA DO GESTOR - GATEKEEPER)
# ------------------------------------------------------------------------------
def renderizar_homologacao_chefia():
    st.markdown("### 🛡️ Mesa de Homologação e Triagem do Gestor")
    st.caption("Os processos liberados na revisão da SEAT aguardam nesta comporta. Homologue para liberar o trabalho operacional ou retire de pauta.")
    
    # Trava RBAC: Apenas Raiz ou Gerente operam esta mesa
    if st.session_state.get("nivel_acesso") not in ["Raiz", "Gerente"]:
        st.warning("🔒 **Acesso Restrito à Chefia:** Apenas o Gestor da SEXP ou a Administração Geral podem homologar pautas ou fazer inclusões de última hora.")
        st.info("Por favor, acesse as abas de **Painel Ativo** ao lado para executar suas tarefas de expedição e revisão.")
        return

    col_lote, col_avulso = st.columns([1.8, 1.2])
    
    with col_lote:
        st.markdown("#### 📥 Fila de Homologação (Vindos da SEAT)")
        try:
            dados = buscar_todos_paginado("pauta_sexp")
            pendentes = [r for r in dados if r.get("status") == "Aguardando Homologação Chefia"] if dados else []
            
            if pendentes:
                df_pend = pd.DataFrame(pendentes)
                st.markdown(f"**Processos Aguardando Liberação:** `{len(df_pend)}`")
                
                # Ação Global de Homologação
                if st.button("🚀 Homologar e Liberar TODOS para a Esteira", type="primary", use_container_width=True):
                    try:
                        for idx, item in df_pend.iterrows():
                            conn.table("pauta_sexp").update({"status": "Liberado p/ Expedição"}).eq("id", item["id"]).execute()
                        st.success(f"🚀 Comporta aberta! {len(df_pend)} processos liberados para a equipe da SEXP.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro na homologação em lote: {e}")
                        
                st.markdown("---")
                
                expedidores, revisores, todos = carregar_equipes()
                ausentes = obter_colaboradores_ausentes_hoje()
                disponiveis = [c for c in todos if c not in ausentes] if todos else ["André", "Elaine"]
                
                # Homologação ou Retirada Individual com opção de troca de dupla
                for idx, row in df_pend.iterrows():
                    id_row = row["id"]
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2.2, 1.8, 1.2])
                        with c1:
                            bg_urg = "🚨 " if row.get("urgente") == 1 else ""
                            st.markdown(f"**{bg_urg}{row.get('processo')}** (`{row.get('relator')}`)")
                            st.caption(f"Sessão: {row.get('sessao')} | Entrada: {row.get('data_entrada', '')}")
                        with c2:
                            # Permite ao gestor ajustar quem expede e quem revisa antes de soltar na esteira
                            exp_atual = row.get("expedidor", disponiveis[0] if disponiveis else "André")
                            rev_atual = row.get("revisor", disponiveis[1] if len(disponiveis) > 1 else exp_atual)
                            
                            idx_exp = disponiveis.index(exp_atual) if exp_atual in disponiveis else 0
                            idx_rev = disponiveis.index(rev_atual) if rev_atual in disponiveis else (1 if len(disponiveis) > 1 else 0)
                            
                            novo_exp = st.selectbox("Expedidor:", disponiveis, index=idx_exp, key=f"sel_exp_{id_row}")
                            opcoes_rev = [c for c in disponiveis if c != novo_exp]
                            novo_rev = st.selectbox("Revisor:", opcoes_rev if opcoes_rev else disponiveis, key=f"sel_rev_{id_row}")
                            
                        with c3:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("🚀 Liberar", key=f"lib_{id_row}", type="primary", use_container_width=True):
                                conn.table("pauta_sexp").update({
                                    "status": "Liberado p/ Expedição",
                                    "expedidor": novo_exp,
                                    "revisor": novo_rev
                                }).eq("id", id_row).execute()
                                st.rerun()
                                
                            if st.button("🚫 Retirar", key=f"ret_{id_row}", type="secondary", use_container_width=True):
                                conn.table("pauta_sexp").update({
                                    "status": "Retirado de Pauta",
                                    "observacao": "🚫 Retirado pela Chefia na SEXP"
                                }).eq("id", id_row).execute()
                                st.warning(f"Processo {row.get('processo')} retirado da pauta!")
                                st.rerun()
            else:
                st.success("✨ A fila de homologação está limpa! Todos os processos recebidos já foram liberados.")
        except Exception as e:
            st.error(f"Erro ao carregar fila de homologação: {e}")
            
    with col_avulso:
        with st.container(border=True):
            st.markdown("#### ⚡ Válvula de Emergência (Inclusão Avulsa)")
            st.caption("Para processos que entraram na pauta de última hora ou demandam ofício avulso urgente sem passar pela SEAT.")
            
            with st.form("form_avulso_sexp"):
                av_proc = st.text_input("Nº do Processo:", placeholder="00600-00000000/2026-00")
                c_a1, c_a2 = st.columns(2)
                with c_a1:
                    av_rel = st.selectbox("Relator:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT"])
                    av_urg = st.checkbox("🚨 É Urgente?", value=True)
                with c_a2:
                    av_ses = st.selectbox("Sessão:", ["Sessão Ordinária", "Ordinária Virtual", "Sessão Administrativa", "Sessão Reservada"])
                    
                expedidores, revisores, todos = carregar_equipes()
                ausentes = obter_colaboradores_ausentes_hoje()
                disp = [c for c in todos if c not in ausentes] if todos else ["André", "Elaine"]
                
                exp_sel = st.selectbox("Atribuir Expedidor (A):", disp)
                revs_op = [c for c in disp if c != exp_sel]
                rev_sel = st.selectbox("Atribuir Revisor (B):", revs_op if revs_op else disp)
                av_obs = st.text_input("Motivo da Inclusão:", placeholder="Ex: determinação verbal em Plenário")
                
                if st.form_submit_button("🚀 Injetar Direto na Esteira Ativa", type="primary"):
                    if av_proc.strip():
                        try:
                            novo_avulso = {
                                "processo": av_proc.strip(),
                                "relator": av_rel,
                                "sessao": av_ses,
                                "expedidor": exp_sel,
                                "revisor": rev_sel,
                                "status": "Liberado p/ Expedição",
                                "urgente": 1 if av_urg else 0,
                                "observacao": f"⚡ Inclusão Avulsa Chefia: {av_obs}",
                                "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                            }
                            conn.table("pauta_sexp").insert(novo_avulso).execute()
                            st.success("Processo injetado diretamente no Painel Ativo da SEXP!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao injetar avulso: {e}")
                    else:
                        st.warning("Informe o número do processo.")

# ------------------------------------------------------------------------------
# 3. ABAS OPERACIONAIS: PAINÉIS DE EXPEDIÇÃO E HISTÓRICO
# ------------------------------------------------------------------------------
def renderizar_painel_ordinario():
    st.markdown("### 📬 Painel Ativo — Sessões Ordinárias (Pauta Comum)")
    st.caption("Processos das Sessões Ordinárias e Ordinárias Virtuais liberados para expedição de ofícios.")
    
    try:
        dados = buscar_todos_paginado("pauta_sexp")
        if not dados:
            st.info("Nenhum processo na base da SEXP.")
            return
            
        df = pd.DataFrame(dados)
        # Filtro: Apenas Ordinárias, SEM urgência, em status operacional ativo
        df_ord = df[
            (df["sessao"].isin(["Sessão Ordinária", "Ordinária Virtual"])) &
            (df.get("urgente", 0) == 0) &
            (df["status"].isin(["Liberado p/ Expedição", "Em Expedição", "Expedido - Aguardando Revisão"]))
        ]
        renderizar_cartoes_expedicao(df_ord, tipo_painel="geral")
    except Exception as e:
        st.error(f"Erro no painel ordinário: {e}")

def renderizar_painel_urgentes():
    st.markdown("### 🚨 Pauta de Urgências — Sessões Ordinárias (Segregada)")
    st.caption("Mesa de alta prioridade! Processos com prazos curtos (ex: 5 dias), liminares cautelares ou sustentações orais.")
    
    try:
        dados = buscar_todos_paginado("pauta_sexp")
        if not dados:
            st.info("Nenhum processo na base da SEXP.")
            return
            
        df = pd.DataFrame(dados)
        # Filtro: Apenas Ordinárias, COM urgência (1), em status operacional ativo
        df_urg = df[
            (df["sessao"].isin(["Sessão Ordinária", "Ordinária Virtual"])) &
            (df.get("urgente", 0) == 1) &
            (df["status"].isin(["Liberado p/ Expedição", "Em Expedição", "Expedido - Aguardando Revisão"]))
        ]
        renderizar_cartoes_expedicao(df_urg, tipo_painel="urgente")
    except Exception as e:
        st.error(f"Erro no painel de urgências: {e}")

def renderizar_painel_especiais():
    st.markdown("### 🔒 Sessões Especiais (Administrativa & Reservada)")
    st.caption("Neste painel, os processos comuns e urgentes permanecem na mesma lista, sendo os urgentes destacados visualmente.")
    
    try:
        dados = buscar_todos_paginado("pauta_sexp")
        if not dados:
            st.info("Nenhum processo na base da SEXP.")
            return
            
        df = pd.DataFrame(dados)
        # Filtro: Apenas Administrativa e Reservada, em status operacional ativo (misturando urgentes e não urgentes)
        df_esp = df[
            (df["sessao"].isin(["Sessão Administrativa", "Sessão Reservada"])) &
            (df["status"].isin(["Liberado p/ Expedição", "Em Expedição", "Expedido - Aguardando Revisão"]))
        ]
        renderizar_cartoes_expedicao(df_esp, tipo_painel="misto")
    except Exception as e:
        st.error(f"Erro no painel de sessões especiais: {e}")

def renderizar_historico():
    st.markdown("### 📜 Histórico e Arquivo Geral do S.A.D.E.")
    st.caption("Repositório de todos os processos que já tiveram seus ofícios expedidos, revisados e concluídos.")
    
    try:
        dados = buscar_todos_paginado("pauta_sexp")
        if not dados:
            st.info("Nenhum histórico registrado ainda.")
            return
            
        df = pd.DataFrame(dados)
        df_hist = df[df["status"].isin(["Concluído", "Retirado de Pauta"])]
        
        if df_hist.empty:
            st.info("Nenhum processo concluído ou arquivado no momento.")
            return
            
        st.markdown(f"**Total Arquivado:** `{len(df_hist)} processo(s)`")
        
        cols_show = [c for c in ["processo", "relator", "sessao", "expedidor", "revisor", "status", "data_conclusao", "observacao"] if c in df_hist.columns]
        st.dataframe(df_hist[cols_show], use_container_width=True, hide_index=True)
        
        # Opção de exportação para Excel/CSV
        csv_export = df_hist[cols_show].to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Histórico Completo (CSV)", data=csv_export, file_name=f"historico_sade_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

def renderizar_afastamentos_leitura():
    st.markdown("### 🏝️ Quadro de Férias e Afastamentos (Modo Leitura)")
    st.caption("Consulte abaixo os colegas de recesso ou férias. O cadastro e alteração de períodos é realizado no painel do GAB.")
    try:
        afast = buscar_todos_paginado("afastamentos")
        if afast:
            df_af = pd.DataFrame(afast)
            st.dataframe(df_af[["usuario", "motivo", "data_inicio", "data_fim"]], use_container_width=True, hide_index=True)
        else:
            st.success("✨ Toda a equipe da SEXP está 100% ativa e disponível!")
    except Exception:
        st.info("Tabela de afastamentos sem registros no momento.")

# ------------------------------------------------------------------------------
# 4. FUNÇÃO PRINCIPAL DO MÓDULO (PONTO DE ENTRADA DO ROTEADOR)
# ------------------------------------------------------------------------------
def run():
    st.markdown("<div style='font-size: 26px; font-weight: bold; color: #1E3A8A;'>📬 SEXP — Setor de Expedição (S.A.D.E.)</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size: 14px; color: #4B5563; margin-bottom: 20px; border-bottom: 2px solid #E5E7EB; padding-bottom: 8px;'>Sistema de Acompanhamento de Expedição, Emissão de Ofícios e Controle de Prazos</div>", unsafe_allow_html=True)
    
    t_homolog, t_ord, t_urg, t_esp, t_hist, t_ferias = st.tabs([
        "🛡️ Homologação Chefia",
        "📬 Painel Ordinário",
        "🚨 Pauta de Urgências",
        "🔒 Sessões Especiais",
        "📜 Histórico S.A.D.E.",
        "🏝️ Afastamentos (Leitura)"
    ])
    
    with t_homolog:
        renderizar_homologacao_chefia()
    with t_ord:
        renderizar_painel_ordinario()
    with t_urg:
        renderizar_painel_urgentes()
    with t_esp:
        renderizar_painel_especiais()
    with t_hist:
        renderizar_historico()
    with t_ferias:
        renderizar_afastamentos_leitura()

if __name__ == "__main__":
    run()
