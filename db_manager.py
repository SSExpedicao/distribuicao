# ==============================================================================
# ARQUIVO: db_manager.py
# MISSÃO: Gerenciar a conexão com o Supabase e fornecer funções de leitura/escrita
# ==============================================================================

import streamlit as st
from supabase import create_client, Client
from datetime import datetime

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

def garantir_usuario_mestre():
    """Garante que o Secretário (Nível Raiz) exista no banco para evitar bloqueio do sistema."""
    try:
        res = conn.table("usuarios_acesso").select("id").eq("login", "secretario").limit(1).execute()
        if not res.data:
            mestre = {
                "login": "secretario",
                "senha": "admin",
                "nome": "Secretário das Sessões",
                "cargo": "Secretário",
                "setor": "GAB",
                "nivel_acesso": "Raiz",
                "ativo": True
            }
            conn.table("usuarios_acesso").insert(mestre).execute()
    except Exception:
        pass

# Executa verificação de segurança ao carregar o módulo
garantir_usuario_mestre()
