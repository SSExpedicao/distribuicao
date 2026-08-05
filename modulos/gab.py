"""
modulos/gab.py - Gabinete
Secretaria das Sessoes - TCDF

Responsabilidades:
- Visão gerencial consolidada
- Gestão de colaboradores
- Aprovação de ausências
- Escala do Plenário
- Agenda do Secretário
- Auditoria e configurações
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import streamlit as st

import db_manager
from modulos.gerenciar_dados import _renderizar_gerenciar_dados

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False

# ============================================================
# CONSTANTES
# ============================================================

SETORES_SISTEMA = ["GAB", "SEAT", "SEXP"]

CARGOS_PADRAO = [
    "Assessor",
    "Gerente",
    "Secretário",
    "Subsecretário",
    "Estagiário",
    "Desenvolvedor",
]

VINCULOS_PADRAO = [
    "efetivo",
    "comissionado",
    "cedido",
    "temporário",
    "estagiário",
    "terceirizado",
]

NIVEIS_ACESSO_PADRAO = [
    "OPERACIONAL",
    "GESTOR_SETORIAL",
    "ADMIN_GABINETE",
    "SUPER_ADMIN_CRIADOR",
]

STATUS_AUSENCIA_PERMITIDOS = [
    "PENDENTE",
    "APROVADA",
    "REPROVADA",
    "NOTIFICADO",
]

TIPOS_AUSENCIA = [
    "FERIAS",
    "ATESTADO",
    "ABONO",
]

# ============================================================
# HELPERS GERAIS
# ============================================================

def _normalizar_texto(texto: Any) -> str:
    """
    Normaliza texto para comparação tolerante.
    """
    if texto is None:
        return ""

    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.split())

def _formatar_data_curta(data_valor: Any) -> str:
    """
    Converte data ISO para DD/MM/AAAA.
    """
    if not data_valor:
        return "-"

    try:
        texto = str(data_valor).replace("Z", "+00:00")
        if "T" in texto:
            dt = datetime.fromisoformat(texto)
        else:
            dt = datetime.strptime(texto[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(data_valor)[:10]

def _formatar_data_hora(data_valor: Any) -> str:
    """
    Converte data/hora ISO para DD/MM/AAAA HH:MM.
    """
    if not data_valor:
        return "-"

    try:
        texto = str(data_valor).replace("Z", "+00:00")
        dt = datetime.fromisoformat(texto)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(data_valor)

def _bool_label(valor: Any) -> str:
    """
    Representação amigável de booleano.
    """
    return "Sim" if bool(valor) else "Não"

def _tem_permissao_gab(usuario: Dict[str, Any]) -> bool:
    """
    Define se o usuário pode operar funções de gabinete.
    """
    nivel = str(usuario.get("nivel_acesso", "") or "").strip()
    cargo = _normalizar_texto(usuario.get("cargo", ""))

    return (
        nivel in {"SUPER_ADMIN_CRIADOR", "ADMIN_GABINETE", "GESTOR_SETORIAL"}
        or cargo in {"gerente", "secretario", "subsecretario", "desenvolvedor", "criador", "raiz"}
    )

def _tem_permissao_total_colaboradores(usuario: Dict[str, Any]) -> bool:
    """
    Permissão para gestão de colaboradores.
    """
    nivel = str(usuario.get("nivel_acesso", "") or "").strip()
    return nivel in {"SUPER_ADMIN_CRIADOR", "ADMIN_GABINETE"}

def _resolver_nome_exibicao(colaborador: Dict[str, Any]) -> str:
    """
    Retorna o nome preferencial para exibição.
    """
    nome_guerra = str(colaborador.get("nome_guerra", "") or "").strip()
    nome = str(colaborador.get("nome", "") or "").strip()

    if nome_guerra:
        return nome_guerra
    return nome

def _ordenar_colaboradores(colaboradores: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ordena colaboradores por setor e nome.
    """
    return sorted(
        colaboradores,
        key=lambda c: (
            _normalizar_texto(c.get("setor", "")),
            _normalizar_texto(c.get("nome_exibicao", "") or c.get("nome_guerra", "") or c.get("nome", "")),
            _normalizar_texto(c.get("matricula", "")),
        ),
    )

def _obter_colaboradores(
    incluir_inativos: bool = True,
    incluir_contas_tecnicas: bool = True,
) -> List[Dict[str, Any]]:
    """
    Retorna colaboradores a partir da camada canônica.
    """
    try:
        colaboradores = db_manager.listar_equipe(
            incluir_inativos=incluir_inativos,
            incluir_contas_tecnicas=incluir_contas_tecnicas,
        ) or []

        resultado = []
        for c in colaboradores:
            item = dict(c)
            item["nome_exibicao"] = item.get("nome_exibicao") or _resolver_nome_exibicao(item)
            resultado.append(item)

        return _ordenar_colaboradores(resultado)
    except Exception as e:
        print(f"[GAB ERROR] _obter_colaboradores: {e}")
        return []

def _coletar_metricas_setor(setor: str) -> Dict[str, int]:
    """
    Consolida KPIs básicos por setor.
    """
    setor_norm = _normalizar_texto(setor)
    colaboradores = [
        c for c in _obter_colaboradores(incluir_inativos=True, incluir_contas_tecnicas=True)
        if _normalizar_texto(c.get("setor", "")) == setor_norm
    ]

    ativos = [c for c in colaboradores if bool(c.get("ativo", False))]
    inativos = [c for c in colaboradores if not bool(c.get("ativo", False))]

    return {
        "total": len(colaboradores),
        "ativos": len(ativos),
        "inativos": len(inativos),
    }

