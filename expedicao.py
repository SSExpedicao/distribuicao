import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import time
import unicodedata
import difflib
from st_supabase_connection import SupabaseConnection

# ==========================================
# 1. FRONTEND: CONFIGURAÇÃO INICIAL DA PÁGINA
# ==========================================
st.set_page_config(page_title="Sistema de Sessões", layout="wide")

# ==========================================
# 2. BACKEND: CONEXÃO COM A NUVEM SUPABASE
# ==========================================
try:
    conn = st.connection("supabase", type=SupabaseConnection)
except Exception as e:
    st.error(f"Erro crítico: Não foi possível conectar ao Supabase. Verifique seu secrets.toml. Detalhe: {e}")
    st.stop()

def normalizar_texto(texto):
    """Remove acentos, espaços extras e deixa tudo minúsculo para comparação."""
    if not texto or str(texto).strip() == "": return ""
    texto = str(texto).strip().lower()
    # Remove os acentos matematicamente
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto

def higienizar_colaborador(nome_digitado, lista_oficial_nomes):
    """Compara o que foi digitado com a lista oficial da equipe."""
    if not nome_digitado or str(nome_digitado).strip() == "": return ""
    
    nome_norm = normalizar_texto(nome_digitado)
    
    # 1. Tenta correspondência exata primeiro (ignorando acentos e maiúsculas)
    for nome_oficial in lista_oficial_nomes:
        if nome_norm == normalizar_texto(nome_oficial):
            return nome_oficial
            
    # 2. Se não achou exato, usa Inteligência de Similaridade (erros de digitação)
    lista_norm = [normalizar_texto(n) for n in lista_oficial_nomes]
    matches = difflib.get_close_matches(nome_norm, lista_norm, n=1, cutoff=0.75)
    
    if matches:
        indice = lista_norm.index(matches[0])
        return lista_oficial_nomes[indice]
        
    # 3. É UM NOME TOTALMENTE NOVO
    return str(nome_digitado).strip().title()

def higienizar_dados(processo, relator=""):
    proc_limpo = str(processo).strip()
    if proc_limpo.lower().endswith("-e"):
        proc_limpo = proc_limpo[:-2]
        
    rel_limpo = str(relator).strip().upper()
    mapa_relatores = {
        "RR": "GCRR", "AM": "GCAM", "PT": "GCPT", 
        "AC": "GCAC", "IM": "GCIM", "MM": "GCMM", "VF": "GAVF"
    }
    if rel_limpo in mapa_relatores:
        rel_limpo = mapa_relatores[rel_limpo]
        
    return proc_limpo, rel_limpo
    
def init_db():
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
        st.sidebar.error(f"Aviso: Erro ao iniciar banco de dados (Equipe). {e}")

def gerenciar_usuario(acao, nome_atual, novo_nome=None, expedicao=0, revisao=0, cargo="Assessor"):
    try:
        if acao == 'adicionar': 
            conn.client.table("equipe").insert({"nome": nome_atual, "expedicao": expedicao, "revisao": revisao, "cargo": cargo}).execute()
        elif acao == 'remover': 
            conn.client.table("equipe").delete().eq("nome", nome_atual).execute()
        elif acao == 'substituir': 
            conn.client.table("equipe").update({"nome": novo_nome, "expedicao": expedicao, "revisao": revisao, "cargo": cargo}).eq("nome", nome_atual).execute()
        elif acao == 'editar': 
            conn.client.table("equipe").update({"expedicao": expedicao, "revisao": revisao, "cargo": cargo}).eq("nome", nome_atual).execute()
        return True, "✅ Operação realizada com sucesso!"
    except Exception as e: 
        return False, f"❌ Erro no banco de dados: {e}"

def carregar_equipes():
    try:
        resposta = conn.client.table("equipe").select("nome").order("nome").execute()
        todos = [linha['nome'] for linha in resposta.data]
        return todos, todos, todos
    except Exception as e:
        st.error(f"Erro ao tentar ler a equipe no Supabase: {e}")
        return [], [], []

def renomear_sessao(nome_antigo, novo_nome, tipo_sessao_alvo):
    try:
        conn.client.table("processos").update({"nome_sessao": novo_nome}).eq("nome_sessao", nome_antigo).eq("tipo_sessao", tipo_sessao_alvo).execute()
        return True, f"✅ Número atualizado para: {novo_nome}"
    except Exception as e: return False, f"❌ Erro ao renomear: {e}"

def remover_processo(numero_processo, nome_sessao, motivo):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        resultado = conn.client.table("processos").select("id, relator").eq("numero_processo", numero_processo).eq("nome_sessao", nome_sessao).execute().data
        if not resultado: return False, f"❌ Processo '{numero_processo}' não encontrado na sessão do dia {nome_sessao}."
        id_proc, relator = resultado[0]['id'], resultado[0]['relator']
        conn.client.table("processos_excluidos").insert({"numero_processo": numero_processo, "relator": relator, "data_exclusao": agora, "motivo": motivo}).execute()
        conn.client.table("processos").delete().eq("id", id_proc).execute()
        return True, f"✅ Processo '{numero_processo}' removido e enviado para o histórico de exclusões!"
    except Exception as e: return False, f"❌ Erro: {e}"

def apagar_sessao_especifica(tipo_sessao, nome_sessao, motivo):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        processos_sessao = conn.client.table("processos").select("numero_processo, relator").eq("tipo_sessao", tipo_sessao).eq("nome_sessao", nome_sessao).execute().data
        if motivo not in ["Incluído errado", "Teste"]:
            for proc in processos_sessao:
                conn.client.table("processos_excluidos").insert({"numero_processo": proc['numero_processo'], "relator": proc['relator'], "data_exclusao": agora, "motivo": motivo}).execute()
        conn.client.table("processos").delete().eq("tipo_sessao", tipo_sessao).eq("nome_sessao", nome_sessao).execute()
    except Exception as e:
        st.error(f"Erro ao apagar sessão: {e}")

def carregar_excluidos():
    try: 
        dados = buscar_todos_paginado("processos_excluidos")
        return pd.DataFrame(dados)
    except: 
        return pd.DataFrame()
    
def processo_existe(numero_processo, nome_sessao):
    try:
        res = conn.client.table("processos").select("id", count="exact").eq("numero_processo", numero_processo).eq("nome_sessao", nome_sessao).execute()
        return res.count > 0
    except: return False

def marcar_urgente(numero_processo):
    numero_processo, _ = higienizar_dados(numero_processo)
    try:
        res = conn.client.table("processos").select("id").eq("numero_processo", numero_processo).eq("despachado", 0).execute().data
        if not res: return False, f"❌ Processo {numero_processo} não encontrado nas sessões ativas. Insira-o na sua pauta atual primeiro."
        
        for p in res:
            conn.client.table("processos").update({"urgente": 1}).eq("id", p['id']).execute()
        return True, f"🚨 Processo {numero_processo} destacado como URGENTE!"
    except Exception as e: return False, f"❌ Erro: {e}"
        
def atualizar_processo(id_processo, mudancas):
    if not mudancas: return
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    payload = {}
    for col_banco, val in mudancas.items():
        payload[col_banco] = val
        if col_banco == 'expedido_ok': payload["data_expedido"] = agora if val == 1 else None
        elif col_banco == 'revisado_ok': payload["data_revisado"] = agora if val == 1 else None
        elif col_banco == 'despachado': payload["data_conclusao"] = agora if val == 1 else None
    try: 
        conn.client.table("processos").update(payload).eq("id", id_processo).execute()
    except Exception as e: 
        st.toast(f"Falha ao atualizar banco: {e}")

def obter_expedidor(opcoes, nome_sessao):
    if len(opcoes) == 1: return opcoes[0]
    try:
        res = conn.client.table("processos").select("expedicao").execute().data
        contagem = {nome: 0 for nome in opcoes}
        for row in res:
            exp = row.get('expedicao')
            if exp in contagem:
                contagem[exp] += 1
        
        menor_carga = min(contagem.values())
        empatados = [nome for nome, carga in contagem.items() if carga == menor_carga]
        
        import random
        return random.choice(empatados)
    except:
        import random
        return random.choice(opcoes)

def obter_revisor(expedidor, nome_sessao, opcoes):
    opcoes_validas = [opt for opt in opcoes if opt != expedidor]
    if not opcoes_validas: return expedidor 
    if len(opcoes_validas) == 1: return opcoes_validas[0] 
    
    try:
        res_sessao = conn.client.table("processos").select("expedicao, revisao").eq("nome_sessao", nome_sessao).execute().data
        
        for row in res_sessao:
            e = row.get('expedicao')
            r = row.get('revisao')
            if e == expedidor and r in opcoes_validas:
                return r
                
        mandam_para_mim = set()
        for row in res_sessao:
            e = row.get('expedicao')
            r = row.get('revisao')
            if r == expedidor and e:
                mandam_para_mim.add(e)
        
        opcoes_anti_casal = [opt for opt in opcoes_validas if opt not in mandam_para_mim]
        candidatos = opcoes_anti_casal if opcoes_anti_casal else opcoes_validas
        
        if len(candidatos) == 1: return candidatos[0]
        
        res_hist = conn.client.table("processos").select("revisao").eq("expedicao", expedidor).execute().data
        historico_parcerias = {nome: 0 for nome in candidatos}
        
        for row in res_hist:
            r_hist = row.get('revisao')
            if r_hist in historico_parcerias:
                historico_parcerias[r_hist] += 1
                
        menor_parceria = min(historico_parcerias.values())
        empatados_parceria = [nome for nome, qtd in historico_parcerias.items() if qtd == menor_parceria]
        
        import random
        return random.choice(empatados_parceria)
        
    except:
        import random
        return random.choice(opcoes_validas)

def obter_colaboradores_ausentes_hoje():
    try:
        hoje = datetime.now().date()
        res = conn.client.table("afastamentos").select("usuario, data_inicio, data_fim").execute().data
        ausentes = []
        for row in res:
            ini = datetime.strptime(row['data_inicio'], "%d/%m/%Y").date()
            fim = datetime.strptime(row['data_fim'], "%d/%m/%Y").date()
            if ini <= hoje <= fim:
                ausentes.append(row['usuario'])
        return ausentes
    except:
        return []

