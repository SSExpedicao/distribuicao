# ==============================================================================
# ARQUIVO: db_manager.py
# MISSÃO: Gerenciar a conexão com o Supabase e fornecer funções de leitura/escrita
# VERSÃO: 2.0 — Com auto-verificação e criação de tabelas
# ==============================================================================
import streamlit as st
from supabase import create_client, Client
from datetime import datetime
import io
import os
import tempfile

def extrair_texto_arquivo(arquivo_upload):
    """
    Extrai texto de arquivos PDF, DOCX ou TXT enviados via upload.
    Retorna o texto extraído ou None em caso de erro.
    """
    import streamlit as st
    
    try:
        # Pega extensão do arquivo
        nome_arquivo = arquivo_upload.name.lower()
        
        # Lê os bytes do arquivo
        bytes_arquivo = arquivo_upload.getvalue()
        
        texto = ""
        
        if nome_arquivo.endswith('.txt'):
            texto = bytes_arquivo.decode('utf-8', errors='replace')
            
        elif nome_arquivo.endswith('.pdf'):<br/>
            try:
                import PyPDF2
                with io.BytesIO(bytes_arquivo) as arquivo_pdf:
                    leitor = PyPDF2.PdfReader(arquivo_pdf)
                    for pagina in leitor.pages:
                        texto += pagina.extract_text() + "
"
            except ImportError:<br/>
                try:
                    import pdfplumber
                    with io.BytesIO(bytes_arquivo) as arquivo_pdf:<br/>
                        with pdfplumber.open(arquivo_pdf) as pdf:<br/>
                            for pagina in pdf.pages:
                                texto_extraido = pagina.extract_text()
                                if texto_extraido:
                                    texto += texto_extraido + "
"
                except ImportError:<br/>
                    st.error("📦 Biblioteca de PDF não instalada. Execute: pip install PyPDF2 pdfplumber")
                    return None
                    
        elif nome_arquivo.endswith('.docx'):<br/>
            try:
                import docx
                with io.BytesIO(bytes_arquivo) as arquivo_docx:
                    documento = docx.Document(arquivo_docx)
                    for paragrafo in documento.paragraphs:
                        texto += paragrafo.text + "
"
            except ImportError:<br/>
                st.error("📦 Biblioteca python-docx não instalada. Execute: pip install python-docx")
                return None
        else:<br/>
            st.error(f"❌ Formato não suportado: {nome_arquivo}. Use PDF, DOCX ou TXT.")
            return None
            
        return texto.strip() if texto.strip() else None
        
    except Exception as e:<br/>
        st.error(f"❌ Erro ao extrair texto do arquivo: {e}")
        return None

@st.cache_resource
def init_connection() -> Client:
    """Inicializa a conexão com o Supabase buscando as credenciais do Streamlit Secrets."""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("🚨 Erro de Conexão: Verifique se SUPABASE_URL e SUPABASE_KEY estão configurados no Secrets do Streamlit Cloud ou no arquivo .streamlit/secrets.toml local.")
        st.stop()

def get_db_connection() -> Client:
    """Retorna a instância da conexão com o banco de dados (Alias para compatibilidade)."""
    return init_connection()

# Conexão Global
conn = init_connection()

