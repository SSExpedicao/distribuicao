"""
db_manager.py
Gerenciador de Banco de Dados do Hub SS - Secretaria das Sessoes - TCDF

Arquitetura:
- Python
- Streamlit
- Supabase (PostgreSQL)

Funcao:
- Centralizar toda a comunicacao com o banco
- Nenhum modulo cria conexao propria
- Toda leitura e escrita passa por aqui

Principios:
- Singleton: uma conexao por execucao
- Error handling: falhas retornam None, False ou []
- Type hints: clareza e manutencao
- Fonte unica de verdade para pessoas: usuarios_acesso
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import date
import os
import random
import string
import streamlit as st

# ============================================================
# IMPORTS CONDICIONAIS
# ============================================================

try:
    from pypdf import PdfReader
    PDF_OK = True
except ImportError:
    try:
        from PyPDF2 import PdfReader
        PDF_OK = True
    except ImportError:
        PDF_OK = False

try:
    import docx
    DOCX_OK = True
except ImportError:
    DOCX_OK = False

# ============================================================
# CREDENCIAIS
# ============================================================

def _carregar_credenciais() -> Tuple[str, str]:
    """
    Carrega credenciais do Supabase na ordem:
    1. Streamlit secrets
    2. Variaveis de ambiente

    Raises:
        RuntimeError: se as credenciais nao estiverem configuradas.
    """
    try:
        url = str(st.secrets["supabase"]["url"]).strip()
        key = str(st.secrets["supabase"]["key"]).strip()
        if url and key:
            return url, key
    except Exception:
        pass

    url_env = str(os.environ.get("SUPABASE_URL", "")).strip()
    key_env = str(os.environ.get("SUPABASE_KEY", "")).strip()

    if url_env and key_env:
        return url_env, key_env

    raise RuntimeError(
        "Credenciais do Supabase nao encontradas em st.secrets nem em variaveis de ambiente."
    )

# ============================================================
# CONEXAO SINGLETON
# ============================================================

_cliente: Optional[Any] = None

def get_supabase():
    """
    Retorna a instancia singleton do cliente Supabase.
    """
    global _cliente

    if _cliente is not None:
        return _cliente

    try:
        from supabase import create_client

        url, key = _carregar_credenciais()
        _cliente = create_client(url, key)
        return _cliente
    except ImportError:
        print("[DB FATAL] Biblioteca 'supabase' nao instalada. Execute: pip install supabase")
        return None
    except Exception as e:
        print(f"[DB FATAL] Erro ao conectar com Supabase: {e}")
        return None

def reiniciar_conexao() -> None:
    """
    Forca a recriacao da conexao na proxima chamada.
    """
    global _cliente
    _cliente = None

# ============================================================
# TABELAS CONHECIDAS
# ============================================================

TABELAS_SISTEMA = [
    "usuarios_acesso",
    "afastamentos",
    "auditoria_chefia",
    "avisos",
    "avisos_gab",
    "config_doe",
    "configuracoes",
    "despachos_ds",
    "distribuicao_sexp",
    "duplas_doe",
    "escala_publicacao",
    "escala_plenario",
    "ferias_colaboradores",
    "ferias_sexp",
    "oficios",
    "oficios_ds",
    "palavras_sercon_nip",
    "palavras_urgencia_nip",
    "pauta_quarta",
    "pauta_seat",
    "pauta_semand",
    "pauta_sercon",
    "pauta_sexp",
    "processos",
    "processos_excluidos",
    "processos_sercon",
    "processos_urgentes",
    "regras_palavras_chave",
    "regras_substituicao_nip",
    "solicitacoes_ausencia",
    "agenda_secretario",
]

def verificar_tabelas() -> Dict[str, bool]:
    """
    Verifica quais tabelas do sistema existem no banco.
    """
    cliente = get_supabase()
    if not cliente:
        return {tabela: False for tabela in TABELAS_SISTEMA}

    resultado: Dict[str, bool] = {}

    for tabela in TABELAS_SISTEMA:
        try:
            cliente.table(tabela).select("id").limit(1).execute()
            resultado[tabela] = True
        except Exception:
            resultado[tabela] = False

    return resultado

# ============================================================
# HELPERS INTERNOS
# ============================================================

def _invalidar_cache() -> None:
    """
    Limpa o cache de dados do Streamlit apos alteracoes.
    """
    st.cache_data.clear()

def _normalizar_texto_canonico(valor: Any) -> str:
    """
    Normaliza texto para comparacao segura.
    Remove acentos, converte para minusculas e elimina espacos extras.
    """
    import unicodedata

    if valor is None:
        return ""

    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return " ".join(texto.split())

def _eh_conta_tecnica(cargo: Any, nivel_acesso: Any) -> bool:
    """
    Determina se o usuario deve ser tratado como conta tecnica.
    """
    cargo_norm = _normalizar_texto_canonico(cargo)
    nivel_norm = _normalizar_texto_canonico(nivel_acesso)

    return (
        nivel_norm == "super_admin_criador"
        or cargo_norm == "desenvolvedor"
    )

def _resolver_nivel_acesso_padrao(cargo: str, setor: str) -> str:
    """
    Resolve um nivel de acesso padrao quando ele nao vier informado.
    """
    cargo_norm = _normalizar_texto_canonico(cargo)
    setor_norm = _normalizar_texto_canonico(setor)

    if cargo_norm == "desenvolvedor":
        return "SUPER_ADMIN_CRIADOR"

    if "gerente" in cargo_norm or "chefe" in cargo_norm:
        return "GESTOR_SETORIAL"

    if setor_norm == "gab" and (
        "secretari" in cargo_norm
        or "subsecretari" in cargo_norm
        or "gabinete" in cargo_norm
    ):
        return "ADMIN_GABINETE"

    return "OPERACIONAL"

def _buscar_usuario_acesso_por_identificador(identificador: Any) -> Optional[Dict[str, Any]]:
    """
    Busca um usuario de usuarios_acesso por id ou matricula.
    """
    cliente = get_supabase()
    if not cliente:
        return None

    identificador_str = str(identificador or "").strip()
    if not identificador_str:
        return None

    try:
        if identificador_str.isdigit():
            resp_id = (
                cliente.table("usuarios_acesso")
                .select("*")
                .eq("id", int(identificador_str))
                .limit(1)
                .execute()
            )
            dados_id = resp_id.data or []
            if dados_id:
                return dados_id[0]

        resp_matricula = (
            cliente.table("usuarios_acesso")
            .select("*")
            .eq("matricula", identificador_str)
            .limit(1)
            .execute()
        )
        dados_matricula = resp_matricula.data or []
        if dados_matricula:
            return dados_matricula[0]

        return None
    except Exception as e:
        print(f"[DB ERROR] _buscar_usuario_acesso_por_identificador: {e}")
        return None

def _contas_tecnicas_ativas_excluindo(identificador_excluido: Any) -> List[Dict[str, Any]]:
    """
    Retorna contas tecnicas ativas, excluindo um id especifico.
    """
    usuarios = listar_usuarios_acesso_canonicos(
        incluir_contas_tecnicas=True,
        apenas_ativos=True,
    ) or []

    resultado = []
    for usuario in usuarios:
        if not usuario.get("conta_tecnica", False):
            continue
        if str(usuario.get("id")) == str(identificador_excluido):
            continue
        resultado.append(usuario)

    return resultado

# ============================================================
# CRUD GENERICO
# ============================================================

def inserir(tabela: str, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Insere um registro na tabela.
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = cliente.table(tabela).insert(dados).execute()
        if resp.data:
            _invalidar_cache()
            return resp.data[0]
        return None
    except Exception as e:
        print(f"[DB ERROR] inserir({tabela}): {e}")
        return None

@st.cache_data(ttl=30, show_spinner=False)
def buscar_todos(
    tabela: str,
    filtros: Optional[Dict[str, Any]] = None,
    ordem_coluna: Optional[str] = None,
    ordem_desc: bool = False,
    limite: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Busca registros da tabela, com filtros e ordenacao opcionais.
    """
    cliente = get_supabase()
    if not cliente:
        return []

    try:
        query = cliente.table(tabela).select("*")

        if filtros:
            for coluna, valor in filtros.items():
                query = query.eq(coluna, valor)

        if ordem_coluna:
            query = query.order(ordem_coluna, desc=ordem_desc)

        if limite:
            query = query.limit(limite)

        resp = query.execute()
        return resp.data if resp.data else []
    except Exception as e:
        print(f"[DB ERROR] buscar_todos({tabela}): {e}")
        return []

