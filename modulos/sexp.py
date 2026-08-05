import streamlit as st
from datetime import date, timedelta
import db_manager
from modulos.gerenciar_dados import _renderizar_gerenciar_dados

# ==================== CONSTANTES ====================

TIPOS_SESSAO_SEXP = [
    "Sessão Ordinária",
    "Sessão Ordinária Virtual",
    "Sessão Reservada",
    "Sessão Administrativa",
    "Urgentes",
]

def _eh_o_colaborador(usuario, nome_colaborador):
    """
    Verifica se o nome do colaborador corresponde ao usuário logado.
    """
    if not usuario or not nome_colaborador:
        return False

    nome_usuario = usuario.get("nome", "") or ""
    nome_guerra = usuario.get("nome_guerra", "") or ""

    return (
        nome_colaborador.strip().lower() == nome_usuario.strip().lower()
        or nome_colaborador.strip().lower() == nome_guerra.strip().lower()
    )

def _formatar_data_curta(data):
    """
    Formata uma data ISO (YYYY-MM-DD) para DD/MM/AAAA.
    """
    if not data:
        return "—"

    try:
        from datetime import datetime

        if "T" in str(data):
            dt = datetime.fromisoformat(str(data))
        else:
            dt = datetime.strptime(str(data)[:10], "%Y-%m-%d")

        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(data)[:10] if data else "—"

# ==================== FUNÇÕES AUXILIARES ====================

def _normalizar_texto(texto):
    import unicodedata

    if not texto:
        return ""

    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
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

def _tem_permissao_gestao(usuario):
    """
    Verifica se o usuário tem perfil de gestão.
    """
    nivel = usuario.get("nivel_acesso", "")
    cargo = _normalizar_texto(usuario.get("cargo", ""))

    return (
        nivel in ("SUPER_ADMIN_CRIADOR", "ADMIN_GABINETE", "GESTOR_SETORIAL")
        or cargo in ("gerente", "criador", "raiz")
    )

def _get_nome_curto(colab):
    """
    Extrai o nome de guerra limpo; se não houver, usa o primeiro nome.
    """
    if not colab:
        return ""

    ng = colab.get("nome_guerra")
    if ng and str(ng).strip():
        return str(ng).strip()

    nome_comp = str(colab.get("nome", "")).strip()
    return nome_comp.split()[0] if nome_comp else ""

def _obter_colaboradores():
    """
    Busca colaboradores ativos da SEXP a partir de usuarios_acesso.
    Esta função retorna a base do setor.
    A política de elegibilidade do sorteio fica centralizada no db_manager.
    """
    try:
        todos = db_manager.buscar_todos("usuarios_acesso", filtros={"ativo": True}) or []
        return [u for u in todos if _normalizar_texto(u.get("setor", "")) == "sexp"]
    except Exception:
        return []

def _obter_colaboradores_por_cargo(tipo_sessao):
    """
    Retorna os colaboradores elegíveis para o sorteio automático da SEXP
    usando a política centralizada no db_manager.

    Regras já resolvidas no backend:
    - Sessão Ordinária, Sessão Ordinária Virtual e Urgentes:
      entram assessores e estagiários, gerente fica fora
    - Sessão Reservada:
      entram apenas assessores
    - Sessão Administrativa:
      entra apenas o gerente
    - Conta técnica do desenvolvedor fica fora da distribuição automática
    """
    try:
        colaboradores = db_manager.listar_colaboradores_elegiveis_distribuicao(
            setor="SEXP",
            tipo_sessao=tipo_sessao,
            incluir_contas_tecnicas=False,
        ) or []

        resultado = []

        for colaborador in colaboradores:
            if not isinstance(colaborador, dict):
                continue

            nome = str(colaborador.get("nome", "") or "").strip()
            matricula = str(colaborador.get("matricula", "") or "").strip()
            setor = str(colaborador.get("setor", "") or "").strip()

            if not nome:
                continue

            if not matricula:
                continue

            if not setor:
                continue

            resultado.append(colaborador)

        resultado.sort(
            key=lambda item: (
                str(item.get("nome_exibicao", "") or "").strip().lower(),
                str(item.get("matricula", "") or "").strip(),
            )
        )

        return resultado

    except Exception as e:
        print(f"[ERRO SEXP _obter_colaboradores_por_cargo] {e}")
        return []

# ==================== SINCRONIZAÇÃO COM SEAT ====================

def _sincronizar_com_seat():
    """
    Sincroniza processos finalizados da SEAT para a tabela da SEXP.
    """
    try:
        processos_seat = db_manager.buscar_todos("pauta_seat") or []

        prontos_seat = [
            p for p in processos_seat
            if p.get("status") == "encaminhado"
            or p.get("sessao_finalizada") is True
        ]

        todos_sexp = db_manager.buscar_todos("distribuicao_sexp") or []

        if not prontos_seat:
            return 0, len(todos_sexp)

        urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
        nums_urgentes = {
            _normalizar_numero_processo(u.get("processo_numero", ""))
            for u in urgentes_seat
        }

        nums_existentes = {
            _normalizar_numero_processo(d.get("processo_numero", ""))
            for d in todos_sexp
            if d.get("processo_numero")
        }

        novos_inseridos = 0

        for p in prontos_seat:
            num_norm = _normalizar_numero_processo(
                p.get("processo_numero", "")
            )

            if not num_norm or num_norm in nums_existentes:
                continue

            tipo_sexp = _determinar_tabela_destino_sexp(
                p,
                nums_urgentes,
            )

            novo_registro = {
                "processo_numero": p.get("processo_numero", ""),
                "relator": p.get("relator", ""),
                "tipo_sessao": tipo_sexp,
                "numero_sessao": p.get("numero_sessao", ""),
                "dia_sessao": p.get("dia_sessao", ""),
                "distribuido": False,
                "expedido": False,
                "revisado": False,
                "comentario": p.get("comentario", "") or "",
            }

            res = db_manager.inserir(
                "distribuicao_sexp",
                novo_registro,
            )

            if res:
                novos_inseridos += 1
                nums_existentes.add(num_norm)

        return novos_inseridos, len(todos_sexp) + novos_inseridos

    except Exception as e:
        print(f"[ERRO SINCRONIZACAO SEXP] {e}")
        return 0, 0

