"""
Monitor DODF — Diário Oficial do Distrito Federal
Rastreia publicações que mencionam nomes de colaboradores do TCDF.
Executado diariamente via GitHub Actions.
"""

import os
import re
import json
import requests
from datetime import datetime, timedelta
from supabase import create_client

# ============================================================
# CONFIGURAÇÃO
# ============================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
DODF_BASE = "https://dodf.df.gov.br"

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
    """Busca todos os colaboradores ativos na tabela usuarios_acesso."""
    try:
        result = sb.table("usuarios_acesso").select("nome,setor,vinculo,matricula").eq("ativo", True).execute()
        return result.data or []
    except Exception as e:
        print(f"[ERRO] Falha ao buscar colaboradores: {e}")
        return []

# ============================================================
# BUSCAR EDIÇÕES DO DODF
# ============================================================
def buscar_edicoes_dodf(data_alvo):
    """
    Busca as edições do DODF para uma data específica.
    O DODF publica através de um sistema web com API interna.
    Tenta múltiplos endpoints conhecidos.
    """
    edicoes = []
    data_str = data_alvo.strftime("%Y-%m-%d")
    
    # Endpoint 1: API de busca do DODF
    endpoints = [
        f"{DODF_BASE}/api/tipo_edicao?data={data_str}",
        f"{DODF_BASE}/api/edicao?data={data_str}",
    ]
    
    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json"
            })
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    edicoes = data
                    break
                elif isinstance(data, dict) and "edicoes" in data:
                    edicoes = data["edicoes"]
                    break
        except Exception as e:
            print(f"[AVISO] Endpoint {endpoint} falhou: {e}")
            continue
    
    # Fallback: buscar lista de JSONs publicados
    if not edicoes:
        try:
            # O DODF publica JSONs em formato: dodf_XXX_YYYY-MM-DD.json
            for dia_offset in range(0, 3):  # Hoje + 2 dias anteriores
                data_busca = data_alvo - timedelta(days=dia_offset)
                data_busca_str = data_busca.strftime("%Y-%m-%d")
                
                # Tentar buscar a lista de matérias do dia
                url_lista = f"{DODF_BASE}/dodf/materia/listar?data={data_busca_str}"
                resp = requests.get(url_lista, timeout=30, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                if resp.status_code == 200:
                    try:
                        materias = resp.json()
                        if isinstance(materias, list):
                            for mat in materias:
                                mat["data_publicacao"] = data_busca_str
                                edicoes.append(mat)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"[AVISO] Fallback de listagem falhou: {e}")
    
    return edicoes

# ============================================================
# BUSCAR CONTEÚDO DE UMA MATÉRIA
# ============================================================
def buscar_conteudo_materia(co_materia, data_publicacao):
    """Busca o conteúdo completo de uma matéria específica do DODF."""
    try:
        url = f"{DODF_BASE}/dodf/materia/visualizar?co_data={co_materia}"
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code == 200:
            return resp.text, url
    except Exception as e:
        print(f"[AVISO] Falha ao buscar matéria {co_materia}: {e}")
    return None, None

# ============================================================
# BUSCAR TEXTO COMPLETO DO DODF DO DIA
# ============================================================
def buscar_texto_dodf_completo(data_alvo):
    """
    Busca o texto completo de todas as matérias do DODF do dia.
    Usa a API de busca textual do DODF.
    """
    textos = []
    data_str = data_alvo.strftime("%d/%m/%Y")
    
    # Tentar API de busca com termo genérico para listar todas as matérias
    try:
        url_busca = f"{DODF_BASE}/dodf/buscar"
        payload = {
            "data_inicio": data_str,
            "data_fim": data_str,
            "termo": "TCDF",
            "pagina": 1
        }
        resp = requests.post(url_busca, json=payload, timeout=60, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json"
        })
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "resultados" in data:
                for r in data["resultados"]:
                    textos.append({
                        "texto": r.get("texto", ""),
                        "url": r.get("url", ""),
                        "titulo": r.get("titulo", ""),
                        "data": data_str
                    })
            elif isinstance(data, list):
                for r in data:
                    textos.append({
                        "texto": r.get("texto", r.get("conteudo", "")),
                        "url": r.get("url", ""),
                        "titulo": r.get("titulo", ""),
                        "data": data_str
                    })
    except Exception as e:
        print(f"[AVISO] API de busca do DODF falhou: {e}")
    
    return textos

# ============================================================
# EXTRAIR TRECHO RELEVANTE
# ============================================================
def extrair_trecho(texto, nome, contexto=200):
    """Extrai um trecho do texto ao redor do nome encontrado."""
    idx = texto.find(nome)
    if idx == -1:
        return ""
    inicio = max(0, idx - contexto)
    fim = min(len(texto), idx + len(nome) + contexto)
    trecho = texto[inicio:fim]
    # Limpar quebras de linha excessivas
    trecho = re.sub(r'\n{3,}', '\n\n', trecho)
    return trecho.strip()

