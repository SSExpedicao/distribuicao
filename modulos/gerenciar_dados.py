"""
Gerenciamento de Dados — Limpeza e exclusão de processos
Módulo reutilizável para integrar como subtab em qualquer setor.
Acesso restrito: Raiz e Gerente.
"""

import streamlit as st
from db_manager import buscar_todos, deletar, atualizar

# ============================================================
# MAPEAMENTO DE TABELAS POR SETOR
# ============================================================
TABELAS_POR_SETOR = {
    "SEAT": {
        "principais": ["pauta_seat"],
        "urgentes": ["processos_urgentes"],
        "descricao": "Pauta da SEAT + Urgentes"
    },
    "SEXP": {
        "principais": ["distribuicao_sexp", "pauta_sexp"],
        "urgentes": ["processos_urgentes"],
        "descricao": "Distribuição SEXP + Pauta SEXP"
    },
    "SERCON": {
        "principais": ["pauta_sercon", "processos_sercon"],
        "urgentes": [],
        "descricao": "Pauta SERCON + Processos SERCON"
    },
    "SEMAND": {
        "principais": ["pauta_semand"],
        "urgentes": [],
        "descricao": "Pauta SEMAND"
    },
    "GERAL": {
        "principais": ["processos", "pauta_quarta"],
        "urgentes": ["processos_urgentes"],
        "descricao": "Processos gerais + Pauta Quarta"
    },
}

