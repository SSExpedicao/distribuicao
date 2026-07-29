"""
Monitor DOE-TCDF — Diário Oficial Eletrônico do TCDF
Rastreia publicações que mencionam nomes de colaboradores.
O DOE-TCDF é HTML puro, publicado em https://doe.tc.df.gov.br/
"""

import os
import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client

# ============================================================
# CONFIGURAÇÃO
# ============================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
DOE_BASE = "https://doe.tc.df.gov.br"

# ============================================================
# CONEXÃO SUPABASE
# ============================================================
def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERRO] SUPABASE_URL e SUPABASE_KEY não definidos")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================
# BUSCAR COLABORADORES ATIVOS
# ============================================================
def buscar_colaboradores(sb):
    try:
        result = sb.table("usuarios_acesso").select("nome,setor,vinculo,matricula").eq("ativo", True).execute()
        return result.data or []
    except Exception as e:
        print(f"[ERRO] Falha ao buscar colaboradores: {e}")
        return []

# ============================================================
# BUSCAR EDIÇÃO DO DIA DO DOE-TCDF
# ============================================================
def buscar_edicao_doe():
    """
    Faz scrape da página principal do DOE-TCDF.
    O portal publica a edição do dia em HTML, com seções:
    - Atos da Presidência / Portarias
    - Atos da Segedam / Outros Atos
    - Atos da Segep / Despachos
    - Atos da Sesbe / Despachos
    Cada publicação tem um botão "Extrato" e "Baixar PDF".
    """
    try:
        resp = requests.get(DOE_BASE, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code != 200:
            print(f"[ERRO] Status {resp.status_code} ao acessar DOE-TCDF")
            return None, None
        
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Extrair número da edição e data
        titulo_edicao = None
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "strong", "b"]):
            texto = tag.get_text(strip=True)
            if "Edição" in texto and "de" in texto:
                titulo_edicao = texto
                break
        
        # Extrair texto completo de todas as publicações
        texto_completo = soup.get_text(separator="\n", strip=True)
        
        # Limpar texto (remover linhas vazias excessivas)
        texto_completo = re.sub(r'\n{3,}', '\n\n', texto_completo)
        
        return texto_completo, titulo_edicao
    
    except Exception as e:
        print(f"[ERRO] Falha ao acessar DOE-TCDF: {e}")
        return None, None

# ============================================================
# BUSCAR EXTRATOS INDIVIDUAIS
# ============================================================
def buscar_extratos_doe(html_raw):
    """
    Extrai os textos individuais de cada publicação do DOE-TCDF.
    Cada publicação é separada por "Extrato" no final.
    Retorna uma lista de dicionários com texto e seção.
    """
    try:
        soup = BeautifulSoup(html_raw, "html.parser")
        publicacoes = []
        
        # O DOE-TCDF estrutura as publicações em blocos
        # Cada bloco termina com "Extrato" e botões de compartilhar/baixar
        blocos = soup.find_all(["div", "article", "section"])
        
        for bloco in blocos:
            texto = bloco.get_text(separator="\n", strip=True)
            if len(texto) > 50:  # Ignorar blocos muito pequenos
                publicacoes.append({
                    "texto": texto,
                    "secao": _identificar_secao(texto)
                })
        
        # Se não encontrou blocos estruturados, usar o texto completo
        if not publicacoes:
            texto_completo = soup.get_text(separator="\n", strip=True)
            # Dividir por "Extrato" (separador natural entre publicações)
            partes = re.split(r'\nExtrato\n', texto_completo)
            for parte in partes:
                parte = parte.strip()
                if len(parte) > 50:
                    publicacoes.append({
                        "texto": parte,
                        "secao": _identificar_secao(parte)
                    })
        
        return publicacoes
    
    except Exception as e:
        print(f"[ERRO] Falha ao extrair publicações: {e}")
        return []

# ============================================================
# IDENTIFICAR SEÇÃO DA PUBLICAÇÃO
# ============================================================
def _identificar_secao(texto):
    """Identifica a qual seção do DOE-TCDF a publicação pertence."""
    texto_upper = texto.upper()
    if "PRESIDÊNCIA" in texto_upper or "PORTARIA" in texto_upper:
        return "Atos da Presidência"
    elif "SEGEDAM" in texto_upper:
        return "Atos da Segedam"
    elif "SEGEP" in texto_upper:
        return "Atos da Segep"
    elif "SESBE" in texto_upper:
        return "Atos da Sesbe"
    return "Geral"

