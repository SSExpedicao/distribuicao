"""
modulos/seat.py - SEAT: Edicao e Triagem
Secretaria das Sessoes - TCDF

Sub-etapa 1A+1B: Pauta Ativa com sessoes + Distribuicao Equalitaria

Fluxo de status:
  inclusao -> em_edicao -> em_revisao -> encaminhado

RBAC:
- modo_edicao=True: pode incluir, distribuir, alterar status, editar atribuicoes
- modo_edicao=False: somente visualizacao
"""

import streamlit as st
import csv
import io
import unicodedata
from datetime import datetime, date
import db_manager

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False

# ============================================================
# CONSTANTES
# ============================================================

STATUS_FLOW = {
    "inclusao": {
        "label": "📥 Inclusao",
        "proximo": "em_edicao",
        "acao_proximo": "▶ Iniciar Edicao",
    },
    "em_edicao": {
        "label": "✏️ Em Edicao",
        "proximo": "em_revisao",
        "acao_proximo": "▶ Enviar para Revisao",
    },
    "em_revisao": {
        "label": "🔍 Em Revisao",
        "proximo": "encaminhado",
        "acao_proximo": "▶ Encaminhar para SEXP",
    },
    "encaminhado": {
        "label": "📤 Encaminhado",
        "proximo": None,
        "acao_proximo": None,
    },
}

TIPOS_SESSAO = [
    "Ordinaria",
    "Ordinaria Virtual",
    "Reservada",
    "Administrativa",
    "Urgente",
]

# ============================================================
# FUNCOES AUXILIARES: NORMALIZACAO E HIGIENIZACAO
# ============================================================

def _normalizar_texto(texto: str) -> str:
    """
    Normaliza texto para comparacao:
    minusculas, sem acentos, sem espacos extras.
    Usado para matching de nomes e numeros de processo.
    """
    if not texto:
        return ""
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = ' '.join(texto.split())
    return texto

def _normalizar_tipo_sessao(tipo: str) -> str:
    """
    Normaliza o tipo de sessao do CSV para corresponder aos valores padrao.
    Aceita variacoes como 'ordinaria', 'Ordinária', 'ORDINARIA'.
    """
    if not tipo:
        return ""
    tipo_norm = _normalizar_texto(tipo)
    for tipo_padrao in TIPOS_SESSAO:
        if _normalizar_texto(tipo_padrao) == tipo_norm:
            return tipo_padrao
    return tipo.strip()

def _higienizar_colaborador(nome_digitado: str, nomes_oficiais: list) -> str:
    """
    Faz matching inteligente entre nome digitado e nome oficial da equipe.
    Tolerante a variacoes de escrita (acentos, maiusculas, espacos).

    Returns:
        Nome oficial se encontrado, ou nome digitado original.
    """
    if not nome_digitado or not nomes_oficiais:
        return nome_digitado or ""

    alvo = _normalizar_texto(nome_digitado)

    # 1. Match exato normalizado
    for oficial in nomes_oficiais:
        if _normalizar_texto(oficial) == alvo:
            return oficial

    # 2. Match por primeiro nome + ultimo nome
    partes_alvo = alvo.split()
    for oficial in nomes_oficiais:
        partes_oficial = _normalizar_texto(oficial).split()
        if len(partes_alvo) >= 2 and len(partes_oficial) >= 2:
            if partes_alvo[0] == partes_oficial[0] and partes_alvo[-1] == partes_oficial[-1]:
                return oficial

    # 3. Match por primeiro nome
    for oficial in nomes_oficiais:
        partes_oficial = _normalizar_texto(oficial).split()
        if partes_oficial and partes_alvo and partes_oficial[0] == partes_alvo[0]:
            return oficial

    return nome_digitado

def _formatar_data(data_iso: str) -> str:
    """Converte data ISO para DD/MM/YYYY HH:MM."""
    if not data_iso:
        return "-"
    try:
        dt = datetime.fromisoformat(str(data_iso).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(data_iso) if data_iso else "-"

def _formatar_data_curta(data_iso: str) -> str:
    """Converte data ISO para DD/MM/YYYY."""
    if not data_iso:
        return "-"
    try:
        dt = datetime.fromisoformat(str(data_iso).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(data_iso) if data_iso else "-"

# ============================================================
# FUNCOES AUXILIARES: EQUIPE E AFASTAMENTOS
# ============================================================

def _obter_equipe_seat() -> list:
    """
    Retorna lista de nomes dos membros ativos da