# ==============================================================================
# FUNÇÃO DE AUTO-CRIAÇÃO E VERIFICAÇÃO DE TABELAS
# ==============================================================================
def garantir_tabelas_existentes():
    """
    Verifica se todas as tabelas do Hub SS existem no Supabase.
    Se não existirem, cria via execução de SQL.
    Usa CREATE TABLE IF NOT EXISTS para não destruir tabelas existentes.
    """
    sql_criacao = """
    -- Tabela de usuários (controle de acesso RBAC)
    CREATE TABLE IF NOT EXISTS public.usuarios_acesso (
        id SERIAL PRIMARY KEY,
        login TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        nome TEXT NOT NULL,
        cargo TEXT NOT NULL,
        setor TEXT NOT NULL,
        nivel_acesso TEXT NOT NULL DEFAULT 'Operacional',
        ativo BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Tabela de palavras-chave (dicionário dinâmico do Motor NIP)
    CREATE TABLE IF NOT EXISTS public.regras_palavras_chave (
        id SERIAL PRIMARY KEY,
        categoria TEXT NOT NULL,
        palavra_chave TEXT NOT NULL,
        setor_alvo TEXT NOT NULL,
        ativo BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Tabela de equipe
    CREATE TABLE IF NOT EXISTS public.equipe (
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        expedicao TEXT DEFAULT 'Não',
        revisao TEXT DEFAULT 'Não',
        setor TEXT,
        ativo BOOLEAN DEFAULT TRUE
    );

    -- Tabela de afastamentos
    CREATE TABLE IF NOT EXISTS public.afastamentos (
        id SERIAL PRIMARY KEY,
        usuario TEXT NOT NULL,
        motivo TEXT,
        data_inicio TEXT,
        data_fim TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Esteiras operacionais (pautas dos setores)
    CREATE TABLE IF NOT EXISTS public.pauta_seat (
        id SERIAL PRIMARY KEY,
        processo TEXT, relator TEXT, sessao TEXT,
        editor TEXT, revisor TEXT,
        editado_ok INT DEFAULT 0, revisado_ok INT DEFAULT 0,
        urgente INT DEFAULT 0, status TEXT DEFAULT 'Em Edição',
        data_entrada TEXT, observacao TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.pauta_sexp (
        id SERIAL PRIMARY KEY,
        processo TEXT, relator TEXT, sessao TEXT,
        expedidor TEXT, revisor TEXT,
        urgente INT DEFAULT 0, status TEXT DEFAULT 'Aguardando Homologação Chefia',
        data_entrada TEXT, data_expedicao TEXT, data_conclusao TEXT,
        observacao TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.pauta_sercon (
        id SERIAL PRIMARY KEY,
        processo TEXT, relator TEXT, motivo_gatilho TEXT,
        status TEXT DEFAULT 'Pendente Análise Contábil',
        analista_responsavel TEXT,
        data_entrada TEXT, data_conclusao TEXT,
        observacao TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.pauta_semand (
        id SERIAL PRIMARY KEY,
        processo TEXT, relator TEXT, destinatario TEXT,
        status TEXT DEFAULT 'Aguardando Expedição de Mandado',
        urgente INT DEFAULT 0, oficial_responsavel TEXT,
        data_entrada TEXT, data_conclusao TEXT,
        observacao TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Tabelas litúrgicas
    CREATE TABLE IF NOT EXISTS public.pauta_quarta (
        id SERIAL PRIMARY KEY,
        processo TEXT, relator TEXT, tipo_pauta TEXT,
        sessao_alvo TEXT, editor TEXT, revisor TEXT,
        status TEXT, data_registro TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.escala_publicacao (
        id SERIAL PRIMARY KEY,
        mes TEXT, dia_semana TEXT, dupla TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    try:
        conn.rpc("executar_sql", {"sql": sql_criacao}).execute()
    except Exception:
        # Se a RPC não existir, tenta via postgrest (pode falhar em alguns Supabases)
        # Nesse caso, o admin deve rodar o SQL manualmente no SQL Editor
        pass

def garantir_usuario_mestre():
    """Garante que o Secretário (Nível Raiz) exista no banco para evitar bloqueio do sistema."""
    try:
        res = conn.table("usuarios_acesso").select("id").eq("login", "secretario").limit(1).execute()
        if not res.data:
            mestre = {
                "login": "secretario",
                "senha": "123",
                "nome": "Secretário de Sessões",
                "cargo": "Secretário",
                "setor": "GAB",
                "nivel_acesso": "Raiz",
                "ativo": True
            }
            conn.table("usuarios_acesso").insert(mestre).execute()
    except Exception:
        pass

# Executa verificação de segurança ao carregar o módulo
garantir_tabelas_existentes()
garantir_usuario_mestre()

# ==============================================================================
# FUNÇÕES DE LEITURA/ESCRITA
# ==============================================================================
def buscar_todos_paginado(tabela: str, tamanho_pagina: int = 1000):
    """Busca todos os registros de uma tabela superando o limite padrão de 1000 linhas da API."""
    try:
        todos_dados = []
        offset = 0
        while True:
            resposta = conn.table(tabela).select("*").range(offset, offset + tamanho_pagina - 1).execute()
            if not resposta.data:
                break
            todos_dados.extend(resposta.data)
            if len(resposta.data) < tamanho_pagina:
                break
            offset += tamanho_pagina
        return todos_dados
    except Exception as e:
        return []

def carregar_equipes():
    """Retorna listas separadas para o rodízio: Expedidores, Revisores e Todos os Ativos."""
    try:
        dados = buscar_todos_paginado("equipe")
        if not dados:
            return ["Equipe Vazia"], ["Equipe Vazia"], ["Equipe Vazia"]
        expedidores = [item["nome"] for item in dados if item.get("expedicao") == "Sim"]
        revisores = [item["nome"] for item in dados if item.get("revisao") == "Sim"]
        todos = [item["nome"] for item in dados]
        return expedidores if expedidores else ["Nenhum"], revisores if revisores else ["Nenhum"], todos if todos else ["Nenhum"]
    except Exception:
        return ["Erro"], ["Erro"], ["Erro"]

def obter_colaboradores_ausentes_hoje():
    """Consulta a tabela de afastamentos e retorna quem está de férias ou atestado HOJE."""
    try:
        afastados = buscar_todos_paginado("afastamentos")
        ausentes = []
        hoje = datetime.now()
        for reg in afastados:
            try:
                dt_ini = datetime.strptime(reg["data_inicio"], "%d/%m/%Y")
                dt_fim = datetime.strptime(reg["data_fim"], "%d/%m/%Y")
                if dt_ini <= hoje <= dt_fim:
                    ausentes.append(reg["usuario"])
            except ValueError:
                continue
        return ausentes
    except Exception:
        return []