def _verificar_todos_revisados_seat():
    """
    Verifica se todos os processos da SEAT já foram revisados.
    """
    try:
        processos_seat = db_manager.buscar_todos("pauta_seat") or []

        if not processos_seat:
            return False, 0, 0

        total = len(processos_seat)
        encaminhados = len(
            [
                p for p in processos_seat
                if p.get("status") == "encaminhado"
            ]
        )

        return encaminhados == total, encaminhados, total

    except Exception:
        return False, 0, 0

def _determinar_tabela_destino_sexp(processo, nums_urgentes):
    """
    Determina em qual tabela do SEXP o processo deve aparecer.
    """
    p_num = _normalizar_numero_processo(
        processo.get("processo_numero", "")
    )

    is_urgente = p_num in nums_urgentes
    tipo_sessao = processo.get("tipo_sessao", "Sessão Ordinária")
    tipo_norm = _normalizar_texto(tipo_sessao)

    if "reservada" in tipo_norm:
        return "Sessão Reservada"
    elif is_urgente:
        return "Urgentes"
    elif "virtual" in tipo_norm:
        return "Sessão Ordinária Virtual"
    elif "administrativa" in tipo_norm:
        return "Sessão Administrativa"
    else:
        return "Sessão Ordinária"
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
    """
    Executa a distribuição em cadeia com trava otimista.
    """
    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []

        try:
            urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
            nums_urgentes = {
                _normalizar_numero_processo(u.get("processo_numero", "")) for u in urgentes_seat
            }
        except Exception:
            nums_urgentes = set()

        processos = [
            d for d in todos
            if _determinar_tabela_destino_sexp(d, nums_urgentes) == tipo_sessao
            and not d.get("distribuido", False)
            and not d.get("removido_pauta", False)
        ]

        if not processos:
            st.warning("Nenhum processo pendente encontrado para este tipo de sessão.")
            return 0

        if not colaboradores_selecionados or len(colaboradores_selecionados) < 2:
            st.error("Selecione pelo menos 2 colaboradores para formar a cadeia de duplas.")
            return 0

        duplas = _gerar_cadeia_duplas([{"nome": n} for n in colaboradores_selecionados])
        if not duplas:
            return 0

        sucessos = 0
        ignorados = 0
        erros_detalhados = []

        cliente = db_manager.get_supabase()

        for i, p in enumerate(processos):
            id_reg = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")

            if id_reg:
                proc_atual = db_manager.buscar_por_id("distribuicao_sexp", id_reg)
                if proc_atual and proc_atual.get("distribuido", False):
                    ignorados += 1
                    continue

            par = duplas[i % len(duplas)]

            dados_update = {
                "expedidor": par[0],
                "revisor": par[1],
                "distribuido": True,
                "tipo_sessao": tipo_sessao,
            }

            res = None

            if id_reg:
                try:
                    res = db_manager.atualizar("distribuicao_sexp", id_reg, dados_update)
                except Exception as err_mgr:
                    erros_detalhados.append(f"Erro ID {id_reg}: {str(err_mgr)}")

            if not res and cliente and p.get("processo_numero"):
                try:
                    num_proc = p["processo_numero"]
                    resp = (
                        cliente.table("distribuicao_sexp")
                        .update(dados_update)
                        .eq("processo_numero", num_proc)
                        .execute()
                    )
                    if resp.data and len(resp.data) > 0:
                        res = resp.data[0]
                    else:
                        erros_detalhados.append(
                            f"Proc {num_proc}: Supabase não encontrou a linha ou RLS bloqueou."
                        )
                except Exception as err_api:
                    erros_detalhados.append(
                        f"API Supabase Proc {p.get('processo_numero')}: {str(err_api)}"
                    )

            if res:
                sucessos += 1

        if ignorados > 0:
            st.warning(
                f"⚠️ Operação parcial: {ignorados} processo(s) já haviam sido distribuídos por outro colaborador simultaneamente."
            )

        if sucessos == 0 and erros_detalhados:
            with st.expander("🛠️ Diagnóstico do Erro no Supabase (Clique para ver detalhes)", expanded=True):
                for erro in set(erros_detalhados):
                    st.error(erro)

        return sucessos

    except Exception as e:
        st.error(f"Erro crítico no algoritmo de distribuição: {str(e)}")
        return 0

# ==================== SIDEBAR ====================

