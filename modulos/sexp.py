import streamlit as st
from datetime import date, timedelta

# ==================== CONSTANTES ====================

TIPOS_SESSAO_SEXP = [
    "Sessão Ordinária",
    "Sessão Ordinária Virtual",
    "Sessão Reservada",
    "Sessão Administrativa",
    "Urgentes",
]

# ==================== FUNÇÕES AUXILIARES ====================

def _normalizar_texto(texto):
    import unicodedata
    if not texto:
        return ""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto

def _normalizar_numero_processo(numero):
    if not numero:
        return ""
    numero = str(numero).strip()
    numero = numero.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
    if numero.endswith("-e"):
        numero = numero[:-2]
    if numero.endswith("-E"):
        numero = numero[:-2]
    numero = numero.replace("\u200b", "").replace("\u00a0", "").replace("\ufeff", "")
    return numero.strip()

# ==================== COLABORADORES ====================

def _obter_colaboradores():
    try:
        return db_manager.buscar_todos(
            "colaboradores_sexp",
            filtros={"ativo": True},
            ordem_coluna="nome",
            ordem_desc=False,
        ) or []
    except Exception:
        return []

def _obter_colaboradores_por_cargo(tipo_sessao):
    """
    Retorna colaboradores elegiveis para um tipo de sessao.
    - Reservada: exclui estagiarios
    - Administrativa: apenas gerentes/criador/raiz
    - Outras: todos
    """
    todos = _obter_colaboradores()
    tipo_norm = _normalizar_texto(tipo_sessao)

    if "reservada" in tipo_norm:
        return [c for c in todos if _normalizar_texto(c.get("cargo", "")) != "estagiario"]
    elif "administrativa" in tipo_norm:
        return [c for c in todos if _normalizar_texto(c.get("cargo", "")) in ("gerente", "criador", "raiz")]
    else:
        return todos

# ==================== DISTRIBUICAO ====================

def _gerar_cadeia_duplas(colaboradores):
    """
    Gera cadeia de duplas: A->B, B->C, C->D, D->A
    Retorna lista de (expedidor, revisor).
    """
    nomes = [c.get("nome", "") for c in colaboradores if c.get("nome")]
    if len(nomes) < 2:
        return []

    duplas = []
    n = len(nomes)
    for i in range(n):
        expedidor = nomes[i]
        revisor = nomes[(i + 1) % n]
        duplas.append((expedidor, revisor))
    return duplas

def _determinar_tabela_sexp(tipo_sessao, is_urgente):
    """
    Determina em qual tabela do SEXP o processo deve ir.
    - Reservada: sempre na tabela Reservada (mesmo se urgente)
    - Urgente e nao-Reservada: tabela Urgentes
    - Nao-urgente: tabela do seu tipo de sessao
    """
    tipo_norm = _normalizar_texto(tipo_sessao)

    if "reservada" in tipo_norm:
        return "Sessão Reservada"

    if is_urgente:
        return "Urgentes"

    if "ordinaria" in tipo_norm and "virtual" not in tipo_norm:
        return "Sessão Ordinária"
    elif "virtual" in tipo_norm:
        return "Sessão Ordinária Virtual"
    elif "administrativa" in tipo_norm:
        return "Sessão Administrativa"
    else:
        return "Sessão Ordinária"

