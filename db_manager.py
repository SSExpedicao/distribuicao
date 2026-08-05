"""
db_manager.py
Gerenciador de Banco de Dados do Hub SS - Secretaria das Sessoes - TCDF

Arquitetura: Python + Streamlit + Supabase (PostgreSQL)
Funcao: Centralizar TODA comunicacao com o banco Supabase.
        Nenhum modulo do sistema cria sua propria conexao; todos passam por aqui.

Principios:
- Singleton: uma conexao por execucao
- Error handling: toda operacao retorna resultado ou None, nunca quebra a app
- Type hints: para clareza e manutencao
- Zero acoplamento com UI: nao importa Streamlit, so conhece banco
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import date
import os
import random
import string
import streamlit as st # ADICIONADO: Necessario para usar o motor de cache do Streamlit

# ============================================================
# IMPORTS CONDICIONAIS (Extracao de texto de arquivos)
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
# CONFIGURACAO DE CREDENCIAIS
# ============================================================

_FALLBACK_URL = "https://bporhwdxwsuqnezkyhmn.supabase.co"
_FALLBACK_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJwb3Jod2R4d3N1cW5lemt5aG1uIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTk4Njc3MCwiZXhwIjoyMDk1NTYyNzcwfQ.kJNF9PkhQsBcr5Ecloifo3aGrCrXNn5cWT_5Q2smA-c"

def _carregar_credenciais() -> Tuple[str, str]:
    """
    Carrega credenciais do Supabase na ordem:
    1. Streamlit Secrets (producao)
    2. Variaveis de ambiente (desenvolvimento local)
    3. Valores hardcoded (fallback)
    """
    try:
        import streamlit as st
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return url, key
    except (ImportError, KeyError, FileNotFoundError):
        pass

    url_env = os.environ.get("SUPABASE_URL")
    key_env = os.environ.get("SUPABASE_KEY")
    if url_env and key_env:
        return url_env, key_env

    return _FALLBACK_URL, _FALLBACK_KEY

# ============================================================
# GERENCIAMENTO DE CONEXAO (SINGLETON)
# ============================================================

_cliente: Optional[Any] = None

def get_supabase():
    """
    Retorna a instancia do cliente Supabase (padrao Singleton).
    Cria a conexao na primeira chamada e reutiliza nas subsequentes.
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

def reiniciar_conexao():
    """Forca a recriacao da conexao na proxima chamada."""
    global _cliente
    _cliente = None

# ============================================================
# VERIFICACAO DE ESTRUTURA
# ============================================================

TABELAS_SISTEMA = [
    "usuarios_acesso",
    "afastamentos",
    "auditoria_chefia",
    "avisos",
    "config_doe",
    "configuracoes",
    "despachos_ds",
    "distribuicao_sexp",
    "duplas_doe",
    "escala_publicacao",
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
]

def verificar_tabelas() -> Dict[str, bool]:
    """Verifica quais tabelas do sistema existem no banco."""
    cliente = get_supabase()
    if not cliente:
        return {t: False for t in TABELAS_SISTEMA}

    resultado = {}
    for tabela in TABELAS_SISTEMA:
        try:
            cliente.table(tabela).select("id").limit(1).execute()
            resultado[tabela] = True
        except Exception:
            resultado[tabela] = False

    return resultado

# ============================================================
# OPERACOES CRUD GENERICAS
# ============================================================

def _invalidar_cache():
    """Limpa a memoria do Streamlit garantindo dados frescos apos modificacoes."""
    st.cache_data.clear()