def _renderizar_sidebar_sexp(usuario):
    """
    Mostra tabelas de Expedição e Revisão + Urgentes na barra lateral.
    """
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

    if cargo == "operacional":
        meus = [d for d in distribuidos if d.get("expedidor") == nome or d.get("revisor") == nome]
    else:
        meus = distribuidos

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

    try:
        urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
        nums_urgentes = {
            _normalizar_numero_processo(u.get("processo_numero", "")) for u in urgentes_seat
        }
    except Exception:
        nums_urgentes = set()

    urgentes_total = 0
    urgentes_faltam = 0

    for d in distribuidos:
        tipo = d.get("tipo_sessao", "")
        num_norm = _normalizar_numero_processo(d.get("processo_numero", ""))

        is_urg = (tipo == "Urgentes") or (
            "reservada" in _normalizar_texto(tipo) and num_norm in nums_urgentes
        )

        if is_urg and not d.get("removido_pauta", False):
            urgentes_total += 1
            if not d.get("expedido", False):
                urgentes_faltam += 1

    with st.sidebar:
        st.markdown("---")
        st.markdown("##### 📤 Expedição")

        if dados_exp:
            linhas_exp = []
            for colab, dados in sorted(dados_exp.items()):
                linhas_exp.append(
                    {
                        "Colaborador": colab,
                        "Qtd": dados["qtd"],
                        "Faltam": dados["faltam"],
                    }
                )

            df_exp = pd.DataFrame(linhas_exp)
            st.dataframe(df_exp, hide_index=True, use_container_width=True)
        else:
            st.caption("Nenhum processo para expedir.")

        st.markdown("---")
        st.markdown("##### ✅ Revisão")

        if dados_rev:
            linhas_rev = []
            for colab, dados in sorted(dados_rev.items()):
                linhas_rev.append(
                    {
                        "Colaborador": colab,
                        "Qtd": dados["qtd"],
                        "Faltam": dados["faltam"],
                    }
                )

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

def _auto_atribuir_administrativa_jessyca():
    """
    Atribui automaticamente processos da Sessão Administrativa
    ao responsável configurado no banco.
    """
    try:
        config = db_manager.buscar_todos("configuracoes") or []
        responsavel = None

        for c in config:
            if c.get("chave") == "responsavel_sessao_administrativa":
                responsavel = c.get("valor")
                break

        if not responsavel:
            return

        todos_sexp = db_manager.buscar_todos("distribuicao_sexp") or []
        admin_nao_atribuidos = [
            d for d in todos_sexp
            if _determinar_tabela_destino_sexp(d, set()) == "Sessão Administrativa"
            and not d.get("distribuido", False)
        ]

        for p in admin_nao_atribuidos:
            id_linha = p.get("id")
            if id_linha:
                db_manager.atualizar(
                    "distribuicao_sexp",
                    id_linha,
                    {
                        "distribuido": True,
                        "expedidor": responsavel,
                    },
                )

    except Exception:
        pass