# ============================================================
# EXTRAIR TRECHO RELEVANTE
# ============================================================
def extrair_trecho(texto, nome, contexto=200):
    """Extrai um trecho do texto ao redor do nome encontrado."""
    idx = texto.upper().find(nome.upper())
    if idx == -1:
        return ""
    inicio = max(0, idx - contexto)
    fim = min(len(texto), idx + len(nome) + contexto)
    trecho = texto[inicio:fim]
    trecho = re.sub(r'\n{3,}', '\n\n', trecho)
    return trecho.strip()

# ============================================================
# CRIAR ALERTA NO BANCO
# ============================================================
def criar_alerta(sb, colaborador, trecho, url, data_publicacao, secao=""):
    try:
        # Verificar duplicata
        existing = sb.table("avisos").select("id").eq("nome_completo", colaborador["nome"]).eq("fonte", "DOE_TCDF").eq("data_publicacao", data_publicacao).execute()
        if existing.data:
            return False
        
        sb.table("avisos").insert({
            "nome_completo": colaborador["nome"],
            "matricula": colaborador.get("matricula", ""),
            "fonte": "DOE_TCDF",
            "tipo_alerta": "PUBLICACAO_NOME",
            "trecho_publicacao": trecho[:2000],
            "data_publicacao": data_publicacao,
            "url_origem": url,
            "destinatario_id": colaborador.get("matricula", ""),
            "lido": False,
            "validado": False,
            "ativo": 1,
            "mensagem": f"Nome encontrado no DOE-TCDF ({secao}): {colaborador['nome']}"
        }).execute()
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao criar alerta para {colaborador['nome']}: {e}")
        return False

# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================
def main():
    print("=" * 60)
    print("MONITOR DOE-TCDF — Diário Oficial Eletrônico do TCDF")
    print(f"Execução: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)
    
    sb = get_supabase()
    if not sb:
        print("[FALHA] Não foi possível conectar ao Supabase")
        return
    
    # 1. Buscar colaboradores ativos
    colaboradores = buscar_colaboradores(sb)
    print(f"\n[1/4] {len(colaboradores)} colaboradores ativos encontrados")
    
    if not colaboradores:
        print("[FALHA] Nenhum colaborador encontrado")
        return
    
    # 2. Buscar edição do DOE-TCDF
    print(f"\n[2/4] Acessando portal DOE-TCDF...")
    dia_semana = datetime.now().weekday()
    
    # Pular finais de semana (DOE-TCDF não publica)
    if dia_semana >= 5:
        print("  Final de semana — DOE-TCDF não publica. Encerrando.")
        return
    
    texto_completo, titulo_edicao = buscar_edicao_doe()
    
    if not texto_completo:
        print("[AVISO] Não foi possível obter o conteúdo do DOE-TCDF hoje")
        return
    
    print(f"  Edição encontrada: {titulo_edicao or 'Não identificada'}")
    print(f"  Tamanho do texto: {len(texto_completo)} caracteres")
    
    # 3. Extrair publicações individuais
    print(f"\n[3/4] Extraindo publicações...")
    
    # Buscar HTML bruto novamente para extrair blocos
    try:
        resp = requests.get(DOE_BASE, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        publicacoes = buscar_extratos_doe(resp.text)
    except:
        publicacoes = [{"texto": texto_completo, "secao": "Geral"}]
    
    print(f"  {len(publicacoes)} publicação(ões) extraída(s)")
    
    # 4. Procurar nomes dos colaboradores
    print(f"\n[4/4] Procurando nomes dos colaboradores...")
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    total_alertas = 0
    
    for pub in publicacoes:
        texto = pub["texto"]
        secao = pub["secao"]
        
        for col in colaboradores:
            nome = col["nome"]
            if nome.upper() in texto.upper():
                trecho = extrair_trecho(texto, nome)
                if trecho:
                    if criar_alerta(sb, col, trecho, DOE_BASE, data_hoje, secao):
                        total_alertas += 1
                        print(f"  [ALERTA] {nome} encontrado no DOE-TCDF ({secao})!")
    
    # Resumo final
    print("\n" + "=" * 60)
    print(f"EXECUÇÃO CONCLUÍDA")
    print(f"Total de alertas criados: {total_alertas}")
    print(f"Colaboradores monitorados: {len(colaboradores)}")
    print(f"Publicações analisadas: {len(publicacoes)}")
    print("=" * 60)

if __name__ == "__main__":
    main()