def buscar_por_id(tabela: str, id_registro: int) -> Optional[Dict[str, Any]]:
    """
    Busca um registro pelo id.
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = cliente.table(tabela).select("*").eq("id", id_registro).limit(1).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"[DB ERROR] buscar_por_id({tabela}, {id_registro}): {e}")
        return None

def atualizar(tabela: str, id_registro: int, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Atualiza um registro pelo id.
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = cliente.table(tabela).update(dados).eq("id", id_registro).execute()
        if resp.data:
            _invalidar_cache()
            return resp.data[0]
        return None
    except Exception as e:
        print(f"[DB ERROR] atualizar({tabela}, {id_registro}): {e}")
        return None

def deletar(tabela: str, id_registro: int) -> bool:
    """
    Deleta um registro pelo id.
    """
    cliente = get_supabase()
    if not cliente:
        return False

    try:
        cliente.table(tabela).delete().eq("id", id_registro).execute()
        _invalidar_cache()
        return True
    except Exception as e:
        print(f"[DB ERROR] deletar({tabela}, {id_registro}): {e}")
        return False

@st.cache_data(ttl=30, show_spinner=False)
def buscar_todos_paginado(
    tabela: str,
    pagina: int = 1,
    por_pagina: int = 50,
    filtros: Optional[Dict[str, Any]] = None,
    ordem_coluna: Optional[str] = None,
    ordem_desc: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Busca registros paginados usando range do Supabase.
    """
    cliente = get_supabase()
    if not cliente:
        return [], 0

    try:
        offset_inicio = (pagina - 1) * por_pagina
        offset_fim = offset_inicio + por_pagina - 1

        query = cliente.table(tabela).select("*", count="exact")

        if filtros:
            for coluna, valor in filtros.items():
                query = query.eq(coluna, valor)

        if ordem_coluna:
            query = query.order(ordem_coluna, desc=ordem_desc)

        query = query.range(offset_inicio, offset_fim)
        resp = query.execute()

        dados = resp.data if resp.data else []
        total = resp.count if hasattr(resp, "count") and resp.count is not None else len(dados)

        return dados, total
    except Exception as e:
        print(f"[DB ERROR] buscar_todos_paginado({tabela}): {e}")
        return [], 0