def _renderizar_pauta_ativa_sexp(usuario, modo_edicao):
    """
    Renderiza a Pauta Ativa da SEXP.
    """
    st.markdown("### 📋 Pauta Ativa , SEXP")
    st.caption("Processos revisados na SEAT aguardando distribuição. Selecione a equipe abaixo para disparar o lote.")

    novos, _ = _sincronizar_com_seat()
    if novos > 0:
        st.success(f"✅ {novos} novo(s) processo(s) importado(s) da SEAT!")
        st.markdown("---")

    if modo_edicao:
        _auto_atribuir_administrativa_jessyca()

    todos_revisados, encaminhados, total_seat = _verificar_todos_revisados_seat()

    if todos_revisados and total_seat > 0:
        st.success(f"🎉 Todos os {total_seat} processos da SEAT foram revisados e estão prontos para distribuição.")
    elif total_seat > 0:
        st.info(f"📊 SEAT: {encaminhados} de {total_seat} revisados. Aguardando {total_seat - encaminhados} processo(s).")

    st.markdown("---")

    try:
        todos_sexp = db_manager.buscar_todos("distribuicao_sexp") or []
        urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
        nums_urgentes = {_normalizar_numero_processo(u.get("processo_numero", "")) for u in urgentes_seat}
    except Exception:
        todos_sexp = []
        nums_urgentes = set()

    tem_algum_exibido = False

    for tipo in TIPOS_SESSAO_SEXP:
        if tipo == "Sessão Administrativa":
            continue

        processos = [d for d in todos_sexp if _determinar_tabela_destino_sexp(d, nums_urgentes) == tipo]
        if not processos:
            continue

        tem_algum_exibido = True
        nao_distribuidos = [d for d in processos if not d.get("distribuido", False)]
        distribuidos = [d for d in processos if d.get("distribuido", False)]

        st.markdown(f"#### {tipo}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total", len(processos))
        col2.metric("Não Distribuídos", len(nao_distribuidos))
        col3.metric("Distribuídos", len(distribuidos))

        if modo_edicao and nao_distribuidos:
            elegiveis = _obter_colaboradores_por_cargo(tipo)
            nomes_elegiveis = sorted(
                list(set([_get_nome_curto(c) for c in elegiveis if _get_nome_curto(c)]))
            )

            if nomes_elegiveis:
                with st.expander(f"⚙️ Distribuir {len(nao_distribuidos)} processo(s) de {tipo}", expanded=True):
                    st.markdown("**Selecione os colaboradores que participarão do rodízio em cadeias:**")

                    selecionados = st.multiselect(
                        "Colaboradores Elegíveis",
                        options=nomes_elegiveis,
                        default=nomes_elegiveis,
                        key=f"multiselect_{tipo}",
                    )

                    if st.button(
                        f"📤 Distribuir {len(nao_distribuidos)} processo(s)",
                        key=f"btn_dist_{tipo}",
                        type="primary",
                        use_container_width=True,
                    ):
                        if len(selecionados) < 2:
                            st.error("Selecione pelo menos 2 colaboradores para formar a cadeia de duplas (A expede e B revisa).")
                        else:
                            qtd = _executar_distribuicao(tipo, selecionados)
                            if qtd > 0:
                                st.success(f"✅ {qtd} processo(s) distribuído(s) em cadeia! Acesse a aba Distribuição ou Urgentes para operar.")
                                st.rerun()
            else:
                st.warning("Nenhum colaborador elegível ativo cadastrado para este tipo de sessão.")

        st.markdown("---")

    if not todos_sexp or not tem_algum_exibido:
        st.info("Nenhum processo aguardando distribuição na pauta.")
        return

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

        if is_reservada:
            st.write(f"**Despachado via:** {forma_despacho if forma_despacho else '—'}")

        comentarios_atuais = p.get("comentarios", "") or ""
        if comentarios_atuais:
            st.write("**Comentários:**")
            st.write(comentarios_atuais)
        else:
            st.write("**Comentários:** Nenhum")

        if modo_edicao:
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                pode_expedir = (nome == p.get("expedidor")) or cargo in ("gerente", "criador", "raiz")

                if is_reservada and not expedido and pode_expedir:
                    nova_forma = st.selectbox(
                        "Despachar via *",
                        options=["", "E-mail", "Mensageria", "Barramento"],
                        index=0,
                        key=f"forma_{p['id']}",
                    )

                    if st.button("📤 Marcar Expedido", key=f"exp_{p['id']}", type="primary"):
                        if not nova_forma:
                            st.error("Selecione a forma de despacho antes de marcar como expedido.")
                        else:
                            proc_atual = db_manager.buscar_por_id("distribuicao_sexp", p["id"])
                            if proc_atual and proc_atual.get("expedido"):
                                st.warning("⚠️ Este processo já foi marcado como expedido por outro colaborador.")
                                st.rerun()
                            else:
                                db_manager.atualizar(
                                    "distribuicao_sexp",
                                    p["id"],
                                    {
                                        "expedido": True,
                                        "forma_despacho": nova_forma,
                                    },
                                )
                                st.success(f"Marcado como expedido via {nova_forma}!")
                                st.rerun()

                elif pode_expedir and not expedido:
                    if st.button("📤 Marcar Expedido", key=f"exp_{p['id']}"):
                        proc_atual = db_manager.buscar_por_id("distribuicao_sexp", p["id"])
                        if proc_atual and proc_atual.get("expedido"):
                            st.warning("⚠️ Este processo já foi marcado como expedido por outro colaborador.")
                            st.rerun()
                        else:
                            db_manager.atualizar("distribuicao_sexp", p["id"], {"expedido": True})
                            st.success("Marcado como expedido!")
                            st.rerun()

                elif expedido and pode_expedir:
                    if st.button("↩️ Desfazer Expedição", key=f"unexp_{p['id']}"):
                        db_manager.atualizar(
                            "distribuicao_sexp",
                            p["id"],
                            {
                                "expedido": False,
                                "revisado": False,
                                "forma_despacho": None,
                            },
                        )
                        st.rerun()

            with col_b:
                pode_revisar = (nome == p.get("revisor")) or cargo in ("gerente", "criador", "raiz")

                if pode_revisar and expedido and not revisado:
                    if st.button("✅ Marcar Revisado", key=f"rev_{p['id']}"):
                        proc_atual = db_manager.buscar_por_id("distribuicao_sexp", p["id"])
                        if proc_atual and proc_atual.get("revisado"):
                            st.warning("⚠️ Este processo já foi marcado como revisado por outro colaborador.")
                            st.rerun()
                        else:
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
    """
    Renderiza a aba de Distribuição com tabelas interativas separadas por Sessão/Data.
    """
    import pandas as pd

    cargo = _normalizar_texto(usuario.get("cargo", "operacional"))
    is_gerente = _tem_permissao_gestao(usuario)

    st.markdown("### 📤 Distribuição , Esteira Operacional")
    st.caption("As tabelas são geradas e isoladas automaticamente pelo Número e Dia da Sessão.")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp", ordem_coluna="id", ordem_desc=False) or []
    except Exception:
        todos = []

    distribuidos = [
        d for d in todos
        if d.get("distribuido", False)
        and not d.get("removido_pauta", False)
        and not d.get("sessao_finalizada", False)
    ]

    if not distribuidos:
        st.info("Nenhum processo tramitando na esteira de distribuição no momento.")
        return

    try:
        urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
        nums_urgentes = {_normalizar_numero_processo(u.get("processo_numero", "")) for u in urgentes_seat}
    except Exception:
        nums_urgentes = set()

    tipos_com_processos = [
        t for t in TIPOS_SESSAO_SEXP
        if t != "Urgentes" and any(_determinar_tabela_destino_sexp(d, nums_urgentes) == t for d in distribuidos)
    ]

    if not tipos_com_processos:
        st.info("Nenhum processo distribuído.")
        return

    sub_tabs = st.tabs(tipos_com_processos)

    for idx_tab, tipo in enumerate(tipos_com_processos):
        with sub_tabs[idx_tab]:
            procs_tipo = [d for d in distribuidos if _determinar_tabela_destino_sexp(d, nums_urgentes) == tipo]

            if cargo == "operacional" and not is_gerente:
                procs_tipo = [
                    d for d in procs_tipo
                    if _eh_o_colaborador(usuario, d.get("expedidor")) or _eh_o_colaborador(usuario, d.get("revisor"))
                ]

            if not procs_tipo:
                st.info("Nenhum processo atribuído a você neste tipo de sessão.")
                continue

            sessoes_isoladas = {}

            for p in procs_tipo:
                num_s = p.get("numero_sessao") or p.get("sessao_numero") or "S/N"
                dia_raw = str(p.get("dia_sessao", ""))[:10]
                dia_fmt = _formatar_data_curta(dia_raw) if ("-" in dia_raw or "/" in dia_raw) else (dia_raw or "Data N/I")
                chave_sessao = f"Sessão {num_s} , ({dia_fmt})"

                if chave_sessao not in sessoes_isoladas:
                    sessoes_isoladas[chave_sessao] = []

                sessoes_isoladas[chave_sessao].append(p)

            for idx_ses, (chave, processos) in enumerate(sessoes_isoladas.items()):
                st.markdown(f"#### 📅 {chave}")

                total = len(processos)
                expedidos = sum(1 for p in processos if p.get("expedido", False))
                revisados = sum(1 for p in processos if p.get("revisado", False))

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total", total)
                col2.metric("Pendentes", total - expedidos)
                col3.metric("Expedidos", expedidos)
                col4.metric("Revisados", revisados)

                dados_df = []
                for p in processos:
                    id_reg = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")
                    dados_df.append(
                        {
                            "ID": id_reg,
                            "Processo Nº": p.get("processo_numero", ""),
                            "Relator": p.get("relator", "") or "-",
                            "Expedidor": p.get("expedidor", "") or "-",
                            "Expedido ✅": bool(p.get("expedido", False)),
                            "Revisor": p.get("revisor", "") or "-",
                            "Revisado ✅": bool(p.get("revisado", False)),
                            "Comentários": p.get("comentarios", "") or "",
                        }
                    )

                df = pd.DataFrame(dados_df)

                if modo_edicao:
                    df_editado = st.data_editor(
                        df,
                        column_config={
                            "ID": None,
                            "Processo Nº": st.column_config.TextColumn("Nº Processo", disabled=True),
                            "Relator": st.column_config.TextColumn("Relator", disabled=True),
                            "Expedidor": st.column_config.TextColumn("Expedidor", disabled=True),
                            "Expedido ✅": st.column_config.CheckboxColumn("Expedido?", default=False),
                            "Revisor": st.column_config.TextColumn("Revisor", disabled=True),
                            "Revisado ✅": st.column_config.CheckboxColumn("Revisado?", default=False),
                            "Comentários": st.column_config.TextColumn("Observações", disabled=True),
                        },
                        hide_index=True,
                        use_container_width=True,
                        key=f"tbl_dist_{tipo}_{idx_tab}_{idx_ses}",
                    )

                    if not df.equals(df_editado):
                        for index, row in df_editado.iterrows():
                            if row["Expedido ✅"] != df.loc[index, "Expedido ✅"] or row["Revisado ✅"] != df.loc[index, "Revisado ✅"]:
                                db_manager.atualizar(
                                    "distribuicao_sexp",
                                    int(row["ID"]),
                                    {
                                        "expedido": bool(row["Expedido ✅"]),
                                        "revisado": bool(row["Revisado ✅"]),
                                    },
                                )
                        st.success("🎉 Tabela atualizada no banco!")
                        st.rerun()
                else:
                    st.dataframe(df.drop(columns=["ID"]), hide_index=True, use_container_width=True)

                if modo_edicao:
                    st.markdown("##### 🚫 Retirar Processo da Pauta")
                    st.caption("O processo sai da distribuição mas fica registrado na auditoria como Retirado de Pauta.")

                    with st.expander("Retirar processo desta sessão", expanded=False):
                        proc_remover = st.selectbox(
                            "Selecionar processo para retirar",
                            range(len(processos)),
                            format_func=lambda i: f"{processos[i].get('processo_numero', '—')} | {processos[i].get('relator', '—')}",
                            key=f"sel_remover_{tipo}_{idx_tab}_{idx_ses}",
                        )

                        if proc_remover is not None:
                            proc_sel = processos[proc_remover]

                            motivo = st.text_input(
                                "Motivo da retirada (opcional)",
                                placeholder="Ex: Retirado a pedido do relator, processo cancelado...",
                                key=f"motivo_remover_{tipo}_{idx_tab}_{idx_ses}",
                            )

                            confirmar_remocao = st.checkbox(
                                "Confirmo que desejo retirar este processo da pauta",
                                key=f"chk_remover_{tipo}_{idx_tab}_{idx_ses}",
                            )

                            if st.button(
                                "🚫 Retirar de Pauta",
                                type="primary",
                                disabled=not confirmar_remocao,
                                use_container_width=True,
                                key=f"btn_remover_{tipo}_{idx_tab}_{idx_ses}",
                            ):
                                id_remover = proc_sel.get("id") or proc_sel.get("id_distribuicao") or proc_sel.get("id_processo")
                                if id_remover:
                                    db_manager.atualizar(
                                        "distribuicao_sexp",
                                        id_remover,
                                        {
                                            "removido_pauta": True,
                                            "status": "retirado_pauta",
                                            "comentarios": f"RETIRADO DE PAUTA: {motivo}" if motivo else "RETIRADO DE PAUTA",
                                        },
                                    )
                                    st.success(f"✅ Processo {proc_sel.get('processo_numero', '—')} retirado da pauta!")
                                    st.rerun()

                if modo_edicao and is_gerente:
                    faltam_fechar = total - revisados

                    if faltam_fechar == 0:
                        st.success(f"🎉 Todos os {total} processos de {chave} foram expedidos e revisados!")
                    else:
                        st.warning(f"⚠️ Atenção: ainda restam {faltam_fechar} processo(s) pendentes de revisão final em {chave}.")

                    confirmar = st.checkbox(f"Estou ciente e desejo arquivar a {chave}", key=f"chk_{tipo}_{idx_tab}_{idx_ses}")

                    if st.button(
                        f"🔒 Finalizar Sessão ({chave})",
                        key=f"btn_fim_{tipo}_{idx_tab}_{idx_ses}",
                        type="primary",
                        disabled=not confirmar,
                        use_container_width=True,
                    ):
                        with st.spinner(f"Arquivando pauta {chave}..."):
                            ignorados = 0
                            for p in processos:
                                id_fechar = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")
                                if id_fechar:
                                    proc_atual = db_manager.buscar_por_id("distribuicao_sexp", id_fechar)
                                    if proc_atual and proc_atual.get("sessao_finalizada"):
                                        ignorados += 1
                                        continue

                                    db_manager.atualizar(
                                        "distribuicao_sexp",
                                        id_fechar,
                                        {
                                            "sessao_finalizada": True,
                                            "status": "arquivado",
                                        },
                                    )

                        if ignorados > 0:
                            st.warning(f"⚠️ {ignorados} processo(s) ignorados pois já haviam sido arquivados por outro gerente.")

                        st.success(f"✅ {chave} encerrada e arquivada!")
                        st.rerun()

                st.markdown("---")

