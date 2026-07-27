import streamlit as st
from datetime import date, timedelta
import db_manager  # ← ADICIONAR ESTA LINHA

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
    Retorna colaboradores elegíveis para um tipo de sessão.
    - Reservada: exclui estagiários
    - Administrativa: apenas gerentes
    - Outras: todos exceto gerentes
    """
    todos = _obter_colaboradores()
    tipo_norm = _normalizar_texto(tipo_sessao)

    if "reservada" in tipo_norm:
        return [c for c in todos if _normalizar_texto(c.get("cargo", "")) != "estagiario" and _normalizar_texto(c.get("cargo", "")) != "gerente"]
    elif "administrativa" in tipo_norm:
        return [c for c in todos if _normalizar_texto(c.get("cargo", "")) in ("gerente", "criador", "raiz")]
    else:
        return [c for c in todos if _normalizar_texto(c.get("cargo", "")) not in ("gerente", "criador", "raiz")]

# ==================== SINCRONIZAÇÃO COM SEAT ====================

def _sincronizar_com_seat():
    """
    Puxa processos do SEAT (status 'encaminhado') que ainda não foram importados no SEXP.
    Retorna o número de processos REALMENTE importados.
    """
    try:
        processos_seat = db_manager.buscar_todos("pauta_seat") or []
        processos_prontos = [p for p in processos_seat if p.get("status") == "encaminhado"]

        if not processos_prontos:
            return 0, 0

        ja_importados = db_manager.buscar_todos("distribuicao_sexp") or []
        nums_importados = set()
        for d in ja_importados:
            nums_importados.add(_normalizar_numero_processo(d.get("processo_numero", "")))

        try:
            urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
            nums_urgentes = set()
            for u in urgentes_seat:
                nums_urgentes.add(_normalizar_numero_processo(u.get("processo_numero", "")))
        except Exception:
            nums_urgentes = set()

        novos = []
        for p in processos_prontos:
            p_num = _normalizar_numero_processo(p.get("processo_numero", ""))
            if p_num and p_num not in nums_importados:
                novos.append(p)

        if not novos:
            return 0, len(processos_prontos)

        total_inseridos = 0
        erros = 0

        for p in novos:
            p_num = _normalizar_numero_processo(p.get("processo_numero", ""))
            is_urgente = p_num in nums_urgentes
            tipo_sessao = p.get("tipo_sessao", "Sessão Ordinária")

            tipo_norm = _normalizar_texto(tipo_sessao)
            if "reservada" in tipo_norm:
                tabela_destino = "Sessão Reservada"
            elif is_urgente:
                tabela_destino = "Urgentes"
            elif "virtual" in tipo_norm:
                tabela_destino = "Sessão Ordinária Virtual"
            elif "administrativa" in tipo_norm:
                tabela_destino = "Sessão Administrativa"
            else:
                tabela_destino = "Sessão Ordinária"

            resultado = db_manager.inserir("distribuicao_sexp", {
                "processo_numero": p_num,
                "relator": p.get("relator", "") or "",
                "tipo_sessao": tabela_destino,
                "expedidor": None,
                "expedido": False,
                "revisor": None,
                "revisado": False,
                "comentarios": "",
                "origem_seat_id": p.get("id"),
                "distribuido": False,
            })

            if resultado is not None:
                total_inseridos += 1
            else:
                erros += 1

        if erros > 0 and total_inseridos == 0:
            # Todas as inserções falharam — provavelmente a tabela não existe
            return 0, len(processos_prontos)

        return total_inseridos, len(processos_prontos)
    except Exception as e:
        return 0, 0

def _verificar_todos_revisados_seat():
    """Verifica se todos os processos da SEAT já foram revisados (encaminhados)."""
    try:
        processos_seat = db_manager.buscar_todos("pauta_seat") or []
        if not processos_seat:
            return False, 0, 0
        total = len(processos_seat)
        encaminhados = len([p for p in processos_seat if p.get("status") == "encaminhado"])
        return encaminhados == total, encaminhados, total
    except Exception:
        return False, 0, 0

# ==================== DISTRIBUIÇÃO ====================

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

def _executar_distribuicao(tipo_sessao, colaboradores_selecionados):
    """Executa a distribuição de processos para um tipo de sessão específico."""
    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
        processos = [d for d in todos if d.get("tipo_sessao") == tipo_sessao and not d.get("distribuido", False)]

        if not processos:
            return 0

        if not colaboradores_selecionados or len(colaboradores_selecionados) < 2:
            return 0

        duplas = _gerar_cadeia_duplas([{"nome": n} for n in colaboradores_selecionados])
        if not duplas:
            return 0

        for i, p in enumerate(processos):
            par = duplas[i % len(duplas)]
            db_manager.atualizar("distribuicao_sexp", p["id"], {
                "expedidor": par[0],
                "revisor": par[1],
                "distribuido": True,
            })

        return len(processos)
    except Exception:
        return 0

# ==================== SIDEBAR ====================

def _renderizar_sidebar_sexp(usuario):
    """Mostra tabelas de Expedição e Revisão + Urgentes na barra lateral."""
    import pandas as pd

    cargo = usuario.get("cargo", "operacional")
    nome = usuario.get("nome", "")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        todos = []

    if not todos:
        return

    distribuidos = [d for d in todos if d.get("distribuido", False)]

    # Filtrar por cargo
    if cargo == "operacional":
        meus = [d for d in distribuidos if d.get("expedidor") == nome or d.get("revisor") == nome]
    else:
        meus = distribuidos

    # Tabela 1: Expedição
    dados_exp = {}
    for d in meus:
        exp = d.get("expedidor", "")
        if not exp:
            continue
        if exp not in dados_exp:
            dados_exp[exp] = {"qtd": 0, "faltam": 0}
        dados_exp[exp]["qtd"] += 1
        if not d.get("expedido", False):
            dados_exp[exp]["faltam"] += 1

    # Tabela 2: Revisão
    dados_rev = {}
    for d in meus:
        rev = d.get("revisor", "")
        if not rev:
            continue
        if rev not in dados_rev:
            dados_rev[rev] = {"qtd": 0, "faltam": 0}
        dados_rev[rev]["qtd"] += 1
        if not d.get("revisado", False):
            dados_rev[rev]["faltam"] += 1

    # Urgentes (Ordinária + Reservada)
    urgentes_total = 0
    urgentes_faltam = 0
    for d in distribuidos:
        tipo = d.get("tipo_sessao", "")
        if d.get("tipo_sessao") == "Urgentes" or "reservada" in _normalizar_texto(tipo):
            urgentes_total += 1
            if not d.get("expedido", False):
                urgentes_faltam += 1

    with st.sidebar:
        st.markdown("---")
        st.markdown("##### 📤 Expedição")

        if dados_exp:
            linhas_exp = []
            for colab, dados in sorted(dados_exp.items()):
                linhas_exp.append({
                    "Colaborador": colab,
                    "Qtd": dados["qtd"],
                    "Faltam": dados["faltam"],
                })
            df_exp = pd.DataFrame(linhas_exp)
            st.dataframe(df_exp, hide_index=True, use_container_width=True)
        else:
            st.caption("Nenhum processo para expedir.")

        st.markdown("---")
        st.markdown("##### ✅ Revisão")

        if dados_rev:
            linhas_rev = []
            for colab, dados in sorted(dados_rev.items()):
                linhas_rev.append({
                    "Colaborador": colab,
                    "Qtd": dados["qtd"],
                    "Faltam": dados["faltam"],
                })
            df_rev = pd.DataFrame(linhas_rev)
            st.dataframe(df_rev, hide_index=True, use_container_width=True)
        else:
            st.caption("Nenhum processo para revisar.")

        st.markdown("---")
        st.markdown("##### 🚨 Urgentes")
        col_u1, col_u2 = st.columns(2)
        with col_u1:
            st.metric("Total", urgentes_total)
        with col_u2:
            st.metric("Faltam", urgentes_faltam)

# ==================== PAUTA ATIVA ====================

def _renderizar_pauta_ativa_sexp(usuario, modo_edicao):
    """Renderiza a aba de Pauta Ativa do SEXP."""
    cargo = usuario.get("cargo", "operacional")
    is_gerente = cargo in ("gerente", "criador", "raiz")

    st.markdown("### 📋 Pauta Ativa — SEXP")
    st.caption(
        "Processos revisados na SEAT, aguardando distribuição. "
        "Selecione os colaboradores que participarão da distribuição de cada sessão."
    )

    # Sincronizar com SEAT
    novos, total_prontos = _sincronizar_com_seat()
    if novos > 0:
        st.success(f"✅ {novos} processo(s) importado(s) da SEAT!")
        st.markdown("---")

    # Verificar se todos os processos da SEAT foram revisados
    todos_revisados, encaminhados, total_seat = _verificar_todos_revisados_seat()
    if todos_revisados and total_seat > 0:
        st.success(
            f"🎉 **Todos os {total_seat} processos da SEAT foram revisados!** "
            f"Todos os processos estão prontos para distribuição."
        )
    elif total_seat > 0:
        st.info(
            f"📊 **SEAT:** {encaminhados} de {total_seat} processos revisados. "
            f"Aguardando revisão de {total_seat - encaminhados} processo(s)."
        )

    st.markdown("---")

    # Listar processos por tipo de sessão
    try:
        todos_sexp = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        todos_sexp = []

    for tipo in TIPOS_SESSAO_SEXP:
        processos = [d for d in todos_sexp if d.get("tipo_sessao") == tipo]
        if not processos:
            continue

        nao_distribuidos = [d for d in processos if not d.get("distribuido", False)]
        distribuidos = [d for d in processos if d.get("distribuido", False)]

        st.markdown(f"#### {tipo}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total", len(processos))
        with col2:
            st.metric("Não Distribuídos", len(nao_distribuidos))
        with col3:
            st.metric("Distribuídos", len(distribuidos))

        # Seleção de colaboradores para distribuição
        if is_gerente and modo_edicao and nao_distribuidos:
            elegiveis = _obter_colaboradores_por_cargo(tipo)
            nomes_elegiveis = [c.get("nome", "") for c in elegiveis]

            if nomes_elegiveis:
                with st.expander(f"⚙️ Distribuir {len(nao_distribuidos)} processo(s) de {tipo}"):
                    st.markdown("**Selecione os colaboradores que participarão:**")
                    selecionados = st.multiselect(
                        "Colaboradores",
                        options=nomes_elegiveis,
                        default=nomes_elegiveis,
                        key=f"multiselect_{tipo}"
                    )

                    if st.button(f"📤 Distribuir {len(nao_distribuidos)} processo(s)", key=f"btn_dist_{tipo}", type="primary"):
                        if len(selecionados) < 2:
                            st.error("Selecione pelo menos 2 colaboradores para formar duplas.")
                        else:
                            qtd = _executar_distribuicao(tipo, selecionados)
                            if qtd > 0:
                                st.success(f"✅ {qtd} processo(s) distribuído(s)!")
                                st.rerun()
                            else:
                                st.error("Erro ao distribuir processos.")

        # Listar processos
        for p in processos:
            distribuido = p.get("distribuido", False)
            expedido = p.get("expedido", False)
            revisado = p.get("revisado", False)

            if revisado:
                icone = "✅"
            elif expedido:
                icone = "📤"
            elif distribuido:
                icone = "📋"
            else:
                icone = "⏳"

            with st.expander(
                f"{icone} {p.get('processo_numero', '')} | "
                f"Relator: {p.get('relator', '-') or '-'} | "
                f"{'Distribuído' if distribuido else 'Aguardando distribuição'}"
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

                comentarios = p.get("comentarios", "") or ""
                if comentarios:
                    st.write(f"**Comentários:**")
                    st.write(comentarios)
                else:
                    st.write("**Comentários:** Nenhum")

        st.markdown("---")

    if not todos_sexp:
        st.info("Nenhum processo importado da SEAT ainda. Aguarde a revisão na SEAT.")

# ==================== DISTRIBUIÇÃO ====================

def _renderizar_card_processo_sexp(p, modo_edicao, usuario):
    cargo = usuario.get("cargo", "operacional")
    nome = usuario.get("nome", "")

    expedido = p.get("expedido", False)
    revisado = p.get("revisado", False)
    tipo_sessao = p.get("tipo_sessao", "")
    is_reservada = "reservada" in _normalizar_texto(tipo_sessao)
    forma_despacho = p.get("forma_despacho", "") or ""

    if revisado:
        icone = "✅"
    elif expedido:
        icone = "📤"
    else:
        icone = "⏳"

    header = (
        f"{icone} {p.get('processo_numero', '')} | "
        f"Relator: {p.get('relator', '-') or '-'} | "
        f"Exp: {p.get('expedidor', '-') or '-'} | "
        f"Rev: {p.get('revisor', '-') or '-'}"
    )
    if is_reservada and forma_despacho:
        header += f" | {forma_despacho}"

    with st.expander(header):
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

        # Forma de despacho (apenas Reservada)
        if is_reservada:
            st.write(f"**Despachado via:** {forma_despacho if forma_despacho else '—'}")

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

                # Se for Reservada, exigir forma de despacho antes de marcar como expedido
                if is_reservada and not expedido and pode_expedir:
                    nova_forma = st.selectbox(
                        "Despachar via *",
                        options=["", "E-mail", "Mensageria", "Barramento"],
                        index=0,
                        key=f"forma_{p['id']}"
                    )
                    if st.button("📤 Marcar Expedido", key=f"exp_{p['id']}", type="primary"):
                        if not nova_forma:
                            st.error("Selecione a forma de despacho antes de marcar como expedido.")
                        else:
                            db_manager.atualizar("distribuicao_sexp", p["id"], {
                                "expedido": True,
                                "forma_despacho": nova_forma,
                            })
                            st.success(f"Marcado como expedido via {nova_forma}!")
                            st.rerun()
                elif pode_expedir and not expedido:
                    if st.button("📤 Marcar Expedido", key=f"exp_{p['id']}"):
                        db_manager.atualizar("distribuicao_sexp", p["id"], {"expedido": True})
                        st.success("Marcado como expedido!")
                        st.rerun()
                elif expedido and pode_expedir:
                    if st.button("↩️ Desfazer Expedição", key=f"unexp_{p['id']}"):
                        db_manager.atualizar("distribuicao_sexp", p["id"], {
                            "expedido": False,
                            "revisado": False,
                            "forma_despacho": None,
                        })
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

def _renderizar_distribuicao_sexp(usuario, modo_edicao):
    """Renderiza a aba de Distribuição com as tabelas por sessão."""
    cargo = usuario.get("cargo", "operacional")
    nome = usuario.get("nome", "")

    st.markdown("### 📤 Distribuição")
    st.caption("Processos distribuídos em cadeia de duplas (A expede → B revisa).")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        todos = []

    distribuidos = [d for d in todos if d.get("distribuido", False)]

    if not distribuidos:
        st.info("Nenhum processo distribuído ainda. Vá na aba 'Pauta Ativa' para distribuir.")
        return

    # Sub-tabs para cada tipo de sessão (exceto Urgentes que tem sua própria aba)
    tipos_com_processos = []
    for tipo in TIPOS_SESSAO_SEXP:
        if tipo == "Urgentes":
            continue
        qtd = len([d for d in distribuidos if d.get("tipo_sessao") == tipo])
        if qtd > 0:
            tipos_com_processos.append(tipo)

    if not tipos_com_processos:
        st.info("Nenhum processo distribuído ainda.")
        return

    sub_tabs = st.tabs(tipos_com_processos)

    for idx, tipo in enumerate(tipos_com_processos):
        with sub_tabs[idx]:
            st.markdown(f"#### {tipo}")

            if "reservada" in _normalizar_texto(tipo):
                st.caption("⚠️ Estagiários não participam desta sessão.")
            elif "administrativa" in _normalizar_texto(tipo):
                st.caption("👤 Apenas gerentes participam desta sessão.")

            processos = [d for d in distribuidos if d.get("tipo_sessao") == tipo]

            if cargo == "operacional":
                processos = [d for d in processos if d.get("expedidor") == nome or d.get("revisor") == nome]

            if not processos:
                st.info("Nenhum processo atribuído a você nesta sessão.")
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

# ==================== URGENTES ====================

def _renderizar_urgentes_sexp(usuario, modo_edicao):
    """Renderiza a aba de Urgentes."""
    cargo = usuario.get("cargo", "operacional")
    nome = usuario.get("nome", "")

    st.markdown("### 🚨 Urgentes")
    st.caption("Processos urgentes (exceto os da Sessão Reservada, que ficam na tabela própria).")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        todos = []

    urgentes = [d for d in todos if d.get("tipo_sessao") == "Urgentes" and d.get("distribuido", False)]

    if cargo == "operacional":
        urgentes = [d for d in urgentes if d.get("expedidor") == nome or d.get("revisor") == nome]

    if not urgentes:
        st.info("Nenhum processo urgente distribuído.")
        return

    total = len(urgentes)
    expedidos = len([p for p in urgentes if p.get("expedido")])
    revisados = len([p for p in urgentes if p.get("revisado")])

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total", total)
    with col2:
        st.metric("Expedidos", expedidos)
    with col3:
        st.metric("Revisados", revisados)

    st.markdown("---")

    for p in urgentes:
        _renderizar_card_processo_sexp(p, modo_edicao, usuario)

# ==================== CONTROLE DE FÉRIAS ====================

def _renderizar_controle_ferias_sexp(usuario, modo_edicao):
    """Renderiza a aba de Controle de Férias."""
    cargo = usuario.get("cargo", "operacional")
    is_gerente = cargo in ("gerente", "criador", "raiz")

    st.markdown("### 🏖️ Controle de Férias")
    st.caption("Gerencie férias dos colaboradores e verifique conflitos com a escala de distribuição.")

    try:
        ferias = db_manager.buscar_todos(
            "ferias_sexp",
            ordem_coluna="data_inicio",
            ordem_desc=True,
        ) or []
    except Exception:
        ferias = []

    # Verificar conflitos
    try:
        todos_dist = db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        todos_dist = []

    # Mostrar conflitos
    ferias_aprovadas = [f for f in ferias if f.get("status") == "aprovada"]
    if ferias_aprovadas:
        st.markdown("#### ⚠️ Conflitos com Distribuição")
        tem_conflito = False
        for f in ferias_aprovadas:
            colaborador = f.get("colaborador", "")
            substituto = f.get("substituto", "")
            processos_colab = [d for d in todos_dist if d.get("expedidor") == colaborador or d.get("revisor") == colaborador]
            pendentes = [d for d in processos_colab if not d.get("revisado", False)]

            if pendentes and not substituto:
                tem_conflito = True
                st.warning(
                    f"⚠️ **{colaborador}** está de férias "
                    f"({str(f.get('data_inicio', ''))[:10]} a {str(f.get('data_fim', ''))[:10]}) "
                    f"e tem **{len(pendentes)} processo(s)** pendente(s) sem substituto designado."
                )
            elif pendentes and substituto:
                st.info(
                    f"ℹ️ **{colaborador}** está de férias. "
                    f"Substituto: **{substituto}**. "
                    f"{len(pendentes)} processo(s) pendente(s)."
                )

        if not tem_conflito:
            st.success("✅ Nenhum conflito de férias com a distribuição atual.")
        st.markdown("---")

    # Listar férias
    st.markdown("#### Férias Cadastradas")
    if ferias:
        for f in ferias:
            icone = "🟢" if f.get("status") == "aprovada" else "🟡"
            substituto = f.get("substituto", "")
            with st.expander(
                f"{icone} {f.get('colaborador', '')} | "
                f"{str(f.get('data_inicio', ''))[:10]} a {str(f.get('data_fim', ''))[:10]} | "
                f"{f.get('status', '').upper()}"
            ):
                st.write(f"**Colaborador:** {f.get('colaborador', '')}")
                st.write(f"**Período:** {f.get('data_inicio', '')} a {f.get('data_fim', '')}")
                st.write(f"**Status:** {f.get('status', '')}")
                if substituto:
                    st.write(f"**Substituto:** {substituto}")
                if f.get("observacoes"):
                    st.write(f"**Observações:** {f.get('observacoes')}")

                if is_gerente and modo_edicao:
                    if f.get("status") == "aprovada" and not substituto:
                        with st.form(f"form_subst_{f['id']}"):
                            novo_subst = st.text_input(
                                "Designar Substituto",
                                placeholder="Nome do substituto",
                                key=f"subst_{f['id']}"
                            )
                            if st.form_submit_button("Designar"):
                                if novo_subst:
                                    db_manager.atualizar("ferias_sexp", f["id"], {
                                        "substituto": novo_subst.strip()
                                    })
                                    st.success(f"Substituto designado: {novo_subst.strip()}")
                                    st.rerun()

                    if f.get("status") == "pendente":
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Aprovar", key=f"ferias_ok_{f['id']}"):
                                db_manager.atualizar("ferias_sexp", f["id"], {"status": "aprovada"})
                                st.success("Férias aprovadas!")
                                st.rerun()
                        with col2:
                            if st.button("Rejeitar", key=f"ferias_no_{f['id']}"):
                                db_manager.atualizar("ferias_sexp", f["id"], {"status": "rejeitada"})
                                st.rerun()
    else:
        st.info("Nenhuma férias cadastrada.")

    # Cadastrar férias
    if is_gerente and modo_edicao:
        st.markdown("---")
        st.markdown("##### Cadastrar Férias")
        with st.form("form_nova_ferias_sexp"):
            col1, col2, col3 = st.columns(3)
            with col1:
                ferias_colab = st.text_input("Colaborador *", key="ferias_c_sexp")
                ferias_ini = st.date_input("Data Início *", key="ferias_i_sexp")
            with col2:
                ferias_fim = st.date_input("Data Fim *", key="ferias_f_sexp")
                ferias_obs = st.text_area("Observações", key="ferias_o_sexp", height=60)
            with col3:
                ferias_status = st.selectbox("Status", options=["pendente", "aprovada"], key="ferias_s_sexp")

            if st.form_submit_button("Cadastrar Férias", type="primary"):
                if not ferias_colab:
                    st.error("Informe o nome do colaborador.")
                elif ferias_fim < ferias_ini:
                    st.error("A data fim não pode ser anterior à data início.")
                else:
                    db_manager.inserir("ferias_sexp", {
                        "colaborador": ferias_colab.strip(),
                        "data_inicio": str(ferias_ini),
                        "data_fim": str(ferias_fim),
                        "observacoes": ferias_obs.strip(),
                        "status": ferias_status,
                    })
                    st.success("Férias cadastradas!")
                    st.rerun()

# ==================== FUNÇÃO PRINCIPAL ====================

def renderizar(usuario: dict, modo_edicao: bool = False):
    """Função principal do módulo SEXP."""
    nome = usuario.get("nome", "Usuário")
    cargo = usuario.get("cargo", "operacional")
    setor = usuario.get("setor", "SEXP")

    st.markdown(f"**Colaborador:** {nome} | **Cargo:** {cargo} | **Setor:** {setor}")

    if not modo_edicao:
        st.info("Você está em modo de visualização. Operações de edição estão bloqueadas.")

    st.markdown("---")

    # Sincronizar com SEAT automaticamente
    novos, _ = _sincronizar_com_seat()
    if novos > 0:
        st.success(f"✅ {novos} processo(s) importado(s) da SEAT!")
        st.markdown("---")

    # Sidebar
    _renderizar_sidebar_sexp(usuario)

    # Tabs
    tab_pauta, tab_dist, tab_urg, tab_ferias = st.tabs([
        "Pauta Ativa",
        "Distribuição",
        "Urgentes",
        "Controle de Férias",
    ])

    with tab_pauta:
        _renderizar_pauta_ativa_sexp(usuario, modo_edicao)

    with tab_dist:
        _renderizar_distribuicao_sexp(usuario, modo_edicao)

    with tab_urg:
        _renderizar_urgentes_sexp(usuario, modo_edicao)

    with tab_ferias:
        _renderizar_controle_ferias_sexp(usuario, modo_edicao)
