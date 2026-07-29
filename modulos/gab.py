"""
GAB — Torre de Controle (Gabinete)
Módulo principal do Gabinete com Dashboard Geral, tabs por setor,
controle de férias, auditoria, avisos e pedido de vista.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import db_manager
from modulos.busca_diarios import _renderizar_busca_diarios
from modulos.gerenciar_dados import _tem_permissao_gestao

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def renderizar(usuario: dict, modo_edicao: bool = False):
    """Função principal do módulo GAB."""
    if not usuario or not isinstance(usuario, dict):
        st.error("Não foi possível carregar os dados do usuário.")
        return

    nome = usuario.get("nome", "Usuário")
    cargo = usuario.get("cargo", "—")
    setor = usuario.get("setor", "GAB")

    st.markdown(f"**Colaborador:** {nome} | **Cargo:** {cargo} | **Setor:** {setor}")
    st.markdown("---")

    # ============================================================
    # SIDEBAR ESQUERDO — AVISOS, PEDIDO DE VISTA, URGENTES
    # ============================================================
    _renderizar_sidebar_gab(usuario)

    # ============================================================
    # BANNER DE AVISOS ATIVOS (TOPO DA PÁGINA)
    # ============================================================
    _renderizar_banner_avisos(usuario)

    # ============================================================
    # TABS PRINCIPAIS
    # ============================================================
    tab_dashboard, tab_seat, tab_sexp, tab_sercon, tab_semand = st.tabs([
        "📊 Dashboard Geral",
        "📂 SEAT",
        "📂 SEXP",
        "📂 SERCON",
        "📂 SEMAND",
    ])

    tab_escala, tab_ferias, tab_busca, tab_agenda, tab_auditoria = st.tabs([
        "📅 Escala do Plenário",
        "🏖️ Controle de Férias",
        "🔍 Pesquisa nos Diários",
        "📋 Agenda do Secretário",
        "📝 Auditoria",
    ])

    with tab_dashboard:
        _renderizar_dashboard_geral(usuario)
    with tab_seat:
        _renderizar_dashboard_setor(usuario, "SEAT")
    with tab_sexp:
        _renderizar_dashboard_setor(usuario, "SEXP")
    with tab_sercon:
        st.info("Módulo SERCON em desenvolvimento — aguardando definição do fluxo operacional.")
    with tab_semand:
        st.info("Módulo SEMAND em desenvolvimento — aguardando definição do fluxo operacional.")
    with tab_escala:
        st.info("Escala do Plenário em desenvolvimento.")
    with tab_ferias:
        _renderizar_controle_ferias(usuario)
    with tab_busca:
        _renderizar_busca_diarios(usuario)
    with tab_agenda:
        st.info("Agenda do Secretário em desenvolvimento.")
    with tab_auditoria:
        _renderizar_auditoria(usuario)

# ============================================================
# DASHBOARD GERAL
# ============================================================
def _renderizar_dashboard_geral(usuario):
    """Dashboard principal com métricas de volume, tempo e desempenho."""
    st.markdown("### 📊 Dashboard Geral do Gabinete")
    st.caption("Visão consolidada de todos os setores — dados em tempo real.")

    # ============================================================
    # MÉTRICAS DE VOLUME
    # ============================================================
    st.markdown("#### 📈 Métricas de Volume")

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

    # Calcular métricas
    total_seat = len([p for p in seat_processos if not p.get("sessao_finalizada", False) and not p.get("removido_pauta", False)])
    total_sexp = len([p for p in sexp_distribuicao if not p.get("sessao_finalizada", False) and not p.get("removido_pauta", False) and p.get("distribuido", False)])
    total_urgentes = len(urgentes)
    urgentes_ativos = len([u for u in urgentes if not u.get("despachado", False)])
    urgentes_despachados = len([u for u in urgentes if u.get("despachado", False)])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Processos SEAT", total_seat)
    col2.metric("Processos SEXP", total_sexp)
    col3.metric("Urgentes Ativos", urgentes_ativos)
    col4.metric("Urgentes Despachados", urgentes_despachados)

    # ============================================================
    # GRÁFICO DE PIZZA — Processos por Sessão
    # ============================================================
    st.markdown("#### 🥧 Processos por Sessão")

    # Agrupar por número de sessão (SEAT + SEXP)
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
        df_sessoes = pd.DataFrame(
            list(sessoes.items()),
            columns=["Sessão", "Quantidade"]
        )
        st.dataframe(df_sessoes, hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum processo ativo no momento.")

    # ============================================================
    # MÉTRICAS DE TEMPO — SEAT
    # ============================================================
    st.markdown("#### ⏱️ Métricas de Tempo — SEAT")

    tempos_seat = _calcular_tempos_seat(seat_processos)
    col_t1, col_t2, col_t3 = st.columns(3)
    col_t1.metric("Tempo Médio de Edição", tempos_seat.get("edicao", "—"))
    col_t2.metric("Tempo Médio de Revisão", tempos_seat.get("revisao", "—"))
    col_t3.metric("Tempo de Finalização da Sessão", tempos_seat.get("finalizacao", "—"))

    # ============================================================
    # MÉTRICAS DE TEMPO — SEXP
    # ============================================================
    st.markdown("#### ⏱️ Métricas de Tempo — SEXP")

    tempos_sexp = _calcular_tempos_sexp(sexp_distribuicao)
    col_x1, col_x2, col_x3 = st.columns(3)
    col_x1.metric("Tempo Médio de Expedição", tempos_sexp.get("expedicao", "—"))
    col_x2.metric("Tempo Médio de Revisão", tempos_sexp.get("revisao", "—"))
    col_x3.metric("Tempo de Finalização da Sessão", tempos_sexp.get("finalizacao", "—"))

    # ============================================================
    # QUADRO DE COLABORADORES
    # ============================================================
    st.markdown("#### 👥 Desempenho de Colaboradores")
    _renderizar_quadro_colaboradores(seat_processos, sexp_distribuicao)

    # ============================================================
    # LINHA DO TEMPO — DESPACHOS DA SEMANA
    # ============================================================
    st.markdown("#### 📅 Linha do Tempo — Despachos da Semana")
    _renderizar_linha_tempo_despachos(seat_processos, sexp_distribuicao)

# ============================================================
# DASHBOARD POR SETOR
# ============================================================
def _renderizar_dashboard_setor(usuario, setor):
    """Dashboard operacional de cada setor."""
    st.markdown(f"### 📂 Dashboard Operacional — {setor}")

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

        # Desempenho por colaborador
        st.markdown("#### Desempenho por Colaborador")
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

        # Desempenho por colaborador
        st.markdown("#### Desempenho por Colaborador")
        _renderizar_desempenho_colaborador(processos, "SEXP")

# ============================================================
# SIDEBAR DO GAB
# ============================================================
def _renderizar_sidebar_gab(usuario):
    """Renderiza os elementos do sidebar: Avisos, Pedido de Vista, Urgentes."""
    is_gestor = _tem_permissao_gestao(usuario)

    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📢 Avisos do Gabinete")

        if is_gestor:
            with st.expander("➕ Enviar Aviso"):
                # Determinar escopo de envio
                if usuario.get("cargo", "").lower() in ["criador", "raiz", "admin"] or "juan" in usuario.get("nome", "").lower():
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

        # ============================================================
        # PEDIDO DE VISTA (somente Raiz/Criador)
        # ============================================================
        st.markdown("---")
        st.markdown("### 👁️ Pedido de Vista")

        if is_gestor and (usuario.get("cargo", "").lower() in ["criador", "raiz", "admin"] or "juan" in usuario.get("nome", "").lower()):
            with st.expander("Registrar Pedido de Vista"):
                num_proc = st.text_input("Número do Processo", placeholder="Ex: 1234567-89.2024.8.26.0000", key="num_vista_gab")

                if st.button("🔍 Localizar e Marcar", type="primary", use_container_width=True, key="btn_vista_gab"):
                    if num_proc.strip():
                        _processar_pedido_vista(num_proc.strip(), usuario)
                    else:
                        st.warning("Digite o número do processo.")
        else:
            st.info("Acesso restrito a Raiz.")

        # ============================================================
        # CONTADOR DE URGENTES
        # ============================================================
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
# # ============================================================
def _renderizar_banner_avisos(usuario):
    """Renderiza banner rotativo de avisos ativos no topo da página."""
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
        # Verificar se ainda está dentro da duração
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
# CONTROLE DE FÉRIAS (APROVAÇÃO)
# ============================================================
def _renderizar_controle_ferias(usuario):
    """Tab de aprovação de férias, atestados e abonos."""
    is_gestor = _tem_permissao_gestao(usuario)

    if not is_gestor:
        st.warning("⚠️ Acesso restrito a Raiz, Gerentes e Secretarias.")
        return

    st.markdown("### 🏖️ Controle de Férias, Atestados e Abonos")
    st.caption("Aprove ou rejeite solicitações pendentes de colaboradores.")

    try:
        solicitacoes = db_manager.buscar_todos("solicitacoes_ausencia", ordem_coluna="data_inicio", ordem_desc=False) or []
    except Exception:
        solicitacoes = []

    pendentes = [s for s in solicitacoes if s.get("status") == "PENDENTE"]

    if not pendentes:
        st.success("✅ Nenhuma solicitação pendente no momento.")
        return

    st.markdown(f"**{len(pendentes)} solicitação(ões) aguardando aprovação:**")

    for s in pendentes:
        sid = s.get("id")
        nome = s.get("colaborador_nome", "—")
        setor = s.get("setor", "—")
        tipo = s.get("tipo", "—")
        data_ini = s.get("data_inicio", "—")[:10]
        data_fim = s.get("data_fim", "—")[:10]
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

            col_apr, col_rej = st.columns(2)
            with col_apr:
                if st.button("✅ Aprovar", key=f"btn_apr_{sid}", type="primary", use_container_width=True):
                    db_manager.atualizar("solicitacoes_ausencia", sid, {"status": "APROVADA"})
                    st.success(f"✅ Solicitação de {nome} aprovada!")
                    st.rerun()
            with col_rej:
                if st.button("❌ Rejeitar", key=f"btn_rej_{sid}", use_container_width=True):
                    db_manager.atualizar("solicitacoes_ausencia", sid, {"status": "REJEITADA"})
                    st.info(f"Solicitação de {nome} rejeitada.")
                    st.rerun()

# ============================================================
# AUDITORIA
# ============================================================
def _renderizar_auditoria(usuario):
    """Tab de auditoria — tabela corrida de todos os processos."""
    st.markdown("### 📝 Auditoria de Processos")
    st.caption("Tabela corrida de todos os processos que passaram pelos setores. Processos podem aparecer duplicados.")

    # Buscar dados de todas as tabelas
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

    # Filtros
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

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def _calcular_tempos_seat(processos):
    """Calcula tempos médios de edição, revisão e finalização da SEAT."""
    result = {"edicao": "—", "revisao": "—", "finalizacao": "—"}
    # TODO: Implementar cálculo real quando houver timestamps de edição/revisão
    return result

def _calcular_tempos_sexp(processos):
    """Calcula tempos médios de expedição, revisão e finalização da SEXP."""
    result = {"expedicao": "—", "revisao": "—", "finalizacao": "—"}
    # TODO: Implementar cálculo real quando houver timestamps de expedição/revisão
    return result

def _renderizar_quadro_colaboradores(seat_processos, sexp_processos):
    """Quadro com nomes de colaboradores, total trabalhado e ativos."""
    colaboradores = {}

    # SEAT
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

    # SEXP
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

        if setor == "SEAT" and p.get("revisado"):
            colaboradores[pessoa]["concluidos"] += 1
        elif setor == "SEXP" and p.get("revisado"):
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

    # Contar DS e Sustentações da SEAT
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

    # Tabela por dia
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