def _renderizar_urgentes_sexp(usuario, modo_edicao):
    """
    Renderiza a aba de Urgentes em tabela interativa.
    """
    import pandas as pd

    cargo = _normalizar_texto(usuario.get("cargo", "operacional"))
    is_gerente = _tem_permissao_gestao(usuario)

    st.markdown("### 🚨 Processos Urgentes , Esteira Prioritária")
    st.caption("Processos com prioridade de tramitação. Tabela interativa com gravação em tempo real.")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp", ordem_coluna="id", ordem_desc=False) or []
    except Exception:
        todos = []

    processos_urg = [
        d for d in todos
        if d.get("tipo_sessao") == "Urgentes"
        and d.get("distribuido", False)
        and not d.get("removido_pauta", False)
        and not d.get("sessao_finalizada", False)
    ]

    if cargo == "operacional" and not is_gerente:
        processos_urg = [
            d for d in processos_urg
            if _eh_o_colaborador(usuario, d.get("expedidor")) or _eh_o_colaborador(usuario, d.get("revisor"))
        ]

    if not processos_urg:
        st.info("Nenhum processo urgente tramitando no momento.")
        return

    sessoes_isoladas = {}

    for p in processos_urg:
        num_s = p.get("numero_sessao") or p.get("sessao_numero") or "S/N"
        dia_raw = str(p.get("dia_sessao", ""))[:10]
        dia_fmt = _formatar_data_curta(dia_raw) if ("-" in dia_raw or "/" in dia_raw) else (dia_raw or "Data N/I")
        chave_sessao = f"Urgentes , Sessão {num_s} ({dia_fmt})"

        if chave_sessao not in sessoes_isoladas:
            sessoes_isoladas[chave_sessao] = []

        sessoes_isoladas[chave_sessao].append(p)

    for idx_ses, (chave, processos) in enumerate(sessoes_isoladas.items()):
        st.markdown(f"#### ⚡ {chave}")

        total = len(processos)
        expedidos = sum(1 for p in processos if p.get("expedido", False))
        revisados = sum(1 for p in processos if p.get("revisado", False))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Urgentes", total)
        col2.metric("Pendentes", total - expedidos)
        col3.metric("Expedidos", expedidos)
        col4.metric("Revisados", revisados)

        dados_df = []
        for p in processos:
            id_reg = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")
            dados_df.append(
                {
                    "ID": id_reg,
                    "Processo Nº": p.get("processo_numero", ""),
                    "Relator": p.get("relator", "") or "-",
                    "Expedidor": p.get("expedidor", "") or "-",
                    "Expedido ✅": bool(p.get("expedido", False)),
                    "Revisor": p.get("revisor", "") or "-",
                    "Revisado ✅": bool(p.get("revisado", False)),
                    "Comentários / Observação": p.get("comentarios", "") or "Tramitação Prioritária",
                }
            )

        df = pd.DataFrame(dados_df)

        if modo_edicao:
            df_editado = st.data_editor(
                df,
                column_config={
                    "ID": None,
                    "Processo Nº": st.column_config.TextColumn("Nº Processo", disabled=True),
                    "Relator": st.column_config.TextColumn("Relator", disabled=True),
                    "Expedidor": st.column_config.TextColumn("Expedidor", disabled=True),
                    "Expedido ✅": st.column_config.CheckboxColumn("Expedido?", default=False),
                    "Revisor": st.column_config.TextColumn("Revisor", disabled=True),
                    "Revisado ✅": st.column_config.CheckboxColumn("Revisado?", default=False),
                    "Comentários / Observação": st.column_config.TextColumn("Observações", disabled=True),
                },
                hide_index=True,
                use_container_width=True,
                key=f"tbl_urg_{idx_ses}",
            )

            if not df.equals(df_editado):
                for index, row in df_editado.iterrows():
                    if row["Expedido ✅"] != df.loc[index, "Expedido ✅"] or row["Revisado ✅"] != df.loc[index, "Revisado ✅"]:
                        db_manager.atualizar(
                            "distribuicao_sexp",
                            int(row["ID"]),
                            {
                                "expedido": bool(row["Expedido ✅"]),
                                "revisado": bool(row["Revisado ✅"]),
                            },
                        )
                st.success("🎉 Urgentes atualizados no banco!")
                st.rerun()
        else:
            st.dataframe(df.drop(columns=["ID"]), hide_index=True, use_container_width=True)

        if modo_edicao and is_gerente:
            confirmar = st.checkbox(
                f"Estou ciente e desejo arquivar os processos de {chave}",
                key=f"chk_urg_{idx_ses}",
            )

            if st.button(
                f"🔒 Finalizar Sessão de Urgentes ({chave})",
                key=f"btn_fim_urg_{idx_ses}",
                type="primary",
                disabled=not confirmar,
            ):
                with st.spinner(f"Arquivando pauta {chave}..."):
                    ignorados = 0
                    for p in processos:
                        id_fechar = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")
                        if id_fechar:
                            proc_atual = db_manager.buscar_por_id("distribuicao_sexp", id_fechar)
                            if proc_atual and proc_atual.get("sessao_finalizada"):
                                ignorados += 1
                                continue

                            db_manager.atualizar(
                                "distribuicao_sexp",
                                id_fechar,
                                {
                                    "sessao_finalizada": True,
                                    "status": "arquivado",
                                },
                            )

                if ignorados > 0:
                    st.warning(f"⚠️ {ignorados} processo(s) ignorados pois já haviam sido arquivados por outro gerente.")

                st.success(f"✅ {chave} encerrada e arquivada com sucesso!")
                st.rerun()

        st.markdown("---")