def _sincronizar_com_seat():
    """
    Puxa processos do SEAT (status encaminhado) que ainda nao foram distribuidos no SEXP.
    """
    try:
        processos_seat = db_manager.buscar_todos("pauta_seat") or []
        processos_prontos = [p for p in processos_seat if p.get("status") == "encaminhado"]

        if not processos_prontos:
            return 0

        ja_distribuidos = db_manager.buscar_todos("distribuicao_sexp") or []
        nums_distribuidos = set()
        for d in ja_distribuidos:
            nums_distribuidos.add(_normalizar_numero_processo(d.get("processo_numero", "")))

        try:
            urgentes = db_manager.buscar_todos("processos_urgentes") or []
            nums_urgentes = set()
            for u in urgentes:
                nums_urgentes.add(_normalizar_numero_processo(u.get("processo_numero", "")))
        except Exception:
            nums_urgentes = set()

        novos = []
        for p in processos_prontos:
            p_num = _normalizar_numero_processo(p.get("processo_numero", ""))
            if p_num and p_num not in nums_distribuidos:
                novos.append(p)

        if not novos:
            return 0

        por_tabela = {}
        for p in novos:
            p_num = _normalizar_numero_processo(p.get("processo_numero", ""))
            is_urgente = p_num in nums_urgentes
            tabela = _determinar_tabela_sexp(p.get("tipo_sessao", ""), is_urgente)
            if tabela not in por_tabela:
                por_tabela[tabela] = []
            por_tabela[tabela].append(p)

        total = 0
        for tabela, processos in por_tabela.items():
            colaboradores = _obter_colaboradores_por_cargo(tabela)
            duplas = _gerar_cadeia_duplas(colaboradores)

            if not duplas:
                for p in processos:
                    p_num = _normalizar_numero_processo(p.get("processo_numero", ""))
                    db_manager.inserir("distribuicao_sexp", {
                        "processo_numero": p_num,
                        "relator": p.get("relator", "") or "",
                        "tipo_sessao": tabela,
                        "expedidor": None,
                        "expedido": False,
                        "revisor": None,
                        "revisado": False,
                        "comentarios": "",
                        "origem_seat_id": p.get("id"),
                    })
                    total += 1
            else:
                for i, p in enumerate(processos):
                    par = duplas[i % len(duplas)]
                    p_num = _normalizar_numero_processo(p.get("processo_numero", ""))
                    db_manager.inserir("distribuicao_sexp", {
                        "processo_numero": p_num,
                        "relator": p.get("relator", "") or "",
                        "tipo_sessao": tabela,
                        "expedidor": par[0],
                        "expedido": False,
                        "revisor": par[1],
                        "revisado": False,
                        "comentarios": "",
                        "origem_seat_id": p.get("id"),
                    })
                    total += 1

        return total
    except Exception:
        return 0

# ==================== SIDEBAR ====================

def _renderizar_sidebar_sexp(usuario):
    cargo = usuario.get("cargo", "operacional")
    nome = usuario.get("nome", "")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        todos = []

    if not todos:
        return

    if cargo == "operacional":
        meus = [d for d in todos if d.get("expedidor") == nome or d.get("revisor") == nome]
    else:
        meus = todos

    expedir = len([d for d in meus if not d.get("expedido")])
    revisar = len([d for d in meus if d.get("expedido") and not d.get("revisado")])

    with st.sidebar:
        st.markdown("---")
        st.markdown("##### 📤 SEXP — Expedição")
        st.write(f"**Para expedir:** {expedir}")
        st.write(f"**Para revisar:** {revisar}")

# ==================== CARDS ====================

