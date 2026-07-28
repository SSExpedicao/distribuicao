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

def _tem_permissao_gestao(usuario):
    """Verifica se o usuário tem perfil de gestão (Chefia, Gabinete ou Criador)."""
    nivel = usuario.get("nivel_acesso", "")
    cargo = _normalizar_texto(usuario.get("cargo", ""))
    return (
        nivel in ("SUPER_ADMIN_CRIADOR", "ADMIN_GABINETE", "GESTOR_SETORIAL") or
        cargo in ("gerente", "criador", "raiz")
    )

# ==================== COLABORADORES (FONTE ÚNICA: usuarios_acesso) ====================

def _get_nome_curto(colab):
    """Extrai rigorosamente o Nome de Guerra limpo; se não houver, usa o primeiro nome."""
    if not colab:
        return ""
    ng = colab.get("nome_guerra")
    if ng and str(ng).strip():
        return str(ng).strip()
    nome_comp = str(colab.get("nome", "")).strip()
    return nome_comp.split()[0] if nome_comp else ""

def _obter_colaboradores():
    """
    Busca colaboradores diretamente em 'usuarios_acesso' (SSOT).
    Elimina o uso de tabelas paralelas.
    """
    try:
        todos = db_manager.buscar_todos("usuarios_acesso", filtros={"ativo": True}) or []
        # Filtra rigorosamente quem está lotado no setor SEXP (independente de maiúsculas/minúsculas)
        return [u for u in todos if _normalizar_texto(u.get("setor", "")) == "sexp"]
    except Exception:
        return []

def _obter_colaboradores_por_cargo(tipo_sessao):
    """
    Retorna colaboradores elegíveis para o rodízio.
    CORREÇÃO: Gerentes AGORA PARTICIPAM normalmente de todas as sessões ordinárias e urgentes!
    """
    todos = _obter_colaboradores()
    tipo_norm = _normalizar_texto(tipo_sessao)

    if "reservada" in tipo_norm:
        # Em sessões reservadas, apenas estagiários ficam de fora
        return [
            c for c in todos 
            if _normalizar_texto(c.get("cargo", "")) != "estagiario" 
            and _normalizar_texto(c.get("vinculo", "")) != "estagiario"
        ]
    else:
        # Em todas as outras (Ordinária, Urgentes, etc), TODOS participam (incluindo Gerentes e Chefes!)
        return todos

# ==================== SINCRONIZAÇÃO COM SEAT ====================

def _sincronizar_com_seat():
    """
    Sincroniza processos finalizados da SEAT para a tabela da SEXP,
    padronizando os nomes dos tipos de sessão automaticamente.
    """
    try:
        processos_seat = db_manager.buscar_todos("pauta_seat") or []
        prontos_seat = [
            p for p in processos_seat 
            if p.get("status") == "encaminhado" or p.get("sessao_finalizada") is True
        ]
        
        todos_sexp = db_manager.buscar_todos("distribuicao_sexp") or []
        if not prontos_seat:
            return 0, len(todos_sexp)

        urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
        nums_urgentes = {
            _normalizar_numero_processo(u.get("processo_numero", "")) for u in urgentes_seat
        }

        nums_existentes = {
            _normalizar_numero_processo(d.get("processo_numero", "")) 
            for d in todos_sexp if d.get("processo_numero")
        }

        novos_inseridos = 0
        for p in prontos_seat:
            num_norm = _normalizar_numero_processo(p.get("processo_numero", ""))
            if not num_norm or num_norm in nums_existentes:
                continue

            # Converte "Ordinaria" para "Sessão Ordinária" ao salvar no SEXP
            tipo_sexp = _determinar_tabela_destino_sexp(p, nums_urgentes)
            
            novo_registro = {
                "processo_numero": p.get("processo_numero", ""),
                "relator": p.get("relator", ""),
                "tipo_sessao": tipo_sexp,
                "distribuido": False,
                "expedido": False,
                "revisado": False,
                "comentarios": p.get("comentarios", "") or "",
            }
            
            res = db_manager.inserir("distribuicao_sexp", novo_registro)
            if res:
                novos_inseridos += 1
                nums_existentes.add(num_norm)

        return novos_inseridos, len(todos_sexp) + novos_inseridos

    except Exception as e:
        print(f"[ERRO SINCRONIZACAO SEXP] {e}")
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