def _verificar_radar_choques_sexp(data_ini, data_fim, id_ignorar=None):
    """
    Radar de choques para ausências da SEXP.
    """
    from datetime import date

    try:
        solicitacoes = db_manager.buscar_todos("solicitacoes_ausencia") or []
    except Exception:
        return []

    choques = []

    for s in solicitacoes:
        if id_ignorar and str(s.get("id")) == str(id_ignorar):
            continue

        if s.get("status") not in ("APROVADA", "NOTIFICADO"):
            continue

        if s.get("setor", "").upper() != "SEXP":
            continue

        s_ini = date.fromisoformat(str(s.get("data_inicio"))[:10])
        s_fim = date.fromisoformat(str(s.get("data_fim"))[:10])

        if data_ini <= s_fim and data_fim >= s_ini:
            tipo_label = "Férias" if s.get("tipo") == "FERIAS" else ("Atestado" if s.get("tipo") == "ATESTADO" else "Abono")
            choques.append(
                {
                    "colaborador": s.get("colaborador_nome", "Colaborador"),
                    "tipo": tipo_label,
                    "inicio": s_ini.strftime("%d/%m/%Y"),
                    "fim": s_fim.strftime("%d/%m/%Y"),
                }
            )

    return choques

def _renderizar_ausencias_sexp(modo_edicao: bool, usuario: dict):
    """
    Renderiza a aba de Férias, Atestados e Abono da SEXP.
    """
    from datetime import date
    import pandas as pd

    if not usuario or not isinstance(usuario, dict):
        st.warning("Não foi possível carregar os dados do usuário logado.")
        return

    st.markdown("### 🌴 Férias, Atestados e Abono")
    st.caption(
        "Solicitação de férias, registro de atestados médicos e pedido de abono. "
        "Férias e abonos são enviados para análise da chefia no Gabinete. "
        "Atestados médicos são notificados automaticamente."
    )

    nome_usuario = usuario.get("nome", "Colaborador")
    matricula_usuario = str(usuario.get("matricula", ""))

    tab_solicitar, tab_quadro = st.tabs(
        [
            "➕ Nova Solicitação",
            "📅 Quadro Público de Ausências",
        ]
    )

    with tab_solicitar:
        st.markdown(f"**Colaborador Solicitante:** `{nome_usuario}` (Matrícula: `{matricula_usuario}`)")
        st.info("O sistema identifica seu perfil automaticamente. Selecione o tipo de registro abaixo.")

        tipo_registro = st.radio(
            "Tipo de Registro",
            ["Férias", "Atestado Médico", "Abono"],
            horizontal=True,
            key="tipo_registro_sexp",
        )

        with st.form("form_registro_ausencia_sexp"):
            col1, col2 = st.columns(2)

            with col1:
                data_ini = st.date_input("Data de Início *", value=date.today(), key="dt_ini_sexp")

            with col2:
                data_fim = st.date_input("Data de Retorno / Fim *", value=date.today(), key="dt_fim_sexp")

            observacoes = st.text_area(
                "Observações / Motivo",
                placeholder="Informações adicionais para a chefia ou equipe...",
                height=70,
                key="obs_ausencia_sexp",
            )

            submit_ausencia = st.form_submit_button("Registrar no Sistema", type="primary", use_container_width=True)

            if submit_ausencia:
                if data_fim < data_ini:
                    st.error("A data de término não pode ser anterior à data de início.")
                else:
                    dias_total = (data_fim - data_ini).days + 1

                    if tipo_registro == "Férias":
                        tipo_db = "FERIAS"
                        status_inicial = "PENDENTE"
                    elif tipo_registro == "Atestado Médico":
                        tipo_db = "ATESTADO"
                        status_inicial = "NOTIFICADO"
                    else:
                        tipo_db = "ABONO"
                        status_inicial = "PENDENTE"

                    choques = _verificar_radar_choques_sexp(data_ini, data_fim)

                    dados_ausencia = {
                        "matricula": matricula_usuario,
                        "colaborador_nome": nome_usuario,
                        "setor": "SEXP",
                        "tipo": tipo_db,
                        "data_inicio": data_ini.isoformat(),
                        "data_fim": data_fim.isoformat(),
                        "dias_afastado": dias_total,
                        "observacoes": observacoes.strip(),
                        "status": status_inicial,
                    }

                    res = db_manager.inserir("solicitacoes_ausencia", dados_ausencia)

                    if res:
                        if tipo_db == "FERIAS":
                            msg = f"✅ Solicitação de férias ({dias_total} dias) enviada para análise da chefia no Gabinete."
                        elif tipo_db == "ATESTADO":
                            msg = f"✅ Atestado médico ({dias_total} dias) notificado com sucesso e publicado no quadro!"
                        else:
                            msg = f"✅ Pedido de abono ({dias_total} dias) enviado para análise da chefia no Gabinete."

                        st.success(msg)

                        if choques:
                            st.warning(f"⚠️ Atenção: {len(choques)} colaborador(es) da SEXP já têm ausência programada neste período:")
                            for c in choques:
                                st.write(f"- **{c['colaborador']}** , {c['tipo']} de {c['inicio']} a {c['fim']}")

                        st.rerun()
                    else:
                        st.error("Erro ao registrar no banco de dados.")

    with tab_quadro:
        st.markdown("#### Ausências Programadas, Atestados e Abonos , SEXP")
        st.caption("Consulte este quadro antes de solicitar férias ou abono para evitar sobreposição de datas na equipe.")

        try:
            todas_ausencias = db_manager.buscar_todos(
                "solicitacoes_ausencia",
                filtros={"setor": "SEXP"},
                ordem_coluna="data_inicio",
                ordem_desc=False,
            ) or []
        except Exception:
            todas_ausencias = []

        publicas = [a for a in todas_ausencias if a.get("status") in ("APROVADA", "NOTIFICADO")]

        if not publicas:
            st.info("Nenhuma ausência ou afastamento programado no momento.")
        else:
            dados_quadro = []

            for a in publicas:
                tipo_raw = a.get("tipo", "AUSENCIA")
                if tipo_raw == "FERIAS":
                    tipo_lbl = "🌴 Férias"
                elif tipo_raw == "ATESTADO":
                    tipo_lbl = "🏥 Atestado"
                elif tipo_raw == "ABONO":
                    tipo_lbl = "📋 Abono"
                else:
                    tipo_lbl = "📝 Ausência"

                ini_str = _formatar_data_curta(a.get("data_inicio"))
                fim_str = _formatar_data_curta(a.get("data_fim"))

                dados_quadro.append(
                    {
                        "Colaborador": a.get("colaborador_nome", ""),
                        "Tipo": tipo_lbl,
                        "Período": f"{ini_str} a {fim_str}",
                        "Dias": f"{a.get('dias_afastado', '-')} dia(s)",
                        "Observação": a.get("observacoes", "") or "—",
                    }
                )

            df_quadro = pd.DataFrame(dados_quadro)
            st.dataframe(df_quadro, hide_index=True, use_container_width=True)

