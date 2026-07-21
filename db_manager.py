import streamlit as st
from supabase import create_client, Client
from datetime import datetime
import io

@st.cache_resource
def init_connection():
    """Inicializa a conexão com o Supabase via Streamlit Secrets."""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("🚨 Conexão falhou. Verifique SUPABASE_URL e SUPABASE_KEY no .streamlit/secrets.toml")
        st.stop()

conn = init_connection()

def get_db_connection():
    """Retorna conexão ativa (alias para compatibilidade)."""
    return conn

def extrair_texto_arquivo(arquivo_upload):
    """Extrai texto de PDF, DOCX ou TXT enviado via upload."""
    try:
        nome = arquivo_upload.name.lower()
        bytes_arq = arquivo_upload.getvalue()
        texto = ""

        if nome.endswith('.txt'):
            texto = bytes_arq.decode('utf-8', errors='replace')
        elif nome.endswith('.pdf'):
            try:
                import PyPDF2
                with io.BytesIO(bytes_arq) as f:
                    leitor = PyPDF2.PdfReader(f)
                    for p in leitor.pages:
                        texto += p.extract_text() + "\n"
            except ImportError:
                try:
                    import pdfplumber
                    with io.BytesIO(bytes_arq) as f:
                        with pdfplumber.open(f) as pdf:
                            for p in pdf.pages:
                                t = p.extract_text()
                                if t: texto += t + "\n"
                except ImportError:
                    st.error("Instale PyPDF2 ou pdfplumber: pip install PyPDF2 pdfplumber")
                    return None
        elif nome.endswith('.docx'):
            try:
                import docx
                with io.BytesIO(bytes_arq) as f:
                    doc = docx.Document(f)
                    for par in doc.paragraphs:
                        texto += par.text + "\n"
            except ImportError:
                st.error("Instale python-docx: pip install python-docx")
                return None
        else:
            st.error(f"Formato não suportado: {nome}. Use PDF, DOCX ou TXT.")
            return None

        return texto.strip() if texto.strip() else None
    except Exception as e:
        st.error(f"Erro ao extrair texto: {e}")
        return None

def verificar_criar_tabelas():
    """Auto-cria as tabelas do Hub SS no Supabase se não existirem."""
    sql = """
    CREATE TABLE IF NOT EXISTS public.usuarios_acesso (
        id SERIAL PRIMARY KEY, login TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL, nome TEXT NOT NULL, cargo TEXT NOT NULL,
        setor TEXT NOT NULL, nivel_acesso TEXT DEFAULT 'Operacional',
        ativo BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW()
    );
    INSERT INTO public.usuarios_acesso (login,senha,nome,cargo,setor,nivel_acesso,ativo)
    VALUES ('secretario','123','Secretário das Sessões','Secretário','GAB','Raiz',TRUE),
           ('gerente.seat','123','Gestor SEAT','Gerente','SEAT','Gerente',TRUE),
           ('gerente.sexp','123','Gestor SEXP','Gerente','SEXP','Gerente',TRUE),
           ('elaine.seat','123','Elaine Assessora','Assessor','SEAT','Operacional',TRUE),
           ('andre.sexp','123','André Assessor','Assessor','SEXP','Operacional',TRUE)
    ON CONFLICT (login) DO NOTHING;

    CREATE TABLE IF NOT EXISTS public.regras_palavras_chave (
        id SERIAL PRIMARY KEY, categoria TEXT NOT NULL,
        palavra_chave TEXT NOT NULL, setor_alvo TEXT NOT NULL,
        ativo BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.equipe (
        id SERIAL PRIMARY KEY, nome TEXT NOT NULL,
        expedicao TEXT DEFAULT 'Não', revisao TEXT DEFAULT 'Não',
        setor TEXT, ativo BOOLEAN DEFAULT TRUE
    );

    CREATE TABLE IF NOT EXISTS public.afastamentos (
        id SERIAL PRIMARY KEY, usuario TEXT NOT NULL,
        motivo TEXT, data_inicio TEXT, data_fim TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.pauta_seat (
        id SERIAL PRIMARY KEY, processo TEXT, relator TEXT,
        sessao TEXT, editor TEXT, revisor TEXT,
        editado_ok INT DEFAULT 0, revisado_ok INT DEFAULT 0,
        urgente INT DEFAULT 0, status TEXT DEFAULT 'Em Edição',
        data_entrada TEXT, observacao TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.pauta_sexp (
        id SERIAL PRIMARY KEY, processo TEXT, relator TEXT,
        sessao TEXT, expedidor TEXT, revisor TEXT,
        urgente INT DEFAULT 0, status TEXT DEFAULT 'Aguardando Homologação Chefia',
        data_entrada TEXT, data_expedicao TEXT, data_conclusao TEXT,
        observacao TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.pauta_sercon (
        id SERIAL PRIMARY KEY, processo TEXT, relator TEXT,
        motivo_gatilho TEXT, status TEXT DEFAULT 'Pendente Análise Contábil',
        analista_responsavel TEXT, data_entrada TEXT, data_conclusao TEXT,
        observacao TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.pauta_semand (
        id SERIAL PRIMARY KEY, processo TEXT, relator TEXT,
        destinatario TEXT, status TEXT DEFAULT 'Aguardando Expedição de Mandado',
        urgente INT DEFAULT 0, oficial_responsavel TEXT,
        data_entrada TEXT, data_conclusao TEXT, observacao TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.pauta_quarta (
        id SERIAL PRIMARY KEY, processo TEXT, relator TEXT,
        tipo_pauta TEXT, sessao_alvo TEXT, editor TEXT, revisor TEXT,
        status TEXT, data_registro TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.escala_publicacao (
        id SERIAL PRIMARY KEY, mes TEXT, dia_semana TEXT,
        dupla TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    try:
        conn.rpc("exec_sql", {"query": sql})
    except Exception:
        st.warning("⚠️ Não foi possível criar tabelas automaticamente. Execute o SQL manual no Supabase SQL Editor.")

def buscar_todos_paginado(tabela: str, tamanho_pagina: int = 1000):
    """Busca todos os registros de uma tabela superando o limite de 1000 linhas."""
    try:
        todos = []
        offset = 0
        while True:
            resp = conn.table(tabela).select("*").range(offset, offset + tamanho_pagina - 1).execute()
            if not resp.data:
                break
            todos.extend(resp.data)
            if len(resp.data) < tamanho_pagina:
                break
            offset += tamanho_pagina
        return todos
    except Exception:
        return []

def carregar_equipes():
    """Retorna listas de expedidores, revisores e todos os ativos."""
    try:
        dados = buscar_todos_paginado("equipe")
        if not dados:
            return ["Equipe Vazia"], ["Equipe Vazia"], ["Equipe Vazia"]
        expedidores = [i["nome"] for i in dados if i.get("expedicao") == "Sim"]
        revisores = [i["nome"] for i in dados if i.get("revisao") == "Sim"]
        todos = [i["nome"] for i in dados]
        return (expedidores or ["Nenhum"], revisores or ["Nenhum"], todos or ["Nenhum"])
    except Exception:
        return ["Erro"], ["Erro"], ["Erro"]

def obter_colaboradores_ausentes_hoje():
    """Retorna lista de colaboradores afastados hoje (férias/atestado)."""
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