def _determinar_tabela_destino_sexp(processo, nums_urgentes):
    """Determina em qual tabela do SEXP o processo deve aparecer."""
    p_num = _normalizar_numero_processo(processo.get("processo_numero", ""))
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
    Executa a distribuição em cadeia com pareamento normalizado de sessões
    e fallback blindado de gravação no banco de dados.
    """
    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
        
        # Puxa os urgentes para classificar os processos rigorosamente igual à interface
        try:
            urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
            nums_urgentes = {
                _normalizar_numero_processo(u.get("processo_numero", "")) for u in urgentes_seat
            }
        except Exception:
            nums_urgentes = set()

        # CORREÇÃO BINÁRIA: Usa _determinar_tabela_destino_sexp para enxergar os 38 processos!
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
        erros_detalhados = []
        cliente = db_manager.get_supabase()

        for i, p in enumerate(processos):
            par = duplas[i % len(duplas)]
            dados_update = {
                "expedidor": par[0],
                "revisor": par[1],
                "distribuido": True,
                "tipo_sessao": tipo_sessao,  # Salva o nome padronizado no banco para sempre!
            }

            res = None
            id_reg = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")

            # 1ª Tentativa: Via db_manager usando o ID
            if id_reg:
                try:
                    res = db_manager.atualizar("distribuicao_sexp", id_reg, dados_update)
                except Exception as err_mgr:
                    erros_detalhados.append(f"Erro ID {id_reg}: {str(err_mgr)}")

            # 2ª Tentativa (Ataque Direto Supabase): Se db_manager falhou ou retornou vazio
            if not res and cliente and p.get("processo_numero"):
                try:
                    num_proc = p["processo_numero"]
                    resp = cliente.table("distribuicao_sexp").update(dados_update).eq("processo_numero", num_proc).execute()
                    if resp.data and len(resp.data) > 0:
                        res = resp.data[0]
                    else:
                        erros_detalhados.append(f"Proc {num_proc}: Supabase não encontrou a linha ou RLS bloqueou.")
                except Exception as err_api:
                    erros_detalhados.append(f"API Supabase Proc {p.get('processo_numero')}: {str(err_api)}")

            if res:
                sucessos += 1

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

    # Urgentes (Ordinária + Reservada que REALMENTE são urgentes)
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
        
        # Só entra se for da tabela Urgentes OU se for da Reservada e estiver na lista de urgência!
        is_urg = (tipo == "Urgentes") or ("reservada" in _normalizar_texto(tipo) and num_norm in nums_urgentes)
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

def _auto_atribuir_administrativa_jessyca():
    """Gatilho silencioso: encontra processos da Sessão Administrativa e atribui direto para a Jéssyca (Gerência)."""
    try:
        todos = db_manager.buscar_todos("distribuicao_sexp") or []
        urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []
        nums_urgentes = {_normalizar_numero_processo(u.get("processo_numero", "")) for u in urgentes_seat}

        for p in todos:
            tipo = _determinar_tabela_destino_sexp(p, nums_urgentes)
            if tipo == "Sessão Administrativa" and not p.get("distribuido", False) and not p.get("sessao_finalizada", False):
                id_reg = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")
                if id_reg:
                    db_manager.atualizar("distribuicao_sexp", id_reg, {
                        "expedidor": "Jessyca",
                        "revisor": "Jessyca",
                        "distribuido": True,
                        "tipo_sessao": "Sessão Administrativa"
                    })
    except Exception as e:
        print(f"[ERRO BYPASS ADMINISTRATIVA] {e}")

def _renderizar_pauta_ativa_sexp(usuario, modo_edicao):
    """Renderiza a Pauta Ativa apenas com métricas e painel de distribuição em cadeia (Sem listas longas)."""
    is_gerente = _tem_permissao_gestao(usuario)

    st.markdown("### 📋 Pauta Ativa — SEXP")
    st.caption("Processos revisados na SEAT aguardando distribuição. Selecione a equipe abaixo para disparar o lote.")

    novos, _ = _sincronizar_com_seat()
    if novos > 0:
        st.success(f"✅ {novos} novo(s) processo(s) importado(s) da SEAT!")
        st.markdown("---")

    # Executa o bypass automático da Sessão Administrativa para a Jéssyca
    if modo_edicao:
        _auto_atribuir_administrativa_jessyca()

    todos_revisados, encaminhados, total_seat = _verificar_todos_revisados_seat()
    if todos_revisados and total_seat > 0:
        st.success(f"🎉 **Todos os {total_seat} processos da SEAT foram revisados!** Prontos para distribuição.")
    elif total_seat > 0:
        st.info(f"📊 **SEAT:** {encaminhados} de {total_seat} revisados. Aguardando {total_seat - encaminhados} processo(s).")

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
        # A Sessão Administrativa pula a Pauta Ativa porque vai direto para a esteira de Distribuição com a Jéssyca
        if tipo == "Sessão Administrativa": continue

        processos = [d for d in todos_sexp if _determinar_tabela_destino_sexp(d, nums_urgentes) == tipo]
        if not processos: continue

        tem_algum_exibido = True
        nao_distribuidos = [d for d in processos if not d.get("distribuido", False)]
        distribuidos = [d for d in processos if d.get("distribuido", False)]

        st.markdown(f"#### {tipo}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total", len(processos))
        col2.metric("Não Distribuídos", len(nao_distribuidos))
        col3.metric("Distribuídos", len(distribuidos))

        # Quadro de Seleção de Colaboradores (Liberado para toda a equipe operando no setor)
        if modo_edicao and nao_distribuidos:
            elegiveis = _obter_colaboradores_por_cargo(tipo)
            nomes_elegiveis = sorted(list(set([_get_nome_curto(c) for c in elegiveis if _get_nome_curto(c)])))

            if nomes_elegiveis:
                with st.expander(f"⚙️ Distribuir {len(nao_distribuidos)} processo(s) de {tipo}", expanded=True):
                    st.markdown("**Selecione os colaboradores que participarão do rodízio em cadeias:**")
                    selecionados = st.multiselect(
                        "Colaboradores Elegíveis",
                        options=nomes_elegiveis,
                        default=nomes_elegiveis,
                        key=f"multiselect_{tipo}"
                    )

                    if st.button(f"📤 Distribuir {len(nao_distribuidos)} processo(s)", key=f"btn_dist_{tipo}", type="primary", use_container_width=True):
                        if len(selecionados) < 2:
                            st.error("Selecione pelo menos 2 colaboradores para formar a cadeia de duplas (A expede → B revisa).")
                        else:
                            qtd = _executar_distribuicao(tipo, selecionados)
                            if qtd > 0:
                                st.success(f"✅ {qtd} processo(s) distribuído(s) em cadeia! Acesse a aba 'Distribuição' ou 'Urgentes' para operar.")
                                st.rerun()
                            else:
                                st.error("Erro ao distribuir processos no banco de dados.")
            else:
                st.warning("Nenhum colaborador elegível ativo cadastrado para este tipo de sessão.")

        st.markdown("---")

    if not todos_sexp or not tem_algum_exibido:
        st.info("Nenhum processo aguardando distribuição na pauta.")

        # Listagem dos Cards de Processos
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

    if not todos_sexp or not tem_algum_exibido:
        st.info("Nenhum processo importado da SEAT ainda. Aguarde a finalização da sessão na SEAT.")
        
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

    """Renderiza a aba de Distribuição com tabelas interativas SEPARADAS por Sessão/Data e botão restrito a gerentes."""

    import pandas as pd

    cargo = _normalizar_texto(usuario.get("cargo", "operacional"))

    is_gerente = _tem_permissao_gestao(usuario)



    st.markdown("### 📤 Distribuição — Esteira Operacional")

    st.caption("As tabelas são geradas e isoladas automaticamente pelo Número e Dia da Sessão.")



    try:

        todos = db_manager.buscar_todos("distribuicao_sexp", ordem_coluna="id", ordem_desc=False) or []

    except Exception:

        todos = []



    distribuidos = [d for d in todos if d.get("distribuido", False) and not d.get("removido_pauta", False) and not d.get("sessao_finalizada", False)]



    if not distribuidos:

        st.info("Nenhum processo tramitando na esteira de distribuição no momento.")

        return



    try:

        urgentes_seat = db_manager.buscar_todos("processos_urgentes") or []

        nums_urgentes = {_normalizar_numero_processo(u.get("processo_numero", "")) for u in urgentes_seat}

    except Exception:

        nums_urgentes = set()



    tipos_com_processos = [t for t in TIPOS_SESSAO_SEXP if t != "Urgentes" and any(_determinar_tabela_destino_sexp(d, nums_urgentes) == t for d in distribuidos)]



    if not tipos_com_processos:

        st.info("Nenhum processo distribuído.")

        return



    sub_tabs = st.tabs(tipos_com_processos)



    for idx_tab, tipo in enumerate(tipos_com_processos):

        with sub_tabs[idx_tab]:

            procs_tipo = [d for d in distribuidos if _determinar_tabela_destino_sexp(d, nums_urgentes) == tipo]

            if cargo == "operacional" and not is_gerente:

                procs_tipo = [d for d in procs_tipo if _eh_o_colaborador(usuario, d.get("expedidor")) or _eh_o_colaborador(usuario, d.get("revisor"))]



            if not procs_tipo:

                st.info("Nenhum processo atribuído a você neste tipo de sessão.")

                continue



            # AGRUPAMENTO ANTI-AGLOMERAÇÃO: Separa rigorosamente por Número da Sessão e Dia

            sessoes_isoladas = {}

            for p in procs_tipo:

                num_s = p.get("numero_sessao") or p.get("sessao_numero") or "S/N"

                dia_raw = str(p.get("dia_sessao", ""))[:10]

                dia_fmt = _formatar_data_curta(dia_raw) if ("-" in dia_raw or "/" in dia_raw) else (dia_raw or "Data N/I")

                chave_sessao = f"Sessão {num_s} — ({dia_fmt})"

                

                if chave_sessao not in sessoes_isoladas:

                    sessoes_isoladas[chave_sessao] = []

                sessoes_isoladas[chave_sessao].append(p)



            # Desenha uma tabela interativa independente para cada sessão/data

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

                    dados_df.append({

                        "ID": id_reg,

                        "Processo Nº": p.get("processo_numero", ""),

                        "Relator": p.get("relator", "") or "-",

                        "Expedidor": p.get("expedidor", "") or "-",

                        "Expedido ✅": bool(p.get("expedido", False)),

                        "Revisor": p.get("revisor", "") or "-",

                        "Revisado ✅": bool(p.get("revisado", False)),

                        "Comentários": p.get("comentarios", "") or ""

                    })



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

                            "Comentários": st.column_config.TextColumn("Observações", disabled=True)

                        },

                        hide_index=True, use_container_width=True, key=f"tbl_dist_{tipo}_{idx_tab}_{idx_ses}"

                    )



                    if not df.equals(df_editado):

                        for index, row in df_editado.iterrows():

                            if row["Expedido ✅"] != df.loc[index, "Expedido ✅"] or row["Revisado ✅"] != df.loc[index, "Revisado ✅"]:

                                db_manager.atualizar("distribuicao_sexp", int(row["ID"]), {

                                    "expedido": bool(row["Expedido ✅"]),

                                    "revisado": bool(row["Revisado ✅"])

                                })

                        st.success("🎉 Tabela atualizada no banco!")

                        st.rerun()

                else:

                    st.dataframe(df.drop(columns=["ID"]), hide_index=True, use_container_width=True)



                # BOTÃO DE FINALIZAR SESSÃO: Exclusivo para o Gerente / Criador!

                if modo_edicao and is_gerente:

                    confirmar = st.checkbox(f"Estou ciente e desejo arquivar a {chave}", key=f"chk_{tipo}_{idx_tab}_{idx_ses}")

                    if st.button(f"🔒 Finalizar Sessão ({chave})", key=f"btn_fim_{tipo}_{idx_tab}_{idx_ses}", type="primary", disabled=not confirmar):

                        with st.spinner(f"Arquivando pauta {chave}..."):

                            for p in processos:

                                id_fechar = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")

                                if id_fechar:

                                    db_manager.atualizar("distribuicao_sexp", id_fechar, {"sessao_finalizada": True, "status": "arquivado"})

                        st.success(f"✅ {chave} encerrada e arquivada!")

                        st.rerun()

                st.markdown("---")



            # Montando a Tabela Interativa

            dados_df = []

            for p in processos:

                id_reg = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")

                dados_df.append({

                    "ID": id_reg,

                    "Processo Nº": p.get("processo_numero", ""),

                    "Relator": p.get("relator", "") or "-",

                    "Expedidor": p.get("expedidor", "") or "-",

                    "Expedido ✅": bool(p.get("expedido", False)),

                    "Revisor": p.get("revisor", "") or "-",

                    "Revisado ✅": bool(p.get("revisado", False)),

                    "Comentários / Forma Despacho": p.get("comentarios", "") or p.get("forma_despacho", "") or ""

                })



            df = pd.DataFrame(dados_df)



            # Se estiver em modo edição, usa tabela interativa onde os checkboxes alteram o banco!

            if modo_edicao:

                df_editado = st.data_editor(

                    df,

                    column_config={

                        "ID": None, # Ocultada

                        "Processo Nº": st.column_config.TextColumn("Nº Processo", disabled=True),

                        "Relator": st.column_config.TextColumn("Relator", disabled=True),

                        "Expedidor": st.column_config.TextColumn("Expedidor", disabled=True),

                        "Expedido ✅": st.column_config.CheckboxColumn("Expedido?", default=False),

                        "Revisor": st.column_config.TextColumn("Revisor", disabled=True),

                        "Revisado ✅": st.column_config.CheckboxColumn("Revisado?", default=False),

                        "Comentários / Forma Despacho": st.column_config.TextColumn("Observações", disabled=True)

                    },

                    hide_index=True,

                    use_container_width=True,

                    key=f"editor_tab_{tipo}_{idx}"

                )



                # Sincroniza alterações feitas direto nos checkboxes da tabela com o Supabase

                if not df.equals(df_editado):

                    for index, row in df_editado.iterrows():

                        id_linha = row["ID"]

                        exp_atual = row["Expedido ✅"]

                        rev_atual = row["Revisado ✅"]

                        exp_antigo = df.loc[index, "Expedido ✅"]

                        rev_antigo = df.loc[index, "Revisado ✅"]



                        if exp_atual != exp_antigo or rev_atual != rev_antigo:

                            db_manager.atualizar("distribuicao_sexp", int(id_linha), {

                                "expedido": bool(exp_atual),

                                "revisado": bool(rev_atual)

                            })

                    st.success("🎉 Alteração gravada na tabela com sucesso!")

                    st.rerun()

            else:

                st.dataframe(df.drop(columns=["ID"]), hide_index=True, use_container_width=True)



            st.markdown("---")

            

            # Botão de Finalizar Sessão no rodapé

            if modo_edicao:

                faltam_fechar = total - revisados

                if faltam_fechar == 0:

                    st.success(f"🎉 **Todos os {total} processos de {tipo} foram expedidos e revisados!**")

                else:

                    st.warning(f"⚠️ **Atenção:** Ainda restam **{faltam_fechar}** processo(s) pendentes de revisão final nesta sessão.")



                confirmar = st.checkbox(

                    f"Estou ciente das pendências e desejo encerrar a esteira operatória da {tipo}.", 

                    key=f"chk_encerrar_{tipo}_{idx}"

                )



                if st.button(f"🔒 Finalizar Sessão ({tipo}) e Arquivar Pauta", key=f"btn_fim_sexp_{tipo}_{idx}", type="primary", disabled=not confirmar, use_container_width=True):

                    with st.spinner("Arquivando pauta e liberando esteira..."):

                        for p in processos:

                            id_fechar = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")

                            if id_fechar:

                                db_manager.atualizar("distribuicao_sexp", id_fechar, {"sessao_finalizada": True, "status": "arquivado"})

                    st.success(f"✅ {tipo} encerrada com sucesso!")

                    st.rerun()
# ==================== URGENTES ====================

def _renderizar_urgentes_sexp(usuario, modo_edicao):
    """Renderiza a aba de Urgentes em Tabela Interativa (igual Ordinária), isolada por Sessão/Data com encerramento de chefia."""
    import pandas as pd
    cargo = _normalizar_texto(usuario.get("cargo", "operacional"))
    is_gerente = _tem_permissao_gestao(usuario)

    st.markdown("### 🚨 Processos Urgentes — Esteira Prioritária")
    st.caption("Processos com prioridade de tramitação. Tabela interativa com gravação em tempo real.")

    try:
        todos = db_manager.buscar_todos("distribuicao_sexp", ordem_coluna="id", ordem_desc=False) or []
    except Exception:
        todos = []

    processos_urg = [d for d in todos if d.get("tipo_sessao") == "Urgentes" and d.get("distribuido", False) and not d.get("removido_pauta", False) and not d.get("sessao_finalizada", False)]

    if cargo == "operacional" and not is_gerente:
        processos_urg = [d for d in processos_urg if _eh_o_colaborador(usuario, d.get("expedidor")) or _eh_o_colaborador(usuario, d.get("revisor"))]

    if not processos_urg:
        st.info("Nenhum processo urgente tramitando no momento.")
        return

    # AGRUPAMENTO ANTI-AGLOMERAÇÃO: Separa por Número da Sessão e Dia
    sessoes_isoladas = {}
    for p in processos_urg:
        num_s = p.get("numero_sessao") or p.get("sessao_numero") or "S/N"
        dia_raw = str(p.get("dia_sessao", ""))[:10]
        dia_fmt = _formatar_data_curta(dia_raw) if ("-" in dia_raw or "/" in dia_raw) else (dia_raw or "Data N/I")
        chave_sessao = f"Urgentes — Sessão {num_s} ({dia_fmt})"
        
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
            dados_df.append({
                "ID": id_reg,
                "Processo Nº": p.get("processo_numero", ""),
                "Relator": p.get("relator", "") or "-",
                "Expedidor": p.get("expedidor", "") or "-",
                "Expedido ✅": bool(p.get("expedido", False)),
                "Revisor": p.get("revisor", "") or "-",
                "Revisado ✅": bool(p.get("revisado", False)),
                "Comentários / Observação": p.get("comentarios", "") or "Tramitação Prioritária"
            })

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
                    "Comentários / Observação": st.column_config.TextColumn("Observações", disabled=True)
                },
                hide_index=True, use_container_width=True, key=f"tbl_urg_{idx_ses}"
            )

            if not df.equals(df_editado):
                for index, row in df_editado.iterrows():
                    if row["Expedido ✅"] != df.loc[index, "Expedido ✅"] or row["Revisado ✅"] != df.loc[index, "Revisado ✅"]:
                        db_manager.atualizar("distribuicao_sexp", int(row["ID"]), {
                            "expedido": bool(row["Expedido ✅"]),
                            "revisado": bool(row["Revisado ✅"])
                        })
                st.success("🎉 Urgentes atualizados no banco!")
                st.rerun()
        else:
            st.dataframe(df.drop(columns=["ID"]), hide_index=True, use_container_width=True)

        # BOTÃO DE FINALIZAR SESSÃO DE URGENTES: Exclusivo para o Gerente / Criador!
        if modo_edicao and is_gerente:
            confirmar = st.checkbox(f"Estou ciente e desejo arquivar os processos de {chave}", key=f"chk_urg_{idx_ses}")
            if st.button(f"🔒 Finalizar Sessão de Urgentes ({chave})", key=f"btn_fim_urg_{idx_ses}", type="primary", disabled=not confirmar):
                with st.spinner(f"Arquivando pauta {chave}..."):
                    for p in processos:
                        id_fechar = p.get("id") or p.get("id_distribuicao") or p.get("id_processo")
                        if id_fechar:
                            db_manager.atualizar("distribuicao_sexp", id_fechar, {"sessao_finalizada": True, "status": "arquivado"})
                st.success(f"✅ {chave} encerrada e arquivada com sucesso!")
                st.rerun()
        st.markdown("---")

        for p in processos_urg:
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