def inserir(tabela: str, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insere um registro na tabela especificada."""
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = cliente.table(tabela).insert(dados).execute()
        if resp.data:
            _invalidar_cache() # ATUALIZACAO: Limpa cache ao inserir
            return resp.data[0]
        return None
    except Exception as e:
        print(f"[DB ERROR] inserir({tabela}): {e}")
        return None

# ATUALIZACAO: Aplicado o escudo de cache para otimizar milhoes de requisicoes
@st.cache_data(ttl=30, show_spinner=False)
def buscar_todos(
    tabela: str,
    filtros: Optional[Dict[str, Any]] = None,
    ordem_coluna: Optional[str] = None,
    ordem_desc: bool = False,
    limite: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Busca registros da tabela, com filtros e ordenacao opcionais."""
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
    """Busca um registro especifico pelo ID."""
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = cliente.table(tabela).select("*").eq("id", id_registro).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"[DB ERROR] buscar_por_id({tabela}, {id_registro}): {e}")
        return None

def atualizar(tabela: str, id_registro: int, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Atualiza um registro pelo ID."""
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = cliente.table(tabela).update(dados).eq("id", id_registro).execute()
        if resp.data:
            _invalidar_cache() # ATUALIZACAO: Limpa cache ao modificar
            return resp.data[0]
        return None
    except Exception as e:
        print(f"[DB ERROR] atualizar({tabela}, {id_registro}): {e}")
        return None

def deletar(tabela: str, id_registro: int) -> bool:
    """Deleta um registro pelo ID."""
    cliente = get_supabase()
    if not cliente:
        return False
    try:
        cliente.table(tabela).delete().eq("id", id_registro).execute()
        _invalidar_cache() # ATUALIZACAO: Limpa cache ao deletar
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao deletar de {tabela}: {e}")
        return False

# ATUALIZACAO: Aplicado o escudo de cache tambem na paginacao
@st.cache_data(ttl=30, show_spinner=False)
def buscar_todos_paginado(
    tabela: str,
    pagina: int = 1,
    por_pagina: int = 50,
    filtros: Optional[Dict[str, Any]] = None,
    ordem_coluna: Optional[str] = None,
    ordem_desc: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """Busca registros com paginacao (usando range do Supabase)."""
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
    Gera senha no formato tcdf.ssXXXX onde XXXX sao 4 digitos aleatorios.
    Usada ao criar novos usuarios.
    """
    digitos = ''.join(random.choices(string.digits, k=4))
    return f"tcdf.ss{digitos}"

def validar_senha(senha: str) -> bool:
    """
    Valida se a senha segue o formato tcdf.ssXXXX.
    - Deve comecar com 'tcdf.ss'
    - Deve ter exatamente 4 digitos apos a raiz
    """
    if not senha or not senha.startswith("tcdf.ss"):
        return False
    sufixo = senha[7:]  # remove "tcdf.ss"
    return len(sufixo) == 4 and sufixo.isdigit()

def autenticar_usuario(matricula: str, senha: str) -> Optional[Dict[str, Any]]:
    """
    Autentica um usuario pela matricula e senha.

    Returns:
        Dados do usuario se autenticado, None caso contrario
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = (
            cliente.table("usuarios_acesso")
            .select("*")
            .eq("matricula", matricula.strip())
            .eq("senha", senha.strip())
            .eq("ativo", True)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"[DB ERROR] autenticar_usuario: {e}")
        return None

def alterar_senha(matricula: str, senha_nova: str) -> bool:
    """
    Altera a senha de um usuario.
    A senha deve seguir o formato tcdf.ssXXXX.

    Returns:
        True se alterada com sucesso, False caso contrario
    """
    if not validar_senha(senha_nova):
        return False

    cliente = get_supabase()
    if not cliente:
        return False

    try:
        resp = (
            cliente.table("usuarios_acesso")
            .update({"senha": senha_nova})
            .eq("matricula", matricula)
            .execute()
        )
        return bool(resp.data)
    except Exception as e:
        print(f"[DB ERROR] alterar_senha: {e}")
        return False

def semear_usuarios_iniciais() -> bool:
    """
    Cria usuarios iniciais se a tabela estiver vazia.
    Inclui os 5 niveis de RBAC.

    Returns:
        True se executou com sucesso, False se falhou
    """
    cliente = get_supabase()
    if not cliente:
        return False

    try:
        resp = cliente.table("usuarios_acesso").select("id").limit(1).execute()
        if resp.data:
            return True

        usuarios = [
            # Criador
            {"matricula": "1918", "nome": "Juan Mauricio Del Carpio Peredo", "senha": "tcdf.ss2025", "cargo": "criador", "setor": "GAB", "vinculo": "servidor", "ativo": True},

            # Raiz
            {"matricula": "1001", "nome": "Secretario", "senha": "tcdf.ss2025", "cargo": "raiz", "setor": "GAB", "vinculo": "servidor", "ativo": True},
            {"matricula": "1002", "nome": "Subsecretario", "senha": "tcdf.ss2025", "cargo": "raiz", "setor": "GAB", "vinculo": "servidor", "ativo": True},
            {"matricula": "1003", "nome": "Assessor Especial", "senha": "tcdf.ss2025", "cargo": "raiz", "setor": "GAB", "vinculo": "servidor", "ativo": True},

            # Secretaria
            {"matricula": "2001", "nome": "Secretaria 1", "senha": "tcdf.ss2025", "cargo": "secretaria", "setor": "GAB", "vinculo": "servidor", "ativo": True},
            {"matricula": "2002", "nome": "Secretaria 2", "senha": "tcdf.ss2025", "cargo": "secretaria", "setor": "GAB", "vinculo": "servidor", "ativo": True},

            # Gerentes
            {"matricula": "3001", "nome": "Chefe SEAT", "senha": "tcdf.ss2025", "cargo": "gerente", "setor": "SEAT", "vinculo": "servidor", "ativo": True},
            {"matricula": "3002", "nome": "Chefe SEXP", "senha": "tcdf.ss2025", "cargo": "gerente", "setor": "SEXP", "vinculo": "servidor", "ativo": True},
            {"matricula": "3003", "nome": "Chefe SERCON", "senha": "tcdf.ss2025", "cargo": "gerente", "setor": "SERCON", "vinculo": "servidor", "ativo": True},
            {"matricula": "3004", "nome": "Chefe SEMAND", "senha": "tcdf.ss2025", "cargo": "gerente", "setor": "SEMAND", "vinculo": "servidor", "ativo": True},

            # Operacionais
            {"matricula": "4001", "nome": "Assessor SEAT", "senha": "tcdf.ss2025", "cargo": "operacional", "setor": "SEAT", "vinculo": "servidor", "ativo": True},
            {"matricula": "4002", "nome": "Assessor SEXP", "senha": "tcdf.ss2025", "cargo": "operacional", "setor": "SEXP", "vinculo": "servidor", "ativo": True},
            {"matricula": "4003", "nome": "Estagiario SEAT", "senha": "tcdf.ss2025", "cargo": "operacional", "setor": "SEAT", "vinculo": "estagiario", "ativo": True},
            {"matricula": "4004", "nome": "Terceirizado SEAT", "senha": "tcdf.ss2025", "cargo": "operacional", "setor": "SEAT", "vinculo": "terceirizado", "ativo": True},
        ]

        resp = cliente.table("usuarios_acesso").insert(usuarios).execute()
        return bool(resp.data)
    except Exception as e:
        print(f"[DB ERROR] semear_usuarios_iniciais: {e}")
        return False

def listar_usuarios_acesso_canonicos(
    setor: Optional[str] = None,
    apenas_ativos: bool = True,
    incluir_contas_tecnicas: bool = False,
    niveis_acesso: Optional[List[str]] = None,
    cargos: Optional[List[str]] = None,
    vinculos: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Retorna usuários da tabela usuarios_acesso já normalizados e prontos
    para consumo operacional pelos módulos do sistema.

    Esta função é a nova camada canônica de leitura de colaboradores.
    Ela NÃO decide, sozinha, elegibilidade final de distribuição por setor
    e tipo de sessão. Ela entrega a base saneada para que SEAT, SEXP e GAB
    apliquem suas regras específicas sem ler usuarios_acesso de forma crua.

    Args:
        setor: Filtra usuários por setor, com normalização textual.
        apenas_ativos: Quando True, retorna apenas registros com ativo=True.
        incluir_contas_tecnicas: Quando False, exclui contas técnicas, como
            SUPER_ADMIN_CRIADOR e cargo Desenvolvedor.
        niveis_acesso: Lista opcional de níveis de acesso permitidos.
        cargos: Lista opcional de cargos permitidos.
        vinculos: Lista opcional de vínculos permitidos.

    Returns:
        Lista de dicionários contendo os dados originais do usuário e campos
        derivados de normalização para uso seguro nos módulos.

    Raises:
        Não levanta exceções para a camada superior. Em caso de falha,
        retorna lista vazia e registra o erro no log.
    """
    import unicodedata

def listar_colaboradores_elegiveis_distribuicao(
    setor: str,
    tipo_sessao: Optional[str] = None,
    incluir_contas_tecnicas: bool = False,
) -> List[Dict[str, Any]]:
    """
    Retorna os colaboradores elegíveis para o sorteio automático de distribuição,
    com base na tabela canônica usuarios_acesso e nas regras operacionais reais
    de cada setor.

    Esta função decide apenas quem entra no sorteio automático.
    Ela NÃO trata:
    - edição manual posterior da distribuição pela chefia
    - redistribuição manual
    - inclusão manual de exceções após o sorteio

    Regras implementadas:

    SEAT:
    - entram automaticamente assessores da SEAT
    - entra automaticamente Matheus Guimarães De Sousa Coelho
    - ficam fora automaticamente Luis Felipe Coelho Medina, Thaís,
      demais gerentes, estagiários e contas técnicas

    SEXP:
    - Sessão Ordinária, Sessão Ordinária Virtual e Urgentes:
      entram assessores e estagiários, gerente fica fora
    - Sessão Reservada:
      entram apenas assessores
    - Sessão Administrativa:
      entra apenas o gerente

    Args:
        setor: Setor da distribuição, por exemplo "SEAT" ou "SEXP".
        tipo_sessao: Tipo da sessão, obrigatório para aplicar regras da SEXP.
        incluir_contas_tecnicas: Quando False, exclui contas técnicas do sorteio.

    Returns:
        Lista de usuários já normalizados e elegíveis para o sorteio automático.

    Raises:
        Não propaga exceções para a camada superior. Em caso de erro, retorna [].
    """
    import unicodedata

def _normalizar_texto_canonico(valor: Any) -> str:
    """
    Normaliza texto para comparação segura no backend.
    Remove acentos, converte para minúsculas e elimina espaços extras.
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

def listar_usuarios_acesso_canonicos(
    setor: Optional[str] = None,
    apenas_ativos: bool = True,
    incluir_contas_tecnicas: bool = False,
    niveis_acesso: Optional[List[str]] = None,
    cargos: Optional[List[str]] = None,
    vinculos: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Retorna usuários da tabela usuarios_acesso já normalizados e prontos
    para consumo operacional pelos módulos do sistema.

    Esta função é a camada canônica de leitura de colaboradores.
    Ela não decide, sozinha, elegibilidade final de distribuição por setor
    e tipo de sessão. Ela entrega a base saneada para que SEAT, SEXP e GAB
    apliquem suas regras específicas sem ler usuarios_acesso de forma crua.

    Args:
        setor: Filtra usuários por setor, com normalização textual.
        apenas_ativos: Quando True, retorna apenas registros com ativo=True.
        incluir_contas_tecnicas: Quando False, exclui contas técnicas, como
            SUPER_ADMIN_CRIADOR e cargo Desenvolvedor.
        niveis_acesso: Lista opcional de níveis de acesso permitidos.
        cargos: Lista opcional de cargos permitidos.
        vinculos: Lista opcional de vínculos permitidos.

    Returns:
        Lista de dicionários contendo os dados originais do usuário e campos
        derivados de normalização para uso seguro nos módulos.
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

        conta_tecnica = (
            nivel_acesso_normalizado == "super_admin_criador"
            or cargo_usuario_normalizado == "desenvolvedor"
        )

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
    Retorna os colaboradores elegíveis para o sorteio automático de distribuição,
    com base na tabela canônica usuarios_acesso e nas regras operacionais reais
    de cada setor.

    Esta função decide apenas quem entra no sorteio automático.
    Ela não trata:
    - edição manual posterior da distribuição pela chefia
    - redistribuição manual
    - inclusão manual de exceções após o sorteio

    Regras implementadas:

    SEAT:
    - entram automaticamente assessores da SEAT
    - entra automaticamente Matheus Guimarães De Sousa Coelho
    - ficam fora automaticamente Luis Felipe Coelho Medina, Thaís,
      demais gerentes, estagiários e contas técnicas

    SEXP:
    - Sessão Ordinária, Sessão Ordinária Virtual e Urgentes:
      entram assessores e estagiários, gerente fica fora
    - Sessão Reservada:
      entram apenas assessores
    - Sessão Administrativa:
      entra apenas o gerente

    Args:
        setor: Setor da distribuição, por exemplo "SEAT" ou "SEXP".
        tipo_sessao: Tipo da sessão, obrigatório para aplicar regras da SEXP.
        incluir_contas_tecnicas: Quando False, exclui contas técnicas do sorteio.

    Returns:
        Lista de usuários já normalizados e elegíveis para o sorteio automático.
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
            if not isinstance(colaborador, dict):
                continue

            if colaborador.get("conta_tecnica", False) and not incluir_contas_tecnicas:
                continue

            nome_norm = str(colaborador.get("nome_normalizado", "") or "").strip()
            nome_guerra_norm = str(colaborador.get("nome_guerra_normalizado", "") or "").strip()
            cargo_norm = str(colaborador.get("cargo_normalizado", "") or "").strip()
            vinculo_norm = str(colaborador.get("vinculo_normalizado", "") or "").strip()
            nivel_norm = str(colaborador.get("nivel_acesso_normalizado", "") or "").strip()
            setor_colab_norm = str(colaborador.get("setor_normalizado", "") or "").strip()

            if setor_colab_norm != setor_norm:
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
# OPERACOES ESPECIFICAS: EQUIPE (FONTE ÚNICA: usuarios_acesso)
# ============================================================

def listar_equipe(setor: Optional[str] = None, apenas_ativos: bool = True) -> List[Dict[str, Any]]:
    """Lista membros da equipe lendo da Fonte Única da Verdade (usuarios_acesso)."""
    filtros = {}
    if setor:
        filtros["setor"] = setor
    if apenas_ativos:
        filtros["ativo"] = True

    # Lê de usuarios_acesso e prioriza ordenação pelo nome de guerra
    return buscar_todos("usuarios_acesso", filtros=filtros, ordem_coluna="nome_guerra")

def adicionar_membro_equipe(nome: str, cargo: str, setor: str, vinculo: str = "servidor", nome_guerra: str = "") -> Optional[Dict[str, Any]]:
    """Adiciona um novo colaborador diretamente em usuarios_acesso."""
    matricula_gerada = f"E{random.randint(10000, 99999)}"
    return inserir("usuarios_acesso", {
        "matricula": matricula_gerada,
        "nome": nome,
        "nome_guerra": nome_guerra or nome.split()[0],
        "senha": "tcdf.2026",
        "cargo": cargo,
        "setor": setor,
        "vinculo": vinculo,
        "ativo": True,
    })

def atualizar_membro_equipe(id_membro: int, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Atualiza dados de um colaborador na tabela de acesso."""
    return atualizar("usuarios_acesso", id_membro, dados)

def remover_membro_equipe(id_membro: int) -> bool:
    """Inativa um colaborador no sistema (soft delete)."""
    return atualizar("usuarios_acesso", id_membro, {"ativo": False}) is not None
        
# ============================================================
# OPERACOES ESPECIFICAS: AFASTAMENTOS
# ============================================================

def listar_afastamentos(apenas_ativos: bool = True) -> List[Dict[str, Any]]:
    """Lista afastamentos cadastrados."""
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
    """Adiciona um afastamento."""
    return inserir("afastamentos", {
        "nome": nome,
        "tipo": tipo,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "motivo": motivo,
        "ativo": True,
    })

def remover_afastamento(id_afastamento: int) -> bool:
    """Inativa um afastamento (soft delete)."""
    return atualizar("afastamentos", id_afastamento, {"ativo": False}) is not None

def verificar_afastado(nome: str, data_verificacao: Optional[str] = None) -> bool:
    """
    Verifica se um membro esta afastado em uma data especifica.
    Usado pelo sistema de distribuicao para excluir membros do sorteio.
    """
    if data_verificacao is None:
        data_verificacao = date.today().isoformat()

    afastamentos = listar_afastamentos(apenas_ativos=True)

    for afast in afastamentos:
        if afast.get("nome", "").strip().lower() != nome.strip().lower():
            continue
        inicio = str(afast.get("data_inicio", ""))
        fim = str(afast.get("data_fim", ""))
        if inicio <= data_verificacao <= fim:
            return True

    return False

def listar_nomes_afastados() -> List[str]:
    """
    Retorna lista de nomes de membros atualmente afastados.
    Usado para exclusao automatica no sorteio de distribuicao.
    """
    hoje = date.today().isoformat()
    afastamentos = listar_afastamentos(apenas_ativos=True)

    nomes = []
    for afast in afastamentos:
        inicio = str(afast.get("data_inicio", ""))
        fim = str(afast.get("data_fim", ""))
        if inicio <= hoje <= fim:
            nome = afast.get("nome", "").strip()
            if nome:
                nomes.append(nome)

    return nomes

# ============================================================
# OPERACOES ESPECIFICAS: REGRAS DE PALAVRAS-CHAVE (MOTOR NIP)
# ============================================================

def listar_regras_palavras_chave(apenas_ativas: bool = True) -> List[Dict[str, Any]]:
    """Lista regras de palavras-chave do Motor NIP."""
    filtros = {}
    if apenas_ativas:
        filtros["ativo"] = True

    return buscar_todos("regras_palavras_chave", filtros=filtros, ordem_coluna="palavra_original")

def adicionar_regra_palavra_chave(
    palavra_original: str,
    palavra_substituta: str,
    tipo: str = "substituicao",
) -> Optional[Dict[str, Any]]:
    """Adiciona uma regra de transposicao de verbo ou substituicao."""
    return inserir("regras_palavras_chave", {
        "palavra_original": palavra_original.lower().strip(),
        "palavra_substituta": palavra_substituta.lower().strip(),
        "tipo": tipo,
        "ativo": True,
    })

def atualizar_regra_palavra_chave(id_regra: int, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Atualiza uma regra de palavra-chave."""
    return atualizar("regras_palavras_chave", id_regra, dados)

def remover_regra_palavra_chave(id_regra: int) -> bool:
    """Inativa uma regra de palavra-chave (soft delete)."""
    return atualizar("regras_palavras_chave", id_regra, {"ativo": False}) is not None

def semear_regras_padrao() -> bool:
    """
    Cria regras de transposicao de verbos padrao se a tabela estiver vazia.
    O Motor NIP usa estas regras para transpor subjuntivo -> infinitivo imperativo.
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

        resp = cliente.table("regras_palavras_chave").insert(regras).execute()
        return bool(resp.data)
    except Exception as e:
        print(f"[DB ERROR] semear_regras_padrao: {e}")
        return False

# ============================================================
# EXTRACAO DE TEXTO DE ARQUIVOS
# ============================================================

def extrair_texto_pdf(arquivo) -> str:
    """Extrai texto de um arquivo PDF."""
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
    """Extrai texto de um arquivo DOCX."""
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
    Extrai texto de um arquivo (PDF, DOCX ou TXT).
    Detecta o tipo automaticamente pela extensao ou tipo MIME.
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