# ============================================================
# FUNÇÃO PRINCIPAL — RENDERIZAR SUBTAB
# ============================================================
def _renderizar_gerenciar_dados(usuario, setor):
    """
    Renderiza a subtab de gerenciamento de dados.
    
    Parâmetros:
    - usuario: dict com dados do usuário logado
    - setor: string ("SEAT", "SEXP", "SERCON", "SEMAND", "GERAL")
    """

    # Verificar permissão
    perfil = usuario.get("perfil", "").lower()
    is_raiz = perfil in ["raiz", "criador", "admin"]
    is_gerente = "gerente" in perfil or "gerência" in perfil

    if not is_raiz and not is_gerente:
        st.warning("⚠️ Acesso restrito a Raiz e Gerentes.")
        return

    st.markdown("### 🗑️ Gerenciar Dados do Setor")
    st.caption(f"Setor: **{setor}** — {TABELAS_POR_SETOR.get(setor, {}).get('descricao', '—')}")

    st.divider()

    # ============================================================
    # OPÇÃO 1: EXCLUIR PROCESSO INDIVIDUAL
    # ============================================================
    st.markdown("#### 🔍 Excluir Processo Individual")

    config = TABELAS_POR_SETOR.get(setor, {})
    todas_tabelas = config.get("principais", []) + config.get("urgentes", [])

    if not todas_tabelas:
        st.error("Nenhuma tabela configurada para este setor.")
        return

    # Selecionar tabela
    tabela_sel = st.selectbox(
        "Selecionar tabela",
        todas_tabelas,
        key=f"tabela_del_{setor}"
    )

    # Buscar processos da tabela
    processos = []
    try:
        processos = buscar_todos(tabela_sel) or []
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
        return

    if not processos:
        st.info(f"Nenhum processo encontrado na tabela `{tabela_sel}`.")
    else:
        # Criar lista de opções para o selectbox
        opcoes = []
        for p in processos:
            pid = p.get("id", "—")
            numero = p.get("processo_numero", p.get("numero_processo", p.get("numero", "—")))
            relator = p.get("relator", "—")
            opcoes.append(f"ID: {pid} | {numero} | Relator: {relator}")

        processo_sel = st.selectbox(
            f"Selecionar processo ({len(processos)} encontrados)",
            range(len(opcoes)),
            format_func=lambda i: opcoes[i],
            key=f"proc_del_{setor}"
        )

        if processo_sel is not None:
            proc = processos[processo_sel]
            pid = proc.get("id")

            # Mostrar detalhes do processo selecionado
            with st.expander("Detalhes do processo"):
                for k, v in proc.items():
                    st.write(f"**{k}:** {v}")

            col_del, col_espaco = st.columns([1, 3])
            with col_del:
                confirmar_del = st.checkbox(
                    "Confirmo que desejo excluir este processo",
                    key=f"conf_del_{setor}"
                )
                if st.button(
                    "🗑️ Excluir Processo",
                    type="primary",
                    disabled=not confirmar_del,
                    use_container_width=True,
                    key=f"btn_del_{setor}"
                ):
                    try:
                        deletar(tabela_sel, pid)
                        st.success(f"✅ Processo {pid} excluído de `{tabela_sel}`!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {e}")

    st.divider()

    # ============================================================
    # OPÇÃO 2: LIMPAR TODOS OS PROCESSOS (BULK)
    # ============================================================
    st.markdown("#### ⚠️ Limpar Todos os Processos")
    st.warning(
        "🚨 **ATENÇÃO:** Esta ação é **IRREVERSÍVEL**. "
        "Todos os processos serão excluídos permanentemente. "
        "Use apenas para resetar o sistema antes do go-live."
    )

    # Mostrar contagem por tabela
    st.markdown("**Resumo de dados que serão excluídos:**")
    contagem_total = 0
    for tab in todas_tabelas:
        try:
            dados = buscar_todos(tab) or []
            contagem = len(dados)
            contagem_total += contagem
            st.write(f"- `{tab}`: **{contagem}** registro(s)")
        except:
            st.write(f"- `{tab}`: erro ao contar")

    st.write(f"**Total a excluir: {contagem_total} registro(s)**")

    # Selecionar o que limpar
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        limpar_principais = st.checkbox(
            f"Limpar tabelas principais ({', '.join(config.get('principais', []))})",
            value=True,
            key=f"chk_main_{setor}"
        )
    with col_l2:
        limpar_urgentes = st.checkbox(
            f"Limpar urgentes ({', '.join(config.get('urgentes', []))})",
            value=False,
            key=f"chk_urg_{setor}"
        )

    tabelas_para_limpar = []
    if limpar_principais:
        tabelas_para_limpar.extend(config.get("principais", []))
    if limpar_urgentes:
        tabelas_para_limpar.extend(config.get("urgentes", []))

    if tabelas_para_limpar:
        # Dupla confirmação
        confirmar1 = st.checkbox(
            f"Confirmo que desejo excluir TODOS os {contagem_total} registros",
            key=f"conf_bulk1_{setor}"
        )
        confirmar2 = st.checkbox(
            "Estou ciente de que esta ação NÃO pode ser desfeita",
            key=f"conf_bulk2_{setor}"
        )

        # Input de confirmação por texto
        texto_confirma = st.text_input(
            f"Digite 'LIMPAR' para confirmar a exclusão de {len(tabelas_para_limpar)} tabela(s)",
            placeholder="LIMPAR",
            key=f"txt_conf_{setor}"
        )

        pode_limpar = (
            confirmar1
            and confirmar2
            and texto_confirma.strip().upper() == "LIMPAR"
        )

        if st.button(
            "🚨 LIMPAR TUDO AGORA",
            type="primary",
            disabled=not pode_limpar,
            use_container_width=True,
            key=f"btn_bulk_{setor}"
        ):
            erros = []
            excluidos = 0
            for tab in tabelas_para_limpar:
                try:
                    dados = buscar_todos(tab) or []
                    for d in dados:
                        did = d.get("id")
                        if did:
                            deletar(tab, did)
                            excluidos += 1
                except Exception as e:
                    erros.append(f"{tab}: {e}")

            if erros:
                st.error(f"Concluído com {len(erros)} erro(s): {', '.join(erros)}")
            else:
                st.success(f"✅ {excluidos} registro(s) excluído(s) de {len(tabelas_para_limpar)} tabela(s)!")
            st.rerun()

    st.divider()

    # ============================================================
    # OPÇÃO 3: MOVER PARA PROCESSOS_EXCLUIDOS (SOFT DELETE)
    # ============================================================
    st.markdown("#### 📦 Arquivar (Soft Delete)")
    st.caption("Em vez de excluir permanentemente, move os processos para a tabela `processos_excluidos`.")

    if st.button(
        "📦 Arquivar todos os processos do setor",
        use_container_width=True,
        key=f"btn_archive_{setor}"
    ):
        excluidos = 0
        for tab in config.get("principais", []):
            try:
                dados = buscar_todos(tab) or []
                for d in dados:
                    did = d.get("id")
                    if did:
                        # Marcar como arquivado em vez de deletar
                        atualizar(tab, did, {
                            "status": "arquivado",
                            "sessao_finalizada": True
                        })
                        excluidos += 1
            except:
                pass
        st.success(f"✅ {excluidos} processo(s) arquivado(s)!")
        st.rerun()