def renderizar(usuario: dict, modo_edicao: bool = False):
    """
    Função principal do módulo SEXP.
    """
    nome = usuario.get("nome", "Usuário")
    cargo = usuario.get("cargo", "operacional")
    setor = usuario.get("setor", "SEXP")

    st.markdown(f"**Colaborador:** {nome} | **Cargo:** {cargo} | **Setor:** {setor}")

    if not modo_edicao:
        st.info("Você está em modo de visualização. Operações de edição estão bloqueadas.")

    st.markdown("---")

    novos, _ = _sincronizar_com_seat()
    if novos > 0:
        st.success(f"✅ {novos} processo(s) importado(s) da SEAT!")
        st.markdown("---")

    _renderizar_sidebar_sexp(usuario)

    tab_pauta, tab_dist, tab_urg, tab_ferias, tab_gerenciar = st.tabs(
        [
            "Pauta Ativa",
            "Distribuição",
            "Urgentes",
            "Férias e Afastamentos",
            "🗑️ Gerenciar Dados",
        ]
    )

    with tab_pauta:
        _renderizar_pauta_ativa_sexp(usuario, modo_edicao)

    with tab_dist:
        _renderizar_distribuicao_sexp(usuario, modo_edicao)

    with tab_urg:
        _renderizar_urgentes_sexp(usuario, modo_edicao)

    with tab_ferias:
        _renderizar_ausencias_sexp(modo_edicao, usuario)

    with tab_gerenciar:
        _renderizar_gerenciar_dados(usuario, "SEXP")
