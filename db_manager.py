"""
db_manager.py
Gerenciador de Banco de Dados do Hub SS - Secretaria das Sessões - TCDF

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
# AVISO DE SEGURANCA: As credenciais abaixo sao um fallback para desenvolvimento.
# Em producao, configure no Streamlit Cloud > Settings > Secrets:
#
# [supabase]
# url = "https://bporhwdxwsuqnezkyhmn.supabase.co"
# key = "sua_service_role_key_aqui"
# ============================================================

_FALLBACK_URL = "https://bporhwdxwsuqnezkyhmn.supabase.co"
_FALLBACK_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJwb3Jod2R4d3N1cW5lemt5aG1uIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTk4Njc3MCwiZXhwIjoyMDk1NTYyNzcwfQ.kJNF9PkhQsBcr5Ecloifo3aGrCrXNn5cWT_5Q2smA-c"

def _carregar_credenciais() -> Tuple[str, str]:
    """
    Carrega credenciais do Supabase na ordem:
    1. Streamlit Secrets (producao - recomendado)
    2. Variaveis de ambiente (desenvolvimento local)
    3. Valores hardcoded (fallback - NAO usar em producao)
    """
    # 1. Streamlit Secrets
    try:
        import streamlit as st
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return url, key
    except (ImportError, KeyError, FileNotFoundError):
        pass

    # 2. Variaveis de ambiente
    url_env = os.environ.get("SUPABASE_URL")
    key_env = os.environ.get("SUPABASE_KEY")
    if url_env and key_env:
        return url_env, key_env

    # 3. Fallback hardcoded
    return _FALLBACK_URL, _FALLBACK_KEY

# ============================================================
# GERENCIAMENTO DE CONEXAO (SINGLETON)
# ============================================================

_cliente: Optional[Any] = None

def get_supabase():
    """
    Retorna a instancia do cliente Supabase (padrao Singleton).
    Cria a conexao na primeira chamada e reutiliza nas subsequentes.

    Returns:
        Cliente Supabase conectado, ou None se falhar.
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
    """
    Forca a recriacao da conexao na proxima chamada de get_supabase().
    Util quando algo deu errado e precisa reconectar.
    """
    global _cliente
    _cliente = None

# ============================================================
# VERIFICACAO DE ESTRUTURA
# ============================================================

TABELAS_SISTEMA = [
    "usuarios_acesso",
    "regras_palavras_chave",
    "equipe",
    "afastamentos",
    "pauta_seat",
    "pauta_sexp",
    "pauta_sercon",
    "pauta_semand",
    "pauta_quarta",
    "escala_publicacao",
]

def verificar_tabelas() -> Dict[str, bool]:
    """
    Verifica quais tabelas do sistema existem no banco.
    Tenta um SELECT simples em cada uma.

    Returns:
        Dicionario {nome_tabela: True/False}
    """
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