# ============================================================
# AUTENTICACAO E GESTAO DE USUARIOS
# ============================================================

def gerar_senha_aleatoria() -> str:
    """
    Gera senha no formato tcdf.ssXXXX.
    """
    digitos = "".join(random.choices(string.digits, k=4))
    return f"tcdf.ss{digitos}"

def validar_senha(senha: str) -> bool:
    """
    Valida formatos legados aceitos pelo sistema.

    Aceita:
    - tcdf.ssXXXX
    - tcdf.XXXX...
    """
    senha = str(senha or "").strip()
    if not senha:
        return False

    if senha.startswith("tcdf.ss"):
        sufixo = senha[7:]
        return len(sufixo) == 4 and sufixo.isdigit()

    if senha.startswith("tcdf.") and len(senha) >= 8:
        return True

    return False

def autenticar_usuario(matricula: str, senha: str) -> Optional[Dict[str, Any]]:
    """
    Autentica um usuario por matricula e senha.
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = (
            cliente.table("usuarios_acesso")
            .select("*")
            .eq("matricula", str(matricula).strip())
            .eq("senha", str(senha).strip())
            .eq("ativo", True)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"[DB ERROR] autenticar_usuario: {e}")
        return None

def alterar_senha(matricula: str, senha_nova: str) -> bool:
    """
    Altera a senha de um usuario.
    """
    if not validar_senha(senha_nova):
        return False

    cliente = get_supabase()
    if not cliente:
        return False

    try:
        resp = (
            cliente.table("usuarios_acesso")
            .update({"senha": str(senha_nova).strip()})
            .eq("matricula", str(matricula).strip())
            .execute()
        )
        if resp.data:
            _invalidar_cache()
            return True
        return False
    except Exception as e:
        print(f"[DB ERROR] alterar_senha: {e}")
        return False

def semear_usuarios_iniciais() -> bool:
    """
    Cria usuarios iniciais somente se a tabela estiver vazia.
    """
    cliente = get_supabase()
    if not cliente:
        return False

    try:
        resp = cliente.table("usuarios_acesso").select("id").limit(1).execute()
        if resp.data:
            return True

        usuarios = [
            {
                "matricula": "0001",
                "nome": "Criador Desenvolvedor",
                "nome_guerra": "Desenvolvedor",
                "senha": "tcdf.2026",
                "cargo": "Desenvolvedor",
                "setor": "GAB",
                "vinculo": "efetivo",
                "ativo": True,
                "nivel_acesso": "SUPER_ADMIN_CRIADOR",
            },
            {
                "matricula": "1918",
                "nome": "Juan Mauricio Del Carpio Peredo",
                "nome_guerra": "Juan",
                "senha": "tcdf.2026",
                "cargo": "Assessor",
                "setor": "GAB",
                "vinculo": "efetivo",
                "ativo": True,
                "nivel_acesso": "OPERACIONAL",
            },
            {
                "matricula": "3001",
                "nome": "Chefe SEAT",
                "nome_guerra": "Chefe SEAT",
                "senha": "tcdf.2026",
                "cargo": "Gerente",
                "setor": "SEAT",
                "vinculo": "efetivo",
                "ativo": True,
                "nivel_acesso": "GESTOR_SETORIAL",
            },
            {
                "matricula": "3002",
                "nome": "Chefe SEXP",
                "nome_guerra": "Chefe SEXP",
                "senha": "tcdf.2026",
                "cargo": "Gerente",
                "setor": "SEXP",
                "vinculo": "efetivo",
                "ativo": True,
                "nivel_acesso": "GESTOR_SETORIAL",
            },
            {
                "matricula": "4001",
                "nome": "Assessor SEAT",
                "nome_guerra": "Assessor SEAT",
                "senha": "tcdf.2026",
                "cargo": "Assessor",
                "setor": "SEAT",
                "vinculo": "efetivo",
                "ativo": True,
                "nivel_acesso": "OPERACIONAL",
            },
            {
                "matricula": "4002",
                "nome": "Assessor SEXP",
                "nome_guerra": "Assessor SEXP",
                "senha": "tcdf.2026",
                "cargo": "Assessor",
                "setor": "SEXP",
                "vinculo": "efetivo",
                "ativo": True,
                "nivel_acesso": "OPERACIONAL",
            },
            {
                "matricula": "4003",
                "nome": "Estagiario SEXP",
                "nome_guerra": "Estagiario SEXP",
                "senha": "tcdf.2026",
                "cargo": "Estagiario",
                "setor": "SEXP",
                "vinculo": "estagiario",
                "ativo": True,
                "nivel_acesso": "OPERACIONAL",
            },
        ]

        resp_insert = cliente.table("usuarios_acesso").insert(usuarios).execute()
        if resp_insert.data:
            _invalidar_cache()
            return True
        return False
    except Exception as e:
        print(f"[DB ERROR] semear_usuarios_iniciais: {e}")
        return False

# ============================================================
# CAMADA CANONICA DE USUARIOS
# ============================================================

def listar_usuarios_acesso_canonicos(
    setor: Optional[str] = None,
    apenas_ativos: bool = True,
    incluir_contas_tecnicas: bool = False,
    niveis_acesso: Optional[List[str]] = None,
    cargos: Optional[List[str]] = None,
    vinculos: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Retorna usuarios de usuarios_acesso ja normalizados para consumo pelos modulos.
    """
    try:
        usuarios = buscar_todos("usuarios_acesso") or []
    except Exception as e:
        print(f"[DB ERROR] listar_usuarios_acesso_canonicos: {e}")
        return []

    setor_normalizado = _normalizar_texto_canonico(setor) if setor else ""
    niveis_permitidos = {
        _normalizar_texto_canonico(valor)
        for valor in (niveis_acesso or [])
        if valor
    }
    cargos_permitidos = {
        _normalizar_texto_canonico(valor)
        for valor in (cargos or [])
        if valor
    }
    vinculos_permitidos = {
        _normalizar_texto_canonico(valor)
        for valor in (vinculos or [])
        if valor
    }

    resultado: List[Dict[str, Any]] = []

    for usuario in usuarios:
        ativo = bool(usuario.get("ativo", False))
        nome = str(usuario.get("nome", "") or "").strip()
        nome_guerra = str(usuario.get("nome_guerra", "") or "").strip()
        matricula = str(usuario.get("matricula", "") or "").strip()
        setor_usuario = str(usuario.get("setor", "") or "").strip()
        cargo_usuario = str(usuario.get("cargo", "") or "").strip()
        vinculo_usuario = str(usuario.get("vinculo", "") or "").strip()
        nivel_acesso_usuario = str(usuario.get("nivel_acesso", "") or "").strip()

        nome_normalizado = _normalizar_texto_canonico(nome)
        nome_guerra_normalizado = _normalizar_texto_canonico(nome_guerra)
        setor_usuario_normalizado = _normalizar_texto_canonico(setor_usuario)
        cargo_usuario_normalizado = _normalizar_texto_canonico(cargo_usuario)
        vinculo_usuario_normalizado = _normalizar_texto_canonico(vinculo_usuario)
        nivel_acesso_normalizado = _normalizar_texto_canonico(nivel_acesso_usuario)

        nome_exibicao = nome_guerra if nome_guerra else nome
        conta_tecnica = _eh_conta_tecnica(cargo_usuario, nivel_acesso_usuario)

        if apenas_ativos and not ativo:
            continue

        if not incluir_contas_tecnicas and conta_tecnica:
            continue

        if setor_normalizado and setor_usuario_normalizado != setor_normalizado:
            continue

        if niveis_permitidos and nivel_acesso_normalizado not in niveis_permitidos:
            continue

        if cargos_permitidos and cargo_usuario_normalizado not in cargos_permitidos:
            continue

        if vinculos_permitidos and vinculo_usuario_normalizado not in vinculos_permitidos:
            continue

        registro = dict(usuario)
        registro["matricula"] = matricula
        registro["nome"] = nome
        registro["nome_guerra"] = nome_guerra
        registro["nome_exibicao"] = nome_exibicao
        registro["nome_normalizado"] = nome_normalizado
        registro["nome_guerra_normalizado"] = nome_guerra_normalizado
        registro["setor_normalizado"] = setor_usuario_normalizado
        registro["cargo_normalizado"] = cargo_usuario_normalizado
        registro["vinculo_normalizado"] = vinculo_usuario_normalizado
        registro["nivel_acesso_normalizado"] = nivel_acesso_normalizado
        registro["conta_tecnica"] = conta_tecnica

        resultado.append(registro)

    resultado.sort(
        key=lambda item: (
            _normalizar_texto_canonico(item.get("nome_exibicao", "")),
            _normalizar_texto_canonico(item.get("matricula", "")),
        )
    )

    return resultado

