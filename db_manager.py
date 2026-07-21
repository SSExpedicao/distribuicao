# ==============================================================================
# ARQUIVO: db_manager.py
# MISSÃO: Conector Central do Supabase, Higienização de Dados e Funções Auxiliares
# ==============================================================================

import streamlit as st
import pandas as pd
import unicodedata
import difflib
from datetime import datetime
from st_supabase_connection import SupabaseConnection

# ------------------------------------------------------------------------------
# 1. INICIALIZAÇÃO DA CONEXÃO COM A NUVEM SUPABASE
# ------------------------------------------------------------------------------
@st.cache_resource
def get_db_connection():
    """Cria e retorna a conexão blindada com o Supabase usando cache do Streamlit."""
    try:
        conn = st.connection("supabase", type=SupabaseConnection)
        return conn
    except Exception as e:
        st.error(f"🚨 Erro crítico de comunicação com a Nuvem Supabase: {e}")
        st.stop()

# Instância global de conexão para ser consumida pelos outros módulos
conn = get_db_connection()

# ------------------------------------------------------------------------------
# 2. INTELIGÊNCIA DE HIGIENIZAÇÃO E PADRONIZAÇÃO DE TEXTO
# ------------------------------------------------------------------------------
def normalizar_texto(texto):
    """Remove acentos, espaços extras e converte para minúsculo para comparação exata."""
    if not texto or str(texto).strip() == "": 
        return ""
    texto = str(texto).strip().lower()
    # Separa os caracteres dos acentos e remove as marcações diacríticas
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto

def higienizar_colaborador(nome_digitado, lista_oficial_nomes):
    """Cruza o nome digitado com a lista oficial da equipe, corrigindo erros de digitação."""
    if not nome_digitado or str(nome_digitado).strip() == "": 
        return ""
    
    nome_norm = normalizar_texto(nome_digitado)
    
    # 1. Correspondência exata direta
    for nome_oficial in lista_oficial_nomes:
        if nome_norm == normalizar_texto(nome_oficial):
            return nome_oficial
            
    # 2. Inteligência de similaridade para erros de digitação (difflib)
    lista_norm = [normalizar_texto(n) for n in lista_oficial_nomes]
    matches = difflib.get_close_matches(nome_norm, lista_norm, n=1, cutoff=0.75)
    
    if matches:
        indice = lista_norm.index(matches[0])
        return lista_oficial_nomes[indice]
        
    # 3. Se for um nome genuinamente novo, padroniza com a primeira letra maiúscula
    return str(nome_digitado).strip().title()

def higienizar_dados(processo, relator=""):
    """Limpa sufixos de processo (ex: '-e') e converte siglas de gabinetes."""
    proc_limpo = str(processo).strip()
    if proc_limpo.lower().endswith("-e"):
        proc_limpo = proc_limpo[:-2]
        
    rel_limpo = str(relator).strip().upper()
    mapa_relatores = {
        "RR": "GCRR", "AM": "GCAM", "PT": "GCPT", 
        "AC": "GCAC", "IM": "GCIM", "MM": "GCMM", "VF": "GAVF", 
        "GAVF / SUBST.": "GAVF", "VF / SUBST.": "GAVF", "AT": "GPAT"
    }
    if rel_limpo in mapa_relatores:
        rel_limpo = mapa_relatores[rel_limpo]
        
    return proc_limpo, rel_limpo

# ------------------------------------------------------------------------------
# 3. MOTOR DE LEITURA BLINDADA (BURlando LIMITE DE 1.000 LINHAS DO SUPABASE)
# ------------------------------------------------------------------------------
def buscar_todos_paginado(nome_tabela, coluna_eq=None, valor_eq=None):
    """
    Realiza paginação automática em lotes de 1.000 linhas para impedir que o 
    Supabase corte relatórios históricos grandes ou trave por excesso de carga.
    """
    todos_dados = []
    inicio = 0
    tamanho_lote = 1000

    while True:
        try:
            query = conn.client.table(nome_tabela).select("*")
            if coluna_eq and valor_eq:
                query = query.eq(coluna_eq, valor_eq)

            resposta = query.range(inicio, inicio + tamanho_lote - 1).execute()

            if not resposta.data:
                break

            todos_dados.extend(resposta.data)

            # Se o lote retornou menos de 1000, significa que chegamos ao fim da tabela
            if len(resposta.data) < tamanho_lote:
                break

            inicio += tamanho_lote
        except Exception as e:
            st.error(f"Erro na leitura paginada da tabela '{nome_tabela}': {e}")
            break

    return todos_dados

# ------------------------------------------------------------------------------
# 4. GESTÃO DE EQUIPE E SEGURANÇA DE ACESSO
# ------------------------------------------------------------------------------
def carregar_equipes():
    """Busca a lista de colaboradores no banco e separa por atribuição operacional."""
    try:
        resposta = conn.client.table("equipe").select("nome, expedicao, revisao").order("nome").execute()
        if not resposta.data:
            return [], [], []
            
        todos = [linha['nome'] for linha in resposta.data]
        expedidores = [linha['nome'] for linha in resposta.data if linha.get('expedicao') == 1]
        revisores = [linha['nome'] for linha in resposta.data if linha.get('revisao') == 1]
        
        return expedidores, revisores, todos
    except Exception as e:
        st.error(f"Erro ao carregar dados da equipe: {e}")
        return [], [], []

def obter_colaboradores_ausentes_hoje():
    """Verifica a tabela de afastamentos e retorna quem está de férias ou atestado hoje."""
    try:
        hoje = datetime.now().date()
        res = conn.client.table("afastamentos").select("usuario, data_inicio, data_fim").execute().data
        ausentes = []
        for row in res:
            try:
                ini = datetime.strptime(row['data_inicio'], "%d/%m/%Y").date()
                fim = datetime.strptime(row['data_fim'], "%d/%m/%Y").date()
                if ini <= hoje <= fim:
                    ausentes.append(row['usuario'])
            except ValueError:
                continue
        return ausentes
    except Exception:
        return []

def init_db():
    """Verificação de segurança que popula a equipe inicial se o banco estiver vazio."""
    try:
        res = conn.client.table("equipe").select("nome").limit(1).execute()
        if not res.data:
            iniciais = [
                {"nome": "André", "expedicao": 1, "revisao": 1, "cargo": "Assessor"},
                {"nome": "Elaine", "expedicao": 1, "revisao": 1, "cargo": "Assessor"},
                {"nome": "Kátia", "expedicao": 1, "revisao": 1, "cargo": "Assessor"},
                {"nome": "Luana C", "expedicao": 1, "revisao": 1, "cargo": "Estagiário"},
                {"nome": "Jessyca", "expedicao": 1, "revisao": 1, "cargo": "Chefia"},
                {"nome": "Lu Fiorote", "expedicao": 1, "revisao": 1, "cargo": "Assessor"},
                {"nome": "Mariana", "expedicao": 1, "revisao": 1, "cargo": "Assessor"},
                {"nome": "Maurício", "expedicao": 1, "revisao": 1, "cargo": "Assessor"}
            ]
            conn.client.table("equipe").insert(iniciais).execute()
    except Exception as e:
        st.sidebar.error(f"Aviso de Inicialização: {e}")