# ============================================================
# CRIAR ALERTA NO BANCO
# ============================================================
def criar_alerta(sb, colaborador, trecho, url, data_publicacao):
    """Insere um alerta na tabela avisos."""
    try:
        # Verificar se já existe alerta duplicado
        existing = sb.table("avisos").select("id").eq("nome_completo", colaborador["nome"]).eq("fonte", "DODF").eq("data_publicacao", data_publicacao).execute()
        if existing.data:
            return False  # Já existe
        
        sb.table("avisos").insert({
            "nome_completo": colaborador["nome"],
            "matricula": colaborador.get("matricula", ""),
            "fonte": "DODF",
            "tipo_alerta": "PUBLICACAO_NOME",
            "trecho_publicacao": trecho[:2000],
            "data_publicacao": data_publicacao,
            "url_origem": url,
            "destinatario_id": colaborador.get("matricula", ""),
            "lido": False,
            "validado": False,
            "ativo": 1,
            "mensagem": f"Nome encontrado no DODF: {colaborador['nome']}"
        }).execute()
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao criar alerta para {colaborador['nome']}: {e}")
        return False

# ============================================================
# VERIFICAR ALERTAS DE CONTRATO DE ESTÁGIO
# ============================================================
def verificar_contrato_estagio(sb, colaboradores):
    """Verifica se há menções a contratos de estágio no DODF."""
    alertas_criados = 0
    try:
        estagiarios = [c for c in colaboradores if c.get("vinculo") == "Estagiário"]
        if not estagiarios:
            return 0
        
        # Buscar edições dos últimos 7 dias
        for dias_atras in range(0, 8):
            data_busca = datetime.now() - timedelta(days=dias_atras)
            data_str = data_busca.strftime("%Y-%m-%d")
            
            textos = buscar_texto_dodf_completo(data_busca)
            
            for item in textos:
                texto = item.get("texto", "").upper()
                url = item.get("url", "")
                
                # Procurar por "CONTRATO DE ESTÁGIO" + nome do estagiário
                if "CONTRATO" in texto and "ESTÁGIO" in texto:
                    for est in estagiarios:
                        nome_upper = est["nome"].upper()
                        if nome_upper in texto:
                            trecho = extrair_trecho(texto, nome_upper)
                            if trecho:
                                if criar_alerta(sb, est, trecho, url, data_str):
                                    alertas_criados += 1
                                    print(f"  [ESTÁGIO] Alerta criado: {est['nome']}")
    except Exception as e:
        print(f"[ERRO] Verificação de contrato de estágio falhou: {e}")
    
    return alertas_criados

# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================
def main():
    print("=" * 60)
    print("MONITOR DODF — Diário Oficial do Distrito Federal")
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
    
    # 2. Buscar texto do DODF de hoje (e ontem como fallback)
    total_alertas = 0
    
    for dias_atras in range(0, 2):  # Hoje e ontem
        data_busca = datetime.now() - timedelta(days=dias_atras)
        data_str = data_busca.strftime("%Y-%m-%d")
        dia_semana = data_busca.weekday()
        
        # Pular finais de semana (DODF não publica)
        if dia_semana >= 5:
            print(f"\n[2/4] {data_str} — Final de semana, pulando...")
            continue
        
        print(f"\n[2/4] Buscando DODF de {data_str}...")
        textos = buscar_texto_dodf_completo(data_busca)
        
        if not textos:
            print(f"  [AVISO] Nenhuma matéria encontrada para {data_str}")
            continue
        
        print(f"  {len(textos)} matéria(s) encontrada(s)")
        
        # 3. Procurar nomes dos colaboradores
        print(f"\n[3/4] Procurando nomes dos colaboradores...")
        for item in textos:
            texto = item.get("texto", "")
            url = item.get("url", "")
            
            if not texto:
                continue
            
            for col in colaboradores:
                nome = col["nome"]
                # Buscar nome completo (case-insensitive)
                if nome.upper() in texto.upper():
                    trecho = extrair_trecho(texto, nome)
                    if trecho:
                        if criar_alerta(sb, col, trecho, url, data_str):
                            total_alertas += 1
                            print(f"  [ALERTA] {nome} encontrado no DODF!")
    
    # 4. Verificar contratos de estágio
    print(f"\n[4/4] Verificando contratos de estágio...")
    alertas_estagio = verificar_contrato_estagio(sb, colaboradores)
    total_alertas += alertas_estagio
    
    # Resumo final
    print("\n" + "=" * 60)
    print(f"EXECUÇÃO CONCLUÍDA")
    print(f"Total de alertas criados: {total_alertas}")
    print(f"Colaboradores monitorados: {len(colaboradores)}")
    print("=" * 60)

if __name__ == "__main__":
    main()