def inserir(tabela: str, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Insere um registro na tabela especificada.

    Args:
        tabela: Nome da tabela no Supabase
        dados: Dicionario com colunas e valores

    Returns:
        Registro inserido (com ID gerado), ou None se falhar
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = cliente.table(tabela).insert(dados).execute()
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        print(f"[DB ERROR] inserir({tabela}): {e}")
        return None

def buscar_todos(
    tabela: str,
    filtros: Optional[Dict[str, Any]] = None,
    ordem_coluna: Optional[str] = None,
    ordem_desc: bool = False,
    limite: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Busca registros da tabela, com filtros e ordenacao opcionais.

    Args:
        tabela: Nome da tabela
        filtros: Dicionario {coluna: valor} para filtro de igualdade
        ordem_coluna: Coluna para ordenar o resultado
        ordem_desc: True para ordem decrescente
        limite: Numero maximo de registros

    Returns:
        Lista de registros, ou lista vazia se falhar
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
    Busca um registro especifico pelo ID.

    Returns:
        Registro encontrado, ou None
    """
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
    """
    Atualiza um registro pelo ID.

    Returns:
        Registro atualizado, ou None se falhar
    """
    cliente = get_supabase()
    if not cliente:
        return None

    try:
        resp = cliente.table(tabela).update(dados).eq("id", id_registro).execute()
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        print(f"[DB ERROR] atualizar({tabela}, {id_registro}): {e}")
        return None

def deletar(tabela: str, id_registro: int) -> bool:
    """
    Deleta um registro pelo ID (remocao fisica).

    Returns:
        True se deletado, False se falhou
    """
    cliente = get_supabase()
    if not cliente:
        return False

    try:
        resp = cliente.table(tabela).delete().eq("id", id_registro).execute()
        return bool(resp.data)
    except Exception as e:
        print(f"[DB ERROR] deletar({tabela}, {id_registro}): {e}")
        return False

def buscar_todos_paginado(
    tabela: str,
    pagina: int = 1,
    por_pagina: int = 50,
    filtros: Optional[Dict[str, Any]] = None,
    ordem_coluna: Optional[str] = None,
    ordem_desc: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Busca registros com paginacao (usando range do Supabase).

    Args:
        pagina: Numero da pagina (comeca em 1)
        por_pagina: Registros por pagina
        filtros: Dicionario {coluna: valor} para filtrar
        ordem_coluna: Coluna para ordenar
        ordem_desc: True para ordem decrescente

    Returns:
        Tupla (lista_de_registros, total_de_registros)
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
# OPERACOES ESPECIFICAS: USUARIOS E AUTENTICACAO
# ============================================================

def autenticar_usuario(email: str, senha: str) -> Optional[Dict[str, Any]]:
    """
    Autentica um usuario pelo email e senha.

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
            .eq("email", email)
            .eq("senha", senha)
            .eq("ativo", True)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"[DB ERROR] autenticar_usuario: {e}")
        return None

def semear_usuarios_iniciais() -> bool:
    """
    Cria usuarios iniciais se a tabela estiver vazia.
    Deve ser chamado na inicializacao do app.py.

    Returns:
        True se executou com sucesso, False se falhou
    """
    cliente = get_supabase()
    if not cliente:
        return False

    try:
        # Verificar se ja existem usuarios
        resp = cliente.table("usuarios_acesso").select("id").limit(1).execute()
        if resp.data:
            return True

        usuarios = [
            {"nome": "Secretario", "email": "secretario@tcdf.gov.br", "senha": "tcdf2025", "cargo": "raiz", "setor": "GAB", "ativo": True},
            {"nome": "Subsecretario", "email": "subsecretario@tcdf.gov.br", "senha": "tcdf2025", "cargo": "raiz", "setor": "GAB", "ativo": True},
            {"nome": "Chefe SEAT", "email": "chefeseat@tcdf.gov.br", "senha": "tcdf2025", "cargo": "gerente", "setor": "SEAT", "ativo": True},
            {"nome": "Chefe SEXP", "email": "chefesexp@tcdf.gov.br", "senha": "tcdf2025", "cargo": "gerente", "setor": "SEXP", "ativo": True},
            {"nome": "Chefe SERCON", "email": "chefesercon@tcdf.gov.br", "senha": "tcdf2025", "cargo": "gerente", "setor": "SERCON", "ativo": True},
            {"nome": "Chefe SEMAND", "email": "chefesemand@tcdf.gov.br", "senha": "tcdf2025", "cargo": "gerente", "setor": "SEMAND", "ativo": True},
            {"nome": "Assessor SEAT", "email": "assessorseat@tcdf.gov.br", "senha": "tcdf2025", "cargo": "operacional", "setor": "SEAT", "ativo": True},
            {"nome": "Assessor SEXP", "email": "assessorsexp@tcdf.gov.br", "senha": "tcdf2025", "cargo": "operacional", "setor": "SEXP", "ativo": True},
            {"nome": "Estagiario SEAT", "email": "estagiarioseat@tcdf.gov.br", "senha": "tcdf2025", "cargo": "operacional", "setor": "SEAT", "ativo": True},
        ]

        resp = cliente.table("usuarios_acesso").insert(usuarios).execute()
        return bool(resp.data)
    except Exception as e:
        print(f"[DB ERROR] semear_usuarios_iniciais: {e}")
        return False

# ============================================================
# OPERACOES ESPECIFICAS: EQUIPE
# ============================================================

def listar_equipe(setor: Optional[str] = None, apenas_ativos: bool = True) -> List[Dict[str, Any]]:
    """
    Lista membros da equipe, opcionalmente filtrados por setor.

    Returns:
        Lista de membros
    """
    filtros = {}
    if setor:
        filtros["setor"] = setor
    if apenas_ativos:
        filtros["ativo"] = True

    return buscar_todos("equipe", filtros=filtros, ordem_coluna="nome")

def adicionar_membro_equipe(nome: str, cargo: str, setor: str, funcao: str) -> Optional[Dict[str, Any]]:
    """
    Adiciona um novo membro a equipe.

    Returns:
        Registro criado, ou None se falhou
    """
    return inserir("equipe", {
        "nome": nome,
        "cargo": cargo,
        "setor": setor,
        "funcao": funcao,
        "ativo": True,
    })

def atualizar_membro_equipe(id_membro: int, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Atualiza dados de um membro da equipe."""
    return atualizar("equipe", id_membro, dados)

def remover_membro_equipe(id_membro: int) -> bool:
    """
    Inativa um membro da equipe (soft delete).
    Nao deleta fisicamente para preservar historico.
    """
    return atualizar("equipe", id_membro, {"ativo": False}) is not None

# ============================================================
# OPERACOES ESPECIFICAS: AFASTAMENTOS
# ============================================================

def listar_afastamentos(apenas_ativos: bool = True) -> List[Dict[str, Any]]:
    """
    Lista afastamentos cadastrados.

    Returns:
        Lista de afastamentos
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

    Args:
        nome: Nome do membro afastado
        tipo: 'ferias', 'recesso', 'licenca'
        data_inicio: Data no formato 'YYYY-MM-DD'
        data_fim: Data no formato 'YYYY-MM-DD'
        motivo: Motivo opcional

    Returns:
        Registro criado, ou None se falhou
    """
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

    Args:
        nome: Nome do membro
        data_verificacao: Data no formato 'YYYY-MM-DD'. Default: hoje.

    Returns:
        True se afastado, False caso contrario
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
    """
    Lista regras de palavras-chave do Motor NIP.

    Returns:
        Lista de regras
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
    Adiciona uma regra de transposicao de verbo ou substituicao.

    Args:
        palavra_original: Verbo no subjuntivo (ex: 'conheca')
        palavra_substituta: Verbo no infinitivo (ex: 'conhecer')
        tipo: 'substituicao' ou 'bloqueio'

    Returns:
        Registro criado, ou None se falhou
    """
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
    Deve ser chamado na inicializacao do app.py.
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
    """
    Extrai texto de um arquivo PDF.

    Args:
        arquivo: Objeto de arquivo (UploadedFile do Streamlit ou file-like object)

    Returns:
        Texto extraido, ou string vazia se falhar
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

    Args:
        arquivo: Objeto de arquivo (UploadedFile do Streamlit ou file-like object)

    Returns:
        Texto extraido, ou string vazia se falhar
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
    Extrai texto de um arquivo (PDF, DOCX ou TXT).
    Detecta o tipo automaticamente pela extensao ou tipo MIME.

    Args:
        arquivo: Objeto de arquivo com atributo 'name' ou 'type'

    Returns:
        Texto extraido, ou string vazia se falhar
    """
    if arquivo is None:
        return ""

    nome = getattr(arquivo, "name", "").lower()
    tipo = getattr(arquivo, "type", "").lower()

    # PDF
    if nome.endswith(".pdf") or "pdf" in tipo:
        return extrair_texto_pdf(arquivo)

    # DOCX
    if nome.endswith(".docx") or "word" in tipo:
        return extrair_texto_docx(arquivo)

    # TXT (assumir texto plano)
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