def _obter_processos_pauta_seat() -> List[Dict[str, Any]]:
    try:
        return db_manager.buscar_todos("pauta_seat") or []
    except Exception:
        return []

def _obter_processos_sexp() -> List[Dict[str, Any]]:
    try:
        return db_manager.buscar_todos("distribuicao_sexp") or []
    except Exception:
        return []

def _obter_solicitacoes_ausencia() -> List[Dict[str, Any]]:
    try:
        return db_manager.buscar_todos(
            "solicitacoes_ausencia",
            ordem_coluna="data_inicio",
            ordem_desc=False,
        ) or []
    except Exception:
        return []

def _obter_avisos() -> List[Dict[str, Any]]:
    try:
        return db_manager.buscar_todos(
            "avisos",
            ordem_coluna="created_at",
            ordem_desc=True,
        ) or []
    except Exception:
        return []

def _obter_regras_nip_por_tabela(nome_tabela: str) -> List[Dict[str, Any]]:
    try:
        return db_manager.buscar_todos(
            nome_tabela,
            ordem_coluna="id",
            ordem_desc=False,
        ) or []
    except Exception:
        return []

# ============================================================
# DASHBOARD GERAL
# ============================================================

def _renderizar_dashboard_geral(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Dashboard consolidado do gabinete.
    """
    st.markdown("### 📊 Dashboard Geral")

    metricas_gab = _coletar_metricas_setor("GAB")
    metricas_seat = _coletar_metricas_setor("SEAT")
    metricas_sexp = _coletar_metricas_setor("SEXP")

    pauta_seat = _obter_processos_pauta_seat()
    pauta_sexp = _obter_processos_sexp()
    solicitacoes = _obter_solicitacoes_ausencia()

    seat_encaminhados = len([p for p in pauta_seat if p.get("status") == "encaminhado"])
    seat_pendentes = len([p for p in pauta_seat if p.get("status") != "encaminhado"])

    sexp_distribuidos = len([p for p in pauta_sexp if p.get("distribuido", False)])
    sexp_pendentes = len([p for p in pauta_sexp if not p.get("distribuido", False)])

    ausencias_pendentes = len([s for s in solicitacoes if s.get("status") == "PENDENTE"])
    ausencias_aprovadas = len([s for s in solicitacoes if s.get("status") in {"APROVADA", "NOTIFICADO"}])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Colaboradores Ativos", metricas_gab["ativos"] + metricas_seat["ativos"] + metricas_sexp["ativos"])
    with col2:
        st.metric("SEAT Pendentes", seat_pendentes)
    with col3:
        st.metric("SEXP Pendentes", sexp_pendentes)
    with col4:
        st.metric("Ausências Pendentes", ausencias_pendentes)

    st.markdown("---")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown("#### GAB")
        st.write(f"- Ativos: **{metricas_gab['ativos']}**")
        st.write(f"- Inativos: **{metricas_gab['inativos']}**")
        st.write(f"- Total: **{metricas_gab['total']}**")

    with col_b:
        st.markdown("#### SEAT")
        st.write(f"- Ativos: **{metricas_seat['ativos']}**")
        st.write(f"- Pendentes: **{seat_pendentes}**")
        st.write(f"- Encaminhados: **{seat_encaminhados}**")

    with col_c:
        st.markdown("#### SEXP")
        st.write(f"- Ativos: **{metricas_sexp['ativos']}**")
        st.write(f"- Não distribuídos: **{sexp_pendentes}**")
        st.write(f"- Distribuídos: **{sexp_distribuidos}**")

    st.markdown("---")

    if PANDAS_OK:
        dados = [
            {"Setor": "GAB", "Ativos": metricas_gab["ativos"], "Inativos": metricas_gab["inativos"], "Total": metricas_gab["total"]},
            {"Setor": "SEAT", "Ativos": metricas_seat["ativos"], "Inativos": metricas_seat["inativos"], "Total": metricas_seat["total"]},
            {"Setor": "SEXP", "Ativos": metricas_sexp["ativos"], "Inativos": metricas_sexp["inativos"], "Total": metricas_sexp["total"]},
        ]
        df = pd.DataFrame(dados)
        st.dataframe(df, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Ausências")
    st.write(f"- Pendentes de análise: **{ausencias_pendentes}**")
    st.write(f"- Aprovadas / notificadas: **{ausencias_aprovadas}**")

# ============================================================
# RESUMO DOS SETORES
# ============================================================

def _renderizar_setores(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Visão consolidada de setores.
    """
    st.markdown("### 🏢 Setores")

    colaboradores = _obter_colaboradores(incluir_inativos=True, incluir_contas_tecnicas=True)
    pauta_seat = _obter_processos_pauta_seat()
    pauta_sexp = _obter_processos_sexp()

    if PANDAS_OK:
        linhas = []
        for setor in SETORES_SISTEMA:
            setor_norm = _normalizar_texto(setor)
            colabs_setor = [c for c in colaboradores if _normalizar_texto(c.get("setor", "")) == setor_norm]
            ativos = len([c for c in colabs_setor if c.get("ativo", False)])

            seat_total = 0
            seat_pend = 0
            sexp_total = 0
            sexp_pend = 0

            if setor == "SEAT":
                seat_total = len(pauta_seat)
                seat_pend = len([p for p in pauta_seat if p.get("status") != "encaminhado"])

            if setor == "SEXP":
                sexp_total = len(pauta_sexp)
                sexp_pend = len([p for p in pauta_sexp if not p.get("distribuido", False)])

            linhas.append(
                {
                    "Setor": setor,
                    "Colaboradores Ativos": ativos,
                    "Total Colaboradores": len(colabs_setor),
                    "Carga SEAT": seat_total,
                    "Pendências SEAT": seat_pend,
                    "Carga SEXP": sexp_total,
                    "Pendências SEXP": sexp_pend,
                }
            )

        df = pd.DataFrame(linhas)
        st.dataframe(df, hide_index=True, use_container_width=True)

    st.markdown("---")

    setor_escolhido = st.selectbox("Detalhar setor", options=SETORES_SISTEMA, key="gab_setor_detalhe")
    setor_norm = _normalizar_texto(setor_escolhido)

    colabs_detalhe = [c for c in colaboradores if _normalizar_texto(c.get("setor", "")) == setor_norm]

    st.markdown(f"#### Equipe do {setor_escolhido}")

    if not colabs_detalhe:
        st.info("Nenhum colaborador encontrado para este setor.")
        return

    if PANDAS_OK:
        dados = []
        for c in colabs_detalhe:
            dados.append(
                {
                    "Nome": c.get("nome", ""),
                    "Nome curto": c.get("nome_guerra", "") or "-",
                    "Matrícula": c.get("matricula", ""),
                    "Cargo": c.get("cargo", ""),
                    "Vínculo": c.get("vinculo", ""),
                    "Nível": c.get("nivel_acesso", ""),
                    "Ativo": _bool_label(c.get("ativo", False)),
                }
            )

        df = pd.DataFrame(dados)
        st.dataframe(df, hide_index=True, use_container_width=True)

# ============================================================
# COLABORADORES
# ============================================================

def _renderizar_colaboradores(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Aba principal de gestão de colaboradores.
    """
    st.markdown("### 👥 Colaboradores")
    st.caption(
        "Cadastro, edição e inativação de colaboradores. "
        "A fonte única de verdade é a tabela `usuarios_acesso`."
    )

    pode_gerir = _tem_permissao_total_colaboradores(usuario)
    if not pode_gerir:
        st.warning("Você não possui permissão para alterar colaboradores. Visualização liberada.")
        modo_edicao = False

    colaboradores = _obter_colaboradores(incluir_inativos=True, incluir_contas_tecnicas=True)

    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        filtro_setor = st.selectbox(
            "Filtrar por setor",
            options=["Todos"] + SETORES_SISTEMA,
            key="gab_colab_setor",
        )

    with col_f2:
        filtro_status = st.selectbox(
            "Filtrar por status",
            options=["Todos", "Ativos", "Inativos"],
            key="gab_colab_status",
        )

    with col_f3:
        mostrar_tecnicas = st.checkbox(
            "Mostrar contas técnicas",
            value=True,
            key="gab_colab_tecnicas",
        )

    filtrados = []
    for c in colaboradores:
        if filtro_setor != "Todos" and _normalizar_texto(c.get("setor", "")) != _normalizar_texto(filtro_setor):
            continue

        if filtro_status == "Ativos" and not bool(c.get("ativo", False)):
            continue

        if filtro_status == "Inativos" and bool(c.get("ativo", False)):
            continue

        if not mostrar_tecnicas and bool(c.get("conta_tecnica", False)):
            continue

        filtrados.append(c)

    st.write(f"**{len(filtrados)} colaborador(es) listado(s).**")

    if PANDAS_OK and filtrados:
        dados = []
        for c in filtrados:
            dados.append(
                {
                    "ID": c.get("id"),
                    "Nome": c.get("nome", ""),
                    "Nome curto": c.get("nome_guerra", "") or "-",
                    "Matrícula": c.get("matricula", ""),
                    "Setor": c.get("setor", ""),
                    "Cargo": c.get("cargo", ""),
                    "Vínculo": c.get("vinculo", ""),
                    "Nível": c.get("nivel_acesso", ""),
                    "Ativo": _bool_label(c.get("ativo", False)),
                    "Conta técnica": _bool_label(c.get("conta_tecnica", False)),
                }
            )

        df = pd.DataFrame(dados)
        st.dataframe(df, hide_index=True, use_container_width=True)

    st.markdown("---")

    tab_cadastrar, tab_editar, tab_inativar = st.tabs(
        ["Cadastrar", "Editar", "Remover / Inativar"]
    )

    with tab_cadastrar:
        st.markdown("#### Cadastrar novo colaborador")

        if not modo_edicao:
            st.info("Modo visualização.")
        else:
            with st.form("gab_form_cadastrar_colaborador"):
                col1, col2 = st.columns(2)

                with col1:
                    nome = st.text_input("Nome completo *", key="gab_add_nome")
                    nome_guerra = st.text_input("Nome curto", key="gab_add_nome_guerra")
                    matricula = st.text_input("Matrícula *", key="gab_add_matricula")
                    setor = st.selectbox("Setor *", options=SETORES_SISTEMA, key="gab_add_setor")

                with col2:
                    cargo = st.selectbox("Cargo *", options=CARGOS_PADRAO, key="gab_add_cargo")
                    vinculo = st.selectbox("Vínculo *", options=VINCULOS_PADRAO, key="gab_add_vinculo")
                    nivel_acesso = st.selectbox("Nível de acesso *", options=NIVEIS_ACESSO_PADRAO, key="gab_add_nivel")
                    senha = st.text_input("Senha inicial *", key="gab_add_senha")

                ativo = st.checkbox("Cadastrar como ativo", value=True, key="gab_add_ativo")

                submit_add = st.form_submit_button("Cadastrar colaborador", type="primary", use_container_width=True)

                if submit_add:
                    resultado = db_manager.adicionar_membro_equipe(
                        nome=nome,
                        cargo=cargo,
                        setor=setor,
                        vinculo=vinculo,
                        nome_guerra=nome_guerra,
                        matricula=matricula,
                        nivel_acesso=nivel_acesso,
                        senha=senha,
                        ativo=ativo,
                    )

                    if resultado:
                        st.success(f"Colaborador cadastrado: {nome}.")
                        st.rerun()
                    else:
                        st.error("Não foi possível cadastrar o colaborador.")

    with tab_editar:
        st.markdown("#### Editar colaborador")

        if not filtrados:
            st.info("Nenhum colaborador disponível para edição.")
        elif not modo_edicao:
            st.info("Modo visualização.")
        else:
            opcoes = {
                f"{c.get('nome', '')} | {c.get('matricula', '')} | {c.get('setor', '')}": c
                for c in filtrados
            }

            chave_escolhida = st.selectbox(
                "Selecionar colaborador",
                options=list(opcoes.keys()),
                key="gab_edit_colab_select",
            )

            colaborador = opcoes[chave_escolhida]

            with st.form("gab_form_editar_colaborador"):
                col1, col2 = st.columns(2)

                with col1:
                    edit_nome = st.text_input("Nome completo *", value=str(colaborador.get("nome", "") or ""))
                    edit_nome_guerra = st.text_input("Nome curto", value=str(colaborador.get("nome_guerra", "") or ""))
                    edit_matricula = st.text_input("Matrícula *", value=str(colaborador.get("matricula", "") or ""))
                    edit_setor = st.selectbox(
                        "Setor *",
                        options=SETORES_SISTEMA,
                        index=SETORES_SISTEMA.index(str(colaborador.get("setor", "GAB")))
                        if str(colaborador.get("setor", "GAB")) in SETORES_SISTEMA else 0,
                    )

                with col2:
                    edit_cargo = st.selectbox(
                        "Cargo *",
                        options=CARGOS_PADRAO,
                        index=CARGOS_PADRAO.index(str(colaborador.get("cargo", "Assessor")))
                        if str(colaborador.get("cargo", "Assessor")) in CARGOS_PADRAO else 0,
                    )
                    edit_vinculo = st.selectbox(
                        "Vínculo *",
                        options=VINCULOS_PADRAO,
                        index=VINCULOS_PADRAO.index(str(colaborador.get("vinculo", "efetivo")))
                        if str(colaborador.get("vinculo", "efetivo")) in VINCULOS_PADRAO else 0,
                    )
                    edit_nivel = st.selectbox(
                        "Nível de acesso *",
                        options=NIVEIS_ACESSO_PADRAO,
                        index=NIVEIS_ACESSO_PADRAO.index(str(colaborador.get("nivel_acesso", "OPERACIONAL")))
                        if str(colaborador.get("nivel_acesso", "OPERACIONAL")) in NIVEIS_ACESSO_PADRAO else 0,
                    )
                    edit_senha = st.text_input("Senha *", value=str(colaborador.get("senha", "") or ""))

                edit_ativo = st.checkbox("Ativo", value=bool(colaborador.get("ativo", False)))

                submit_edit = st.form_submit_button("Salvar alterações", type="primary", use_container_width=True)

                if submit_edit:
                    payload = {
                        "nome": edit_nome,
                        "nome_guerra": edit_nome_guerra,
                        "matricula": edit_matricula,
                        "setor": edit_setor,
                        "cargo": edit_cargo,
                        "vinculo": edit_vinculo,
                        "nivel_acesso": edit_nivel,
                        "senha": edit_senha,
                        "ativo": edit_ativo,
                    }

                    resultado = db_manager.atualizar_membro_equipe(colaborador.get("id"), payload)

                    if resultado:
                        st.success(f"Colaborador atualizado: {edit_nome}.")
                        st.rerun()
                    else:
                        st.error("Não foi possível atualizar o colaborador.")

    with tab_inativar:
        st.markdown("#### Remover / Inativar colaborador")

        ativos = [c for c in filtrados if bool(c.get("ativo", False))]

        if not ativos:
            st.info("Nenhum colaborador ativo disponível para inativação.")
        elif not modo_edicao:
            st.info("Modo visualização.")
        else:
            opcoes = {
                f"{c.get('nome', '')} | {c.get('matricula', '')} | {c.get('setor', '')}": c
                for c in ativos
            }

            chave_escolhida = st.selectbox(
                "Selecionar colaborador ativo",
                options=list(opcoes.keys()),
                key="gab_remove_colab_select",
            )

            colaborador = opcoes[chave_escolhida]

            st.warning(
                f"Você está prestes a inativar **{colaborador.get('nome', '')}** "
                f"(matrícula **{colaborador.get('matricula', '')}**)."
            )

            confirmar = st.checkbox(
                "Confirmo a inativação deste colaborador",
                key="gab_remove_colab_confirm",
            )

            if st.button(
                "Inativar colaborador",
                type="primary",
                use_container_width=True,
                disabled=not confirmar,
                key="gab_remove_colab_btn",
            ):
                sucesso = db_manager.remover_membro_equipe(colaborador.get("id"))
                if sucesso:
                    st.success(f"Colaborador inativado: {colaborador.get('nome', '')}.")
                    st.rerun()
                else:
                    st.error("Não foi possível inativar o colaborador.")

# ============================================================
# AUSÊNCIAS DO GABINETE
# ============================================================

def _renderizar_ausencias_gab(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Central de análise de férias, atestados e abonos.
    """
    st.markdown("### 🌴 Solicitações de Férias e Afastamentos")

    solicitacoes = _obter_solicitacoes_ausencia()

    if not solicitacoes:
        st.info("Nenhuma solicitação encontrada.")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        filtro_setor = st.selectbox(
            "Setor",
            options=["Todos"] + SETORES_SISTEMA,
            key="gab_aus_setor",
        )

    with col2:
        filtro_status = st.selectbox(
            "Status",
            options=["Todos"] + STATUS_AUSENCIA_PERMITIDOS,
            key="gab_aus_status",
        )

    with col3:
        filtro_tipo = st.selectbox(
            "Tipo",
            options=["Todos"] + TIPOS_AUSENCIA,
            key="gab_aus_tipo",
        )

    filtradas = []
    for s in solicitacoes:
        if filtro_setor != "Todos" and _normalizar_texto(s.get("setor", "")) != _normalizar_texto(filtro_setor):
            continue
        if filtro_status != "Todos" and str(s.get("status", "") or "").strip() != filtro_status:
            continue
        if filtro_tipo != "Todos" and str(s.get("tipo", "") or "").strip() != filtro_tipo:
            continue
        filtradas.append(s)

    st.write(f"**{len(filtradas)} solicitação(ões)** filtrada(s).")

    if PANDAS_OK and filtradas:
        dados = []
        for s in filtradas:
            dados.append(
                {
                    "ID": s.get("id"),
                    "Colaborador": s.get("colaborador_nome", ""),
                    "Setor": s.get("setor", ""),
                    "Tipo": s.get("tipo", ""),
                    "Início": _formatar_data_curta(s.get("data_inicio")),
                    "Fim": _formatar_data_curta(s.get("data_fim")),
                    "Dias": s.get("dias_afastado", "-"),
                    "Status": s.get("status", ""),
                    "Observações": s.get("observacoes", "") or "-",
                }
            )

        df = pd.DataFrame(dados)
        st.dataframe(df, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Analisar solicitação")

    pendentes = [s for s in filtradas if s.get("status") == "PENDENTE"]

    if not pendentes:
        st.info("Nenhuma solicitação pendente nos filtros atuais.")
        return

    if not _tem_permissao_gab(usuario) or not modo_edicao:
        st.warning("A aprovação ou reprovação exige permissão de gestão em modo de edição.")
        return

    opcoes = {
        f"{s.get('colaborador_nome', '')} | {s.get('tipo', '')} | {_formatar_data_curta(s.get('data_inicio'))} a {_formatar_data_curta(s.get('data_fim'))}": s
        for s in pendentes
    }

    chave_escolhida = st.selectbox(
        "Selecionar solicitação pendente",
        options=list(opcoes.keys()),
        key="gab_ausencia_select",
    )

    solicitacao = opcoes[chave_escolhida]

    with st.form("gab_form_analisar_ausencia"):
        decisao = st.selectbox(
            "Decisão",
            options=["APROVADA", "REPROVADA"],
            key="gab_aus_decisao",
        )

        observacao_gestor = st.text_area(
            "Observação da chefia",
            value=str(solicitacao.get("observacoes", "") or ""),
            height=80,
            key="gab_aus_obs_gestor",
        )

        submit = st.form_submit_button("Salvar decisão", type="primary", use_container_width=True)

        if submit:
            payload = {
                "status": decisao,
                "observacoes": observacao_gestor.strip(),
            }

            resultado = db_manager.atualizar("solicitacoes_ausencia", int(solicitacao["id"]), payload)

            if resultado:
                st.success("Solicitação atualizada com sucesso.")
                st.rerun()
            else:
                st.error("Não foi possível atualizar a solicitação.")

# ============================================================
# AVISOS
# ============================================================

def _renderizar_avisos(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Gestão de avisos internos.
    """
    st.markdown("### 📢 Avisos")

    avisos = _obter_avisos()

    if modo_edicao and _tem_permissao_gab(usuario):
        with st.form("gab_form_aviso"):
            titulo = st.text_input("Título *", key="gab_aviso_titulo")
            mensagem = st.text_area("Mensagem *", height=100, key="gab_aviso_mensagem")
            setor = st.selectbox("Setor", options=["TODOS"] + SETORES_SISTEMA, key="gab_aviso_setor")
            submit = st.form_submit_button("Publicar aviso", type="primary", use_container_width=True)

            if submit:
                if not titulo.strip() or not mensagem.strip():
                    st.error("Título e mensagem são obrigatórios.")
                else:
                    payload = {
                        "titulo": titulo.strip(),
                        "mensagem": mensagem.strip(),
                        "setor": setor,
                        "ativo": True,
                    }
                    resultado = db_manager.inserir("avisos", payload)
                    if resultado:
                        st.success("Aviso publicado.")
                        st.rerun()
                    else:
                        st.error("Não foi possível publicar o aviso.")

        st.markdown("---")

    if not avisos:
        st.info("Nenhum aviso cadastrado.")
        return

    for aviso in avisos:
        if not bool(aviso.get("ativo", True)):
            continue

        with st.expander(f"{aviso.get('titulo', 'Aviso')} | {_formatar_data_hora(aviso.get('created_at'))}"):
            st.write(aviso.get("mensagem", ""))
            st.caption(f"Setor: {aviso.get('setor', 'TODOS')}")

            if modo_edicao and _tem_permissao_gab(usuario):
                if st.button("Desativar aviso", key=f"gab_aviso_off_{aviso.get('id')}"):
                    db_manager.atualizar("avisos", int(aviso["id"]), {"ativo": False})
                    st.rerun()

# ============================================================
# REGRAS DO MOTOR NIP
# ============================================================

def _renderizar_regras_nip(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Gestão de regras do Motor NIP.
    """
    st.markdown("### ⚙️ Regras do Motor NIP")

    tab_subs, tab_urg, tab_sercon = st.tabs(
        ["Substituições", "Palavras de Urgência", "Palavras de SERCON"]
    )

    with tab_subs:
        regras = _obter_regras_nip_por_tabela("regras_substituicao_nip")

        if PANDAS_OK and regras:
            dados = []
            for r in regras:
                dados.append(
                    {
                        "ID": r.get("id"),
                        "Procurar": r.get("procurar", "") or r.get("palavra_original", "") or "",
                        "Substituir por": r.get("substituir_por", "") or r.get("palavra_substituta", "") or "",
                        "Ativo": _bool_label(r.get("ativo", True)),
                    }
                )
            df = pd.DataFrame(dados)
            st.dataframe(df, hide_index=True, use_container_width=True)

        if modo_edicao and _tem_permissao_gab(usuario):
            with st.form("gab_form_regra_substituicao"):
                procurar = st.text_input("Procurar *", key="gab_regra_proc")
                substituir = st.text_input("Substituir por *", key="gab_regra_sub")
                submit = st.form_submit_button("Adicionar regra", type="primary", use_container_width=True)

                if submit:
                    if not procurar.strip() or not substituir.strip():
                        st.error("Preencha ambos os campos.")
                    else:
                        resultado = db_manager.inserir(
                            "regras_substituicao_nip",
                            {
                                "procurar": procurar.strip(),
                                "substituir_por": substituir.strip(),
                                "ativo": True,
                            },
                        )
                        if resultado:
                            st.success("Regra adicionada.")
                            st.rerun()
                        else:
                            st.error("Não foi possível adicionar a regra.")

    with tab_urg:
        regras = _obter_regras_nip_por_tabela("palavras_urgencia_nip")

        if PANDAS_OK and regras:
            df = pd.DataFrame(
                [{"ID": r.get("id"), "Palavra": r.get("palavra", ""), "Ativo": _bool_label(r.get("ativo", True))} for r in regras]
            )
            st.dataframe(df, hide_index=True, use_container_width=True)

        if modo_edicao and _tem_permissao_gab(usuario):
            with st.form("gab_form_palavra_urgente"):
                palavra = st.text_input("Nova palavra de urgência *", key="gab_palavra_urg")
                submit = st.form_submit_button("Adicionar palavra", type="primary", use_container_width=True)

                if submit:
                    if not palavra.strip():
                        st.error("Informe a palavra.")
                    else:
                        resultado = db_manager.inserir(
                            "palavras_urgencia_nip",
                            {"palavra": palavra.strip(), "ativo": True},
                        )
                        if resultado:
                            st.success("Palavra adicionada.")
                            st.rerun()
                        else:
                            st.error("Não foi possível adicionar a palavra.")

    with tab_sercon:
        regras = _obter_regras_nip_por_tabela("palavras_sercon_nip")

        if PANDAS_OK and regras:
            df = pd.DataFrame(
                [
                    {
                        "ID": r.get("id"),
                        "Palavra": r.get("palavra", ""),
                        "Situação": r.get("situacao", ""),
                        "Ativo": _bool_label(r.get("ativo", True)),
                    }
                    for r in regras
                ]
            )
            st.dataframe(df, hide_index=True, use_container_width=True)

        if modo_edicao and _tem_permissao_gab(usuario):
            with st.form("gab_form_palavra_sercon"):
                palavra = st.text_input("Nova palavra de SERCON *", key="gab_palavra_sercon")
                situacao = st.text_input("Situação associada *", key="gab_palavra_sercon_sit")
                submit = st.form_submit_button("Adicionar regra", type="primary", use_container_width=True)

                if submit:
                    if not palavra.strip() or not situacao.strip():
                        st.error("Informe a palavra e a situação.")
                    else:
                        resultado = db_manager.inserir(
                            "palavras_sercon_nip",
                            {
                                "palavra": palavra.strip(),
                                "situacao": situacao.strip(),
                                "ativo": True,
                            },
                        )
                        if resultado:
                            st.success("Regra adicionada.")
                            st.rerun()
                        else:
                            st.error("Não foi possível adicionar a regra.")

# ============================================================
# ESCALA DO PLENÁRIO
# ============================================================

def _obter_escala_plenario() -> List[Dict[str, Any]]:
    """
    Retorna os registros da escala do plenário.
    """
    try:
        return db_manager.buscar_todos(
            "escala_plenario",
            ordem_coluna="data_sessao",
            ordem_desc=False,
        ) or []
    except Exception as e:
        print(f"[GAB ERROR] _obter_escala_plenario: {e}")
        return []

def _renderizar_escala_plenario(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Gestão da escala do plenário.
    """
    st.markdown("### 🏛️ Escala do Plenário")
    st.caption("Controle de escalas e designações para sessões plenárias.")

    escalas = _obter_escala_plenario()

    if PANDAS_OK and escalas:
        dados = []
        for item in escalas:
            dados.append(
                {
                    "ID": item.get("id"),
                    "Data da Sessão": _formatar_data_curta(item.get("data_sessao")),
                    "Turno": item.get("turno", "") or "-",
                    "Responsável": item.get("responsavel", "") or "-",
                    "Apoio": item.get("apoio", "") or "-",
                    "Observações": item.get("observacoes", "") or "-",
                }
            )

        df = pd.DataFrame(dados)
        st.dataframe(df, hide_index=True, use_container_width=True)
    elif not escalas:
        st.info("Nenhuma escala de plenário cadastrada.")

    if not modo_edicao or not _tem_permissao_gab(usuario):
        return

    st.markdown("---")
    st.markdown("#### Cadastrar escala")

    colaboradores = _obter_colaboradores(incluir_inativos=False, incluir_contas_tecnicas=False)
    nomes = sorted(
        list(
            set(
                [
                    c.get("nome_exibicao") or c.get("nome_guerra") or c.get("nome")
                    for c in colaboradores
                    if c.get("nome_exibicao") or c.get("nome_guerra") or c.get("nome")
                ]
            )
        ),
        key=_normalizar_texto,
    )

    with st.form("gab_form_escala_plenario"):
        col1, col2 = st.columns(2)

        with col1:
            data_sessao = st.date_input("Data da sessão *", value=date.today(), key="gab_escala_data")
            turno = st.selectbox("Turno *", options=["Manhã", "Tarde", "Integral"], key="gab_escala_turno")

        with col2:
            responsavel = st.selectbox("Responsável *", options=nomes if nomes else ["Sem colaboradores"], key="gab_escala_responsavel")
            apoio = st.selectbox("Apoio", options=[""] + nomes if nomes else [""], key="gab_escala_apoio")

        observacoes = st.text_area("Observações", height=70, key="gab_escala_obs")

        submit = st.form_submit_button("Salvar escala", type="primary", use_container_width=True)

        if submit:
            if not nomes:
                st.error("Não há colaboradores ativos disponíveis.")
            else:
                resultado = db_manager.inserir(
                    "escala_plenario",
                    {
                        "data_sessao": data_sessao.isoformat(),
                        "turno": turno,
                        "responsavel": responsavel,
                        "apoio": apoio.strip() if apoio else "",
                        "observacoes": observacoes.strip(),
                    },
                )
                if resultado:
                    st.success("Escala cadastrada com sucesso.")
                    st.rerun()
                else:
                    st.error("Não foi possível salvar a escala.")

# ============================================================
# AGENDA DO SECRETÁRIO
# ============================================================

def _obter_agenda_secretario() -> List[Dict[str, Any]]:
    """
    Retorna os compromissos da agenda do secretário.
    """
    try:
        return db_manager.buscar_todos(
            "agenda_secretario",
            ordem_coluna="data_compromisso",
            ordem_desc=False,
        ) or []
    except Exception as e:
        print(f"[GAB ERROR] _obter_agenda_secretario: {e}")
        return []

def _renderizar_agenda_secretario(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Gestão da agenda do secretário.
    """
    st.markdown("### 🗓️ Agenda do Secretário")
    st.caption("Compromissos, reuniões e lembretes institucionais.")

    agenda = _obter_agenda_secretario()

    futuras = []
    passadas = []

    hoje = date.today()

    for item in agenda:
        data_item = str(item.get("data_compromisso", "") or "")[:10]
        try:
            data_obj = date.fromisoformat(data_item)
        except Exception:
            data_obj = None

        if data_obj and data_obj >= hoje:
            futuras.append(item)
        else:
            passadas.append(item)

    st.markdown("#### Próximos compromissos")

    if futuras:
        for item in futuras:
            with st.expander(
                f"{_formatar_data_curta(item.get('data_compromisso'))} | {item.get('titulo', 'Compromisso')}"
            ):
                st.write(f"**Horário:** {item.get('horario', '-') or '-'}")
                st.write(f"**Local:** {item.get('local', '-') or '-'}")
                st.write(f"**Descrição:** {item.get('descricao', '-') or '-'}")
    else:
        st.info("Nenhum compromisso futuro cadastrado.")

    if not modo_edicao or not _tem_permissao_gab(usuario):
        return

    st.markdown("---")
    st.markdown("#### Novo compromisso")

    with st.form("gab_form_agenda_secretario"):
        col1, col2 = st.columns(2)

        with col1:
            titulo = st.text_input("Título *", key="gab_agenda_titulo")
            data_compromisso = st.date_input("Data *", value=date.today(), key="gab_agenda_data")

        with col2:
            horario = st.text_input("Horário", placeholder="Ex: 14:30", key="gab_agenda_horario")
            local = st.text_input("Local", key="gab_agenda_local")

        descricao = st.text_area("Descrição", height=80, key="gab_agenda_descricao")

        submit = st.form_submit_button("Salvar compromisso", type="primary", use_container_width=True)

        if submit:
            if not titulo.strip():
                st.error("O título é obrigatório.")
            else:
                resultado = db_manager.inserir(
                    "agenda_secretario",
                    {
                        "titulo": titulo.strip(),
                        "data_compromisso": data_compromisso.isoformat(),
                        "horario": horario.strip(),
                        "local": local.strip(),
                        "descricao": descricao.strip(),
                    },
                )
                if resultado:
                    st.success("Compromisso salvo.")
                    st.rerun()
                else:
                    st.error("Não foi possível salvar o compromisso.")

# ============================================================
# AUDITORIA
# ============================================================

def _obter_auditoria() -> List[Dict[str, Any]]:
    """
    Retorna registros de auditoria da chefia.
    """
    try:
        return db_manager.buscar_todos(
            "auditoria_chefia",
            ordem_coluna="created_at",
            ordem_desc=True,
        ) or []
    except Exception as e:
        print(f"[GAB ERROR] _obter_auditoria: {e}")
        return []

def _renderizar_auditoria(usuario: Dict[str, Any], modo_edicao: bool):
    """
    Visualização dos registros de auditoria.
    """
    st.markdown("### 🔎 Auditoria")
    st.caption("Rastreabilidade de ações administrativas e operacionais registradas no sistema.")

    registros = _obter_auditoria()

    if not registros:
        st.info("Nenhum registro de auditoria encontrado.")
        return

    col1, col2 = st.columns(2)

    with col1:
        filtro_usuario = st.text_input(
            "Filtrar por usuário",
            placeholder="Digite o nome...",
            key="gab_audit_usuario",
        )

    with col2:
        filtro_acao = st.text_input(
            "Filtrar por ação",
            placeholder="Digite a ação...",
            key="gab_audit_acao",
        )

    filtrados = []
    for r in registros:
        usuario_ok = True
        acao_ok = True

        if filtro_usuario.strip():
            usuario_ok = filtro_usuario.strip().lower() in str(r.get("usuario", "") or "").lower()

        if filtro_acao.strip():
            acao_ok = filtro_acao.strip().lower() in str(r.get("acao", "") or "").lower()

        if usuario_ok and acao_ok:
            filtrados.append(r)

    if PANDAS_OK and filtrados:
        dados = []
        for r in filtrados:
            dados.append(
                {
                    "Data/Hora": _formatar_data_hora(r.get("created_at")),
                    "Usuário": r.get("usuario", "") or "-",
                    "Ação": r.get("acao", "") or "-",
                    "Detalhes": r.get("detalhes", "") or "-",
                }
            )

        df = pd.DataFrame(dados)
        st.dataframe(df, hide_index=True, use_container_width=True)
    elif filtrados:
        for r in filtrados:
            with st.expander(f"{_formatar_data_hora(r.get('created_at'))} | {r.get('usuario', '-') or '-'}"):
                st.write(f"**Ação:** {r.get('acao', '-') or '-'}")
                st.write(f"**Detalhes:** {r.get('detalhes', '-') or '-'}")
    else:
        st.info("Nenhum registro encontrado com os filtros atuais.")

# ============================================================
# SIDEBAR DO GABINETE
# ============================================================

def _renderizar_sidebar_gab(usuario: Dict[str, Any]):
    """
    Indicadores rápidos na barra lateral.
    """
    colaboradores = _obter_colaboradores(incluir_inativos=False, incluir_contas_tecnicas=True)
    solicitacoes = _obter_solicitacoes_ausencia()
    pauta_seat = _obter_processos_pauta_seat()
    pauta_sexp = _obter_processos_sexp()

    total_ativos = len([c for c in colaboradores if c.get("ativo", False)])
    ausencias_pendentes = len([s for s in solicitacoes if s.get("status") == "PENDENTE"])
    seat_pendentes = len([p for p in pauta_seat if p.get("status") != "encaminhado"])
    sexp_pendentes = len([p for p in pauta_sexp if not p.get("distribuido", False)])

    with st.sidebar:
        st.markdown("---")
        st.markdown("#### Painel do Gabinete")
        st.write(f"**Ativos:** {total_ativos}")
        st.write(f"**SEAT pendentes:** {seat_pendentes}")
        st.write(f"**SEXP pendentes:** {sexp_pendentes}")
        st.write(f"**Ausências pendentes:** {ausencias_pendentes}")

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def renderizar(usuario: Dict[str, Any], modo_edicao: bool = False):
    """
    Função principal do módulo GAB.
    """
    nome = usuario.get("nome", "Usuário")
    cargo = usuario.get("cargo", "operacional")
    setor = usuario.get("setor", "GAB")

    st.markdown(f"**Colaborador:** {nome} | **Cargo:** {cargo} | **Setor:** {setor}")

    if not _tem_permissao_gab(usuario):
        st.warning("Seu perfil não possui permissão de gestão do Gabinete.")
        return

    if not modo_edicao:
        st.info("Você está em modo de visualização. Operações de edição estão bloqueadas.")

    st.markdown("---")

    _renderizar_sidebar_gab(usuario)

    tab_dashboard, tab_setores, tab_colaboradores, tab_ausencias, tab_avisos, tab_regras, tab_plenario, tab_agenda, tab_auditoria, tab_gerenciar = st.tabs(
        [
            "Dashboard Geral",
            "Setores",
            "👥 Colaboradores",
            "Férias e Afastamentos",
            "Avisos",
            "Regras Motor NIP",
            "Escala do Plenário",
            "Agenda do Secretário",
            "Auditoria",
            "🗑️ Gerenciar Dados",
        ]
    )

    with tab_dashboard:
        _renderizar_dashboard_geral(usuario, modo_edicao)

    with tab_setores:
        _renderizar_setores(usuario, modo_edicao)

    with tab_colaboradores:
        _renderizar_colaboradores(usuario, modo_edicao)

    with tab_ausencias:
        _renderizar_ausencias_gab(usuario, modo_edicao)

    with tab_avisos:
        _renderizar_avisos(usuario, modo_edicao)

    with tab_regras:
        _renderizar_regras_nip(usuario, modo_edicao)

    with tab_plenario:
        _renderizar_escala_plenario(usuario, modo_edicao)

    with tab_agenda:
        _renderizar_agenda_secretario(usuario, modo_edicao)

    with tab_auditoria:
        _renderizar_auditoria(usuario, modo_edicao)

    with tab_gerenciar:
        _renderizar_gerenciar_dados(usuario, "GAB")