def _renderizar_card_processo_sexp(p, modo_edicao, usuario):
    cargo = usuario.get("cargo", "operacional")
    nome = usuario.get("nome", "")

    expedido = p.get("expedido", False)
    revisado = p.get("revisado", False)

    if revisado:
        icone = "✅"
    elif expedido:
        icone = "📤"
    else:
        icone = "⏳"

    with st.expander(
        f"{icone} {p.get('processo_numero', '')} | "
        f"Relator: {p.get('relator', '-') or '-'} | "
        f"Exp: {p.get('expedidor', '-') or '-'} | "
        f"Rev: {p.get('revisor', '-') or '-'}"
    ):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**Processo:** {p.get('processo_numero', '')}")
            st.write(f"**Relator:** {p.get('relator', '-') or '-'}")
        with col2:
            st.write(f"**Expedidor:** {p.get('expedidor', '—') or '—'}")
            st.write(f"**Revisor:** {p.get('revisor', '—') or '—'}")
        with col3:
            st.write(f"**Expedido:** {'Sim ✅' if expedido else 'Não ⏳'}")
            st.write(f"**Revisado:** {'Sim ✅' if revisado else 'Não ⏳'}")

        comentarios_atuais = p.get("comentarios", "") or ""
        if comentarios_atuais:
            st.write(f"**Comentários:**")
            st.write(comentarios_atuais)
        else:
            st.write("**Comentários:** Nenhum")

        if modo_edicao:
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                pode_expedir = (nome == p.get("expedidor")) or cargo in ("gerente", "criador", "raiz")
                if pode_expedir and not expedido:
                    if st.button("📤 Marcar Expedido", key=f"exp_{p['id']}"):
                        db_manager.atualizar("distribuicao_sexp", p["id"], {"expedido": True})
                        st.success("Marcado como expedido!")
                        st.rerun()
                elif expedido and pode_expedir:
                    if st.button("↩️ Desfazer Expedição", key=f"unexp_{p['id']}"):
                        db_manager.atualizar("distribuicao_sexp", p["id"], {"expedido": False, "revisado": False})
                        st.rerun()

            with col_b:
                pode_revisar = (nome == p.get("revisor")) or cargo in ("gerente", "criador", "raiz")
                if pode_revisar and expedido and not revisado:
                    if st.button("✅ Marcar Revisado", key=f"rev_{p['id']}"):
                        db_manager.atualizar("distribuicao_sexp", p["id"], {"revisado": True})
                        st.success("Marcado como revisado!")
                        st.rerun()
                elif revisado and pode_revisar:
                    if st.button("↩️ Desfazer Revisão", key=f"unrev_{p['id']}"):
                        db_manager.atualizar("distribuicao_sexp", p["id"], {"revisado": False})
                        st.rerun()
                elif not expedido:
                    st.caption("Aguardando expedição")

            with col_c:
                with st.popover("💬 Comentar", key=f"com_pop_{p['id']}"):
                    novo_com = st.text_area("Adicionar comentário", key=f"com_txt_{p['id']}")
                    if st.button("Salvar Comentário", key=f"com_save_{p['id']}"):
                        if novo_com.strip():
                            com_final = comentarios_atuais
                            if com_final:
                                com_final += "\n"
                            com_final += f"[{nome}] {novo_com.strip()}"
                            db_manager.atualizar("distribuicao_sexp", p["id"], {"comentarios": com_final})
                            st.success("Comentário adicionado!")
                            st.rerun()

            if cargo in ("gerente", "criador", "raiz"):
                with st.popover("🔄 Redistribuir", key=f"red_pop_{p['id']}"):
                    st.markdown("**Redistribuir Processo**")
                    colaboradores = _obter_colaboradores()
                    nomes = [c.get("nome", "") for c in colaboradores]

                    novo_exp = st.selectbox("Novo Expedidor", options=["Manter"] + nomes, key=f"red_exp_{p['id']}")
                    novo_rev = st.selectbox("Novo Revisor", options=["Manter"] + nomes, key=f"red_rev_{p['id']}")

                    if st.button("Aplicar Redistribuição", key=f"red_save_{p['id']}"):
                        updates = {}
                        if novo_exp != "Manter":
                            updates["expedidor"] = novo_exp
                        if novo_rev != "Manter":
                            updates["revisor"] = novo_rev
                        if updates:
                            db_manager.atualizar("distribuicao_sexp", p["id"], updates)
                            st.success("Redistribuição aplicada!")
                            st.rerun()

# ==================== TABELAS ====================

def _renderizar_tabela_sessao(tipo_sessao, usuario, modo_edicao):
    cargo = usuario.get("cargo", "operacional")
    nome = usuario.get("nome", "")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        todos = []

    processos = [d for d in todos if d.get("tipo_sessao") == tipo_sessao]

    if cargo == "operacional":
        processos = [d for d in processos if d.get("expedidor") == nome or d.get("revisor") == nome]

    if not processos:
        st.info(f"Nenhum processo em {tipo_sessao}.")
        return

    total = len(processos)
    expedidos = len([p for p in processos if p.get("expedido")])
    revisados = len([p for p in processos if p.get("revisado")])
    pendentes = total - expedidos

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", total)
    with col2:
        st.metric("Pendentes", pendentes)
    with col3:
        st.metric("Expedidos", expedidos)
    with col4:
        st.metric("Revisados", revisados)

    st.markdown("---")

    for p in processos:
        _renderizar_card_processo_sexp(p, modo_edicao, usuario)

# ==================== REDISTRIBUICAO ====================

