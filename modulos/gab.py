"""
GAB — Torre de Controle (Gabinete)
Módulo principal do Gabinete com Dashboard Geral, tabs por setor,
escala do plenário, controle de férias, agenda, diários e auditoria.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import db_manager
from modulos.busca_diarios import _renderizar_busca_diarios
from modulos.gerenciar_dados import _tem_permissao_gestao

# ============================================================
# FUNÇÃO DE SIDEBAR — Chamada pelo app.py via placeholder
# ============================================================
def renderizar_sidebar(usuario, modo_edicao):
    """Chamada pelo app.py para renderizar o sidebar do GAB no placeholder."""
    _renderizar_sidebar_gab(usuario)

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def renderizar(usuario: dict, modo_edicao: bool = False):
    """Função principal do módulo GAB."""
    if not usuario or not isinstance(usuario, dict):
        st.error("Não foi possível carregar os dados do usuário.")
        return

    nome = usuario.get("nome", "Usuário")
    cargo = usuario.get("nivel_acesso", usuario.get("cargo", "—"))
    setor = usuario.get("setor", "GAB")

    st.markdown(f"**Colaborador:** {nome} | **Cargo:** {cargo} | **Setor:** {setor}")
    st.markdown("---")

    # Banner de avisos ativos no topo
    _renderizar_banner_avisos(usuario)

    # Tabs principais do GAB
    tab_dashboard, tab_setores, tab_escala, tab_ferias, tab_agenda, tab_diarios, tab_auditoria = st.tabs([
        "📊 Dashboard Geral",
        "📂 Setores",
        "📅 Escala do Plenário",
        "🏖️ Cadastro de Férias",
        "📋 Agenda do Secretário",
        "🔍 Pesquisa nos Diários",
        "📝 Auditoria",
    ])

    with tab_dashboard:
        _renderizar_dashboard_geral(usuario)
    with tab_setores:
        _renderizar_setores(usuario)
    with tab_escala:
        _renderizar_escala_plenario(usuario)
    with tab_ferias:
        _renderizar_cadastro_ferias(usuario)
    with tab_agenda:
        _renderizar_agenda_secretario(usuario)
    with tab_diarios:
        _renderizar_busca_diarios(usuario)
    with tab_auditoria:
        _renderizar_auditoria(usuario)

# ============================================================
# DASHBOARD GERAL
# ============================================================
def _renderizar_dashboard_geral(usuario):
    """Dashboard principal com métricas consolidadas de todos os setores."""
    st.markdown("### 📊 Dashboard Geral do Gabinete")
    st.caption("Visão consolidada de todos os setores — dados em tempo real.")

    # Buscar dados de todos os setores
    try:
        seat_processos = db_manager.buscar_todos("pauta_seat") or []
    except Exception:
        seat_processos = []

    try:
        sexp_distribuicao = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        sexp_distribuicao = []

    try:
        urgentes = db_manager.buscar_todos("processos_urgentes") or []
    except Exception:
        urgentes = []

    # Métricas de Volume
    st.markdown("#### 📈 Métricas de Volume")

    total_seat = len([p for p in seat_processos if not p.get("sessao_finalizada", False) and not p.get("removido_pauta", False)])
    total_sexp = len([p for p in sexp_distribuicao if not p.get("sessao_finalizada", False) and not p.get("removido_pauta", False) and p.get("distribuido", False)])
    urgentes_ativos = len([u for u in urgentes if not u.get("despachado", False)])
    urgentes_despachados = len([u for u in urgentes if u.get("despachado", False)])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Processos SEAT", total_seat)
    col2.metric("Processos SEXP", total_sexp)
    col3.metric("Urgentes Ativos", urgentes_ativos)
    col4.metric("Urgentes Despachados", urgentes_despachados)

    # Processos por Sessão
    st.markdown("#### 🥧 Processos por Sessão")

    sessoes = {}
    for p in seat_processos:
        if p.get("sessao_finalizada") or p.get("removido_pauta"):
            continue
        num_s = p.get("numero_sessao") or p.get("sessao_numero") or "S/N"
        sessoes[num_s] = sessoes.get(num_s, 0) + 1

    for p in sexp_distribuicao:
        if p.get("sessao_finalizada") or p.get("removido_pauta") or not p.get("distribuido"):
            continue
        num_s = p.get("numero_sessao") or p.get("sessao_numero") or "S/N"
        sessoes[num_s] = sessoes.get(num_s, 0) + 1

    if sessoes:
        df_sessoes = pd.DataFrame(list(sessoes.items()), columns=["Sessão", "Quantidade"])
        st.dataframe(df_sessoes, hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum processo ativo no momento.")

    # Quadro de Colaboradores
    st.markdown("#### 👥 Desempenho de Colaboradores")
    _renderizar_quadro_colaboradores(seat_processos, sexp_distribuicao)

    # Linha do Tempo — Despachos da Semana
    st.markdown("#### 📅 Linha do Tempo — Despachos da Semana")
    _renderizar_linha_tempo_despachos(seat_processos, sexp_distribuicao)

# ============================================================
# TAB SETORES — Subtabs por setor (cada gerente só vê o seu)
# ============================================================
def _renderizar_setores(usuario):
    """Tab de Setores com subtabs. Gerente só vê seu próprio setor."""
    st.markdown("### 📂 Setores Operacionais")

    cargo = usuario.get("nivel_acesso", usuario.get("cargo", "")).lower()
    setor_usuario = usuario.get("setor", "")

    # Raiz/Criador/Secretaria veem todos os setores
    if cargo in ("criador", "raiz", "secretaria", "super_admin_criador", "admin_gabinete", "espectadora_global"):
        setores_visiveis = ["SEAT", "SEXP", "SERCON", "SEMAND"]
    elif cargo in ("gerente", "gestor_setorial"):
        setores_visiveis = [setor_usuario] if setor_usuario != "GAB" else ["SEAT"]
    else:
        setores_visiveis = [setor_usuario] if setor_usuario else ["SEAT"]

    if not setores_visiveis:
        st.warning("Nenhum setor disponível para seu perfil.")
        return

    # Subtabs dentro da tab Setores
    subtabs = st.tabs([f"📂 {s}" for s in setores_visiveis])

    for i, setor in enumerate(setores_visiveis):
        with subtabs[i]:
            _renderizar_conteudo_setor(usuario, setor)

def _renderizar_conteudo_setor(usuario, setor):
    """Conteúdo de cada setor: dashboard + férias dos colaboradores + avisos do setor."""
    # Sub-subtabs dentro de cada setor
    tab_dash, tab_ferias, tab_avisos = st.tabs([
        "📊 Dashboard",
        "🏖️ Férias dos Colaboradores",
        "📢 Avisos do Setor",
    ])

    with tab_dash:
        _renderizar_dashboard_setor(usuario, setor)

    with tab_ferias:
        _renderizar_ferias_setor(usuario, setor)

    with tab_avisos:
        _renderizar_avisos_setor(usuario, setor)

# ============================================================
# DASHBOARD POR SETOR
# ============================================================
def _renderizar_dashboard_setor(usuario, setor):
    """Dashboard operacional de cada setor."""
    st.markdown(f"#### 📊 Dashboard — {setor}")

    if setor == "SEAT":
        try:
            processos = db_manager.buscar_todos("pauta_seat") or []
        except Exception:
            processos = []

        ativos = [p for p in processos if not p.get("sessao_finalizada", False) and not p.get("removido_pauta", False)]
        editados = [p for p in ativos if p.get("editado", False)]
        revisados = [p for p in ativos if p.get("revisado", False)]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Ativos", len(ativos))
        col2.metric("Editados", len(editados))
        col3.metric("Revisados", len(revisados))
        col4.metric("Pendentes", len(ativos) - len(editados))

        st.markdown("##### Desempenho por Colaborador")
        _renderizar_desempenho_colaborador(processos, "SEAT")

    elif setor == "SEXP":
        try:
            processos = db_manager.buscar_todos("distribuicao_sexp") or []
        except Exception:
            processos = []

        ativos = [p for p in processos if not p.get("sessao_finalizada", False) and not p.get("removido_pauta", False) and p.get("distribuido", False)]
        expedidos = [p for p in ativos if p.get("expedido", False)]
        revisados = [p for p in ativos if p.get("revisado", False)]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Ativos", len(ativos))
        col2.metric("Expedidos", len(expedidos))
        col3.metric("Revisados", len(revisados))
        col4.metric("Pendentes", len(ativos) - len(expedidos))

        st.markdown("##### Desempenho por Colaborador")
        _renderizar_desempenho_colaborador(processos, "SEXP")

    elif setor == "SERCON":
        st.info("Módulo SERCON em desenvolvimento — aguardando definição do fluxo operacional.")

    elif setor == "SEMAND":
        st.info("Módulo SEMAND em desenvolvimento — aguardando definição do fluxo operacional.")

# ============================================================
# FÉRIAS DOS COLABORADORES (dentro de cada setor)
# ============================================================
def _renderizar_ferias_setor(usuario, setor):
    """Mostra as solicitações de férias/atestado/abono dos colaboradores do setor."""
    st.markdown(f"#### 🏖️ Férias e Afastamentos — {setor}")
    st.caption("Solicitações de férias, atestados e abonos dos colaboradores deste setor.")

    try:
        solicitacoes = db_manager.buscar_todos(
            "solicitacoes_ausencia",
            filtros={"setor": setor},
            ordem_coluna="data_inicio",
            ordem_desc=False,
        ) or []
    except Exception:
        solicitacoes = []

    if not solicitacoes:
        st.info("Nenhuma solicitação de afastamento registrada para este setor.")
        return

    # Separar por status
    pendentes = [s for s in solicitacoes if s.get("status") == "PENDENTE"]
    aprovadas = [s for s in solicitacoes if s.get("status") == "APROVADA"]
    rejeitadas = [s for s in solicitacoes if s.get("status") == "REJEITADA"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Pendentes", len(pendentes))
    col2.metric("Aprovadas", len(aprovadas))
    col3.metric("Rejeitadas", len(rejeitadas))

    # Mostrar pendentes com botões de aprovação
    if pendentes:
        st.markdown("##### ⏳ Aguardando Aprovação")
        for s in pendentes:
            sid = s.get("id")
            nome = s.get("colaborador_nome", "—")
            tipo = s.get("tipo", "—")
            data_ini = s.get("data_inicio", "—")[:10]
            data_fim = s.get("data_fim", "—")[:10]
            dias = s.get("dias_afastado", "—")
            obs = s.get("observacoes", "") or "—"

            tipo_label = {"FERIAS": "🌴 Férias", "ATESTADO": "🏥 Atestado", "ABONO": "📋 Abono"}.get(tipo, tipo)

            with st.expander(f"{tipo_label} — {nome} — {data_ini} a {data_fim} ({dias} dias)"):
                st.write(f"**Colaborador:** {nome}")
                st.write(f"**Tipo:** {tipo_label}")
                st.write(f"**Período:** {data_ini} a {data_fim}")
                st.write(f"**Dias:** {dias}")
                st.write(f"**Observações:** {obs}")

                is_gestor = _tem_permissao_gestao(usuario)
                if is_gestor:
                    col_apr, col_rej = st.columns(2)
                    with col_apr:
                        if st.button("✅ Aprovar", key=f"apr_setor_{sid}", type="primary", use_container_width=True):
                            db_manager.atualizar("solicitacoes_ausencia", sid, {"status": "APROVADA"})
                            st.success(f"Solicitação de {nome} aprovada!")
                            st.rerun()
                    with col_rej:
                        if st.button("❌ Rejeitar", key=f"rej_setor_{sid}", use_container_width=True):
                            db_manager.atualizar("solicitacoes_ausencia", sid, {"status": "REJEITADA"})
                            st.info(f"Solicitação de {nome} rejeitada.")
                            st.rerun()
                else:
                    st.info("Apenas gestores podem aprovar/rejeitar.")

    # Mostrar aprovadas
    if aprovadas:
        st.markdown("##### ✅ Aprovadas")
        dados_aprov = []
        for s in aprovadas:
            tipo_raw = s.get("tipo", "—")
            tipo_lbl = {"FERIAS": "🌴 Férias", "ATESTADO": "🏥 Atestado", "ABONO": "📋 Abono"}.get(tipo_raw, tipo_raw)
            dados_aprov.append({
                "Colaborador": s.get("colaborador_nome", "—"),
                "Tipo": tipo_lbl,
                "Início": s.get("data_inicio", "—")[:10],
                "Fim": s.get("data_fim", "—")[:10],
                "Dias": s.get("dias_afastado", "—"),
            })
        df_aprov = pd.DataFrame(dados_aprov)
        st.dataframe(df_aprov, hide_index=True, use_container_width=True)

# ============================================================
# AVISOS DO SETOR (dentro de cada setor)
# ============================================================
def _renderizar_avisos_setor(usuario, setor):
    """Avisos que vão somente para aquele setor."""
    st.markdown(f"#### 📢 Avisos — {setor}")
    st.caption(f"Avisos enviados exclusivamente para o setor {setor}.")

    is_gestor = _tem_permissao_gestao(usuario)

    # Formulário de envio (apenas gestores)
    if is_gestor:
        with st.form("form_aviso_setor"):
            st.markdown("**Enviar Aviso para o Setor:**")
            mensagem = st.text_area("Mensagem", placeholder="Digite o aviso...", height=80, key=f"txt_aviso_{setor}")
            duracao = st.number_input("Duração (horas)", min_value=1, value=24, key=f"dur_aviso_{setor}")

            if st.form_submit_button("📢 Publicar", type="primary", use_container_width=True):
                if mensagem.strip():
                    dados_aviso = {
                        "remetente": usuario.get("nome", "—"),
                        "setor_remetente": usuario.get("setor", "GAB"),
                        "escopo": setor,
                        "mensagem": mensagem.strip(),
                        "duracao_horas": duracao,
                        "data_criacao": datetime.now().isoformat(),
                        "ativo": True,
                    }
                    try:def _renderizar_avisos_setor(usuario, setor):
    """Avisos que vão somente para aquele setor."""
    st.markdown(f"#### 📢 Avisos — {setor}")
    st.caption(f"Avisos enviados exclusivamente para o setor {setor}.")

    is_gestor = _tem_permissao_gestao(usuario)

    if is_gestor:
        with st.form(f"form_aviso_setor_{setor}"):
            st.markdown("**Enviar Aviso para o Setor:**")
            mensagem = st.text_area("Mensagem", placeholder="Digite o aviso...", height=80, key=f"txt_aviso_{setor}")
            duracao = st.number_input("Duração (horas)", min_value=1, value=24, key=f"dur_aviso_{setor}")

            if st.form_submit_button("📢 Publicar", type="primary", use_container_width=True):
                if mensagem.strip():
                    dados_aviso = {
                        "remetente": usuario.get("nome", "—"),
                        "setor_remetente": usuario.get("setor", "GAB"),
                        "escopo": setor,
                        "mensagem": mensagem.strip(),
                        "duracao_horas": duracao,
                        "data_criacao": datetime.now().isoformat(),
                        "ativo": True,
                    }
                    try:
                        db_manager.inserir("avisos_gab", dados_aviso)
                        st.success("✅ Aviso publicado!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao publicar: {e}")
                else:
                    st.warning("Digite uma mensagem.")
    else:
        st.info("Apenas gestores podem enviar avisos.")

    try:
        avisos = db_manager.buscar_todos("avisos_gab") or []
    except Exception:
        avisos = []

    agora = datetime.now()
    avisos_setor = []
    for a in avisos:
        if not a.get("ativo", True):
            continue
        if a.get("escopo") != setor:
            continue
        data_criacao = a.get("data_criacao", "")
        if data_criacao:
            try:
                dt_criacao = datetime.fromisoformat(data_criacao)
                duracao_horas = a.get("duracao_horas", 24)
                expira = dt_criacao + timedelta(hours=duracao_horas)
                if agora > expira:
                    continue
            except Exception:
                pass
        avisos_setor.append(a)

    if avisos_setor:
        st.markdown("##### Avisos Ativos")
        for a in avisos_setor:
            remetente = a.get("remetente", "—")
            mensagem = a.get("mensagem", "")
            data_criacao = a.get("data_criacao", "")[:16].replace("T", " ")
            st.warning(f"📢 **{remetente}** ({data_criacao}): {mensagem}")
    else:
        st.info("Nenhum aviso ativo para este setor.")

# ============================================================
# SIDEBAR DO GAB
# ============================================================
def _renderizar_sidebar_gab(usuario):
    """Renderiza os elementos do sidebar: Avisos, Pedido de Vista, Urgentes."""
    is_gestor = _tem_permissao_gestao(usuario)
    cargo = usuario.get("nivel_acesso", usuario.get("cargo", "")).lower()
    is_raiz = cargo in ("criador", "raiz", "admin", "super_admin_criador") or "juan" in usuario.get("nome", "").lower()

    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📢 Avisos do Gabinete")

        if is_gestor:
            with st.expander("➕ Enviar Aviso Geral"):
                if is_raiz:
                    escopo = st.selectbox("Enviar para", ["Todos os Setores", "SEAT", "SEXP", "SERCON", "SEMAND"], key="escopo_aviso_gab")
                else:
                    escopo = usuario.get("setor", "SEAT")
                    st.info(f"Avisos limitados ao seu setor: {escopo}")

                texto_aviso = st.text_area("Mensagem", placeholder="Digite o aviso...", height=80, key="txt_aviso_gab")

                col_dur1, col_dur2 = st.columns(2)
                with col_dur1:
                    duracao_num = st.number_input("Duração", min_value=1, value=24, key="dur_num_gab")
                with col_dur2:
                    duracao_tipo = st.selectbox("Unidade", ["horas", "dias"], key="dur_tipo_gab")

                if st.button("📢 Publicar Aviso", type="primary", use_container_width=True, key="btn_pub_aviso"):
                    if texto_aviso.strip():
                        horas = duracao_num * 24 if duracao_tipo == "dias" else duracao_num
                        dados_aviso = {
                            "remetente": usuario.get("nome", "—"),
                            "setor_remetente": usuario.get("setor", "GAB"),
                            "escopo": escopo if isinstance(escopo, str) else "Todos os Setores",
                            "mensagem": texto_aviso.strip(),
                            "duracao_horas": horas,
                            "data_criacao": datetime.now().isoformat(),
                            "ativo": True,
                        }
                        try:
                            db_manager.inserir("avisos_gab", dados_aviso)
                            st.success("✅ Aviso publicado!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao publicar: {e}")
                    else:
                        st.warning("Digite uma mensagem.")
        else:
            st.info("Apenas gestores podem enviar avisos.")

        # Pedido de Vista
        st.markdown("---")
        st.markdown("### 👁️ Pedido de Vista")

        if is_raiz:
            with st.expander("Registrar Pedido de Vista"):
                num_proc = st.text_input("Número do Processo", placeholder="Ex: 1234567-89.2024.8.26.0000", key="num_vista_gab")
                if st.button("🔍 Localizar e Marcar", type="primary", use_container_width=True, key="btn_vista_gab"):
                    if num_proc.strip():
                        _processar_pedido_vista(num_proc.strip(), usuario)
                    else:
                        st.warning("Digite o número do processo.")
        else:
            st.info("Acesso restrito a Raiz.")

        # Contador de Urgentes
        st.markdown("---")
        st.markdown("### 🚨 Urgentes")

        try:
            urgentes = db_manager.buscar_todos("processos_urgentes") or []
            ativos = [u for u in urgentes if not u.get("despachado", False)]
            despachados = [u for u in urgentes if u.get("despachado", False)]

            col_u1, col_u2 = st.columns(2)
            col_u1.metric("Ativos", len(ativos))
            col_u2.metric("Despachados", len(despachados))
        except Exception:
            st.warning("Erro ao carregar urgentes.")

# ============================================================
# BANNER DE AVISOS ATIVOS (TOPO)
# ============================================================
def _renderizar_banner_avisos(usuario):
    """Renderiza banner de avisos ativos no topo da página."""
    try:
        avisos = db_manager.buscar_todos("avisos_gab") or []
    except Exception:
        return

    setor_usuario = usuario.get("setor", "SEAT")
    agora = datetime.now()

    avisos_ativos = []
    for a in avisos:
        if not a.get("ativo", True):
            continue
        escopo = a.get("escopo", "Todos os Setores")
        if escopo != "Todos os Setores" and escopo != setor_usuario:
            continue
        data_criacao = a.get("data_criacao", "")
        if data_criacao:
            try:
                dt_criacao = datetime.fromisoformat(data_criacao)
                duracao_horas = a.get("duracao_horas", 24)
                expira = dt_criacao + timedelta(hours=duracao_horas)
                if agora > expira:
                    continue
            except Exception:
                pass
        avisos_ativos.append(a)

    if avisos_ativos:
        for a in avisos_ativos:
            remetente = a.get("remetente", "—")
            escopo = a.get("escopo", "—")
            mensagem = a.get("mensagem", "")
            st.warning(f"📢 **{remetente}** ({escopo}): {mensagem}")

# ============================================================
# FUNÇÕES AUXILIARES — DASHBOARD
# ============================================================
def _renderizar_quadro_colaboradores(seat_processos, sexp_processos):
    """Quadro com nomes de colaboradores, total trabalhado e ativos."""
    colaboradores = {}

    for p in seat_processos:
        editor = p.get("editor", "")
        if editor and editor != "—":
            if editor not in colaboradores:
                colaboradores[editor] = {"setor": "SEAT", "total": 0, "ativos": 0}
            colaboradores[editor]["total"] += 1
            if not p.get("sessao_finalizada") and not p.get("removido_pauta"):
                colaboradores[editor]["ativos"] += 1

        revisor = p.get("revisor", "")
        if revisor and revisor != "—":
            if revisor not in colaboradores:
                colaboradores[revisor] = {"setor": "SEAT", "total": 0, "ativos": 0}
            colaboradores[revisor]["total"] += 1
            if not p.get("sessao_finalizada") and not p.get("removido_pauta"):
                colaboradores[revisor]["ativos"] += 1

    for p in sexp_processos:
        expedidor = p.get("expedidor", "")
        if expedidor and expedidor != "—":
            if expedidor not in colaboradores:
                colaboradores[expedidor] = {"setor": "SEXP", "total": 0, "ativos": 0}
            colaboradores[expedidor]["total"] += 1
            if not p.get("sessao_finalizada") and not p.get("removido_pauta"):
                colaboradores[expedidor]["ativos"] += 1

        revisor = p.get("revisor", "")
        if revisor and revisor != "—":
            if revisor not in colaboradores:
                colaboradores[revisor] = {"setor": "SEXP", "total": 0, "ativos": 0}
            colaboradores[revisor]["total"] += 1
            if not p.get("sessao_finalizada") and not p.get("removido_pauta"):
                colaboradores[revisor]["ativos"] += 1

    if not colaboradores:
        st.info("Nenhum colaborador com processos registrados ainda.")
        return

    dados = []
    for nome, info in sorted(colaboradores.items()):
        dados.append({
            "Colaborador": nome,
            "Setor": info["setor"],
            "Total Trabalhado": info["total"],
            "Ativos Agora": info["ativos"],
        })

    df = pd.DataFrame(dados)
    st.dataframe(df, hide_index=True, use_container_width=True)

def _renderizar_desempenho_colaborador(processos, setor):
    """Desempenho individual por colaborador dentro de um setor."""
    colaboradores = {}

    for p in processos:
        if p.get("sessao_finalizada") or p.get("removido_pauta"):
            continue

        if setor == "SEAT":
            pessoa = p.get("editor", "") or p.get("revisor", "")
        else:
            pessoa = p.get("expedidor", "") or p.get("revisor", "")

        if not pessoa or pessoa == "—":
            continue

        if pessoa not in colaboradores:
            colaboradores[pessoa] = {"total": 0, "concluidos": 0}
        colaboradores[pessoa]["total"] += 1

        if p.get("revisado"):
            colaboradores[pessoa]["concluidos"] += 1

    if not colaboradores:
        st.info("Nenhum colaborador com processos ativos neste setor.")
        return

    dados = []
    for nome, info in sorted(colaboradores.items()):
        dados.append({
            "Colaborador": nome,
            "Processos Ativos": info["total"],
            "Concluídos": info["concluidos"],
            "Pendentes": info["total"] - info["concluidos"],
        })

    df = pd.DataFrame(dados)
    st.dataframe(df, hide_index=True, use_container_width=True)

def _renderizar_linha_tempo_despachos(seat_processos, sexp_processos):
    """Linha do tempo de despachos singulares e sustentações orais da semana."""
    hoje = datetime.now().date()
    inicio_semana = hoje - timedelta(days=hoje.weekday())

    dias_semana = []
    for i in range(7):
        dias_semana.append(inicio_semana + timedelta(days=i))

    dados_dia = {d: {"ds": 0, "sustentacao": 0} for d in dias_semana}

    for p in seat_processos:
        data_raw = str(p.get("data_entrada", p.get("criado_em", "")))[:10]
        if not data_raw:
            continue
        try:
            data_proc = datetime.fromisoformat(data_raw).date()
            if data_proc in dados_dia:
                if p.get("tipo") == "DS" or p.get("despacho_singular"):
                    dados_dia[data_proc]["ds"] += 1
                if p.get("tipo") == "SUSTENTACAO" or p.get("sustentacao_oral"):
                    dados_dia[data_proc]["sustentacao"] += 1
        except Exception:
            pass

    total_ds = sum(d["ds"] for d in dados_dia.values())
    total_sust = sum(d["sustentacao"] for d in dados_dia.values())

    col1, col2, col3 = st.columns(3)
    col1.metric("Despachos Singulares (semana)", total_ds)
    col2.metric("Sustentações Orais (semana)", total_sust)
    col3.metric("Total Geral", total_ds + total_sust)

    dados_tabela = []
    for d in dias_semana:
        dados_tabela.append({
            "Dia": d.strftime("%d/%m (%a)"),
            "Despachos Singulares": dados_dia[d]["ds"],
            "Sustentações Orais": dados_dia[d]["sustentacao"],
            "Total do Dia": dados_dia[d]["ds"] + dados_dia[d]["sustentacao"],
        })

    df = pd.DataFrame(dados_tabela)
    st.dataframe(df, hide_index=True, use_container_width=True)

def _processar_pedido_vista(num_processo, usuario):
    """Localiza o processo em todas as tabelas e marca como pedido de vista."""
    tabelas_busca = ["pauta_seat", "distribuicao_sexp", "processos_urgentes"]
    encontrados = 0

    for tabela in tabelas_busca:
        try:
            processos = db_manager.buscar_todos(tabela) or []
            for p in processos:
                p_num = p.get("processo_numero", "")
                if num_processo in p_num or p_num in num_processo:
                    pid = p.get("id")
                    if pid:
                        comentarios_atuais = p.get("comentarios", "") or ""
                        novo_comentario = f"\n[Pedido de Vista — {datetime.now().strftime('%d/%m/%Y %H:%M')} por {usuario.get('nome', '—')}]"
                        db_manager.atualizar(tabela, pid, {
                            "comentarios": comentarios_atuais + novo_comentario,
                            "pedido_vista": True,
                        })
                        encontrados += 1
        except Exception:
            pass

    if encontrados > 0:
        st.success(f"✅ Processo localizado e marcado como pedido de vista em {encontrados} tabela(s)!")
    else:
        st.error("❌ Processo não encontrado em nenhuma tabela. Verifique o número e tente novamente.")

# ============================================================
# ESCALA DO PLENÁRIO
# ============================================================
def _renderizar_escala_plenario(usuario):
    """Escala do Plenário — rodízio toda quarta-feira."""
    st.markdown("### 📅 Escala do Plenário")
    st.caption("Rodízio de acompanhamento do Secretário nas sessões plenárias de quarta-feira.")

    is_gestor = _tem_permissao_gestao(usuario)

    # Buscar escala existente
    try:
        escala = db_manager.buscar_todos("escala_plenario", ordem_coluna="data_sessao", ordem_desc=False) or []
    except Exception:
        escala = []

    # Gerar próximas 4 quartas-feiras se não existirem
    hoje = date.today()
    dias_ate_quarta = (2 - hoje.weekday()) % 7
    if dias_ate_quarta == 0:
        proxima_quarta = hoje
    else:
        proxima_quarta = hoje + timedelta(days=dias_ate_quarta)

    quartas = []
    for i in range(4):
        quartas.append(proxima_quarta + timedelta(weeks=i))

    # Verificar quais quartas já têm registro
    datas_existentes = set()
    for e in escala:
        try:
            d = e.get("data_sessao", "")
            if d:
                datas_existentes.add(datetime.fromisoformat(str(d)[:10]).date())
        except Exception:
            pass

    # Mostrar próximas sessões
    st.markdown("#### Próximas Sessões Plenárias")

    for q in quartas:
        ja_existe = q in datas_existentes
        registro = None
        if ja_existe:
            for e in escala:
                try:
                    d = datetime.fromisoformat(str(e.get("data_sessao", ""))[:10]).date()
                    if d == q:
                        registro = e
                        break
                except Exception:
                    pass

        data_fmt = q.strftime("%d/%m/%Y (%A)")

        if registro:
            secretario = "✅ Presente" if registro.get("secretario_presente", True) else "❌ Ausente"
            acompanhante = registro.get("acompanhante_nome", "—")
            cargo_acomp = registro.get("acompanhante_cargo", "—")
            obs = registro.get("observacoes", "") or "—"

            with st.expander(f"📅 {data_fmt} — {acompanhante} ({cargo_acomp})"):
                st.write(f"**Secretário:** {secretario}")
                st.write(f"**Acompanhante:** {acompanhante} ({cargo_acomp})")
                st.write(f"**Observações:** {obs}")

                if is_gestor:
                    rid = registro.get("id")
                    if st.button("🗑️ Remover", key=f"rm_escala_{rid}"):
                        db_manager.atualizar("escala_plenario", rid, {"ativo": False})
                        st.rerun()
        else:
            with st.expander(f"📅 {data_fmt} — Não definido"):
                if is_gestor:
                    st.markdown("**Definir Acompanhante:**")
                    with st.form(f"form_escala_{q.isoformat()}"):
                        secretario_presente = st.checkbox("Secretário presente", value=True, key=f"sec_pres_{q.isoformat()}")
                        acompanhante_nome = st.text_input("Nome do Acompanhante", key=f"acomp_nome_{q.isoformat()}")
                        acompanhante_cargo = st.selectbox(
                            "Cargo",
                            ["Subsecretário", "Gerente SEAT", "Gerente SEXP", "Gerente SERCON", "Gerente SEMAND", "Assessor Especial"],
                            key=f"acomp_cargo_{q.isoformat()}"
                        )
                        obs_escala = st.text_area("Observações", placeholder="Informações adicionais...", height=60, key=f"obs_escala_{q.isoformat()}")

                        if st.form_submit_button("💾 Salvar Escala", type="primary", use_container_width=True):
                            if acompanhante_nome.strip():
                                dados_escala = {
                                    "data_sessao": q.isoformat(),
                                    "secretario_presente": secretario_presente,
                                    "acompanhante_nome": acompanhante_nome.strip(),
                                    "acompanhante_cargo": acompanhante_cargo,
                                    "observacoes": obs_escala.strip(),
                                    "criado_por": usuario.get("nome", "—"),
                                    "ativo": True,
                                }
                                try:
                                    db_manager.inserir("escala_plenario", dados_escala)
                                    st.success("✅ Escala salva!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao salvar: {e}")
                            else:
                                st.warning("Digite o nome do acompanhante.")
                else:
                    st.info("Aguardando definição pela gestão.")

    # Histórico de escalas
    if escala:
        st.markdown("---")
        st.markdown("#### Histórico de Escalas")
        dados_hist = []
        for e in escala:
            if not e.get("ativo", True):
                continue
            sec = "Presente" if e.get("secretario_presente", True) else "Ausente"
            dados_hist.append({
                "Data": str(e.get("data_sessao", "—"))[:10],
                "Secretário": sec,
                "Acompanhante": e.get("acompanhante_nome", "—"),
                "Cargo": e.get("acompanhante_cargo", "—"),
                "Observações": e.get("observacoes", "") or "—",
            })
        if dados_hist:
            df_hist = pd.DataFrame(dados_hist)
            st.dataframe(df_hist, hide_index=True, use_container_width=True)

# ============================================================
# CADASTRO DE FÉRIAS (Gestão + Secretarias)
# ============================================================
def _renderizar_cadastro_ferias(usuario):
    """Cadastro de férias/abono para o topo da pirâmide: gestão e secretarias."""
    is_gestor = _tem_permissao_gestao(usuario)

    if not is_gestor:
        st.warning("⚠️ Acesso restrito a Raiz, Gerentes e Secretarias.")
        return

    st.markdown("### 🏖️ Cadastro de Férias e Abonos")
    st.caption("Marcação de férias, atestados e abonos para a gestão e secretarias.")

    nome_usuario = usuario.get("nome", "—")
    cargo = usuario.get("nivel_acesso", usuario.get("cargo", "—")).lower()
    is_secretaria = cargo in ("secretaria", "espectadora_global")
    is_raiz = cargo in ("criador", "raiz", "admin", "super_admin_criador") or "juan" in nome_usuario.lower()

    tab_solicitar, tab_quadro, tab_aprovacao = st.tabs([
        "➕ Nova Marcação",
        "📅 Quadro de Afastamentos",
        "✅ Aprovações Pendentes",
    ])

    # --- ABA 1: NOVA MARCAÇÃO ---
    with tab_solicitar:
        st.markdown(f"**Solicitante:** {nome_usuario}")

        with st.form("form_ferias_gab"):
            col1, col2 = st.columns(2)
            with col1:
                data_ini = st.date_input("Data de Início *", value=date.today(), key="dt_ini_ferias_gab")
            with col2:
                data_fim = st.date_input("Data de Retorno/Fim *", value=date.today(), key="dt_fim_ferias_gab")

            tipo_registro = st.radio(
                "Tipo",
                ["Férias", "Atestado Médico", "Abono"],
                horizontal=True,
                key="tipo_ferias_gab"
            )

            observacoes = st.text_area("Observações", placeholder="Informações adicionais...", height=70, key="obs_ferias_gab")

            if st.form_submit_button("Registrar", type="primary", use_container_width=True):
                if data_fim < data_ini:
                    st.error("A data de término não pode ser anterior à data de início.")
                else:
                    dias_total = (data_fim - data_ini).days + 1

                    if tipo_registro == "Férias":
                        tipo_db = "FERIAS"
                    elif tipo_registro == "Atestado Médico":
                        tipo_db = "ATESTADO"
                    else:
                        tipo_db = "ABONO"

                    # Secretaria precisa de confirmação do Secretário/Subsecretário
                    if is_secretaria and not is_raiz:
                        status_inicial = "PENDENTE"
                        msg_sucesso = f"Solicitação de {tipo_registro.lower()} ({dias_total} dias) enviada para confirmação do Secretário/Subsecretário."
                    else:
                        status_inicial = "APROVADA"
                        msg_sucesso = f"✅ {tipo_registro} ({dias_total} dias) registrado e confirmado!"

                    # Verificar choque de datas
                    try:
                        todas = db_manager.buscar_todos("solicitacoes_ausencia") or []
                    except Exception:
                        todas = []

                    choques = []
                    for s in todas:
                        if s.get("status") not in ("APROVADA", "NOTIFICADO"):
                            continue
                        s_ini_raw = str(s.get("data_inicio", ""))[:10]
                        s_fim_raw = str(s.get("data_fim", ""))[:10]
                        if not s_ini_raw or not s_fim_raw:
                            continue
                        try:
                            s_ini = datetime.fromisoformat(s_ini_raw).date()
                            s_fim = datetime.fromisoformat(s_fim_raw).date()
                            if data_ini <= s_fim and data_fim >= s_ini:
                                choques.append({
                                    "nome": s.get("colaborador_nome", "—"),
                                    "tipo": s.get("tipo", "—"),
                                    "inicio": s_ini.strftime("%d/%m/%Y"),
                                    "fim": s_fim.strftime("%d/%m/%Y"),
                                })
                        except Exception:
                            pass

                    dados_ferias = {
                        "matricula": str(usuario.get("matricula", "")),
                        "colaborador_nome": nome_usuario,
                        "setor": usuario.get("setor", "GAB"),
                        "tipo": tipo_db,
                        "data_inicio": data_ini.isoformat(),
                        "data_fim": data_fim.isoformat(),
                        "dias_afastado": dias_total,
                        "observacoes": observacoes.strip(),
                        "status": status_inicial,
                    }

                    try:
                        res = db_manager.inserir("solicitacoes_ausencia", dados_ferias)
                        if res:
                            st.success(msg_sucesso)
                            if choques:
                                st.warning(f"⚠️ **Atenção:** {len(choques)} pessoa(s) já tem afastamento neste período:")
                                for c in choques:
                                    st.write(f"- **{c['nome']}** — {c['tipo']} de {c['inicio']} a {c['fim']}")
                            st.rerun()
                        else:
                            st.error("Erro ao registrar no banco de dados.")
                    except Exception as e:
                        st.error(f"Erro: {e}")

    # --- ABA 2: QUADRO DE AFASTAMENTOS ---
    with tab_quadro:
        st.markdown("#### 📅 Quadro de Afastamentos da Gestão")

        try:
            todas = db_manager.buscar_todos("solicitacoes_ausencia", ordem_coluna="data_inicio", ordem_desc=False) or []
        except Exception:
            todas = []

        publicas = [s for s in todas if s.get("status") in ("APROVADA", "NOTIFICADO")]

        if not publicas:
            st.info("Nenhum afastamento programado no momento.")
        else:
            dados_quadro = []
            for s in publicas:
                tipo_raw = s.get("tipo", "—")
                tipo_lbl = {"FERIAS": "🌴 Férias", "ATESTADO": "🏥 Atestado", "ABONO": "📋 Abono"}.get(tipo_raw, tipo_raw)
                dados_quadro.append({
                    "Colaborador": s.get("colaborador_nome", "—"),
                    "Setor": s.get("setor", "—"),
                    "Tipo": tipo_lbl,
                    "Início": str(s.get("data_inicio", "—"))[:10],
                    "Fim": str(s.get("data_fim", "—"))[:10],
                    "Dias": s.get("dias_afastado", "—"),
                    "Observação": s.get("observacoes", "") or "—",
                })
            df_quadro = pd.DataFrame(dados_quadro)
            st.dataframe(df_quadro, hide_index=True, use_container_width=True)

    # --- ABA 3: APROVAÇÕES PENDENTES ---
    with tab_aprovacao:
        st.markdown("#### ✅ Aprovações Pendentes")

        try:
            pendentes = [s for s in todas if s.get("status") == "PENDENTE"]
        except Exception:
            pendentes = []

        if not pendentes:
            st.success("✅ Nenhuma aprovação pendente.")
        else:
            st.markdown(f"**{len(pendentes)} solicitação(ões) aguardando aprovação:**")

            for s in pendentes:
                sid = s.get("id")
                nome = s.get("colaborador_nome", "—")
                setor = s.get("setor", "—")
                tipo = s.get("tipo", "—")
                data_ini = str(s.get("data_inicio", "—"))[:10]
                data_fim = str(s.get("data_fim", "—"))[:10]
                dias = s.get("dias_afastado", "—")
                obs = s.get("observacoes", "") or "—"

                tipo_label = {"FERIAS": "🌴 Férias", "ATESTADO": "🏥 Atestado", "ABONO": "📋 Abono"}.get(tipo, tipo)

                with st.expander(f"{tipo_label} — {nome} ({setor}) — {data_ini} a {data_fim} ({dias} dias)"):
                    st.write(f"**Colaborador:** {nome}")
                    st.write(f"**Setor:** {setor}")
                    st.write(f"**Tipo:** {tipo_label}")
                    st.write(f"**Período:** {data_ini} a {data_fim}")
                    st.write(f"**Dias:** {dias}")
                    st.write(f"**Observações:** {obs}")

                    # Apenas Raiz/Secretário/Subsecretário podem aprovar
                    if is_raiz:
                        col_apr, col_rej = st.columns(2)
                        with col_apr:
                            if st.button("✅ Aprovar", key=f"apr_ferias_{sid}", type="primary", use_container_width=True):
                                db_manager.atualizar("solicitacoes_ausencia", sid, {"status": "APROVADA"})
                                st.success(f"Solicitação de {nome} aprovada!")
                                st.rerun()
                        with col_rej:
                            if st.button("❌ Rejeitar", key=f"rej_ferias_{sid}", use_container_width=True):
                                db_manager.atualizar("solicitacoes_ausencia", sid, {"status": "REJEITADA"})
                                st.info(f"Solicitação de {nome} rejeitada.")
                                st.rerun()
                    else:
                        st.info("Apenas Raiz/Secretário/Subsecretário podem aprovar.")

# ============================================================
# AGENDA DO SECRETÁRIO
# ============================================================
def _renderizar_agenda_secretario(usuario):
    """Agenda do Secretário — secretaria marca compromissos."""
    is_gestor = _tem_permissao_gestao(usuario)

    if not is_gestor:
        st.warning("⚠️ Acesso restrito a gestores e secretarias.")
        return

    st.markdown("### 📋 Agenda do Secretário")
    st.caption("Registro de compromissos, reuniões e audiências do Secretário.")

    tab_novo, tab_lista = st.tabs(["➕ Novo Compromisso", "📅 Compromissos Agendados"])

    # --- NOVO COMPROMISSO ---
    with tab_novo:
        with st.form("form_agenda"):
            col1, col2 = st.columns(2)
            with col1:
                data_comp = st.date_input("Data *", value=date.today(), key="dt_agenda")
                hora_ini = st.time_input("Hora de Início *", key="hora_ini_agenda")
            with col2:
                hora_fim = st.time_input("Hora de Término *", key="hora_fim_agenda")
                tipo_comp = st.selectbox("Tipo", ["Reunião", "Audiência", "Compromisso Externo", "Outro"], key="tipo_agenda")

            titulo = st.text_input("Título *", placeholder="Ex: Reunião com Diretoria", key="titulo_agenda")
            local = st.text_input("Local", placeholder="Ex: Sala de Reuniões / Gabinete", key="local_agenda")
            descricao = st.text_area("Descrição", placeholder="Detalhes do compromisso...", height=70, key="desc_agenda")

            if st.form_submit_button("💾 Agendar", type="primary", use_container_width=True):
                if not titulo.strip():
                    st.warning("Digite um título.")
                elif hora_fim <= hora_ini:
                    st.warning("A hora de término deve ser posterior à de início.")
                else:
                    dados_agenda = {
                        "data_compromisso": data_comp.isoformat(),
                        "hora_inicio": hora_ini.strftime("%H:%M"),
                        "hora_fim": hora_fim.strftime("%H:%M"),
                        "titulo": titulo.strip(),
                        "descricao": descricao.strip(),
                        "local": local.strip(),
                        "tipo": tipo_comp,
                        "status": "CONFIRMADO",
                        "registrado_por": usuario.get("nome", "—"),
                    }
                    try:
                        res = db_manager.inserir("agenda_secretario", dados_agenda)
                        if res:
                            st.success("✅ Compromisso agendado!")
                            st.rerun()
                        else:
                            st.error("Erro ao agendar.")
                    except Exception as e:
                        st.error(f"Erro: {e}")

    # --- LISTA DE COMPROMISSOS ---
    with tab_lista:
        try:
            compromissos = db_manager.buscar_todos("agenda_secretario", ordem_coluna="data_compromisso", ordem_desc=False) or []
        except Exception:
            compromissos = []

        if not compromissos:
            st.info("Nenhum compromisso agendado.")
            return

        # Filtrar apenas futuros e hoje
        hoje = date.today()
        futuros = []
        for c in compromissos:
            try:
                d = datetime.fromisoformat(str(c.get("data_compromisso", ""))[:10]).date()
                if d >= hoje:
                    futuros.append((d, c))
            except Exception:
                pass

        if not futuros:
            st.info("Nenhum compromisso futuro agendado.")
            return

        futuros.sort(key=lambda x: x[0])

        dados_lista = []
        for d, c in futuros:
            dados_lista.append({
                "Data": d.strftime("%d/%m/%Y"),
                "Início": c.get("hora_inicio", "—"),
                "Fim": c.get("hora_fim", "—"),
                "Título": c.get("titulo", "—"),
                "Tipo": c.get("tipo", "—"),
                "Local": c.get("local", "—"),
                "Registrado por": c.get("registrado_por", "—"),
            })

        df_lista = pd.DataFrame(dados_lista)
        st.dataframe(df_lista, hide_index=True, use_container_width=True)

        # Detalhes em expanders
        st.markdown("##### Detalhes")
        for d, c in futuros:
            cid = c.get("id")
            titulo = c.get("titulo", "—")
            with st.expander(f"📅 {d.strftime('%d/%m/%Y')} {c.get('hora_inicio', '')} — {titulo}"):
                st.write(f"**Título:** {titulo}")
                st.write(f"**Tipo:** {c.get('tipo', '—')}")
                st.write(f"**Data:** {d.strftime('%d/%m/%Y')}")
                st.write(f"**Horário:** {c.get('hora_inicio', '—')} às {c.get('hora_fim', '—')}")
                st.write(f"**Local:** {c.get('local', '—')}")
                st.write(f"**Descrição:** {c.get('descricao', '—')}")
                st.write(f"**Registrado por:** {c.get('registrado_por', '—')}")

                if st.button("🗑️ Cancelar Compromisso", key=f"rm_agenda_{cid}"):
                    db_manager.atualizar("agenda_secretario", cid, {"status": "CANCELADO"})
                    st.info("Compromisso cancelado.")
                    st.rerun()

# ============================================================
# AUDITORIA
# ============================================================
def _renderizar_auditoria(usuario):
    """Tab de auditoria — tabela corrida de todos os processos."""
    st.markdown("### 📝 Auditoria de Processos")
    st.caption("Tabela corrida de todos os processos que entraram no sistema. Processos podem aparecer duplicados.")

    todos_processos = []

    try:
        seat = db_manager.buscar_todos("pauta_seat") or []
        for p in seat:
            todos_processos.append({
                "Setor": "SEAT",
                "Nº Sessão": p.get("numero_sessao", p.get("sessao_numero", "—")),
                "Nº Processo": p.get("processo_numero", "—"),
                "Relator": p.get("relator", "—"),
                "Editor": p.get("editor", "—"),
                "Revisor": p.get("revisor", "—"),
                "Expedidor": "—",
                "Revisor (SEXP)": "—",
                "Entrada": str(p.get("data_entrada", p.get("criado_em", "—")))[:10],
                "Saída": str(p.get("data_saida", "—"))[:10] if p.get("sessao_finalizada") else "—",
                "Status": "Arquivado" if p.get("sessao_finalizada") else ("Retirado" if p.get("removido_pauta") else "Ativo"),
            })
    except Exception:
        pass

    try:
        sexp = db_manager.buscar_todos("distribuicao_sexp") or []
        for p in sexp:
            todos_processos.append({
                "Setor": "SEXP",
                "Nº Sessão": p.get("numero_sessao", p.get("sessao_numero", "—")),
                "Nº Processo": p.get("processo_numero", "—"),
                "Relator": p.get("relator", "—"),
                "Editor": "—",
                "Revisor": "—",
                "Expedidor": p.get("expedidor", "—"),
                "Revisor (SEXP)": p.get("revisor", "—"),
                "Entrada": str(p.get("data_entrada", p.get("criado_em", "—")))[:10],
                "Saída": str(p.get("data_saida", "—"))[:10] if p.get("sessao_finalizada") else "—",
                "Status": "Arquivado" if p.get("sessao_finalizada") else ("Retirado" if p.get("removido_pauta") else "Ativo"),
            })
    except Exception:
        pass

    if not todos_processos:
        st.info("Nenhum processo registrado na auditoria ainda.")
        return

    df = pd.DataFrame(todos_processos)

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        setores = ["Todos"] + list(df["Setor"].unique())
        filtro_setor = st.selectbox("Filtrar por Setor", setores, key="filtro_setor_aud")
    with col_f2:
        status_opcoes = ["Todos"] + list(df["Status"].unique())
        filtro_status = st.selectbox("Filtrar por Status", status_opcoes, key="filtro_status_aud")
    with col_f3:
        busca_proc = st.text_input("Buscar Nº Processo", key="busca_proc_aud")

    df_filtrado = df.copy()
    if filtro_setor != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Setor"] == filtro_setor]
    if filtro_status != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]
    if busca_proc.strip():
        df_filtrado = df_filtrado[df_filtrado["Nº Processo"].str.contains(busca_proc.strip(), case=False, na=False)]

    st.markdown(f"**{len(df_filtrado)} processo(s) encontrado(s)**")
    st.dataframe(df_filtrado, hide_index=True, use_container_width=True, height=500)