def gerar_relatorio_gerencial(mes, ano):
    try:
        df_dados = carregar_dados_sqlite()
        df_afastamentos = carregar_afastamentos()
        
        try:
            df_oficios_banco = pd.DataFrame(conn.client.table("oficios").select("*").eq("oficio_despachado", 1).execute().data)
        except:
            df_oficios_banco = pd.DataFrame()

        if df_dados.empty: return False, "❌ O banco de dados está vazio."
        
        for c in ['data_entrada', 'data_expedido', 'data_revisado', 'data_conclusao']:
            df_dados[c + '_dt'] = pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M:%S", errors='coerce').fillna(
                                  pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M", errors='coerce'))
        
        df_dados['ano_filtro'] = df_dados['data_entrada_dt'].dt.year
        df_dados['mes_filtro'] = df_dados['data_entrada_dt'].dt.month
        
        if mes == 0:
            df_filtrado = df_dados[df_dados['ano_filtro'] == ano].copy()
            periodo_str = f"ANUAL (ANO INTEIRO DE {ano})"
        else:
            df_filtrado = df_dados[(df_dados['ano_filtro'] == ano) & (df_dados['mes_filtro'] == mes)].copy()
            nomes_meses = {1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL", 5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO", 9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"}
            periodo_str = f"{nomes_meses[mes]} DE {ano}"
            
        df_concluidos = df_filtrado[df_filtrado['despachado'] == 1].copy()
        df_tempo_real = df_concluidos[df_concluidos['data_entrada'] != df_concluidos['data_conclusao']].copy()
        
        agora_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
        linhas = []
        linhas.append("====================================================")
        linhas.append("        S.A.D.E. - RELATÓRIO GERENCIAL OPERACIONAL  ")
        linhas.append(f"        PERÍODO: {periodo_str}                      ")
        linhas.append(f"        EMISSÃO: {agora_str}                        ")
        linhas.append("====================================================\n")
        
        # 1. RESUMO EXECUTIVO
        linhas.append("1. RESUMO EXECUTIVO DE PRODUTIVIDADE")
        linhas.append("----------------------------------------------------")
        if not df_concluidos.empty:
            total_p = len(df_concluidos)
            total_s = df_concluidos['nome_sessao'].nunique()
            total_u = len(df_concluidos[df_concluidos['urgente'] == 1])
            linhas.append(f" -> Total de Processos Concluídos e Despachados: {total_p}")
            linhas.append(f" -> Total de Sessões Consolidadas no Período: {total_s}")
            linhas.append(f" -> Demandas Críticas (Urgências) Atendidas com Sucesso: {total_u}\n")
        else:
            linhas.append(" -> Nenhum processo finalizado encontrado neste período de tempo.\n")
            
        # 2. DISTRIBUIÇÃO OPERACIONAL
        linhas.append("2. DISTRIBUIÇÃO OPERACIONAL DA EQUIPE (VOLUMETRIA)")
        linhas.append("----------------------------------------------------")
        if not df_concluidos.empty:
            linhas.append("[ETAPA DE ELABORAÇÃO / EXPEDIÇÃO]")
            exp_v = df_concluidos['expedicao'].value_counts()
            for nome, qtd in exp_v.items(): linhas.append(f"   - {nome}: {qtd} processo(s)")
            linhas.append("\n[ETAPA DE CONFERÊNCIA / REVISÃO]")
            rev_v = df_concluidos['revisao'].value_counts()
            for nome, qtd in rev_v.items(): linhas.append(f"   - {nome}: {qtd} processo(s)")
            linhas.append("")
        else:
            linhas.append(" -> Sem registros de volumetria por equipe no período selecionado.\n")
            
        # 3. EFICIÊNCIA DE TEMPOS
        linhas.append("3. EFICIÊNCIA DE TEMPOS E CADÊNCIA (MÉDIAS REAIS)")
        linhas.append("----------------------------------------------------")
        if not df_tempo_real.empty:
            df_tempo_real['min_exp'] = (df_tempo_real['data_expedido_dt'] - df_tempo_real['data_entrada_dt']).dt.total_seconds() / 60
            df_tempo_real['min_rev'] = (df_tempo_real['data_revisado_dt'] - df_tempo_real['data_expedido_dt']).dt.total_seconds() / 60
            df_tempo_real['min_total'] = (df_tempo_real['data_conclusao_dt'] - df_tempo_real['data_entrada_dt']).dt.total_seconds() / 60
            def fmt(m):
                if pd.isna(m) or m < 0: return "N/A"
                return f"{int(m)} min" if m < 60 else f"{int(m)//60}h {int(m)%60}m"
            linhas.append(f" -> Tempo Médio de Elaboração (Expedição): {fmt(df_tempo_real['min_exp'].mean())}")
            linhas.append(f" -> Tempo Médio de Conferência (Revisão): {fmt(df_tempo_real['min_rev'].mean())}")
            linhas.append(f" -> Tempo de Ciclo Total (Entrada ao Despacho): {fmt(df_tempo_real['min_total'].mean())}\n")
        else:
            linhas.append(" -> Indicadores de tempo real indisponíveis para o intervalo selecionado.\n")
            
        # 4. CONTROLE DE OFÍCIOS
        linhas.append("4. CONTROLE E PRODUTIVIDADE DE OFÍCIOS")
        linhas.append("----------------------------------------------------")
        if not df_oficios_banco.empty and not df_filtrado.empty:
            processos_periodo = df_filtrado['numero_processo'].tolist()
            df_oficios_filtrado = df_oficios_banco[df_oficios_banco['numero_processo'].isin(processos_periodo)].copy()
            
            if not df_oficios_filtrado.empty:
                total_ofic = len(df_oficios_filtrado)
                proc_com_ofic = df_oficios_filtrado['numero_processo'].nunique()
                media_ofic = round(total_ofic / proc_com_ofic, 1) if proc_com_ofic > 0 else 0
                ofic_jur = len(df_oficios_filtrado[df_oficios_filtrado['categoria'] == 'Jurisdicionado'])
                ofic_n_jur = total_ofic - ofic_jur
                
                linhas.append(f" -> Total de Ofícios Expedidos e Despachados: {total_ofic}")
                linhas.append(f" -> Média de Ofícios por Processo Atendido: {media_ofic}")
                linhas.append(f" -> Ofícios para Órgãos Jurisdicionados: {ofic_jur}")
                linhas.append(f" -> Ofícios para Não Jurisdicionados (Empresas/Interessados): {ofic_n_jur}")
                linhas.append("\n[EMISSÃO DE OFÍCIOS POR COLABORADOR]")
                ofic_rank = df_oficios_filtrado['quem_expediu'].value_counts()
                for nome, qtd in ofic_rank.items():
                    linhas.append(f"   - {nome}: {qtd} ofício(s) enviado(s)")
                linhas.append("")
            else:
                linhas.append(" -> Nenhum ofício foi expedido para os processos deste período.\n")
        else:
            linhas.append(" -> Dados de ofícios indisponíveis para o intervalo selecionado.\n")

        # 5. CONTROLE DE AFASTAMENTOS
        linhas.append("5. CONTROLE DE DISPONIBILIDADE E AFASTAMENTOS")
        linhas.append("----------------------------------------------------")
        if not df_afastamentos.empty:
            linhas.append("📌 AUSÊNCIAS REGISTRADAS NO PERÍODO:")
            houve_ausencia = False
            for _, row in df_afastamentos.iterrows():
                dt_ini_af = pd.to_datetime(row['data_inicio'], format="%d/%m/%Y", errors='coerce')
                if dt_ini_af.year == ano and (mes == 0 or dt_ini_af.month == mes):
                    linhas.append(f"   - {row['usuario']} ({row['tipo']}): Afastamento de {row['data_inicio']} a {row['data_fim']}")
                    houve_ausencia = True
            if not houve_ausencia: linhas.append("   - Nenhuma ausência ou licença registrada para a equipe neste período.")
        else:
            linhas.append(" -> Sem registros de afastamentos salvos na base de dados.")
            
        # 6. SITUAÇÃO DA QUARENTENA EM TEMPO REAL
        linhas.append("\n6. AUDITORIA ATUAL DE RETRABALHO (SITUAÇÃO DE AGORA)")
        linhas.append("----------------------------------------------------")
        if 'precisa_correcao' in df_dados.columns:
            df_erros_agora = df_dados[(df_dados['precisa_correcao'] == 1) & (df_dados['despachado'] == 0)]
            if not df_erros_agora.empty:
                linhas.append(f" ⚠️ ALERTA: Existem {len(df_erros_agora)} processo(s) travado(s) na Quarentena neste momento:")
                erros_user = df_erros_agora['expedicao'].value_counts()
                for nome, qtd in erros_user.items():
                    linhas.append(f"   - {nome}: {qtd} processo(s) pendente(s) de correção")
            else:
                linhas.append(" ✅ Setor Limpo: Nenhum processo encontra-se na quarentena neste momento.")
        else:
            linhas.append(" -> Indicadores de quarentena indisponíveis.")

        linhas.append("\n====================================================")
        linhas.append("        FIM DO RELATÓRIO - AUDITORIA AUTOMÁTICA     ")
        linhas.append("====================================================")
        return True, "\n".join(linhas)
    except Exception as e:
        return False, f"Erro interno ao compilar relatório: {e}"

def salvar_novo_processo(numero_processo, relator, tipo_sessao, nome_sessao, expedidores_selecionados, revisores_selecionados):
    numero_processo, relator = higienizar_dados(numero_processo, relator)
    
    if processo_existe(numero_processo, nome_sessao): 
        return False, f"❌ O processo já existe nesta mesma sessão ({nome_sessao})."
    
    # 1. Busca mapeamento de cargos do setor para aplicar as travas de direito de acesso
    try:
        equipe_dados = conn.client.table("equipe").select("nome, cargo").execute().data
        cargos = {row['nome']: row.get('cargo', 'Assessor') for row in equipe_dados}
    except:
        cargos = {}

    ausentes = obter_colaboradores_ausentes_hoje()
    
    # ---------------------------------------------------------
    # TRAVA DE SEGURANÇA 1: SESSÃO ADMINISTRATIVA (Exclusivo da Chefia)
    # ---------------------------------------------------------
    if tipo_sessao == "Sessão Administrativa":
        if "Jessyca" not in ausentes and "Jessyca" in expedidores_selecionados:
            exp_filtrados = ["Jessyca"]
            rev_filtrados = ["Jessyca"]
        else:
            # Contingência: Jessyca de férias/atestado -> repassa para Elaine e André
            exp_filtrados = [n for n in ["Elaine", "André"] if n in expedidores_selecionados]
            rev_filtrados = [n for n in ["Elaine", "André"] if n in revisores_selecionados]
            if not exp_filtrados: exp_filtrados = expedidores_selecionados
            if not rev_filtrados: rev_filtrados = revisores_selecionados

    # ---------------------------------------------------------
    # TRAVA DE SEGURANÇA 2: SESSÃO RESERVADA (Estagiários Bloqueados)
    # ---------------------------------------------------------
    elif tipo_sessao == "Sessão Reservada":
        exp_filtrados = [n for n in expedidores_selecionados if cargos.get(n) != "Estagiário"]
        rev_filtrados = [n for n in revisores_selecionados if cargos.get(n) != "Estagiário"]
        
    else:
        # Ordinárias e Virtuais aceitam todo mundo da escala
        exp_filtrados = expedidores_selecionados
        rev_filtrados = revisores_selecionados

    # Proteção para evitar listas vazias caso a escala de pauta falte membros
    if not exp_filtrados: exp_filtrados = expedidores_selecionados
    if not rev_filtrados: rev_filtrados = revisores_selecionados

    # 2. Puxa histórico da sessão de hoje para balanceamento com os candidatos válidos
    res_sessao = conn.client.table("processos").select("expedicao, revisao").eq("nome_sessao", nome_sessao).execute().data
    
    # Distribuição da Expedição
    contagem_exp = {nome: 0 for nome in exp_filtrados}
    for row in res_sessao:
        exp = row.get('expedicao')
        if exp in contagem_exp: contagem_exp[exp] += 1
    
    responsavel_expedicao = min(contagem_exp, key=contagem_exp.get)
    
    # Distribuição da Revisão (Anti-Casal e Rodízio)
    candidatos_revisores = [nome for nome in rev_filtrados if nome != responsavel_expedicao]
    if not candidatos_revisores:
        responsavel_revisao = responsavel_expedicao
    else:
        contagem_rev = {nome: 0 for nome in candidatos_revisores}
        for row in res_sessao:
            rev = row.get('revisao')
            if rev in contagem_rev: contagem_rev[rev] += 1
            
        ja_mandei_para = [row.get('revisao') for row in res_sessao if row.get('expedicao') == responsavel_expedicao]
        candidatos_prioritarios = [nome for nome in candidatos_revisores if nome not in ja_mandei_para]
        
        if candidatos_prioritarios:
            responsavel_revisao = min(candidatos_prioritarios, key=lambda x: contagem_rev[x])
        else:
            responsavel_revisao = min(candidatos_revisores, key=lambda x: contagem_rev[x])
    
    # Inserção Definitiva
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        conn.client.table("processos").insert({
            "numero_processo": numero_processo, "relator": relator, "tipo_sessao": tipo_sessao, 
            "nome_sessao": nome_sessao, "expedicao": responsavel_expedicao, "revisao": responsavel_revisao, 
            "data_entrada": data_atual, "expedido_ok": 0, "revisado_ok": 0, "despachado": 0, "urgente": 0
        }).execute()
        return True, f"✅ Distribuído com Trava de Acesso! Exp: {responsavel_expedicao} ➔ Rev: {responsavel_revisao}"
    except Exception as e:
        return False, f"❌ Erro ao salvar no banco: {e}"

def buscar_todos_paginado(nome_tabela, coluna_eq=None, valor_eq=None):
    todos_dados = []
    inicio = 0
    tamanho_lote = 1000

    while True:
        query = conn.client.table(nome_tabela).select("*")
        if coluna_eq and valor_eq:
            query = query.eq(coluna_eq, valor_eq)

        resposta = query.range(inicio, inicio + tamanho_lote - 1).execute()

        if not resposta.data:
            break

        todos_dados.extend(resposta.data)

        if len(resposta.data) < tamanho_lote:
            break

        inicio += tamanho_lote

    return todos_dados

def carregar_dados_sqlite(tipo_sessao=None):
    try:
        if tipo_sessao:
            dados = buscar_todos_paginado("processos", "tipo_sessao", tipo_sessao)
        else:
            dados = buscar_todos_paginado("processos")
        return pd.DataFrame(dados)
    except Exception as e: 
        st.error(f"Aviso: Erro ao carregar dados do banco: {e}")
        return pd.DataFrame()

def restaurar_backup(df_backup):
    try:
        conn.client.table("processos").delete().neq("numero_processo", "vazio").execute()
        df_backup = df_backup.astype(object).where(pd.notna(df_backup), None)
        records = df_backup.to_dict(orient="records")
        
        for r in records:
            colunas_para_remover = ['id', 'created_at', 'chave_sessao', 'data_entrada_dt', 'data_expedido_dt', 'data_revisado_dt', 'data_conclusao_dt', 'status_num', 'pendente_flag']
            for col in colunas_para_remover:
                if col in r:
                    del r[col]
            
        conn.client.table("processos").insert(records).execute()
        return True, "✅ Dados restaurados com sucesso!"
    except Exception as e: 
        return False, f"❌ Erro ao tentar restaurar: {e}"

def adicionar_aviso(usuario, numero_processo, mensagem):
    try:
        res = conn.client.table("processos").select("id").eq("numero_processo", numero_processo).eq("despachado", 0).execute().data
        if not res: return False, f"❌ Processo '{numero_processo}' não está ativo em nenhuma sessão no momento."
        
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        conn.client.table("avisos").insert({"usuario": usuario, "numero_processo": numero_processo, "mensagem": mensagem, "data_criacao": agora, "ativo": 1}).execute()
        return True, "✅ Aviso publicado no letreiro!"
    except Exception as e: return False, f"❌ Erro: {e}"

def obter_avisos_pendentes():
    hoje = datetime.now().strftime("%d/%m/%Y")
    try:
        df_av = pd.DataFrame(conn.client.table("avisos").select("*").eq("ativo", 1).execute().data)
        df_proc = pd.DataFrame(conn.client.table("processos").select("numero_processo, nome_sessao, despachado").execute().data)
        if df_av.empty: return pd.DataFrame()
        if df_proc.empty: df_proc = pd.DataFrame(columns=['numero_processo', 'nome_sessao', 'despachado'])
        
        if not df_proc.empty:
            df_proc = df_proc.sort_values(by='despachado', ascending=True).drop_duplicates(subset=['numero_processo'], keep='first')
            
        df_avisos = pd.merge(df_av, df_proc, on='numero_processo', how='left')
        df_avisos = df_avisos[(df_avisos['numero_processo'] == '') | (df_avisos['despachado'] == 0)]
        linhas_validas = []
        for index, row in df_avisos.iterrows():
            data_aviso = row['data_criacao'].split()[0]
            if row['usuario'] == 'Todos':
                if data_aviso == hoje: linhas_validas.append(row)
            else: linhas_validas.append(row)
        return pd.DataFrame(linhas_validas) if linhas_validas else pd.DataFrame(columns=df_avisos.columns)
    except: return pd.DataFrame()

def desativar_aviso(id_aviso):
    try: conn.client.table("avisos").update({"ativo": 0}).eq("id", int(id_aviso)).execute()
    except: pass

def carregar_historico_avisos():
    hoje = datetime.now().strftime("%d/%m/%Y")
    try:
        df_av = pd.DataFrame(conn.client.table("avisos").select("*").execute().data)
        df_proc = pd.DataFrame(conn.client.table("processos").select("numero_processo, despachado").execute().data)
        if df_av.empty: return pd.DataFrame(columns=['numero_processo', 'usuario', 'mensagem', 'data_criacao', 'ativo', 'despachado', 'proc_existe', 'status'])
        df_proc['proc_existe'] = df_proc['numero_processo'] if not df_proc.empty else None
        
        if not df_proc.empty:
            df_proc = df_proc.sort_values(by='despachado', ascending=True).drop_duplicates(subset=['numero_processo'], keep='first')
            
        df = pd.merge(df_av, df_proc, on='numero_processo', how='left')
        status_list = []
        for _, row in df.iterrows():
            data_aviso = row['data_criacao'].split()[0]
            if row['ativo'] == 0: status_list.append('❌ Desativado Manualmente')
            elif row['usuario'] == 'Todos' and data_aviso != hoje: status_list.append('⏳ Expirado Automaticamente (23:59h)')
            elif row['numero_processo'] != '' and row['despachado'] == 1: status_list.append('✅ Concluído (Despachado)')
            elif row['numero_processo'] != '' and pd.isna(row.get('proc_existe')): status_list.append('❌ Processo Removido')
            else: status_list.append('⏳ Ativo no Letreiro')
        df['status'] = status_list
        return df
    except: return pd.DataFrame(columns=['numero_processo', 'usuario', 'mensagem', 'data_criacao', 'ativo', 'despachado', 'proc_existe', 'status'])

def salvar_afastamento(usuario, data_inicio, data_fim, tipo):
    try:
        conn.client.table("afastamentos").insert({"usuario": usuario, "data_inicio": data_inicio, "data_fim": data_fim, "tipo": tipo}).execute()
        return True, "✅ Afastamento registrado com sucesso!"
    except Exception as e: return False, f"❌ Erro ao salvar no banco: {e}"

def carregar_afastamentos():
    try: return pd.DataFrame(conn.client.table("afastamentos").select("*").execute().data)
    except: return pd.DataFrame()

def obter_lista_destinatarios(categoria):
    try:
        res = conn.client.table("oficios").select("destinatario").eq("categoria", categoria).execute().data
        nomes = sorted(list(set([row['destinatario'] for row in res if row.get('destinatario')])))
        return nomes
    except:
        return []

def adicionar_oficio(numero_processo, numero_oficio, categoria, tipo_nao_jurisdicionado, destinatario, clonado, fluxo_documento, quem_expediu):
    try:
        conn.client.table("oficios").insert({
            "numero_processo": numero_processo,
            "numero_oficio": numero_oficio,
            "categoria": categoria,
            "tipo_nao_jurisdicionado": tipo_nao_jurisdicionado,
            "destinatario": destinatario,
            "clonado": int(clonado),
            "fluxo_documento": fluxo_documento,
            "quem_expediu": quem_expediu,
            "oficio_despachado": 0
        }).execute()
        return True, "✅ Ofício cadastrado com sucesso!"
    except Exception as e:
        return False, f"❌ Erro ao cadastrar ofício: {e}"

def liberar_processo_chefia(numero_processo, justificativa, usuario="Chefia"):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        res = conn.client.table("processos").select("id").eq("numero_processo", numero_processo).eq("despachado", 0).execute().data
        if not res: return False, f"❌ O processo {numero_processo} não foi encontrado nas sessões ativas ou já foi despachado."
        
        id_proc = res[0]['id']
        
        conn.client.table("auditoria_chefia").insert({
            "numero_processo": numero_processo,
            "justificativa": justificativa,
            "usuario_chefia": usuario,
            "data_liberacao": agora
        }).execute()
        
        conn.client.table("processos").update({
            "expedido_ok": 1,
            "revisado_ok": 1,
            "despachado": 1, 
            "data_conclusao": agora,
            "precisa_correcao": 0
        }).eq("id", id_proc).execute()
        
        return True, f"✅ Processo {numero_processo} forçado para o histórico com sucesso!"
    except Exception as e:
        return False, f"❌ Erro interno: {e}"

def tem_oficio_cadastrado(numero_processo):
    try:
        res = conn.client.table("oficios").select("id", count="exact").eq("numero_processo", numero_processo).execute()
        return res.count > 0
    except: return False

def verificar_oficios_pendentes(numero_processo):
    try:
        res = conn.client.table("oficios").select("id", count="exact").eq("numero_processo", numero_processo).eq("oficio_despachado", 0).execute()
        return res.count > 0 
    except: return False
        
# ==========================================
# 3. FRONTEND: RENDERIZAÇÃO DA INTERFACE UI
# ==========================================
init_db()
EQUIPE_EXPEDICAO, EQUIPE_REVISAO, TODOS_NOMES = carregar_equipes()

st.title("⚖️ S.A.D.E. - Sistema de Automação de Distribuição e Expedição")

df_avisos = obter_avisos_pendentes()
if not df_avisos.empty:
    textos_aviso = []
    for _, row in df_avisos.iterrows():
        textos_aviso.append(f"🚨 <b>{row['usuario']}</b>: Processo <b>{row['numero_processo']}</b> ({row['nome_sessao']}) ➔ {row['mensagem']}")
    texto_marquee = " &nbsp;&nbsp;&nbsp;&nbsp; | &nbsp;&nbsp;&nbsp;&nbsp; ".join(textos_aviso)
    st.markdown(f"""
        <marquee behavior="scroll" direction="left" scrollamount="8" 
                 style="background-color: #ff4b4b; color: white; padding: 10px; 
                        font-size: 18px; border-radius: 5px; margin-bottom: 20px; font-weight: 500;">
            {texto_marquee}
        </marquee>
    """, unsafe_allow_html=True)

if 'gestor_autenticado' not in st.session_state:
    st.session_state.gestor_autenticado = False

aba_inserir, aba_sessoes, aba_oficios, aba_oficios_relatorio, aba_historico, aba_gestao, aba_ajuda = st.tabs([
    "📥 1. Inserir Novos",
    "🗂️ 2. Painel Ativo",
    "✉️ 2.5. Controle de Ofícios",
    "📄 2.7. Relatório de Expedição",
    "🗄️ 3. Histórico",
    "⚙️ 4. Gestão Administrativa (Restrito)",
    "❓ 5. Ajuda & Glossário"
])

nome_sessao_atual = datetime.now().strftime("%d/%m/%Y")
df_geral_status = carregar_dados_sqlite()
sessoes_finalizadas = []

if not df_geral_status.empty and 'despachado' in df_geral_status.columns:
    status_sessoes = {} 
    
    for _, row in df_geral_status.iterrows():
        tipo = str(row.get('tipo_sessao', '')).strip()
        nome = str(row.get('nome_sessao', '')).strip()
        if not tipo or not nome: continue 
        
        chave = f"{tipo} | {nome}"
        val = str(row.get('despachado', 0)).strip().lower()
        is_done = True if val in ['1', '1.0', 'true', 't'] else False
        
        if chave not in status_sessoes:
            status_sessoes[chave] = 0
            
        if not is_done: 
            status_sessoes[chave] += 1
            
    sessoes_finalizadas = [chave for chave, pend in status_sessoes.items() if pend == 0]
    df_geral_status['chave_sessao'] = df_geral_status['tipo_sessao'].astype(str).str.strip() + " | " + df_geral_status['nome_sessao'].astype(str).str.strip()

# ------------------------------------------
# ABA 1: INSERÇÃO E DISTRIBUIÇÃO
# ------------------------------------------
with aba_inserir:
    st.header("Passo 1: Configurar a Sessão Atual")
    with st.container(border=True):
        tipo_sessao = st.selectbox("Destino (Tipo de Sessão)", ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa", "Urgente"])
        
        hoje = datetime.now().strftime("%d/%m/%Y")
        sessoes_ativas = []
        if not df_geral_status.empty:
            sessoes_ativas = sorted(df_geral_status[df_geral_status['despachado'] == 0]['nome_sessao'].unique().tolist())
            
        modo_sessao = st.radio("Nome / Identificação da Sessão:", 
                               ["Usar a data de hoje (Padrão)", 
                                "Adicionar a uma Sessão Existente", 
                                "Digitar nome manualmente"], horizontal=True)
        
        if modo_sessao == "Usar a data de hoje (Padrão)":
            nome_sessao_atual = hoje
        elif modo_sessao == "Adicionar a uma Sessão Existente":
            if sessoes_ativas:
                nome_sessao_atual = st.selectbox("Escolha a Sessão (Unifica os processos na mesma tabela):", sessoes_ativas)
            else:
                st.warning("Nenhuma sessão ativa encontrada. Usando a data de hoje.")
                nome_sessao_atual = hoje
        else:
            nome_sessao_atual = st.text_input("Digite o nome exato (Ex: Sessão 125 - 10/06/2026):", value=hoje)

        if tipo_sessao == "Urgente":
            st.info("🚨 **Modo Urgente:** Marca processos existentes como urgentes (funciona para todos os tipos).")
            expedidores_ativos, revisores_ativos = [], []
        else:
            opcoes_expedicao, opcoes_revisao = EQUIPE_EXPEDICAO.copy(), EQUIPE_REVISAO.copy()
            col3, col4 = st.columns(2)
            with col3: expedidores_ativos = st.multiselect("👥 Quem fará a Expedição nesta sessão?", opcoes_expedicao, default=opcoes_expedicao)
            with col4: revisores_ativos = st.multiselect("👥 Quem fará a Revisão nesta sessão?", opcoes_revisao, default=opcoes_revisao)

    st.markdown("---")
    st.header("Passo 2: Inserir Processos")
    modo_insercao = st.radio("Método de Inserção", ["Digitar um por vez (Manual)", "Importar Planilha (Em lote)"], horizontal=True)

    if modo_insercao == "Digitar um por vez (Manual)":
        with st.form("form_novo_processo", clear_on_submit=True):
            col_p, col_r = st.columns(2)
            with col_p: novo_processo = st.text_input("Número do Processo")
            if tipo_sessao != "Urgente":
                with col_r: novo_relator = st.text_input("Nome do Relator")
            if st.form_submit_button("Verificar e Processar", type="primary"):
                if tipo_sessao == "Urgente":
                    if novo_processo:
                        ok, msg = marcar_urgente(novo_processo)
                        st.success(msg) if ok else st.error(msg)
                else:
                    if not expedidores_ativos or not revisores_ativos: st.error("❌ Escale a equipe no Passo 1.")
                    elif novo_processo and novo_relator:
                        ok, msg = salvar_novo_processo(novo_processo, novo_relator, tipo_sessao, nome_sessao_atual, expedidores_ativos, revisores_ativos)
                        st.success(msg) if ok else st.error(msg)

    elif modo_insercao == "Importar Planilha (Em lote)":
        st.info("💡 **Dica:** Para importar vários processos de uma vez, baixe a planilha modelo, preencha com seus dados e faça o upload abaixo.")
        df_modelo = pd.DataFrame({"Processo": ["12345/2026", "67890/2026"], "Relator": ["Conselheiro A", "Conselheiro B"]})
        csv_modelo = df_modelo.to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Baixar Planilha Modelo (CSV)", data=csv_modelo, file_name="modelo_importacao.csv", mime="text/csv", type="secondary")

        arquivo_upload = st.file_uploader("Arraste sua planilha preenchida (.csv ou .xlsx)", type=["csv", "xlsx"])
        if arquivo_upload is not None:
            df_upload = pd.read_csv(arquivo_upload, encoding='utf-8-sig') if arquivo_upload.name.endswith('.csv') else pd.read_excel(arquivo_upload)
            st.dataframe(df_upload.head(3))
            if st.button("🚀 Iniciar Importação", type="primary"):
                barra_progresso = st.progress(0)
                sucessos = 0
                for index, row in df_upload.iterrows():
                    processo_val = str(row['Processo']).strip() if pd.notna(row.get('Processo')) else ""
                    if tipo_sessao == "Urgente": 
                        ok, msg = marcar_urgente(processo_val)
                    else:
                        relator_val = str(row.get('Relator', '')).strip() if pd.notna(row.get('Relator')) else ""
                        ok, msg = salvar_novo_processo(processo_val, relator_val, tipo_sessao, nome_sessao_atual, expedidores_ativos, revisores_ativos)
                    if ok: sucessos += 1
                    barra_progresso.progress((index + 1) / len(df_upload))
                st.success(f"🎉 Operação Concluída! {sucessos} processos inseridos.")

    # --- FERRAMENTAS DE MANUTENÇÃO (AGORA ALINHADAS CORRETAMENTE FORA DO IF/ELIF) ---
    st.markdown("---")
    st.header("🛠️ Ferramentas de Manutenção da Pauta")
    
    with st.expander("🗑️ Remover Processo ou 🏷️ Renomear Sessão"):
        # --- REMOVER PROCESSO ---
        st.subheader("🗑️ Remover Processo Específico")
        col_rm1, col_rm2, col_rm3, col_rm4 = st.columns([2, 2, 2, 1])
        with col_rm1: proc_para_remover = st.text_input("Nº Processo:")
        with col_rm2:
            datas_disp = sorted(df_geral_status['nome_sessao'].unique(), reverse=True) if not df_geral_status.empty else []
            data_sessao_remover = st.selectbox("Sessão:", datas_disp)
        with col_rm3: motivo_remocao = st.selectbox("Motivo:", ["Fora de pauta", "Incluído errado", "Teste", "Outros"], key="motivo_proc")
        with col_rm4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("❌ Remover", type="primary", use_container_width=True):
                if proc_para_remover and data_sessao_remover:
                    ok, m = remover_processo(proc_para_remover, data_sessao_remover, motivo_remocao)
                    if ok:
                        st.success(m)
                        time.sleep(1.5)
                        st.rerun()
                    else: st.error(m)
        
        st.markdown("---")
        
        # --- NOMEAR SESSÃO ---
        st.subheader("🏷️ Identificar / Nomear Sessão")
        col_sn1, col_sn2, col_sn3, col_sn4 = st.columns([2, 2, 1, 1.5])
        with col_sn1:
            sessao_alvo = st.selectbox("Sessão Alvo:", datas_disp)
        with col_sn2: tipo_alvo = st.selectbox("Tipo:", ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa"])
        with col_sn3: num_oficial = st.text_input("Número:", placeholder="Ex: 125")
        with col_sn4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🏷️ Confirmar", type="primary", use_container_width=True):
                if num_oficial and sessao_alvo:
                    if " - " in sessao_alvo:
                        data_pura = sessao_alvo.split(" - ")[-1].strip()
                        novo_nome = f"Sessão {num_oficial} - {data_pura}"
                    else: novo_nome = f"Sessão {num_oficial} - {sessao_alvo}"
                    ok, msg = renomear_sessao(sessao_alvo, novo_nome, tipo_alvo)
                    if ok:
                        st.success(msg)
                        time.sleep(1.5)
                        st.rerun()
                    else: st.error(msg)
                else: st.warning("⚠️ Digite o número da pauta.")

# ------------------------------------------
# ABA 2: PAINEL DAS SESSÕES ATIVAS
# ------------------------------------------
with aba_sessoes:
    col_saudacao, col_filtro_p = st.columns([2, 1])
    with col_saudacao:
        st.markdown("### 💼 Minha Mesa de Trabalho")
    with col_filtro_p:
        colab_painel = st.selectbox(
            "Filtrar processos por responsável:", 
            ["👁️ Ver Todos os Processos do Setor"] + TODOS_NOMES,
            key="filtro_colab_painel_ativo",
            label_visibility="collapsed"
        )
    
    if colab_painel != "👁️ Ver Todos os Processos do Setor":
        st.markdown(f"👋 **Bom trabalho, {colab_painel}!** Exibindo estritamente as demandas onde você é o Expedidor ou o Revisor.")
    
    st.markdown("---")
    
    sub_aba_urg, sub_aba_ord, sub_aba_ordv, sub_aba_res, sub_aba_adm = st.tabs([
        "🚨 0. URGENTES", "🏛️ 1. Ordinária", "💻 2. Ordinária Virtual", "🔒 3. Reservada", "📁 4. Administrativa"
    ])
    def exibir_tabela_interativa(df_filtrado, key_prefix, data_sessao, tipo_sessao_tb):
        titulo_placeholder = st.empty()
        
        # Garante que as colunas de quarentena existam para não dar erro
        if 'precisa_correcao' not in df_filtrado.columns: df_filtrado['precisa_correcao'] = 0
        if 'motivo_correcao' not in df_filtrado.columns: df_filtrado['motivo_correcao'] = ""
        
        # DIVISÃO DA TELA: Normais vs Quarentena
        df_normais = df_filtrado[df_filtrado['precisa_correcao'] == 0].copy()
        df_quarentena = df_filtrado[df_filtrado['precisa_correcao'] == 1].copy()

        # =======================================================
        # 1. TABELA PRINCIPAL (MESA DE TRABALHO)
        # =======================================================
        if not df_normais.empty:
            cols_base = ['id', 'urgente', 'numero_processo', 'relator']
            if tipo_sessao_tb == "Urgente": cols_base.append('tipo_sessao')
            cols_base.extend(['expedicao', 'expedido_ok', 'revisao', 'revisado_ok'])
            
            if tipo_sessao_tb == "Sessão Reservada": cols_base.extend(['enviado_email', 'enviado_mensageria', 'recebido'])
            cols_base.append('despachado')

            df_exibicao = df_normais[cols_base].copy()
            
            # TRADUÇÃO E CRIAÇÃO DAS NOVAS COLUNAS
            df_exibicao['expedido_ok'] = df_exibicao['expedido_ok'].astype(bool)
            df_exibicao['despachado'] = df_exibicao['despachado'].astype(bool)
            
            df_exibicao['Status Revisão'] = df_exibicao['revisado_ok'].apply(lambda val: "✅ OK" if val in [1, 1.0, True, '1'] else "⏳ Pendente")
            df_exibicao['Motivo Devolução'] = "" 
            
            # Remove a antiga coluna bool de revisão
            df_exibicao = df_exibicao.drop(columns=['revisado_ok'])
            
            # --- AJUSTE DA ORDEM DAS COLUNAS ---
            final_cols = ['id', 'urgente', 'numero_processo', 'relator']
            if tipo_sessao_tb == "Urgente": final_cols.append('tipo_sessao')
            final_cols.extend(['expedicao', 'expedido_ok', 'revisao', 'Status Revisão', 'Motivo Devolução'])
            
            if tipo_sessao_tb == "Sessão Reservada": 
                final_cols.extend(['enviado_email', 'enviado_mensageria', 'recebido'])
            final_cols.append('despachado') 
            
            df_exibicao = df_exibicao[final_cols]

            if tipo_sessao_tb == "Sessão Reservada": 
                bool_cols = ['enviado_email', 'enviado_mensageria', 'recebido']
                df_exibicao[bool_cols] = df_exibicao[bool_cols].astype(bool)

            rename_dict = {'numero_processo': 'Processo', 'urgente': 'urgente_flag', 'relator': 'Relator', 'tipo_sessao': 'Rito Original', 'expedicao': 'Expedição', 'expedido_ok': 'Expedido', 'revisao': 'Revisor', 'despachado': 'Despachado'}
            if tipo_sessao_tb == "Sessão Reservada": rename_dict.update({'enviado_email': 'E-mail', 'enviado_mensageria': 'Mensageria', 'recebido': 'Recebido'})

            df_exibicao = df_exibicao.rename(columns=rename_dict)
            styled_df = df_exibicao.style.apply(color_urgentes, axis=1)

            # ------------------------------------------------------------------------
            # A SOLUÇÃO DA BRECHA: Identifica se a Mesa está em modo Global (Leitura)
            # ------------------------------------------------------------------------
            painel_atual = st.session_state.get('filtro_colab_painel_ativo', "👁️ Ver Todos os Processos do Setor")
            # --- LÓGICA DE SUPER-PODER DA CHEFIA ---
            # Verifica quem é o chefe atual no banco
            equipe_data = conn.client.table("equipe").select("nome, cargo").execute().data
            chefes = [row['nome'] for row in equipe_data if row.get('cargo') == "Chefia"]
            
            # O modo de edição é liberado se for a chefia OU se o colaborador selecionado for o responsável
            e_chefia = (painel_atual in chefes)
            
            # Bloqueia a edição apenas se não for chefia E estiver em modo global
            modo_leitura = (painel_atual == "👁️ Ver Todos os Processos do Setor" and not e_chefia)
            
            # --- AJUSTE DAS TRAVAS ---
            # Se for chefia, desabilitamos as travas de ofício e revisão
            # Usaremos 'e_chefia' para decidir se permitimos o despacho sem ofício
            
            cfg_colunas = {
                "id": None, 
                "urgente_flag": None, 
                "Processo": st.column_config.TextColumn(disabled=True), 
                "Relator": st.column_config.TextColumn(disabled=True), 
                "Expedição": st.column_config.SelectboxColumn("Expedição", options=TODOS_NOMES, disabled=modo_leitura, required=True), 
                "Expedido": st.column_config.CheckboxColumn("Expedido", disabled=modo_leitura),
                "Revisor": st.column_config.SelectboxColumn("Revisor", options=TODOS_NOMES, disabled=modo_leitura, required=True),
                "Status Revisão": st.column_config.SelectboxColumn("Ação do Revisor", options=["⏳ Pendente", "✅ OK", "❌ Corrigir"], disabled=modo_leitura, required=True),
                "Motivo Devolução": st.column_config.TextColumn("Motivo (Só se Corrigir)", disabled=modo_leitura),
                "Despachado": st.column_config.CheckboxColumn("Despachado", disabled=modo_leitura)
            }
            if tipo_sessao_tb == "Urgente": cfg_colunas["Rito Original"] = st.column_config.TextColumn("Rito Original", disabled=True)
            if tipo_sessao_tb == "Sessão Reservada": cfg_colunas.update({"E-mail": st.column_config.CheckboxColumn("E-mail", disabled=modo_leitura), "Mensageria": st.column_config.CheckboxColumn("Mensageria", disabled=modo_leitura), "Recebido": st.column_config.CheckboxColumn("Recebido", disabled=modo_leitura)})

            pendentes = len(df_exibicao[df_exibicao['Despachado'] == False])
            if pendentes > 0: titulo_placeholder.markdown(f"##### 📅 {data_sessao} | ⏳ {pendentes} Pendentes", unsafe_allow_html=True)
            else: titulo_placeholder.markdown(f"##### 📅 {data_sessao} | ✅ Concluído!", unsafe_allow_html=True)

            # Alerta amigável avisando que a mesa global é apenas para consulta
            if modo_leitura:
                st.info("💡 **Mesa em Modo Leitura (Setor Global):** Para avaliar, revisar ou despachar um processo, selecione o seu nome no filtro do topo da página.")

            with st.form(key=f"form_{key_prefix}_{data_sessao}"):
                edited_df = st.data_editor(styled_df, column_config=cfg_colunas, hide_index=True, use_container_width=True, key=f"{key_prefix}_{data_sessao}")
                submit_button = st.form_submit_button("💾 Salvar Alterações desta Sessão", type="primary", disabled=modo_leitura)

                if submit_button and not modo_leitura:
                    alteracoes_feitas = 0
                    bloqueio_ativo = False
                    
                    for i in range(len(edited_df)):
                        linha_nova = edited_df.iloc[i].to_dict()
                        linha_antiga = df_exibicao.iloc[i].to_dict()
                        if linha_nova != linha_antiga:
                            
                            # A CHEFIA PULA AS TRAVAS!
                            if not e_chefia:
                                # TRAVA: Quem pode mudar a revisão?
                                if linha_nova['Status Revisão'] != linha_antiga['Status Revisão']:
                                    if colab_painel != "👁️ Ver Todos os Processos do Setor" and colab_painel != linha_nova['Revisor']:
                                        st.error(f"🚨 ERRO: Apenas o Revisor ({linha_nova['Revisor']}) pode alterar o Status!")
                                        bloqueio_ativo = True
                                        continue
                                
                                # TRAVA MESTRE: Ofícios e OK do Revisor
                                if linha_nova.get('Despachado') == True and linha_antiga.get('Despachado') == False:
                                    if linha_nova.get('Status Revisão') != "✅ OK":
                                        st.error(f"🚨 ERRO: Só é possível despachar após o '✅ OK' do Revisor!")
                                        bloqueio_ativo = True
                                        continue
                                    
                                    rito_avaliado = linha_nova.get('Rito Original', tipo_sessao_tb)
                                    if rito_avaliado in ["Sessão Ordinária", "Sessão Ordinária Virtual"]:
                                        isento = conn.client.table("processos").select("precisa_correcao").eq("numero_processo", linha_nova['Processo']).execute().data
                                        if not (isento and isento[0].get('precisa_correcao') == 2):
                                            if not tem_oficio_cadastrado(linha_nova['Processo']) or verificar_oficios_pendentes(linha_nova['Processo']):
                                                st.error(f"🚨 ERRO: Processo {linha_nova['Processo']} pendente de ofícios!")
                                                bloqueio_ativo = True
                                                continue
                                                        
                            mudancas = {}
                            
                            if linha_nova['Status Revisão'] != linha_antiga['Status Revisão']:
                                if linha_nova['Status Revisão'] == "❌ Corrigir":
                                    motivo = str(linha_nova.get('Motivo Devolução', '')).strip()
                                    if not motivo:
                                        st.error(f"🚨 Processo {linha_nova['Processo']}: Você marcou para corrigir, mas esqueceu de digitar o 'Motivo'!")
                                        bloqueio_ativo = True
                                        continue
                                    else:
                                        mudancas['precisa_correcao'] = 1
                                        mudancas['motivo_correcao'] = motivo
                                        mudancas['revisado_ok'] = 0
                                elif linha_nova['Status Revisão'] == "✅ OK":
                                    mudancas['revisado_ok'] = 1
                                    mudancas['precisa_correcao'] = 0
                                else:
                                    mudancas['revisado_ok'] = 0

                            mapa_banco_simples = {'Expedição': 'expedicao', 'Revisor': 'revisao', 'Expedido': 'expedido_ok', 'Despachado': 'despachado', 'E-mail': 'enviado_email', 'Mensageria': 'enviado_mensageria', 'Recebido': 'recebido'}
                            for col_tela, col_banco in mapa_banco_simples.items():
                                if col_tela in línea_nova and linha_nova[col_tela] != linha_antiga.get(col_tela):
                                    val = linha_nova[col_tela]
                                    mudancas[col_banco] = 1 if val else 0 if isinstance(val, bool) else val

                            if mudancas:
                                atualizar_processo(int(linha_nova['id']), mudancas)
                                alteracoes_feitas += 1
                                
                    if alteracoes_feitas > 0 and not bloqueio_ativo:
                        st.toast(f"✅ {alteracoes_feitas} processo(s) atualizado(s) no banco!")
                        time.sleep(1) 
                        st.rerun()
                    elif bloqueio_ativo:
                        st.warning("⚠️ Algumas alterações foram canceladas pela Trava de Segurança.")
                        
        # =======================================================
        # 2. TABELA DE QUARENTENA E DEVOLUÇÃO
        # =======================================================
        st.markdown("<br>", unsafe_allow_html=True)
        if not df_quarentena.empty:
            st.error("🚨 PROCESSOS EM QUARENTENA (Revisor encontrou erros que precisam ser arrumados)")
            
            df_q_exib = df_quarentena[['id', 'numero_processo', 'relator', 'expedicao', 'revisao', 'motivo_correcao']].copy()
            # Se estiver na mesa global, o Expedidor também não pode dar baixa na quarentena por aqui
            df_q_exib['Ação do Expedidor'] = False 
            df_q_exib = df_q_exib.rename(columns={'numero_processo':'Processo', 'relator':'Relator', 'expedicao':'Expedidor', 'revisao': 'Revisor', 'motivo_correcao':'Motivo Apontado'})
            
            with st.form(key=f"form_quarentena_{key_prefix}_{data_sessao}"):
                # Usa a variável 'modo_leitura' para desativar o checkbox caso seja a pauta global
                q_edited = st.data_editor(
                    df_q_exib, 
                    hide_index=True, 
                    use_container_width=True,
                    column_config={
                        "id": None,
                        "Processo": st.column_config.TextColumn(disabled=True),
                        "Relator": st.column_config.TextColumn(disabled=True),
                        "Expedidor": st.column_config.TextColumn(disabled=True),
                        "Revisor": st.column_config.TextColumn(disabled=True),
                        "Motivo Apontado": st.column_config.TextColumn(disabled=True),
                        "Ação do Expedidor": st.column_config.CheckboxColumn("✅ Já arrumei. Devolver p/ Revisor!", disabled=modo_leitura)
                    }
                )
                
                if st.form_submit_button("🔄 Confirmar Correções", type="primary", disabled=modo_leitura):
                    q_alterados = 0
                    for i in range(len(q_edited)):
                        if q_edited.iloc[i]['Ação do Expedidor'] == True:
                            id_proc = int(q_edited.iloc[i]['id'])
                            
                            conn.client.table("processos").update({
                                "precisa_correcao": 0, 
                                "motivo_correcao": "", 
                                "revisado_ok": 0 
                            }).eq("id", id_proc).execute()
                            q_alterados += 1
                            
                    if q_alterados > 0:
                        st.success(f"✅ {q_alterados} processo(s) devolvido(s) para a fila de revisão!")
                        time.sleep(1.5)
                        st.rerun()

        st.markdown("---")

         # Identifica quem são os chefes antes de abrir as abas
    equipe_data = conn.client.table("equipe").select("nome, cargo").execute().data
    lista_chefes = [row['nome'] for row in equipe_data if row.get('cargo') == "Chefia"]
    
    # Isso define se o usuário logado tem poderes totais
    e_chefia = (colab_painel in lista_chefes)
    
    with sub_aba_urg:
        st.subheader("🚨 Painel Unificado de Demandas Urgentes")
        df_urg = carregar_dados_sqlite() # Carrega banco amplo
        
        if not df_urg.empty and 'urgente' in df_urg.columns:
            # FILTRA OS URGENTES E IGNORA OS ADMINISTRATIVOS (EXCLUSIVOS DA CHEFIA)
            df_urg = df_urg[(df_urg['urgente'] == 1) & (df_urg['despachado'] == 0) & (df_urg['tipo_sessao'] != "Sessão Administrativa")]
            
            # A lógica mudou: Agora só filtra se não for o modo "Ver Todos" E não for Chefia
            if colab_painel != "👁️ Ver Todos os Processos do Setor" and not e_chefia:
                df_ord = df_ord[(df_ord['expedicao'] == colab_painel) | (df_ord['revisao'] == colab_painel)]
                
            sessoes_com_urgentes = sorted(df_urg['nome_sessao'].unique().tolist())
            
            if sessoes_com_urgentes:
                for data in sessoes_com_urgentes:
                    exibir_tabela_interativa(df_urg[df_urg['nome_sessao'] == data], "urg", data, "Urgente")
            else:
                st.success("✨ Nenhuma pauta crítica ou urgência pendente no momento!")
    with sub_aba_ord:
        df_ord = carregar_dados_sqlite("Sessão Ordinária")
        if not df_ord.empty:
            # BLINDAGEM: Retira os urgentes da pauta comum
            df_ord = df_ord[df_ord['urgente'] == 0]
            
            # A lógica mudou: Agora só filtra se não for o modo "Ver Todos" E não for Chefia
            if colab_painel != "👁️ Ver Todos os Processos do Setor" and not e_chefia:
                 df_ord = df_ord[(df_ord['expedicao'] == colab_painel) | (df_ord['revisao'] == colab_painel)]
            
            sessoes_com_processos = [data for data in df_ord['nome_sessao'].unique() if f"Sessão Ordinária | {str(data).strip()}" not in sessoes_finalizadas]
            
            if sessoes_com_processos:
                for data in sessoes_com_processos:
                    exibir_tabela_interativa(df_ord[df_ord['nome_sessao'] == data], "ord", data, "Sessão Ordinária")
            else:
                st.success("✨ Você não possui nenhum processo ordinário pendente!")

    with sub_aba_ordv:
        df_ordv = carregar_dados_sqlite("Sessão Ordinária Virtual")
        if not df_ordv.empty:
            # BLINDAGEM: Retira os urgentes da pauta comum
            df_ordv = df_ordv[df_ordv['urgente'] == 0]
            
            # A lógica mudou: Agora só filtra se não for o modo "Ver Todos" E não for Chefia
# A lógica mudou: Agora só filtra se não for o modo "Ver Todos" E não for Chefia
            if colab_painel != "👁️ Ver Todos os Processos do Setor" and not e_chefia:
                df_ord = df_ord[(df_ord['expedicao'] == colab_painel) | (df_ord['revisao'] == colab_painel)]
                
            sessoes_com_processos = [data for data in df_ordv['nome_sessao'].unique() if f"Sessão Ordinária Virtual | {str(data).strip()}" not in sessoes_finalizadas]
            
            if sessoes_com_processos:
                for data in sessoes_com_processos:
                    exibir_tabela_interativa(df_ordv[df_ordv['nome_sessao'] == data], "ordv", data, "Sessão Ordinária Virtual")
            else:
                st.success("✨ Você não possui nenhum processo virtual pendente!")

    with sub_aba_res:
        df_res = carregar_dados_sqlite("Sessão Reservada")
        if not df_res.empty:
            # BLINDAGEM: Retira os urgentes da pauta comum
            df_res = df_res[df_res['urgente'] == 0]
            
            # A lógica mudou: Agora só filtra se não for o modo "Ver Todos" E não for Chefia
            if colab_painel != "👁️ Ver Todos os Processos do Setor" and not e_chefia:
                df_ord = df_ord[(df_ord['expedicao'] == colab_painel) | (df_ord['revisao'] == colab_painel)]
                
            sessoes_com_processos = [data for data in df_res['nome_sessao'].unique() if f"Sessão Reservada | {str(data).strip()}" not in sessoes_finalizadas]
            
            if sessoes_com_processos:
                for data in sessoes_com_processos:
                    exibir_tabela_interativa(df_res[df_res['nome_sessao'] == data], "res", data, "Sessão Reservada")
            else:
                st.success("✨ Você não possui nenhum processo reservado pendente!")

    with sub_aba_adm:
        df_adm = carregar_dados_sqlite("Sessão Administrativa")
        if not df_adm.empty:
            # BLINDAGEM: Retira os urgentes da pauta comum
            df_adm = df_adm[df_adm['urgente'] == 0]
            
            # A lógica mudou: Agora só filtra se não for o modo "Ver Todos" E não for Chefia
            if colab_painel != "👁️ Ver Todos os Processos do Setor" and not e_chefia:
                df_ord = df_ord[(df_ord['expedicao'] == colab_painel) | (df_ord['revisao'] == colab_painel)]
                
            sessoes_com_processos = [data for data in df_adm['nome_sessao'].unique() if f"Sessão Administrativa | {str(data).strip()}" not in sessoes_finalizadas]
            
            if sessoes_com_processos:
                for data in sessoes_com_processos:
                    exibir_tabela_interativa(df_adm[df_adm['nome_sessao'] == data], "adm", data, "Sessão Administrativa")
            else:
                st.success("✨ Você não possui nenhum processo administrativo pendente!")

# ------------------------------------------
# ABA 2.5: CONTROLE DE OFÍCIOS E QUARENTENA
# ------------------------------------------
with aba_oficios:
    st.header("✉️ Controle e Expedição de Ofícios")
    
    if df_geral_status.empty or 'despachado' not in df_geral_status.columns or 'tipo_sessao' not in df_geral_status.columns:
        df_ativos_base = pd.DataFrame() 
    else:
        df_ativos_base = df_geral_status[(df_geral_status['despachado'] == 0) & (df_geral_status['tipo_sessao'].isin(['Sessão Ordinária', 'Sessão Ordinária Virtual']))].copy()
    
    if df_ativos_base.empty:
        st.success("✨ Pauta limpa! Nenhum processo aguardando ofícios no momento.")
    else:
        st.subheader("🔍 1. Minha Mesa de Trabalho")
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            tipo_sessao_filtro = st.selectbox("Qual a Sessão?", ["Sessão Ordinária", "Sessão Ordinária Virtual"])
            
        with col_f2:
            quem_expede_global = st.selectbox("Identifique-se (Quem está expedindo?):", TODOS_NOMES)
            
        # O SEGREDO DO FILTRO INDIVIDUAL ESTÁ AQUI:
        df_ativos_filtrado = df_ativos_base[(df_ativos_base['tipo_sessao'] == tipo_sessao_filtro) & (df_ativos_base['expedicao'] == quem_expede_global)]
        
        with col_f3:
            if not df_ativos_filtrado.empty:
                proc_selecionado = st.selectbox("Meus Processos Pendentes:", df_ativos_filtrado['numero_processo'].tolist())
            else:
                st.info("Nenhum processo pendente na sua fila.")
                proc_selecionado = None
                
        st.markdown("---")

        if proc_selecionado:
            proc_data = df_ativos_filtrado[df_ativos_filtrado['numero_processo'] == proc_selecionado].iloc[0]
            if proc_data.get('precisa_correcao') == 1:
                st.error(f"🚨 PROCESSO EM QUARENTENA | Motivo apontado pelo Revisor: **{proc_data.get('motivo_correcao')}**")
                if st.button("✅ Correção Realizada (Retirar da Quarentena)", type="primary"):
                    conn.client.table("processos").update({"precisa_correcao": 0, "motivo_correcao": ""}).eq("numero_processo", proc_selecionado).execute()
                    st.success("Processo corrigido e liberado para a mesa principal!")
                    time.sleep(1.5)
                    st.rerun()
            
            st.subheader("➕ 2. Cadastrar Novo Ofício ou Memorando")
            
            col_o1, col_o2 = st.columns(2)
            with col_o1: 
                cat_oficio = st.selectbox("Categoria:", ["Jurisdicionado", "Não Jurisdicionado", "Memorando (Envio Interno)"])
            with col_o2: 
                if cat_oficio == "Não Jurisdicionado":
                    tipo_nao_jur = st.selectbox("Especificação:", ["Representante", "Direto para Empresa"])
                else:
                    tipo_nao_jur = ""
                    st.write("") 

            lista_dest = obter_lista_destinatarios(cat_oficio)
            opcoes_dest = ["-- Selecionar Existente --"] + lista_dest + ["➕ Cadastrar Novo Destinatário..."]
            dest_selecionado = st.selectbox("Nome do Destinatário (Busca Automática):", opcoes_dest)
            
            dest_final = dest_selecionado
            if dest_selecionado == "➕ Cadastrar Novo Destinatário...":
                dest_final = st.text_input("Digite o nome oficial (O sistema vai aprender este nome para a próxima):")
                
            num_oficio = st.text_input("Nº do Ofício ou Memorando (Ex: 125/2026):")
            
            if cat_oficio == "Jurisdicionado":
                fluxo_doc = "Original no Protocolo | Clone no Processo"
            elif cat_oficio == "Memorando (Envio Interno)":
                fluxo_doc = "Envio Interno (Via Única)"
            else:
                fluxo_doc = "Original no Processo | Clone no Protocolo"
                
            st.info(f"💡 **Regra de Vias Aplicada:** {fluxo_doc}")
            
            if st.button("💾 Adicionar Ofício/Memorando", type="primary", use_container_width=True):
                if dest_final and dest_final != "-- Selecionar Existente --" and num_oficio:
                    ok, m = adicionar_oficio(proc_selecionado, num_oficio, cat_oficio, tipo_nao_jur, dest_final, 1, fluxo_doc, quem_expede_global)
                    
                    # AUTOMAÇÃO: Marca o processo como EXPEDIDO automaticamente no banco
                    agora_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    conn.client.table("processos").update({
                        "precisa_correcao": 0, 
                        "expedido_ok": 1,
                        "data_expedido": agora_str
                    }).eq("numero_processo", proc_selecionado).execute()
                    
                    if ok: 
                        st.success("Ofício gravado e etapa de Expedição concluída!")
                        time.sleep(1)
                        st.rerun()
                    else: st.error(m)
                else:
                    st.warning("⚠️ Preencha o Destinatário e o Número do Ofício.")
                    
            st.markdown("---")

            # -----------------------------------------------------
            # NOVO MÓDULO: ISENÇÃO COM JUSTIFICATIVA OBRIGATÓRIA
            # -----------------------------------------------------
            st.subheader("🚫 3. Isenção de Ofícios (Casos Especiais)")
            col_is1, col_is2 = st.columns([2, 1])
            with col_is1:
                motivo_isencao = st.selectbox("Selecione a Justificativa:", ["Comunicação", "Acórdão", "Pedido de Vista", "Despacho Singular", "Sustentação Oral", "SERCON"])
            with col_is2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🚫 Aplicar Isenção e Expedir", use_container_width=True):
                    agora_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    conn.client.table("processos").update({
                        "precisa_correcao": 2, 
                        "motivo_correcao": f"ISENTO: {motivo_isencao}",
                        "expedido_ok": 1,
                        "data_expedido": agora_str
                    }).eq("numero_processo", proc_selecionado).execute()
                    st.success(f"✅ Processo ISENTO ({motivo_isencao}) e marcado como EXPEDIDO automaticamente!")
                    time.sleep(1.5)
                    st.rerun()

            st.markdown("---")
            
            st.subheader("📋 4. Ofícios Gerados para este Processo")
            try:
                df_oficios = pd.DataFrame(conn.client.table("oficios").select("id, numero_oficio, destinatario, fluxo_documento, oficio_despachado").eq("numero_processo", proc_selecionado).execute().data)
                if not df_oficios.empty:
                    df_oficios['oficio_despachado'] = df_oficios['oficio_despachado'].astype(bool)
                    
                    ed_oficios = st.data_editor(
                        df_oficios,
                        column_config={
                            "id": None, 
                            "numero_oficio": st.column_config.TextColumn("Nº Ofício", disabled=True),
                            "destinatario": st.column_config.TextColumn("Destinatário", disabled=True),
                            "fluxo_documento": st.column_config.TextColumn("Regra da Via", disabled=True),
                            "oficio_despachado": st.column_config.CheckboxColumn("Ofício Despachado?")
                        },
                        hide_index=True, use_container_width=True, key="ed_ofic"
                    )
                    
                    if st.button("💾 Atualizar Status dos Ofícios", type="primary"):
                        alterados = 0
                        for i in range(len(ed_oficios)):
                            id_ofic = int(ed_oficios.iloc[i]['id'])
                            novo_status = 1 if ed_oficios.iloc[i]['oficio_despachado'] else 0
                            status_antigo = 1 if df_oficios.iloc[i]['oficio_despachado'] else 0
                            
                            if novo_status != status_antigo:
                                conn.client.table("oficios").update({"oficio_despachado": novo_status}).eq("id", id_ofic).execute()
                                alterados += 1
                        
                        if alterados > 0:
                            st.success(f"✅ {alterados} ofício(s) atualizado(s)!")
                            time.sleep(1)
                            st.rerun()
                        else: st.warning("Nenhuma alteração feita.")
                else:
                    st.warning("Nenhum ofício cadastrado para este processo ainda.")
            except: pass

# ------------------------------------------
# ABA 2.7: AUDITORIA DE OFÍCIOS E MEMORANDOS
# ------------------------------------------
with aba_oficios_relatorio:
    st.header("📋 Auditoria de Documentos")
    st.write("Visualize o histórico completo de ofícios e memorandos. Use os filtros abaixo para localizar documentos específicos.")

    try:
        # Puxa tudo do banco
        df_auditoria = pd.DataFrame(conn.client.table("oficios").select("*").execute().data)
    except:
        df_auditoria = pd.DataFrame()

    if not df_auditoria.empty:
        # --- ÁREA DE FILTROS ---
        col_filtro1, col_filtro2 = st.columns(2)
        
        with col_filtro1:
            filtro_colab = st.selectbox("Filtrar por Colaborador:", ["Todos"] + TODOS_NOMES)
        with col_filtro2:
            filtro_proc = st.text_input("Filtrar por Nº do Processo:")
            
        # --- LÓGICA DE FILTRAGEM ---
        df_view = df_auditoria.copy()
        
        if filtro_colab != "Todos":
            df_view = df_view[df_view['quem_expediu'] == filtro_colab]
            
        if filtro_proc:
            df_view = df_view[df_view['numero_processo'].astype(str).str.contains(filtro_proc, case=False, na=False)]
            
        # --- CABEÇALHO DO TOTAL ---
        st.markdown("---")
        st.info(f"📍 Total de documentos localizados: **{len(df_view)}**")
        
        # --- TABELA DE AUDITORIA ---
        if not df_view.empty:
            # Selecionando apenas as colunas que você pediu
            df_display = df_view[['numero_processo', 'numero_oficio', 'quem_expediu']].rename(columns={
                'numero_processo': 'Processo', 
                'numero_oficio': 'Nº Ofício/Memo', 
                'quem_expediu': 'Responsável'
            })
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Download da lista filtrada
            csv = df_view.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Exportar Lista Filtrada (CSV)", 
                data=csv, 
                file_name="auditoria_documentos.csv", 
                mime='text/csv'
            )
        else:
            st.warning("Nenhum documento encontrado com esses filtros.")
    else:
        st.info("A base de documentos está vazia.")

# ------------------------------------------
# ABA 3: HISTÓRICO, EXCLUSÕES E AVISOS
# ------------------------------------------
with aba_historico:
    sub_aba_concluidas, sub_aba_lixeira, sub_aba_hist_avisos, sub_aba_hist_ferias = st.tabs([
        "✅ Arquivo: Concluídas", "🗑️ Auditoria: Processos Excluídos", "📢 Auditoria: Histórico de Avisos", "📋 Auditoria: Férias e Ausências"
    ])
    with sub_aba_concluidas:
        st.subheader("Sessões 100% Concluídas")
        if sessoes_finalizadas:
            df_historico = df_geral_status[df_geral_status['chave_sessao'].isin(sessoes_finalizadas)].copy()
            df_historico_display = df_historico[['numero_processo', 'urgente', 'relator', 'expedicao', 'revisao', 'data_conclusao', 'tipo_sessao', 'nome_sessao']].copy()
            df_historico_display = df_historico_display.rename(columns={'numero_processo': 'Processo', 'urgente': 'urgente_flag', 'relator': 'Conselheiro', 'expedicao': 'Expedidor', 'revisao': 'Revisor', 'data_conclusao': 'Data/Hora Conclusão', 'tipo_sessao': 'Tipo de Sessão', 'nome_sessao': 'Data da Sessão'})
            
            with st.expander("🔎 Filtros de Busca Avançada", expanded=True):
                col_f1, col_t1, col_f2, col_f3, col_f4 = st.columns(5)
                
                with col_f1:
                    datas_unicas = sorted(df_historico_display['Data da Sessão'].unique(), reverse=True)
                    filtro_sessao = st.multiselect("📅 Data da Sessão", options=datas_unicas)
                
                with col_t1:
                    tipos_unicos = sorted(df_historico_display['Tipo de Sessão'].dropna().unique())
                    filtro_tipo = st.multiselect("📌 Tipo de Sessão", options=tipos_unicos)
                
                with col_f2:
                    filtro_usuario = st.multiselect("👥 Colaborador", options=TODOS_NOMES)
                with col_f3:
                    filtro_processo = st.text_input("📄 Nº do Processo", placeholder="Ex: 12345")
                with col_f4:
                    filtro_relator = st.text_input("⚖️ Relator", placeholder="Nome...")

            df_filtrado_hist = df_historico_display.copy()
            if filtro_sessao: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Data da Sessão'].isin(filtro_sessao)]
            if filtro_tipo: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Tipo de Sessão'].isin(filtro_tipo)]
            if filtro_usuario: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Expedidor'].isin(filtro_usuario) | df_filtrado_hist['Revisor'].isin(filtro_usuario)]
            if filtro_processo: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Processo'].astype(str).str.contains(filtro_processo, case=False, na=False)]
            if filtro_relator: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Conselheiro'].astype(str).str.contains(filtro_relator, case=False, na=False)]

            st.markdown(f"**📊 Resultados encontrados:** `{len(df_filtrado_hist)}` processos.")
            if not df_filtrado_hist.empty:
                styled_hist = df_filtrado_hist.iloc[::-1].style.apply(color_urgentes, axis=1)
                st.dataframe(styled_hist, hide_index=True, use_container_width=True, column_config={"urgente_flag": None})
            else: st.warning("Nenhum processo encontrado com esses filtros.")
        else: st.info("📭 O histórico está vazio. Nenhuma sessão foi 100% concluída ainda.")

    with sub_aba_lixeira:
        st.subheader("Registro de Exclusões (Auditoria de Pauta)")
        df_excluidos = carregar_excluidos()
        if not df_excluidos.empty:
            df_excluidos_display = df_excluidos.rename(columns={'numero_processo': 'Processo', 'relator': 'Relator', 'data_exclusao': 'Data/Hora da Exclusão', 'motivo': 'Motivo Declarado'})
            st.dataframe(df_excluidos_display[['Processo', 'Relator', 'Motivo Declarado', 'Data/Hora da Exclusão']].iloc[::-1], hide_index=True, use_container_width=True)
            csv_lixo = df_excluidos_display.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Baixar Relatório de Exclusões (CSV)", data=csv_lixo, file_name="auditoria_exclusoes.csv", mime='text/csv', type="secondary")
        else: st.success("✨ A lixeira está vazia. Nenhum processo foi apagado do sistema.")

    with sub_aba_hist_avisos:
        st.subheader("Histórico Completo de Avisos Publicados")
        df_hist_av = carregar_historico_avisos()
        if not df_hist_av.empty:
            df_hist_av_display = df_hist_av.rename(columns={'numero_processo': 'Processo', 'usuario': 'Destinatário do Alerta', 'mensagem': 'Comunicado / Ordem', 'data_criacao': 'Data/Hora de Publicação', 'status': 'Situação Atual'})
            if 'Processo' in df_hist_av_display.columns:
                colunas_ordem = ['Processo', 'Destinatário do Alerta', 'Comunicado / Ordem', 'Data/Hora de Publicação', 'Situação Atual']
                st.dataframe(df_hist_av_display[colunas_ordem].iloc[::-1], hide_index=True, use_container_width=True)
                csv_avisos = df_hist_av_display[colunas_ordem].to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Baixar Relatório de Avisos (CSV)", data=csv_avisos, file_name="auditoria_mural_avisos.csv", mime='text/csv', type="secondary")
        else: st.info("📢 Nenhum comunicado foi publicado no mural de avisos até o momento.")

    with sub_aba_hist_ferias:
        st.subheader("Histórico Geral de Afastamentos Encerrados")
        df_af_hist = carregar_afastamentos()
        if not df_af_hist.empty:
            hoje = datetime.now().date()
            df_af_hist['dt_fim_compare'] = pd.to_datetime(df_af_hist['data_fim'], format="%d/%m/%Y").dt.date
            df_passadas = df_af_hist[df_af_hist['dt_fim_compare'] < hoje].copy()
            if not df_passadas.empty:
                df_passadas_display = df_passadas.rename(columns={'usuario': 'Colaborador', 'tipo': 'Motivo Declarado', 'data_inicio': 'Data Inicial', 'data_fim': 'Data de Retorno'})
                st.dataframe(df_passadas_display[['Colaborador', 'Motivo Declarado', 'Data Inicial', 'Data de Retorno']].iloc[::-1], hide_index=True, use_container_width=True)
                csv_ferias = df_passadas_display[['Colaborador', 'Motivo Declarado', 'Data Inicial', 'Data de Retorno']].to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Baixar Relatório (CSV)", data=csv_ferias, file_name="auditoria_afastamentos.csv", mime='text/csv', type="secondary")
            else: st.info("Nenhum afastamento antigo arquivado no histórico até o momento.")
        else: st.info("Nenhum registro de afastamento encontrado no sistema.")

# ------------------------------------------
# ABA 4: GESTÃO ADMINISTRATIVA (COM SENHA)
# ------------------------------------------
with aba_gestao:
    if not st.session_state.gestor_autenticado:
        st.warning("🔒 Área restrita para a Chefia. Insira a senha para acessar as ferramentas de gestão, dashboards e férias.")
        col_senha1, col_senha2 = st.columns([1, 2])
        with col_senha1:
            senha_digitada = st.text_input("Senha de Acesso:", type="password")
            if st.button("🔓 Desbloquear", type="primary", use_container_width=True):
                if senha_digitada == "admin123":
                    st.session_state.gestor_autenticado = True
                    st.rerun()
                else: st.error("❌ Senha Incorreta!")
                    
    if st.session_state.gestor_autenticado:
        col_titulo, col_btn = st.columns([4, 1])
        col_titulo.subheader("⚙️ Painel de Gestão Administrativa")
        if col_btn.button("🚪 Bloquear Tela", type="secondary", use_container_width=True):
            st.session_state.gestor_autenticado = False
            st.rerun()
            
        st.markdown("---")
        sub_controle, sub_dados, sub_ferias = st.tabs(["📊 4.1. Controle de Banco de Dados", "📈 4.2. Analytics e Desempenho", "🌴 4.3. Afastamentos da Equipe"])
        
        with sub_controle:
            st.subheader("🔑 Liberação Extraordinária de Processo")
            st.write("Force o despacho de um processo travado (ignora regras de ofícios e revisões). Esta ação ficará gravada na Auditoria da Chefia.")
            col_lib1, col_lib2, col_lib3 = st.columns([2, 4, 2])
            with col_lib1:
                proc_forcar = st.text_input("Número do Processo:", key="proc_chefia")
            with col_lib2:
                just_forcar = st.text_input("Justificativa Legal / Motivo:", key="just_chefia")
            with col_lib3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("⚡ Forçar Despacho", type="primary", use_container_width=True):
                    if proc_forcar and just_forcar:
                        ok, m = liberar_processo_chefia(proc_forcar, just_forcar)
                        if ok:
                            st.success(m)
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.error(m)
                    else:
                        st.warning("⚠️ Preencha o número do processo e a justificativa para auditoria.")
            st.markdown("---")
            
            if not df_geral_status.empty:
                data_selecionada = st.selectbox("📅 Data da Sessão (OKs):", sorted(df_geral_status['nome_sessao'].unique(), reverse=True), key="chave_data_oks_gestao")
                df_filtrado = df_geral_status[df_geral_status['nome_sessao'] == data_selecionada]
                col_exp, col_rev = st.columns(2)
                with col_exp: st.dataframe(df_filtrado['expedicao'].value_counts().reset_index(), hide_index=True)
                with col_rev: st.dataframe(df_filtrado['revisao'].value_counts().reset_index(), hide_index=True)

            st.markdown("---")
            with st.expander("⚙️ Área Administrativa Avançada (Equipe e Banco de Dados)"):
                st.subheader("📢 Mural de Avisos (Letreiro)")
                col_av1, col_av2, col_av3 = st.columns([1, 1, 2])
                with col_av1: aviso_usuario = st.selectbox("Para quem?", ["Todos"] + TODOS_NOMES, key="aviso_usr")
                with col_av2: aviso_processo = st.text_input("Nº do Processo Ativo", key="aviso_proc")
                with col_av3: aviso_msg = st.text_input("Mensagem", placeholder="Ex: Tratar com urgência...", key="aviso_msg")
                if st.button("📢 Publicar no Letreiro", type="primary", use_container_width=True):
                    if aviso_processo and aviso_msg:
                        ok, msg = adicionar_aviso(aviso_usuario, aviso_processo, aviso_msg)
                        if ok:
                            st.success(msg)
                            time.sleep(1)
                            st.rerun()
                        else: st.error(msg)
                    else: st.warning("⚠️ Preencha o número do processo e a mensagem.")
                st.markdown("---")

                st.subheader("📄 Relatório Gerencial Mensal/Anual")
                col_m1, col_m2, col_m3 = st.columns([1, 1, 2])
                meses_dict = {0: "🗓️ Anual", 1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
                mes_atual = datetime.now().month
                ano_atual = datetime.now().year
                with col_m1: mes_selecionado = st.selectbox("Período:", list(meses_dict.keys()), index=mes_atual, format_func=lambda x: meses_dict[x])
                with col_m2: ano_selecionado = st.selectbox("Ano:", range(2024, ano_atual + 1), index=ano_atual-2024)
                with col_m3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("📊 Compilar Relatório", type="primary", use_container_width=True):
                        ok, texto_relatorio = gerar_relatorio_gerencial(mes_selecionado, ano_selecionado)
                        if ok:
                            st.success("Relatório gerado com sucesso!")
                            st.code(texto_relatorio, language="markdown")
                            nome_arquivo = f"Relatorio_{ano_selecionado}.txt" if mes_selecionado == 0 else f"Relatorio_{mes_selecionado:02d}_{ano_selecionado}.txt"
                            st.download_button(label="📥 Baixar", data=texto_relatorio.encode('utf-8'), file_name=nome_arquivo, mime="text/plain", type="secondary")
                        else: st.warning(texto_relatorio)
                st.markdown("---")

                st.subheader("👥 Gestão de Colaboradores")
                acao_equipe = st.radio("Selecione a ação:", ["Adicionar Novo", "Editar Permissões", "Substituir Nome", "Remover Colaborador"], horizontal=True)
                if acao_equipe == "Adicionar Novo":
                    col1, col2 = st.columns(2)
                    novo_colab = col1.text_input("Nome do novo colaborador")
                    cargo_colab = col1.selectbox("Função / Cargo no Setor:", ["Assessor", "Estagiário", "Chefia"])
                    faz_exp, faz_rev = col2.checkbox("Participa da Expedição", value=True), col2.checkbox("Participa da Revisão", value=True)
                    if st.button("➕ Adicionar", type="primary", key="add_user"):
                        ok, m = gerenciar_usuario('adicionar', novo_colab, expedicao=int(faz_exp), revisao=int(faz_rev), cargo=cargo_colab)
                        if ok: st.success(m); time.sleep(1); st.rerun()
                        
                elif acao_equipe == "Editar Permissões":
                    col1, col2, col3 = st.columns(3)
                    colab_editar = col1.selectbox("Selecione o colaborador", TODOS_NOMES)
                    cargo_editar = col1.selectbox("Atualizar Cargo:", ["Assessor", "Estagiário", "Chefia"], key="edit_cargo_sel")
                    faz_exp = col2.checkbox("Participa da Expedição", value=True, key="edit_exp")
                    faz_rev = col3.checkbox("Participa da Revisão", value=True, key="edit_rev")
                    if st.button("✏️ Atualizar Permissões", type="primary", key="edit_user"):
                        ok, m = gerenciar_usuario('editar', colab_editar, expedicao=int(faz_exp), revisao=int(faz_rev), cargo=cargo_editar)
                        if ok: st.success(m); time.sleep(1); st.rerun()
                elif acao_equipe == "Substituir Nome":
                    col1, col2, col3 = st.columns(3)
                    colab_atual = col1.selectbox("Quem vai sair?", TODOS_NOMES)
                    novo_nome = col2.text_input("Qual o nome de quem vai entrar?")
                    faz_exp, faz_rev = col3.checkbox("Entra na Expedição?", value=True), col3.checkbox("Entra na Revisão?", value=True)
                    if st.button("🔄 Substituir", type="primary", key="subst_user"):
                        ok, m = gerenciar_usuario('substituir', colab_atual, novo_nome=novo_nome, expedicao=int(faz_exp), revisao=int(faz_rev))
                        if ok: st.success(m); time.sleep(1); st.rerun()
                elif acao_equipe == "Remover Colaborador":
                    colab_remover = st.selectbox("Selecione quem será removido", TODOS_NOMES)
                    if st.button("🗑️ Remover Definitivamente", type="primary", key="rem_user"):
                        ok, m = gerenciar_usuario('remover', colab_remover)
                        if ok: st.success(m); time.sleep(1); st.rerun()
                st.markdown("---")

                st.subheader("💾 Backup e Restauração de Dados")
                col_down, col_up = st.columns(2)
                with col_down:
                    st.markdown("**1. Gerar Arquivo de Segurança**")
                    if not df_geral_status.empty:
                        csv = df_geral_status.to_csv(index=False).encode('utf-8')
                        st.download_button(label="📥 Baixar Backup (CSV)", data=csv, file_name=f"backup_processos_{datetime.now().strftime('%d_%m_%Y')}.csv", mime='text/csv', type="primary", use_container_width=True)
                    else: st.info("O banco de dados está vazio.")
                with col_up:
                    st.markdown("**2. Restaurar Sistema**")
                    arquivo_backup = st.file_uploader("Suba o arquivo CSV para restaurar", type=['csv'], label_visibility="collapsed")
                    if arquivo_backup is not None:
                        if st.button("⚠️ Restaurar Dados Agora", type="primary", use_container_width=True):
                            try:
                                df_upload = pd.read_csv(arquivo_backup, encoding='utf-8-sig')
                                ok, msg = restaurar_backup(df_upload)
                                if ok:
                                    st.success(msg)
                                    time.sleep(1.5)
                                    st.rerun()
                                else: st.error(msg)
                            except Exception as e: st.error(f"Erro ao ler o arquivo: {e}")
                st.markdown("---")
                
                st.subheader("🕰️ Migração de Processos Direto para o Histórico")
                st.write("Insira processos antigos já finalizados. Eles pularão o Painel Ativo e irão direto para o Arquivo.")
                
                df_modelo_hist = pd.DataFrame({
                    "Processo": ["12345/2026", "67890/2026"], 
                    "Relator": ["Conselheiro A", "Conselheiro B"],
                    "Expedidor": ["André", "Elaine"],
                    "Revisor": ["Maurício", "Kátia"],
                    "Data_Sessao": ["12/05/2026", "19/05/2026"],
                    "Tipo_Sessao": ["Sessão Ordinária", "Sessão Reservada"]
                })
                
                st.download_button(
                    label="📥 Baixar Modelo para Histórico (CSV)",
                    data=df_modelo_hist.to_csv(index=False).encode('utf-8'),
                    file_name="modelo_historico.csv", 
                    mime="text/csv", 
                    type="secondary"
                )
                
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    hist_tipo = st.selectbox("Tipo de Sessão (Histórico):", ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa"], key="hist_tipo")
                    hist_sessao = st.text_input("Nome ou Número da Sessão (Ex: Sessão 125):", key="hist_sessao")
                with col_h2:
                    hist_proc = st.text_input("Nº do Processo (Manual):", key="hist_proc")
                    hist_rel = st.text_input("Relator (Manual):", key="hist_rel")
                    
                col_hx, col_hy = st.columns(2)
                with col_hx: 
                    hist_exp = st.text_input("Expedidor:", placeholder="Digite o nome...", key="hist_exp")
                with col_hy: 
                    hist_rev = st.text_input("Revisor:", placeholder="Digite o nome...", key="hist_rev")

                arquivo_hist = st.file_uploader("Planilha de Recuperação (CSV/XLSX):", type=["csv", "xlsx"], key="hist_up")
                if st.button("💾 Enviar Direto para o Histórico", type="primary", use_container_width=True):
                    if not hist_sessao:
                        st.warning("⚠️ Você precisa digitar o Nome da Sessão primeiro.")
                    else:
                        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        
                        if arquivo_hist is not None:
                            try:
                                if arquivo_hist.name.endswith('.csv'):
                                    try: df_up = pd.read_csv(arquivo_hist, encoding='utf-8-sig')
                                    except UnicodeDecodeError:
                                        arquivo_hist.seek(0)
                                        df_up = pd.read_csv(arquivo_hist, encoding='latin-1', sep=';')
                                        if len(df_up.columns) == 1:
                                            arquivo_hist.seek(0)
                                            df_up = pd.read_csv(arquivo_hist, encoding='latin-1', sep=',')
                                else:
                                    df_up = pd.read_excel(arquivo_hist)
                                
                                barra = st.progress(0)
                                lote_insercao = [] 
                                
                                for index, row in df_up.iterrows():
                                    p_val = str(row['Processo']).strip() if pd.notna(row.get('Processo')) else ""
                                    r_val = str(row.get('Relator', '')).strip() if pd.notna(row.get('Relator')) else ""
                                    p_limpo, r_limpo = higienizar_dados(p_val, r_val)
                                    exp_bruto = str(row.get('Expedidor', hist_exp)).strip() if pd.notna(row.get('Expedidor')) else hist_exp
                                    rev_bruto = str(row.get('Revisor', hist_rev)).strip() if pd.notna(row.get('Revisor')) else hist_rev
                                    exp_val = higienizar_colaborador(exp_bruto, TODOS_NOMES)
                                    rev_val = higienizar_colaborador(rev_bruto, TODOS_NOMES)
                                    data_val = str(row.get('Data_Sessao', hist_sessao)).strip() if pd.notna(row.get('Data_Sessao')) else hist_sessao
                                    tipo_val = str(row.get('Tipo_Sessao', hist_tipo)).strip() if pd.notna(row.get('Tipo_Sessao')) else hist_tipo

                                    if " " in data_val and "-" in data_val:
                                        try: data_val = datetime.strptime(data_val.split()[0], "%Y-%m-%d").strftime("%d/%m/%Y")
                                        except: pass

                                    if p_limpo and not processo_existe(p_limpo, data_val):
                                        data_historico = f"{data_val} 23:59:59"
                                        
                                        lote_insercao.append({
                                            "numero_processo": p_limpo, 
                                            "relator": r_limpo, 
                                            "tipo_sessao": tipo_val,     
                                            "nome_sessao": data_val,     
                                            "expedicao": exp_val, 
                                            "revisao": rev_val,   
                                            "data_entrada": data_historico, "data_expedido": data_historico, "data_revisado": data_historico, "data_conclusao": data_historico,
                                            "expedido_ok": 1, "revisado_ok": 1, "despachado": 1, "urgente": 0,
                                            "enviado_email": 0, "enviado_mensageria": 0, "recebido": 0,
                                            "precisa_correcao": 0, "motivo_correcao": ""
                                        })
                                    barra.progress((index + 1) / len(df_up))
                                
                                if lote_insercao:
                                    for i in range(0, len(lote_insercao), 100):
                                        conn.client.table("processos").insert(lote_insercao[i:i+100]).execute()
                                    
                                    st.success(f"🎉 {len(lote_insercao)} processos recuperados e enviados direto para o Histórico!")
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.warning("⚠️ Nenhum processo novo foi inserido (ou já existiam).")

                            except Exception as e:
                                st.error(f"❌ Erro crítico ao processar a planilha: {e}")
                                
                        elif hist_proc:
                            p_limpo, r_limpo = higienizar_dados(hist_proc, hist_rel)
                            if not processo_existe(p_limpo, hist_sessao):
                                try:
                                    conn.client.table("processos").insert({
                                        "numero_processo": p_limpo, "relator": r_limpo, "tipo_sessao": hist_tipo, 
                                        "nome_sessao": hist_sessao, "expedicao": hist_exp, "revisao": hist_rev, 
                                        "data_entrada": agora, "data_expedido": agora, "data_revisado": agora, "data_conclusao": agora,
                                        "expedido_ok": 1, "revisado_ok": 1, "despachado": 1, "urgente": 0,
                                        "enviado_email": 0, "enviado_mensageria": 0, "recebido": 0,
                                        "precisa_correcao": 0, "motivo_correcao": ""
                                    }).execute()
                                    st.success(f"🎉 Processo {p_limpo} enviado para o Histórico!")
                                    time.sleep(2)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")
                            else: st.error("❌ Este processo já existe no sistema.")
                        
                st.subheader("🧹 MODO LIMPEZA: Apagar Banco de Dados")
                st.write("Escolha se deseja apagar apenas os processos de um período específico ou resetar todo o sistema.")
                tipo_limpeza = st.radio("Selecione a ação:", ["Limpar por Período", "Modo Nuclear (Zerar Tudo)"], horizontal=True)
                
                if tipo_limpeza == "Limpar por Período":
                    col_d1, col_d2 = st.columns(2)
                    with col_d1: dt_inicio = st.date_input("De (Data Inicial)", format="DD/MM/YYYY")
                    with col_d2: dt_fim = st.date_input("Até (Data Final)", format="DD/MM/YYYY")
                    confirmacao_periodo = st.checkbox("Tenho certeza. Quero apagar os processos desse período.", key="check_periodo")
                    
                    if st.button("🗑️ Apagar Período", type="primary", disabled=not confirmacao_periodo, use_container_width=True):
                        try:
                            todos_processos = conn.client.table("processos").select("id, data_entrada").execute().data
                            ids_para_apagar = []
                            for p in todos_processos:
                                try:
                                    data_str = str(p['data_entrada']).split()[0]
                                    data_obj = datetime.strptime(data_str, "%d/%m/%Y").date()
                                    if dt_inicio <= data_obj <= dt_fim:
                                        ids_para_apagar.append(p['id'])
                                except: pass
                            if ids_para_apagar:
                                for id_proc in ids_para_apagar:
                                    conn.client.table("processos").delete().eq("id", id_proc).execute()
                                st.success(f"🧹 Limpeza concluída! {len(ids_para_apagar)} processos apagados.")
                                time.sleep(2)
                                st.rerun()
                            else: st.warning("⚠️ Nenhum processo encontrado nesse período.")
                        except Exception as e: st.error(f"❌ Erro ao limpar período: {e}")
                            
                elif tipo_limpeza == "Modo Nuclear (Zerar Tudo)":
                    st.warning("⚠️ Atenção: Isso apagará TODOS os processos (ativos e histórico). A equipe e os afastamentos serão mantidos.")
                    confirmacao_nuclear = st.checkbox("Tenho certeza absoluta. Quero zerar a base de dados.", key="check_nuclear_novo")
                    if st.button("🔥 APAGAR TUDO E COMEÇAR DO ZERO", type="primary", disabled=not confirmacao_nuclear, use_container_width=True):
                        try:
                            conn.client.table("processos").delete().neq("numero_processo", "vazio").execute()
                            conn.client.table("processos_excluidos").delete().neq("numero_processo", "vazio").execute()
                            conn.client.table("avisos").delete().neq("numero_processo", "vazio").execute()
                            st.success("💥 BUM! Banco de dados completamente zerado. Vida nova!")
                            time.sleep(2.5)
                            st.rerun()
                        except Exception as e: st.error(f"❌ Erro ao tentar resetar o banco: {e}")

        with sub_dados:
            st.header("📈 Dashboard Analítico e Distribuição Operacional")
            df_dados = carregar_dados_sqlite()
            if df_dados.empty or 'data_expedido' not in df_dados.columns: 
                st.info("📊 O banco de dados está vazio.")
            else:
                for c in ['data_entrada', 'data_expedido', 'data_revisado', 'data_conclusao']:
                    df_dados[c + '_dt'] = pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M:%S", errors='coerce').fillna(pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M", errors='coerce'))
                df_concluidos = df_dados[df_dados['despachado'] == 1].copy()
                df_tempo_real = df_concluidos[df_concluidos['data_entrada'] != df_concluidos['data_conclusao']].copy()

                df_tempo_real['min_exp'] = 0.0
                df_tempo_real['min_rev'] = 0.0
                df_tempo_real['min_total'] = 0.0

                if not df_tempo_real.empty:
                    df_tempo_real['min_exp'] = (pd.to_datetime(df_tempo_real['data_expedido_dt']) - pd.to_datetime(df_tempo_real['data_entrada_dt'])).dt.total_seconds() / 60
                    df_tempo_real['min_rev'] = (pd.to_datetime(df_tempo_real['data_revisado_dt']) - pd.to_datetime(df_tempo_real['data_expedido_dt'])).dt.total_seconds() / 60
                    df_tempo_real['min_total'] = (pd.to_datetime(df_tempo_real['data_conclusao_dt']) - pd.to_datetime(df_tempo_real['data_entrada_dt'])).dt.total_seconds() / 60

                def format_tempo(minutos):
                    if pd.isna(minutos) or minutos < 0: return "N/A"
                    return f"{int(minutos)} min" if int(minutos) < 60 else f"{int(minutos) // 60}h {int(minutos) % 60}m"

                st.markdown("### Selecione o Perfil de Análise")
                visao_selecionada = st.selectbox("Escolha a Visão:", ["Todo o Setor (Global)"] + TODOS_NOMES, label_visibility="collapsed")
                st.markdown("---")

                if visao_selecionada == "Todo o Setor (Global)":
                    st.subheader("🌐 Visão Macro (Histórico Completo)")
                    col1, col2, col3, col4 = st.columns(4)
                    total_despachados = len(df_concluidos)
                    total_sessoes = df_concluidos['nome_sessao'].nunique()
                    media_proc_sessao = round(total_despachados / total_sessoes) if total_sessoes > 0 else 0
                    total_urgentes = len(df_concluidos[df_concluidos['urgente'] == 1])
                    col1.metric("📦 Total Despachados", total_despachados)
                    col2.metric("🏛️ Sessões Realizadas", total_sessoes)
                    col3.metric("⚖️ Média Proc./Sessão", media_proc_sessao)
                    col4.metric("🔥 Urgências Atendidas", total_urgentes)
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("---")
                    st.markdown("### ✉️ Inteligência de Expedição (Ofícios e Correções)")
                    
                    try:
                        df_oficios_analytics = pd.DataFrame(conn.client.table("oficios").select("*").execute().data)
                    except:
                        df_oficios_analytics = pd.DataFrame()

                    if not df_oficios_analytics.empty:
                        df_ofic_despachados = df_oficios_analytics[df_oficios_analytics['oficio_despachado'] == 1]
                        total_oficios = len(df_ofic_despachados)
                        proc_com_oficios = df_ofic_despachados['numero_processo'].nunique()
                        media_ofic_proc = round(total_oficios / proc_com_oficios, 1) if proc_com_oficios > 0 else 0
                        
                        col_of1, col_of2, col_of3, col_of4 = st.columns(4)
                        col_of1.metric("✉️ Ofícios Expedidos", total_oficios)
                        col_of2.metric("📊 Média Ofícios/Processo", media_ofic_proc)
                        
                        ofic_jur = len(df_ofic_despachados[df_ofic_despachados['categoria'] == 'Jurisdicionado'])
                        col_of3.metric("🏛️ Ofic. Jurisdicionados", ofic_jur)
                        col_of4.metric("🏢 Ofic. Não Jurisdic.", total_oficios - ofic_jur)
                        
                        st.markdown("#### 🏆 Ranking de Emissão de Ofícios")
                        ofic_counts = df_ofic_despachados['quem_expediu'].value_counts().reset_index()
                        ofic_counts.columns = ['Colaborador', 'Ofícios Gerados']
                        
                        if not ofic_counts.empty:
                            fig_ofic = px.bar(ofic_counts, x='Colaborador', y='Ofícios Gerados', text='Ofícios Gerados', color='Ofícios Gerados', color_continuous_scale='Blues')
                            fig_ofic.update_traces(textposition='outside')
                            fig_ofic.update_layout(margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="rgba(0,0,0,0)")
                            st.plotly_chart(fig_ofic, use_container_width=True)
                    else:
                        st.info("Nenhum dado de ofício registrado ainda para gerar estatísticas.")

                    st.markdown("#### 🚨 Termômetro de Retrabalho (Quarentena Ativa)")
                    if 'precisa_correcao' in df_dados.columns:
                        df_erros_ativos = df_dados[df_dados['precisa_correcao'] == 1]
                        total_erros_ativos = len(df_erros_ativos)
                        
                        if total_erros_ativos > 0:
                            st.error(f"⚠️ Atualmente existem {total_erros_ativos} processo(s) travado(s) na quarentena aguardando correção.")
                            erros_por_user = df_erros_ativos['expedicao'].value_counts().reset_index()
                            erros_por_user.columns = ['Expedidor', 'Processos com Erro Ativos']
                            st.dataframe(erros_por_user, hide_index=True)
                        else:
                            st.success("🎉 Zero processos na quarentena hoje! Equipe trabalhando com 100% de precisão.")
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("### 🤝 Volume de Participação Operacional (Carga de Trabalho)")
                    col_g1, col_g2 = st.columns(2)
                    with col_g1:
                        st.markdown("#### 📦 Expedição") 
                        exp_counts = df_concluidos['expedicao'].value_counts().reset_index()
                        exp_counts.columns = ['Colaborador', 'Processos']
                        if not exp_counts.empty:
                            fig_exp = px.pie(exp_counts, values='Processos', names='Colaborador', hole=0.5)
                            fig_exp.update_traces(textposition='inside', textinfo='percent+value')
                            fig_exp.update_layout(margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="rgba(0,0,0,0)", legend_title="Colaborador")
                            st.plotly_chart(fig_exp, use_container_width=True)
                        else: st.info("Sem dados de expedição.")
                    with col_g2:
                        st.markdown("#### 🔍 Revisão") 
                        rev_counts = df_concluidos['revisao'].value_counts().reset_index()
                        rev_counts.columns = ['Colaborador', 'Processos']
                        if not rev_counts.empty:
                            fig_rev = px.pie(rev_counts, values='Processos', names='Colaborador', hole=0.5)
                            fig_rev.update_traces(textposition='inside', textinfo='percent+value')
                            fig_rev.update_layout(margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="rgba(0,0,0,0)", legend_title="Colaborador")
                            st.plotly_chart(fig_rev, use_container_width=True)
                        else: st.info("Sem dados de revisão.")
                    st.markdown("---")
                    st.markdown("### ⏱️ Cadência e Desempenho")
                    c_t1, c_t2, c_t3 = st.columns(3)
                    c_t1.metric("Média de Elaboração (Expedição)", format_tempo(df_tempo_real['min_exp'].mean()))
                    c_t2.metric("Média de Conferência (Revisão)", format_tempo(df_tempo_real['min_rev'].mean()))
                    c_t3.metric("Tempo de Ciclo Total", format_tempo(df_tempo_real['min_total'].mean()))
                    st.markdown("---")
                    st.markdown("### 📡 Radar em Tempo Real (Painel Ativo)")
                    sessoes_stats = df_dados.groupby('nome_sessao')['despachado'].agg(['count', 'sum']).reset_index()
                    ativas_list = sessoes_stats[sessoes_stats['count'] > sessoes_stats['sum']]['nome_sessao'].tolist()
                    df_ativos_reais = df_dados[df_dados['nome_sessao'].isin(ativas_list)].copy()
                    if not df_ativos_reais.empty:
                        col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
                        urg_pendentes = len(df_ativos_reais[(df_ativos_reais['urgente'] == 1) & (df_ativos_reais['despachado'] == 0)])
                        col_r1.metric("📋 Total na Pauta", len(df_ativos_reais))
                        col_r2.metric("⏳ Aguardando Elab.", len(df_ativos_reais[df_ativos_reais['expedido_ok'] == 0]))
                        col_r3.metric("🔍 Aguardando Conf.", len(df_ativos_reais[(df_ativos_reais['expedido_ok'] == 1) & (df_ativos_reais['revisado_ok'] == 0)]))
                        col_r4.metric("✍️ Prontos p/ Despacho", len(df_ativos_reais[(df_ativos_reais['revisado_ok'] == 1) & (df_ativos_reais['despachado'] == 0)]))
                        with col_r5:
                            st.markdown(f"""
                            <div style='background-color: #ff4b4b; padding: 15px; border-radius: 8px; text-align: center; color: white; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);'>
                                <p style='margin: 0; font-size: 14px; font-weight: bold;'>🚨 Urgentes Restantes</p>
                                <h2 style='margin: 0; padding-top: 5px; color: white; font-weight: bold;'>{urg_pendentes}</h2>
                            </div>
                            """, unsafe_allow_html=True)
                    else: st.success("✨ Pauta limpa! Não há processos pendentes no radar ativo neste exato momento.")
                else:
                    st.subheader(f"🔎 Perfil Operacional: {visao_selecionada}")
                    try: ausentes = obter_colaboradores_ausentes_hoje()
                    except: ausentes = []
                    if visao_selecionada in ausentes: st.warning(f"📌 **Status:** Afastamento Legítimo Ativo.", icon="🌴")
                    else: st.info(f"📌 **Status no Dia de Hoje:** Ativo e Operacional.", icon="✅")
                    df_user_exp = df_concluidos[df_concluidos['expedicao'] == visao_selecionada]
                    df_user_rev = df_concluidos[df_concluidos['revisao'] == visao_selecionada]
                    df_user_total = df_concluidos[(df_concluidos['expedicao'] == visao_selecionada) | (df_concluidos['revisao'] == visao_selecionada)]
                    st.markdown("#### 📦 Resumo de Participação Histórica")
                    col_u1, col_u2, col_u3, col_u4 = st.columns(4)
                    col_u1.metric("Participações Totais", len(df_user_total))
                    col_u2.metric("Como Expedidor", len(df_user_exp))
                    col_u3.metric("Como Revisor", len(df_user_rev))
                    col_u4.metric("🔥 Urgências Salvas", len(df_user_total[df_user_total['urgente'] == 1]))
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("#### ⏱️ Qualidade e Cadência")
                    df_user_tempo_exp = df_tempo_real[df_tempo_real['expedicao'] == visao_selecionada]
                    df_user_tempo_rev = df_tempo_real[df_tempo_real['revisao'] == visao_selecionada]
                    cu1, cu2, cu3 = st.columns(3)
                    cu1.metric("Tempo Médio de Elaboração", format_tempo(df_user_tempo_exp['min_exp'].mean()))
                    cu2.metric("Tempo Médio de Conferência", format_tempo(df_user_tempo_rev['min_rev'].mean()))
                    if not df_user_total.empty:
                        parceiros = []
                        parceiros.extend(df_user_exp['revisao'].tolist())
                        parceiros.extend(df_user_rev['expedicao'].tolist())
                        if parceiros:
                            dupla = pd.Series(parceiros).mode()[0]
                            cu3.metric("🤝 Parceiro Mais Frequente", dupla)
                        else: cu3.metric("🤝 Parceiro Operacional", "N/A")
                    else: cu3.metric("🤝 Parceiro Operacional", "N/A")

        with sub_ferias:
            st.header("🌴 Painel de Férias e Afastamentos Operacionais")
            with st.container(border=True):
                st.subheader("📝 Registrar Nova Ausência")
                with st.form("form_afastamento", clear_on_submit=True):
                    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                    with col_f1: usr_afastado = st.selectbox("Colaborador:", TODOS_NOMES)
                    with col_f2: d_inicio = st.date_input("Data de Início:", format="DD/MM/YYYY")
                    with col_f3: d_fim = st.date_input("Data de Fim (Retorno):", format="DD/MM/YYYY")
                    with col_f4: t_afastamento = st.selectbox("Tipo de Ausência:", ["Férias", "Recesso", "Atestado Médico"])
                    if st.form_submit_button("🚀 Confirmar e Bloquear", type="primary", use_container_width=True):
                        if d_inicio > d_fim: st.error("❌ Erro: A data de início não pode ser maior que a de término.")
                        else:
                            ok, msg = salvar_afastamento(usr_afastado, d_inicio.strftime("%d/%m/%Y"), d_fim.strftime("%d/%m/%Y"), t_afastamento)
                            if ok: st.success(msg); time.sleep(1); st.rerun()
                            else: st.error(msg)
            st.markdown("---")
            st.subheader("📋 Quadro de Ausências Ativas (Quem está fora hoje)")
            df_af = carregar_afastamentos()
            if not df_af.empty:
                hoje = datetime.now().date()
                df_af['dt_inicio_compare'] = pd.to_datetime(df_af['data_inicio'], format="%d/%m/%Y").dt.date
                df_af['dt_fim_compare'] = pd.to_datetime(df_af['data_fim'], format="%d/%m/%Y").dt.date
                df_ativas = df_af[(hoje >= df_af['dt_inicio_compare']) & (hoje <= df_af['dt_fim_compare'])].copy()
                if not df_ativas.empty:
                    df_ativas_display = df_ativas.rename(columns={'usuario': 'Colaborador Ausente', 'tipo': 'Tipo / Motivo', 'data_inicio': 'Data de Saída', 'data_fim': 'Data de Retorno'})
                    st.dataframe(df_ativas_display[['Colaborador Ausente', 'Tipo / Motivo', 'Data de Saída', 'Data de Retorno']], hide_index=True, use_container_width=True)
                else: st.success("✨ Toda a equipe operacional está ativa e disponível hoje.")
            else: st.info("✨ Nenhum afastamento ativo registrado no momento.")

# ------------------------------------------
# ABA 5: AJUDA E GLOSSÁRIO (MANUAL DETALHADO)
# ------------------------------------------
with aba_ajuda:
    st.header("📖 Manual Operacional Completo: S.A.D.E.")
    st.markdown("Bem-vindo ao guia definitivo de operação. Siga estas instruções para manter a integridade dos dados e a produtividade do setor.")

    with st.expander("📥 1. Inserir Novos (Recepção de Pauta)"):
        st.markdown("""
        * **Modo Manual:** Escolha o tipo de sessão, o identificador (data ou nome da sessão) e insira o processo e o relator. O sistema fará a distribuição automática baseada na carga de trabalho global.
        * **Importação em Lote (Planilhas):**
            1. **Modelo:** Baixe o arquivo modelo (CSV).
            2. **Formato:** O arquivo **deve** ser salvo obrigatoriamente como `.csv` (separado por vírgula ou ponto e vírgula).
            3. **Regras:** Não altere o nome das colunas `Processo` e `Relator`.
            4. **Upload:** Arraste o arquivo para a área de upload do sistema. O S.A.D.E. processará linha por linha, limpando nomes e validando duplicidades automaticamente.
        """)

    with st.expander("🗂️ 2. Painel Ativo (A Mesa de Trabalho)"):
        st.markdown("""
        * **Fluxo:** É aqui que o trabalho acontece. O sistema filtra os processos da sessão escolhida.
        * **Análise de Dados:** O sistema coleta, em tempo real, o tempo que cada processo leva entre a entrada, expedição, revisão e despacho. Esses dados alimentam os gráficos da aba de Gestão, permitindo que você visualize seu desempenho individual e do setor.
        * **Salvamento:** Ao alterar qualquer status (Expedido/Revisado), você deve confirmar no botão **"💾 Salvar Alterações desta Sessão"**.
        * **Quarentena:** Processos devolvidos pelo revisor ficam na tabela inferior (vermelha). Eles **não** avançam para despacho até que a correção seja feita na Aba 2.5 e o botão "Correção Realizada" seja acionado.
        """)

    with st.expander("✉️ 2.5. Controle de Ofícios & 2.7. Relatório de Expedição"):
        st.markdown("""
        * **Controle:** Cadastro de Jurisdicionados, Não Jurisdicionados e Memorandos. O sistema usa "Autocomplete" para sugerir destinatários recorrentes.
        * **Trava de Segurança:** Processos da Ordinária/Virtual **não podem ser despachados** sem antes ter seus ofícios cadastrados e marcados como despachados (ou o processo ser marcado como "Isento").
        * **Relatório Individual:** Na Aba 2.7, o colaborador gera seu relatório de produção diária, que lista exatamente o que foi feito (ofícios/memorandos) por processo. É a sua lista para "passar a limpo" no sistema do Tribunal.
        """)

    with st.expander("🗄️ 3. Histórico e Auditoria"):
        st.markdown("""
        * **Arquivo:** Sessões 100% concluídas.
        * **Lixeira:** Processos excluídos com registro do motivo.
        * **Histórico de Avisos:** Consulta de comunicados que já rodaram no Letreiro.
        * **Férias e Ausências:** Exibe quem da equipe está afastado. **Regra:** O sistema cruza os dados do cadastro de afastamentos com as datas de distribuição; se um colaborador estiver em período de afastamento, o sistema ignora o nome dele no sorteio automático, evitando que ele receba trabalho enquanto está ausente.
        """)

    with st.expander("⚙️ 4. Gestão Administrativa (Manual de Operações Criticas)"):
        st.markdown("""
        * **Controle de Banco de Dados:** Visualize volumetria de expedição/revisão por data.
        * **Remover Processo:** Exclui um processo da pauta, movendo-o para a lixeira de auditoria.
        * **Mural de Avisos (Letreiro):** Publique avisos. Se marcar para "Todos", o aviso limpa automaticamente após 24h. Se marcar um processo, ele limpa assim que o processo for despachado.
        * **Identificar/Nomear Sessão:** Renomeia o lote de processos (Ex: mudar "10/06/2026" para "Sessão 125 - 10/06/2026").
        * **Relatório Gerencial:** Compila todos os dados de produtividade, tempos de ciclo e ofícios, gerando um resumo textual para exportação.
        * **Gestão de Colaboradores:** Adicione, substitua ou edite as permissões (Expedidor/Revisor) dos membros da equipe.
        * **Backup e Restauração:** O Backup gera um CSV com o banco atual. A Restauração limpa a base e substitui pelos dados do CSV (Use com cautela).
        * **Modo Limpeza:** * **Por Período:** Apaga processos em um intervalo de datas.
            * **Modo Nuclear:** Reseta todo o banco de processos (ativos e histórico). Colaboradores e afastamentos são preservados.
        """)

    with st.expander("📚 Glossário de Termos"):
        st.markdown("""
        * **Modo Nuclear:** Limpeza total do sistema.
        * **Isenção:** Processo marcado com status 2, dispensado de ofícios.
        * **Quarentena:** Estado de bloqueio administrativo para processos com erros.
        * **Sessão:** Unidade lógica de organização (Lotes de trabalho).
        """)