def _renderizar_redistribuicao_geral(modo_edicao, usuario):
    cargo = usuario.get("cargo", "operacional")
    if cargo not in ("gerente", "criador", "raiz"):
        st.info("Apenas gerentes podem redistribuir processos.")
        return

    st.markdown("#### 🔄 Redistribuição Manual")
    st.caption("Gerentes podem redistribuir processos entre colaboradores.")

    col_sync, col_info = st.columns([1, 3])
    with col_sync:
        if st.button("🔄 Sincronizar com SEAT", type="primary"):
            novos = _sincronizar_com_seat()
            if novos > 0:
                st.success(f"✅ {novos} processo(s) puxado(s) do SEAT!")
            else:
                st.info("Nenhum processo novo para puxar.")
            st.rerun()

    st.markdown("---")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        todos = []

    if not todos:
        st.info("Nenhum processo distribuído ainda.")
        return

    colaboradores = _obter_colaboradores()
    nomes = [c.get("nome", "") for c in colaboradores]

    filtro_tabela = st.selectbox(
        "Filtrar por tabela",
        options=["Todas"] + TIPOS_SESSAO_SEXP,
        key="filtro_redist_sexp"
    )

    if filtro_tabela != "Todas":
        todos = [d for d in todos if d.get("tipo_sessao") == filtro_tabela]

    for p in todos:
        with st.expander(
            f"{p.get('processo_numero', '')} | "
            f"{p.get('tipo_sessao', '')} | "
            f"Exp: {p.get('expedidor', '—') or '—'} | "
            f"Rev: {p.get('revisor', '—') or '—'}"
        ):
            st.write(f"**Processo:** {p.get('processo_numero', '')}")
            st.write(f"**Relator:** {p.get('relator', '-') or '-'}")
            st.write(f"**Tabela:** {p.get('tipo_sessao', '')}")
            st.write(f"**Expedidor atual:** {p.get('expedidor', '—') or '—'}")
            st.write(f"**Revisor atual:** {p.get('revisor', '—') or '—'}")
            st.write(f"**Expedido:** {'Sim' if p.get('expedido') else 'Não'}")
            st.write(f"**Revisado:** {'Sim' if p.get('revisado') else 'Não'}")

            with st.form(f"form_redist_{p['id']}"):
                col1, col2 = st.columns(2)
                with col1:
                    novo_exp = st.selectbox(
                        "Novo Expedidor",
                        options=["Manter"] + nomes,
                        key=f"rd_exp_{p['id']}"
                    )
                with col2:
                    novo_rev = st.selectbox(
                        "Novo Revisor",
                        options=["Manter"] + nomes,
                        key=f"rd_rev_{p['id']}"
                    )

                if st.form_submit_button("Aplicar Redistribuição"):
                    updates = {}
                    if novo_exp != "Manter":
                        updates["expedidor"] = novo_exp
                    if novo_rev != "Manter":
                        updates["revisor"] = novo_rev
                    if updates:
                        db_manager.atualizar("distribuicao_sexp", p["id"], updates)
                        st.success("Redistribuição aplicada!")
                        st.rerun()
                    else:
                        st.info("Nenhuma alteração selecionada.")

# ==================== COLABORADORES ====================