def listar_colaboradores_elegiveis_distribuicao(
    setor: str,
    tipo_sessao: Optional[str] = None,
    incluir_contas_tecnicas: bool = False,
) -> List[Dict[str, Any]]:
    """
    Retorna os colaboradores elegiveis para sorteio automatico por setor e tipo de sessao.
    """
    try:
        setor_norm = _normalizar_texto_canonico(setor)
        tipo_sessao_norm = _normalizar_texto_canonico(tipo_sessao) if tipo_sessao else ""

        colaboradores = listar_usuarios_acesso_canonicos(
            setor=setor,
            apenas_ativos=True,
            incluir_contas_tecnicas=incluir_contas_tecnicas,
        ) or []

        elegiveis: List[Dict[str, Any]] = []

        for colaborador in colaboradores:
            nome_norm = str(colaborador.get("nome_normalizado", "") or "").strip()
            nome_guerra_norm = str(colaborador.get("nome_guerra_normalizado", "") or "").strip()
            cargo_norm = str(colaborador.get("cargo_normalizado", "") or "").strip()
            vinculo_norm = str(colaborador.get("vinculo_normalizado", "") or "").strip()
            nivel_norm = str(colaborador.get("nivel_acesso_normalizado", "") or "").strip()
            setor_colab_norm = str(colaborador.get("setor_normalizado", "") or "").strip()

            if setor_colab_norm != setor_norm:
                continue

            if colaborador.get("conta_tecnica", False) and not incluir_contas_tecnicas:
                continue

            is_gerente = (
                nivel_norm == "gestor_setorial"
                or "gerente" in cargo_norm
                or "chefe" in cargo_norm
            )
            is_assessor = "assessor" in cargo_norm
            is_estagiario = "estagi" in cargo_norm or "estagi" in vinculo_norm

            is_matheus_seat = (
                nome_norm == "matheus guimaraes de sousa coelho"
                or nome_guerra_norm == "matheus"
            )
            is_luis_felipe_seat = (
                nome_norm == "luis felipe coelho medina"
                or nome_guerra_norm == "luis felipe"
                or nome_guerra_norm == "luis"
            )
            is_thais_seat = (
                nome_norm == "thais"
                or nome_norm.startswith("thais ")
                or nome_guerra_norm == "thais"
            )

            if setor_norm == "seat":
                if is_luis_felipe_seat:
                    continue

                if is_thais_seat:
                    continue

                if is_matheus_seat:
                    elegiveis.append(colaborador)
                    continue

                if is_assessor and not is_gerente and not is_estagiario:
                    elegiveis.append(colaborador)
                    continue

                continue

            if setor_norm == "sexp":
                if "administrativa" in tipo_sessao_norm:
                    if is_gerente:
                        elegiveis.append(colaborador)
                    continue

                if "reservada" in tipo_sessao_norm:
                    if is_assessor and not is_gerente:
                        elegiveis.append(colaborador)
                    continue

                if (
                    "ordinaria" in tipo_sessao_norm
                    or "virtual" in tipo_sessao_norm
                    or "urgente" in tipo_sessao_norm
                ):
                    if not is_gerente and (is_assessor or is_estagiario):
                        elegiveis.append(colaborador)
                    continue

                if not is_gerente and (is_assessor or is_estagiario):
                    elegiveis.append(colaborador)
                continue

            if not is_gerente:
                elegiveis.append(colaborador)

        elegiveis.sort(
            key=lambda item: (
                _normalizar_texto_canonico(item.get("nome_exibicao", "")),
                _normalizar_texto_canonico(item.get("matricula", "")),
            )
        )

        return elegiveis
    except Exception as e:
        print(f"[DB ERROR] listar_colaboradores_elegiveis_distribuicao: {e}")
        return []