def _renderizar_gerenciar_colaboradores(modo_edicao, usuario):
    cargo = usuario.get("cargo", "operacional")
    if cargo not in ("gerente", "criador", "raiz"):
        st.info("Apenas gerentes podem gerenciar colaboradores.")
        return

    st.markdown("#### 👥 Colaboradores do SEXP")
    st.caption("Gerencie os colaboradores que participam da distribuição.")

    colaboradores = _obter_colaboradores()

    if colaboradores:
        import pandas as pd
        dados = []
        for c in colaboradores:
            dados.append({
                "Nome": c.get("nome", ""),
                "Cargo": c.get("cargo", ""),
                "Ativo": "Sim" if c.get("ativo") else "Não",
            })
        df = pd.DataFrame(dados)
        st.dataframe(df, hide_index=True, use_container_width=True)

        st.markdown("---")

        for c in colaboradores:
            with st.expander(f"{c.get('nome', '')} | {c.get('cargo', '')}"):
                with st.form(f"form_edit_col_{c['id']}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        edit_nome = st.text_input("Nome", value=c.get("nome", ""), key=f"ec_nome_{c['id']}")
                    with col2:
                        edit_cargo = st.selectbox(
                            "Cargo",
                            options=["operacional", "estagiario", "gerente"],
                            index=["operacional", "estagiario", "gerente"].index(c.get("cargo", "operacional")),
                            key=f"ec_cargo_{c['id']}"
                        )

                    if st.form_submit_button("Salvar"):
                        db_manager.atualizar("colaboradores_sexp", c["id"], {
                            "nome": edit_nome.strip(),
                            "cargo": edit_cargo,
                        })
                        st.success("Colaborador atualizado!")
                        st.rerun()

                if st.button("Desativar", key=f"del_col_{c['id']}"):
                    db_manager.atualizar("colaboradores_sexp", c["id"], {"ativo": False})
                    st.success("Colaborador desativado!")
                    st.rerun()
    else:
        st.info("Nenhum colaborador cadastrado.")

    st.markdown("---")
    st.markdown("##### Cadastrar Novo Colaborador")
    with st.form("form_novo_col_sexp"):
        col1, col2 = st.columns(2)
        with col1:
            novo_nome = st.text_input("Nome *", key="nc_nome_sexp")
        with col2:
            novo_cargo = st.selectbox(
                "Cargo",
                options=["operacional", "estagiario", "gerente"],
                key="nc_cargo_sexp"
            )

        if st.form_submit_button("Cadastrar", type="primary"):
            if not novo_nome.strip():
                st.error("Informe o nome do colaborador.")
            else:
                db_manager.inserir("colaboradores_sexp", {
                    "nome": novo_nome.strip(),
                    "cargo": novo_cargo,
                    "ativo": True,
                })
                st.success("Colaborador cadastrado!")
                st.rerun()

# ==================== FUNCAO PRINCIPAL ====================

def renderizar(usuario: dict, modo_edicao: bool = False):
    """Funcao principal do modulo SEXP."""
    nome = usuario.get("nome", "Usuário")
    cargo = usuario.get("cargo", "operacional")
    setor = usuario.get("setor", "SEXP")

    st.markdown(f"**Colaborador:** {nome} | **Cargo:** {cargo} | **Setor:** {setor}")

    if not modo_edicao:
        st.info("Você está em modo de visualização. Operações de edição estão bloqueadas.")

    st.markdown("---")

    # Sincronizar com SEAT automaticamente
    novos = _sincronizar_com_seat()
    if novos > 0:
        st.success(f"✅ {novos} processo(s) puxado(s) do SEAT e distribuído(s)!")
        st.markdown("---")

    # Sidebar
    _renderizar_sidebar_sexp(usuario)

    # Tabs
    tab_ord, tab_virt, tab_res, tab_adm, tab_urg, tab_redist, tab_colab = st.tabs([
        "Sessão Ordinária",
        "Sessão Virtual",
        "Sessão Reservada",
        "Sessão Administrativa",
        "Urgentes",
        "Redistribuição",
        "Colaboradores",
    ])

    with tab_ord:
        st.markdown("### Sessão Ordinária")
        _renderizar_tabela_sessao("Sessão Ordinária", usuario, modo_edicao)

    with tab_virt:
        st.markdown("### Sessão Ordinária Virtual")
        _renderizar_tabela_sessao("Sessão Ordinária Virtual", usuario, modo_edicao)

    with tab_res:
        st.markdown("### Sessão Reservada")
        st.caption("⚠️ Estagiários não participam da distribuição desta sessão.")
        _renderizar_tabela_sessao("Sessão Reservada", usuario, modo_edicao)

    with tab_adm:
        st.markdown("### Sessão Administrativa")
        st.caption("👤 Apenas gerentes participam desta sessão.")
        _renderizar_tabela_sessao("Sessão Administrativa", usuario, modo_edicao)

    with tab_urg:
        st.markdown("### Urgentes")
        st.caption("Processos urgentes (exceto os da Sessão Reservada, que ficam na tabela própria).")
        _renderizar_tabela_sessao("Urgentes", usuario, modo_edicao)

    with tab_redist:
        _renderizar_redistribuicao_geral(modo_edicao, usuario)

    with tab_colab:
        _renderizar_gerenciar_colaboradores(modo_edicao, usuario)