# ============================================================
# OPERACOES ESPECIFICAS: EQUIPE
# ============================================================

def listar_equipe(
    setor: Optional[str] = None,
    incluir_inativos: bool = False,
    incluir_contas_tecnicas: bool = False,
    niveis_acesso: Optional[List[str]] = None,
    cargos: Optional[List[str]] = None,
    vinculos: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Lista colaboradores a partir da camada canônica de usuarios_acesso.
    """
    try:
        colaboradores = listar_usuarios_acesso_canonicos(
            setor=setor,
            apenas_ativos=not incluir_inativos,
            incluir_contas_tecnicas=incluir_contas_tecnicas,
            niveis_acesso=niveis_acesso,
            cargos=cargos,
            vinculos=vinculos,
        ) or []

        resultado: List[Dict[str, Any]] = []

        for colaborador in colaboradores:
            nome = str(colaborador.get("nome", "") or "").strip()
            matricula = str(colaborador.get("matricula", "") or "").strip()
            setor_colaborador = str(colaborador.get("setor", "") or "").strip()

            if not nome or not matricula or not setor_colaborador:
                continue

            resultado.append(colaborador)

        resultado.sort(
            key=lambda item: (
                _normalizar_texto_canonico(item.get("setor", "")),
                _normalizar_texto_canonico(item.get("nome_exibicao", "")),
                _normalizar_texto_canonico(item.get("matricula", "")),
            )
        )

        return resultado
    except Exception as e:
        print(f"[DB ERROR] listar_equipe: {e}")
        return []

def adicionar_membro_equipe(
    nome: str,
    cargo: str,
    setor: str,
    vinculo: str = "servidor",
    nome_guerra: str = "",
    matricula: Optional[str] = None,
    nivel_acesso: Optional[str] = None,
    senha: Optional[str] = None,
    ativo: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Cadastra ou reativa um colaborador em usuarios_acesso.

    Compatibilidade:
    - preserva nome da funcao original
    - aceita os parametros antigos
    - aceita parametros novos via nomeado
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        nome = str(nome or "").strip()
        cargo = str(cargo or "").strip()
        setor = str(setor or "").strip()
        vinculo = str(vinculo or "").strip()
        nome_guerra = str(nome_guerra or "").strip()
        matricula = str(matricula or "").strip()
        nivel_acesso = str(nivel_acesso or "").strip()
        senha = str(senha or "").strip()

        if not nome:
            print("[DB ERROR] adicionar_membro_equipe: nome obrigatorio")
            return None

        if not cargo:
            print("[DB ERROR] adicionar_membro_equipe: cargo obrigatorio")
            return None

        if not setor:
            print("[DB ERROR] adicionar_membro_equipe: setor obrigatorio")
            return None

        if not vinculo:
            print("[DB ERROR] adicionar_membro_equipe: vinculo obrigatorio")
            return None

        if not matricula:
            print("[DB ERROR] adicionar_membro_equipe: matricula obrigatoria")
            return None

        if not nome_guerra:
            nome_guerra = nome.split()[0] if nome.split() else nome

        if not nivel_acesso:
            nivel_acesso = _resolver_nivel_acesso_padrao(cargo, setor)

        if not senha:
            senha = gerar_senha_aleatoria()

        if not validar_senha(senha):
            print("[DB ERROR] adicionar_membro_equipe: senha invalida")
            return None

        resp_existente = (
            cliente.table("usuarios_acesso")
            .select("*")
            .eq("matricula", matricula)
            .limit(1)
            .execute()
        )
        existentes = resp_existente.data or []

        payload = {
            "nome": nome,
            "matricula": matricula,
            "setor": setor,
            "cargo": cargo,
            "vinculo": vinculo,
            "nivel_acesso": nivel_acesso,
            "senha": senha,
            "nome_guerra": nome_guerra,
            "ativo": bool(ativo),
        }

        if existentes:
            registro_existente = existentes[0]
            registro_id = registro_existente.get("id")
            if not registro_id:
                print("[DB ERROR] adicionar_membro_equipe: registro existente sem id")
                return None

            if bool(registro_existente.get("ativo", False)):
                print(f"[DB ERROR] adicionar_membro_equipe: matricula ja ativa -> {matricula}")
                return None

            resp_update = (
                cliente.table("usuarios_acesso")
                .update(payload)
                .eq("id", registro_id)
                .execute()
            )

            if resp_update.data:
                _invalidar_cache()
                return resp_update.data[0]
            return None

        resp_insert = cliente.table("usuarios_acesso").insert(payload).execute()
        if resp_insert.data:
            _invalidar_cache()
            return resp_insert.data[0]

        return None
    except Exception as e:
        print(f"[DB ERROR] adicionar_membro_equipe: {e}")
        return None

def atualizar_membro_equipe(
    id_membro: Any,
    dados: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Atualiza um colaborador de usuarios_acesso.

    Compatibilidade:
    - preserva a assinatura antiga: (id_membro, dados)
    - aceita localizar por id ou matricula
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        registro_existente = _buscar_usuario_acesso_por_identificador(id_membro)
        if not registro_existente:
            print("[DB ERROR] atualizar_membro_equipe: colaborador nao encontrado")
            return None

        registro_id = registro_existente.get("id")
        if not registro_id:
            print("[DB ERROR] atualizar_membro_equipe: registro sem id")
            return None

        dados = dados or {}

        nome_final = str(dados.get("nome", registro_existente.get("nome", "")) or "").strip()
        setor_final = str(dados.get("setor", registro_existente.get("setor", "")) or "").strip()
        cargo_final = str(dados.get("cargo", registro_existente.get("cargo", "")) or "").strip()
        vinculo_final = str(dados.get("vinculo", registro_existente.get("vinculo", "")) or "").strip()
        matricula_final = str(dados.get("matricula", registro_existente.get("matricula", "")) or "").strip()
        nome_guerra_recebido = dados.get("nome_guerra", registro_existente.get("nome_guerra", ""))
        nome_guerra_final = str(nome_guerra_recebido or "").strip()
        senha_final = str(dados.get("senha", registro_existente.get("senha", "")) or "").strip()
        ativo_final = bool(dados.get("ativo", registro_existente.get("ativo", False)))

        nivel_recebido = str(dados.get("nivel_acesso", registro_existente.get("nivel_acesso", "")) or "").strip()
        nivel_final = nivel_recebido or _resolver_nivel_acesso_padrao(cargo_final, setor_final)

        if not nome_final or not setor_final or not cargo_final or not vinculo_final or not matricula_final:
            print("[DB ERROR] atualizar_membro_equipe: campos obrigatorios ausentes")
            return None

        if not nome_guerra_final:
            nome_guerra_final = nome_final.split()[0] if nome_final.split() else nome_final

        if not senha_final or not validar_senha(senha_final):
            print("[DB ERROR] atualizar_membro_equipe: senha invalida")
            return None

        matricula_atual = str(registro_existente.get("matricula", "") or "").strip()
        if matricula_final != matricula_atual:
            resp_colisao = (
                cliente.table("usuarios_acesso")
                .select("id")
                .eq("matricula", matricula_final)
                .limit(1)
                .execute()
            )
            colisoes = resp_colisao.data or []
            if colisoes and colisoes[0].get("id") != registro_id:
                print("[DB ERROR] atualizar_membro_equipe: colisao de matricula")
                return None

        conta_tecnica_atual = _eh_conta_tecnica(
            registro_existente.get("cargo", ""),
            registro_existente.get("nivel_acesso", ""),
        )
        conta_tecnica_final = _eh_conta_tecnica(cargo_final, nivel_final)

        if conta_tecnica_atual and (not ativo_final or not conta_tecnica_final):
            outras_tecnicas = _contas_tecnicas_ativas_excluindo(registro_id)
            if not outras_tecnicas:
                print("[DB ERROR] atualizar_membro_equipe: ultima conta tecnica ativa nao pode ser removida/descaracterizada")
                return None

        payload = {
            "nome": nome_final,
            "setor": setor_final,
            "cargo": cargo_final,
            "vinculo": vinculo_final,
            "matricula": matricula_final,
            "nome_guerra": nome_guerra_final,
            "senha": senha_final,
            "nivel_acesso": nivel_final,
            "ativo": ativo_final,
        }

        resp_update = (
            cliente.table("usuarios_acesso")
            .update(payload)
            .eq("id", registro_id)
            .execute()
        )

        if resp_update.data:
            _invalidar_cache()
            return resp_update.data[0]

        return None
    except Exception as e:
        print(f"[DB ERROR] atualizar_membro_equipe: {e}")
        return None

def remover_membro_equipe(id_membro: Any) -> bool:
    """
    Inativa um colaborador de forma segura.
    """
    cliente = get_supabase()
    if not cliente:
        return False

    try:
        registro = _buscar_usuario_acesso_por_identificador(id_membro)
        if not registro:
            print("[DB ERROR] remover_membro_equipe: colaborador nao encontrado")
            return False

        registro_id = registro.get("id")
        if not registro_id:
            print("[DB ERROR] remover_membro_equipe: registro sem id")
            return False

        if not bool(registro.get("ativo", False)):
            return True

        if _eh_conta_tecnica(registro.get("cargo", ""), registro.get("nivel_acesso", "")):
            outras_tecnicas = _contas_tecnicas_ativas_excluindo(registro_id)
            if not outras_tecnicas:
                print("[DB ERROR] remover_membro_equipe: ultima conta tecnica ativa nao pode ser inativada")
                return False

        resp_update = (
            cliente.table("usuarios_acesso")
            .update({"ativo": False})
            .eq("id", registro_id)
            .execute()
        )

        if resp_update.data:
            _invalidar_cache()
            return True

        return False
    except Exception as e:
        print(f"[DB ERROR] remover_membro_equipe: {e}")
        return False

# ============================================================
# OPERACOES ESPECIFICAS: AFASTAMENTOS
# ============================================================

def listar_afastamentos(apenas_ativos: bool = True) -> List[Dict[str, Any]]:
    """
    Lista afastamentos cadastrados.
    """
    filtros = {}
    if apenas_ativos:
        filtros["ativo"] = True
    return buscar_todos("afastamentos", filtros=filtros, ordem_coluna="data_inicio", ordem_desc=True)

def adicionar_afastamento(
    nome: str,
    tipo: str,
    data_inicio: str,
    data_fim: str,
    motivo: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Adiciona um afastamento.
    """
    return inserir(
        "afastamentos",
        {
            "nome": nome,
            "tipo": tipo,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "motivo": motivo,
            "ativo": True,
        },
    )

def remover_afastamento(id_afastamento: int) -> bool:
    """
    Inativa um afastamento.
    """
    return atualizar("afastamentos", id_afastamento, {"ativo": False}) is not None

def verificar_afastado(nome: str, data_verificacao: Optional[str] = None) -> bool:
    """
    Verifica se um membro esta afastado em uma data especifica.
    """
    if data_verificacao is None:
        data_verificacao = date.today().isoformat()

    afastamentos = listar_afastamentos(apenas_ativos=True)

    for afast in afastamentos:
        if afast.get("nome", "").strip().lower() != str(nome).strip().lower():
            continue

        inicio = str(afast.get("data_inicio", ""))
        fim = str(afast.get("data_fim", ""))

        if inicio <= data_verificacao <= fim:
            return True

    return False

def listar_nomes_afastados() -> List[str]:
    """
    Retorna lista de nomes atualmente afastados.
    """
    hoje = date.today().isoformat()
    afastamentos = listar_afastamentos(apenas_ativos=True)
    nomes: List[str] = []

    for afast in afastamentos:
        inicio = str(afast.get("data_inicio", ""))
        fim = str(afast.get("data_fim", ""))

        if inicio <= hoje <= fim:
            nome = afast.get("nome", "").strip()
            if nome:
                nomes.append(nome)

    return nomes

# ============================================================
# OPERACOES ESPECIFICAS: REGRAS DE PALAVRAS-CHAVE
# ============================================================

def listar_regras_palavras_chave(apenas_ativas: bool = True) -> List[Dict[str, Any]]:
    """
    Lista regras de palavras-chave do Motor NIP.
    """
    filtros = {}
    if apenas_ativas:
        filtros["ativo"] = True
    return buscar_todos("regras_palavras_chave", filtros=filtros, ordem_coluna="palavra_original")

def adicionar_regra_palavra_chave(
    palavra_original: str,
    palavra_substituta: str,
    tipo: str = "substituicao",
) -> Optional[Dict[str, Any]]:
    """
    Adiciona uma regra de substituicao.
    """
    return inserir(
        "regras_palavras_chave",
        {
            "palavra_original": str(palavra_original).lower().strip(),
            "palavra_substituta": str(palavra_substituta).lower().strip(),
            "tipo": tipo,
            "ativo": True,
        },
    )

def atualizar_regra_palavra_chave(id_regra: int, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Atualiza uma regra de palavra-chave.
    """
    return atualizar("regras_palavras_chave", id_regra, dados)

def remover_regra_palavra_chave(id_regra: int) -> bool:
    """
    Inativa uma regra de palavra-chave.
    """
    return atualizar("regras_palavras_chave", id_regra, {"ativo": False}) is not None

def semear_regras_padrao() -> bool:
    """
    Cria regras padrao se a tabela estiver vazia.
    """
    cliente = get_supabase()
    if not cliente:
        return False

    try:
        resp = cliente.table("regras_palavras_chave").select("id").limit(1).execute()
        if resp.data:
            return True

        regras = [
            {"palavra_original": "conheca", "palavra_substituta": "conhecer", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "determine", "palavra_substituta": "determinar", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "autorize", "palavra_substituta": "autorizar", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "defira", "palavra_substituta": "deferir", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "indefira", "palavra_substituta": "indeferir", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "exija", "palavra_substituta": "exigir", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "notifique", "palavra_substituta": "notificar", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "intime", "palavra_substituta": "intimar", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "encaminhe", "palavra_substituta": "encaminhar", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "remeta", "palavra_substituta": "remitir", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "arquive", "palavra_substituta": "arquivar", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "conceda", "palavra_substituta": "conceder", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "negue", "palavra_substituta": "negar", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "reconheca", "palavra_substituta": "reconhecer", "tipo": "substituicao", "ativo": True},
            {"palavra_original": "julgue", "palavra_substituta": "julgar", "tipo": "substituicao", "ativo": True},
        ]

        resp_insert = cliente.table("regras_palavras_chave").insert(regras).execute()
        if resp_insert.data:
            _invalidar_cache()
            return True

        return False
    except Exception as e:
        print(f"[DB ERROR] semear_regras_padrao: {e}")
        return False

# ============================================================
# EXTRACAO DE TEXTO DE ARQUIVOS
# ============================================================

def extrair_texto_pdf(arquivo) -> str:
    """
    Extrai texto de um arquivo PDF.
    """
    if not PDF_OK:
        print("[PDF] Biblioteca nao instalada. Execute: pip install pypdf")
        return ""

    try:
        reader = PdfReader(arquivo)
        texto = ""

        for pagina in reader.pages:
            texto += pagina.extract_text() + "\n"

        return texto.strip()
    except Exception as e:
        print(f"[PDF ERROR] extrair_texto_pdf: {e}")
        return ""

def extrair_texto_docx(arquivo) -> str:
    """
    Extrai texto de um arquivo DOCX.
    """
    if not DOCX_OK:
        print("[DOCX] Biblioteca nao instalada. Execute: pip install python-docx")
        return ""

    try:
        doc = docx.Document(arquivo)
        texto = "\n".join([paragrafo.text for paragrafo in doc.paragraphs])
        return texto.strip()
    except Exception as e:
        print(f"[DOCX ERROR] extrair_texto_docx: {e}")
        return ""

def extrair_texto(arquivo) -> str:
    """
    Extrai texto de arquivo PDF, DOCX ou TXT.
    """
    if arquivo is None:
        return ""

    nome = getattr(arquivo, "name", "").lower()
    tipo = getattr(arquivo, "type", "").lower()

    if nome.endswith(".pdf") or "pdf" in tipo:
        return extrair_texto_pdf(arquivo)

    if nome.endswith(".docx") or "word" in tipo:
        return extrair_texto_docx(arquivo)

    try:
        if hasattr(arquivo, "read"):
            conteudo = arquivo.read()
            if isinstance(conteudo, bytes):
                return conteudo.decode("utf-8", errors="ignore")
            return conteudo

        return str(arquivo)
    except Exception as e:
        print(f"[TXT ERROR] extrair_texto: {e}")
        return ""
