import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import time
from st_supabase_connection import SupabaseConnection

# ==========================================
# 1. FRONTEND: CONFIGURAÇÃO INICIAL DA PÁGINA
# ==========================================
st.set_page_config(page_title="Sistema de Sessões", layout="wide")

# ==========================================
# 2. BACKEND: CONEXÃO COM A NUVEM SUPABASE
# ==========================================
conn = st.connection("supabase", type=SupabaseConnection)

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
        # Tira o 'count="exact"' e busca apenas 1 nome para ver se a tabela está vazia
        res = conn.client.table("equipe").select("nome").limit(1).execute()
        
        # Se a lista voltar vazia, ele insere a equipe inicial
        if not res.data:
            iniciais = [
                {"nome": "André", "expedicao": 1, "revisao": 1},
                {"nome": "Elaine", "expedicao": 1, "revisao": 1},
                {"nome": "Kátia", "expedicao": 1, "revisao": 1},
                {"nome": "Luana C", "expedicao": 1, "revisao": 1},
                {"nome": "Jessyca", "expedicao": 1, "revisao": 1},
                {"nome": "Lu Fiorote", "expedicao": 1, "revisao": 1},
                {"nome": "Mariana", "expedicao": 1, "revisao": 1},
                {"nome": "Maurício", "expedicao": 1, "revisao": 1}
            ]
            conn.client.table("equipe").insert(iniciais).execute()
    except: 
        pass

def carregar_equipes():
    try:
        # Puxa os nomes atualizados do banco
        resposta = conn.client.table("equipe").select("nome").order("nome").execute()
        todos = [linha['nome'] for linha in resposta.data]
        
        # O sistema pede 3 listas na linha 373. 
        # Como unificamos a gestão, mandamos a mesma lista global para as três variáveis!
        return todos, todos, todos
        
    except Exception as e:
        st.error(f"Erro ao tentar ler a equipe no Supabase: {e}")
        return [], [], []

def adicionar_membro_equipe(nome):
    try:
        conn.client.table("equipe").insert({"nome": nome}).execute()
        return True, "✅ Colaborador adicionado com sucesso!"
    except Exception as e:
        return False, f"❌ Erro ao adicionar: {e}"
        
def gerenciar_usuario(acao, nome_atual, novo_nome=None, expedicao=0, revisao=0):
    try:
        if acao == 'adicionar': conn.client.table("equipe").insert({"nome": nome_atual, "expedicao": expedicao, "revisao": revisao}).execute()
        elif acao == 'remover': conn.client.table("equipe").delete().eq("nome", nome_atual).execute()
        elif acao == 'substituir': conn.client.table("equipe").update({"nome": novo_nome, "expedicao": expedicao, "revisao": revisao}).eq("nome", nome_atual).execute()
        elif acao == 'editar': conn.client.table("equipe").update({"expedicao": expedicao, "revisao": revisao}).eq("nome", nome_atual).execute()
        return True, "✅ Operação realizada com sucesso!"
    except Exception as e: return False, f"❌ Erro no banco de dados: {e}"

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
        for proc in processos_sessao:
            conn.client.table("processos_excluidos").insert({"numero_processo": proc['numero_processo'], "relator": proc['relator'], "data_exclusao": agora, "motivo": motivo}).execute()
        conn.client.table("processos").delete().eq("tipo_sessao", tipo_sessao).eq("nome_sessao", nome_sessao).execute()
    except: pass

def carregar_excluidos():
    try: return pd.DataFrame(conn.client.table("processos_excluidos").select("*").execute().data)
    except: return pd.DataFrame()
    
def processo_existe(numero_processo):
    try:
        res = conn.client.table("processos").select("id", count="exact").eq("numero_processo", numero_processo).execute()
        return res.count > 0
    except: return False

def marcar_urgente(numero_processo):
    numero_processo, _ = higienizar_dados(numero_processo)
    try:
        res = conn.client.table("processos").select("id").eq("numero_processo", numero_processo).execute().data
        if not res: return False, f"❌ Processo {numero_processo} não encontrado. Insira-o na sua sessão normal primeiro."
        conn.client.table("processos").update({"urgente": 1}).eq("numero_processo", numero_processo).execute()
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
    try: conn.client.table("processos").update(payload).eq("id", id_processo).execute()
    except: pass

def obter_expedidor(opcoes, nome_sessao):
    if len(opcoes) == 1: return opcoes[0]
    try:
        # O algoritmo olha para a mesa (processos) e vê a carga real de cada um hoje
        res = conn.client.table("processos").select("expedicao").eq("nome_sessao", nome_sessao).execute()
        contagem = {nome: 0 for nome in opcoes}
        for row in res.data:
            if row.get('expedicao') in contagem:
                contagem[row['expedicao']] += 1
        
        # Entrega o processo para quem tem o menor número na contagem
        return min(contagem, key=contagem.get)
    except:
        import random
        return random.choice(opcoes)

def obter_revisor(expedidor, nome_sessao, opcoes):
    # O revisor não pode ser a mesma pessoa que expediu
    opcoes_validas = [opt for opt in opcoes if opt != expedidor]
    if not opcoes_validas: return expedidor # Contingência extrema
    if len(opcoes_validas) == 1: return opcoes_validas[0]
    
    try:
        res = conn.client.table("processos").select("revisao").eq("nome_sessao", nome_sessao).execute()
        contagem = {nome: 0 for nome in opcoes_validas}
        for row in res.data:
            if row.get('revisao') in contagem:
                contagem[row['revisao']] += 1
                
        return min(contagem, key=contagem.get)
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
            # Se o dia de hoje estiver dentro do período, entra na lista de bloqueados
            if ini <= hoje <= fim:
                ausentes.append(row['usuario'])
        return ausentes
    except:
        return []

# --- MOTOR ATUALIZADO DO RELATÓRIO DE AUDITORIA OPERACIONAL ---
def gerar_relatorio_gerencial(mes, ano):
    try:
        # 1. Carrega as bases frescas direto do banco de dados
        df_dados = carregar_dados_sqlite()
        df_afastamentos = carregar_afastamentos()
        
        if df_dados.empty:
            return False, "❌ O banco de dados está vazio. Não há dados para compilar."
            
        # Parse de segurança para os formatos de data e hora do sistema
        for c in ['data_entrada', 'data_expedido', 'data_revisado', 'data_conclusao']:
            df_dados[c + '_dt'] = pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M:%S", errors='coerce').fillna(
                                  pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M", errors='coerce'))
        
        # Cria colunas auxiliares de mês e ano baseadas na entrada do processo
        df_dados['ano_filtro'] = df_dados['data_entrada_dt'].dt.year
        df_dados['mes_filtro'] = df_dados['data_entrada_dt'].dt.month
        
        # 2. Aplica a filtragem inteligente de período (Respeitando a sua escolha na tela)
        if mes == 0:
            df_filtrado = df_dados[df_dados['ano_filtro'] == ano].copy()
            periodo_str = f"ANUAL (ANO INTEIRO DE {ano})"
        else:
            df_filtrado = df_dados[(df_dados['ano_filtro'] == ano) & (df_dados['mes_filtro'] == mes)].copy()
            nomes_meses = {1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL", 5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO", 9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"}
            periodo_str = f"{nomes_meses[mes]} DE {ano}"
            
        df_concluidos = df_filtrado[df_filtrado['despachado'] == 1].copy()
        
        # Filtro de Ouro: Separa os processos reais dos importados em lote do passado
        df_tempo_real = df_concluidos[df_concluidos['data_entrada'] != df_concluidos['data_conclusao']].copy()
        
        agora_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
        
        linhas = []
        linhas.append("====================================================")
        linhas.append("        S.A.D.E. - RELATÓRIO GERENCIAL OPERACIONAL  ")
        linhas.append(f"        PERÍODO: {periodo_str}                      ")
        linhas.append(f"        EMISSÃO: {agora_str}                        ")
        linhas.append("====================================================\n")
        
        # 1. Resumo Quantitativo Geral
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
            
        # 2. Distribuição da Carga de Trabalho (Volumetria Sem Competição)
        linhas.append("2. DISTRIBUIÇÃO OPERACIONAL DA EQUIPE (VOLUMETRIA)")
        linhas.append("----------------------------------------------------")
        if not df_concluidos.empty:
            linhas.append("[ETAPA DE ELABORAÇÃO / EXPEDIÇÃO]")
            exp_v = df_concluidos['expedicao'].value_counts()
            for nome, qtd in exp_v.items():
                linhas.append(f"   - {nome}: {qtd} processo(s)")
                
            linhas.append("\n[ETAPA DE CONFERÊNCIA / REVISÃO]")
            rev_v = df_concluidos['revisao'].value_counts()
            for nome, qtd in rev_v.items():
                linhas.append(f"   - {nome}: {qtd} processo(s)")
            linhas.append("")
        else:
            linhas.append(" -> Sem registros de volumetria por equipe no período selecionado.\n")
            
        # 3. Eficiência de Tempos Médios (Métricas Reais de Velocidade)
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
            
        # 4. Histórico de Afastamentos Ocorridos no Período Escolhido
        linhas.append("4. CONTROLE DE DISPONIBILIDADE E AFASTAMENTOS")
        linhas.append("----------------------------------------------------")
        if not df_afastamentos.empty:
            linhas.append("📌 AUSÊNCIAS REGISTRADAS NO PERÍODO:")
            houve_ausencia = False
            for _, row in df_afastamentos.iterrows():
                dt_ini_af = pd.to_datetime(row['data_inicio'], format="%d/%m/%Y", errors='coerce')
                # Checa se o afastamento começou dentro do ano selecionado E (mês selecionado ou ano inteiro)
                if dt_ini_af.year == ano and (mes == 0 or dt_ini_af.month == mes):
                    linhas.append(f"   - {row['usuario']} ({row['tipo']}): Afastamento de {row['data_inicio']} a {row['data_fim']}")
                    houve_ausencia = True
            if not houve_ausencia:
                linhas.append("   - Nenhuma ausência ou licença registrada para a equipe neste período.")
        else:
            linhas.append(" -> Sem registros de afastamentos salvos na base de dados.")
            
        linhas.append("\n====================================================")
        linhas.append("        FIM DO RELATÓRIO - AUDITORIA AUTOMÁTICA     ")
        linhas.append("====================================================")
        
        return True, "\n".join(linhas)
    except Exception as e:
        return False, f"Erro interno ao compilar relatório: {e}"

def salvar_novo_processo(numero_processo, relator, tipo_sessao, nome_sessao, expedidores, revisores):
    numero_processo, relator = higienizar_dados(numero_processo, relator)
    if processo_existe(numero_processo): 
        return False, "❌ Processo já existe no sistema."
    
    # 1. Busca quem está afastado hoje (Férias, Recesso ou Atestado)
    ausentes_hoje = obter_colaboradores_ausentes_hoje()
    
    # 2. Aplicação das Regras Especiais de Alocação por Tipo de Sessão
    if tipo_sessao == "Sessão Reservada":
        # Jessyca e Luana C não participam da Reservada
        expedidores = [e for e in expedidores if e not in ["Jessyca", "Luana C"]]
        revisores = [r for r in revisores if r not in ["Jessyca", "Luana C"]]
        
    elif tipo_sessao == "Sessão Administrativa":
        # Padrão é a Jessyca. Se ela estiver ausente, a carga vai para André ou Elaine
        if "Jessyca" not in ausentes_hoje:
            expedidores = ["Jessyca"]
            revisores = ["Jessyca"]
        else:
            # Contingência: Filtra André e Elaine que não estejam de férias
            contingencia = [colab for colab in ["André", "Elaine"] if colab not in ausentes_hoje]
            if contingencia:
                expedidores = contingencia
                revisores = contingencia
            else:
                return False, "❌ ERRO: Jessyca está afastada e a equipe de contingência (André/Elaine) também está indisponível."

    # 3. Filtro de Férias/Afastamentos Geral (Retira os ausentes da roleta)
    expedidores_ativos = [e for e in expedidores if e not in ausentes_hoje]
    revisores_ativos = [r for r in revisores if r not in ausentes_hoje]
    
    # Validação de segurança caso o setor fique sem ninguém disponível
    if not expedidores_ativos or not revisores_ativos: 
        return False, "❌ ERRO: Todos os colaboradores selecionados para esta escala estão de férias ou afastados hoje."
    
    # 4. Sorteio Justo (Balanceamento de Carga) com a equipe que sobrou
    responsavel_expedicao = obter_expedidor(expedidores_ativos, nome_sessao)
    responsavel_revisao = obter_revisor(responsavel_expedicao, nome_sessao, revisores_ativos)
    
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        conn.client.table("processos").insert({
            "numero_processo": numero_processo, "relator": relator, "tipo_sessao": tipo_sessao, 
            "nome_sessao": nome_sessao, "expedicao": responsavel_expedicao, "revisao": responsavel_revisao, 
            "data_entrada": data_atual, "expedido_ok": 0, "revisado_ok": 0, "despachado": 0, "urgente": 0,
            "enviado_email": 0, "enviado_mensageria": 0, "recebido": 0
        }).execute()
        return True, f"✅ Distribuído! Expedição: **{responsavel_expedicao}** | Revisão: **{responsavel_revisao}**"
    except Exception as e: 
        return False, f"❌ Erro ao salvar: {e}"

def carregar_dados_sqlite(tipo_sessao=None):
    try:
        if tipo_sessao: dados = conn.client.table("processos").select("*").eq("tipo_sessao", tipo_sessao).execute().data
        else: dados = conn.client.table("processos").select("*").execute().data
        return pd.DataFrame(dados)
    except: return pd.DataFrame()

def restaurar_backup(df_backup):
    try:
        conn.client.table("processos").delete().neq("numero_processo", "vazio").execute()
        
        # SOLUÇÃO APLICADA AQUI: Converte os vazios (NaN) do Pandas para None, que é aceito pelo Supabase
        df_backup = df_backup.astype(object).where(pd.notna(df_backup), None)
        
        records = df_backup.to_dict(orient="records")
        for r in records:
            if 'id' in r: del r['id']
            if 'created_at' in r: del r['created_at']
            
        conn.client.table("processos").insert(records).execute()
        return True, "✅ Dados restaurados com sucesso!"
    except Exception as e: 
        return False, f"❌ Erro ao tentar restaurar: {e}"

init_db()
EQUIPE_EXPEDICAO, EQUIPE_REVISAO, TODOS_NOMES = carregar_equipes()

def adicionar_aviso(usuario, numero_processo, mensagem):
    try:
        res = conn.client.table("processos").select("despachado").eq("numero_processo", numero_processo).execute().data
        if not res: return False, f"❌ Processo '{numero_processo}' não encontrado no sistema."
        if res[0]['despachado'] == 1: return False, f"❌ O processo '{numero_processo}' já foi concluído."
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
        conn.client.table("afastamentos").insert({
            "usuario": usuario,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "tipo": tipo
        }).execute()
        return True, "✅ Afastamento registrado com sucesso!"
    except Exception as e:
        return False, f"❌ Erro ao salvar no banco: {e}"

def carregar_afastamentos():
    try:
        dados = conn.client.table("afastamentos").select("*").execute().data
        return pd.DataFrame(dados)
    except:
        return pd.DataFrame()
    
def gerar_relatorio_gerencial(mes, ano):
    df_proc = carregar_dados_sqlite()
    df_av = carregar_historico_avisos()
    _, _, equipe_total = carregar_equipes()
    equipe_operacional = [n for n in equipe_total if n.lower() != 'jessyca']
    if df_proc.empty: return False, "Nenhum dado encontrado."
    df_proc['data_conclusao_dt'] = pd.to_datetime(df_proc['data_conclusao'], format="%d/%m/%Y %H:%M:%S", errors='coerce')
    df_proc['data_entrada_dt'] = pd.to_datetime(df_proc['data_entrada'], format="%d/%m/%Y %H:%M:%S", errors='coerce')
    if mes == 0:
        df_periodo = df_proc[(df_proc['data_conclusao_dt'].dt.year == ano) & (df_proc['despachado'] == 1)].copy()
        titulo_periodo = f"ANO COMPLETO DE {ano}"
    else:
        df_periodo = df_proc[(df_proc['data_conclusao_dt'].dt.month == mes) & (df_proc['data_conclusao_dt'].dt.year == ano) & (df_proc['despachado'] == 1)].copy()
        titulo_periodo = f"{mes:02d}/{ano}"
    if df_periodo.empty: return False, f"Nenhum processo foi despachado no período selecionado ({titulo_periodo})."
    total_despachado = len(df_periodo)
    df_periodo['tempo_min'] = (df_periodo['data_conclusao_dt'] - df_periodo['data_entrada_dt']).dt.total_seconds() / 60
    tempo_medio = df_periodo['tempo_min'].mean()
    tempo_str = f"{int(tempo_medio)} minutos" if pd.notna(tempo_medio) else "N/A"
    desempenho = {}
    for colab in equipe_operacional:
        exp_count = len(df_periodo[df_periodo['expedicao'] == colab])
        rev_count = len(df_periodo[df_periodo['revisao'] == colab])
        if (exp_count + rev_count) > 0: desempenho[colab] = exp_count + rev_count
    mais_eficiente = max(desempenho, key=desempenho.get) if desempenho else "N/A"
    ops_eficiente = desempenho.get(mais_eficiente, 0)
    participantes_ativos = set(df_periodo['expedicao'].dropna().unique()).union(set(df_periodo['revisao'].dropna().unique()))
    ficou_de_fora = [c for c in equipe_operacional if c not in participantes_ativos]
    sessoes_periodo = df_periodo['nome_sessao'].unique()
    relatorio_sessoes = []
    for s in sessoes_periodo[:15]:
        df_s = df_periodo[df_periodo['nome_sessao'] == s]
        inicio = df_s['data_entrada_dt'].min()
        fim = df_s['data_conclusao_dt'].max()
        if pd.notna(inicio) and pd.notna(fim):
            duracao = (fim - inicio).total_seconds() / 60
            horas = int(duracao // 60)
            mins = int(duracao % 60)
            tempo_fechamento = f"{horas}h {mins}m" if horas > 0 else f"{mins} minutos"
            relatorio_sessoes.append(f"   - Sessão {s}: {tempo_fechamento}")
    if len(sessoes_periodo) > 15: relatorio_sessoes.append(f"   - ... e mais {len(sessoes_periodo) - 15} sessões geridas com sucesso ao longo do período.")
    df_av['data_dt'] = pd.to_datetime(df_av['data_criacao'], format="%d/%m/%Y %H:%M:%S", errors='coerce')
    if mes == 0: df_av_periodo = df_av[(df_av['data_dt'].dt.year == ano)]
    else: df_av_periodo = df_av[(df_av['data_dt'].dt.month == mes) & (df_av['data_dt'].dt.year == ano)]
    avisos_count = {}
    for colab in equipe_operacional: avisos_count[colab] = len(df_av_periodo[df_av_periodo['usuario'] == colab])
    mais_avisado = max(avisos_count, key=avisos_count.get) if avisos_count and max(avisos_count.values()) > 0 else "Nenhum"
    qnt_avisos = avisos_count.get(mais_avisado, 0)

    texto = f"====================================================\n"
    texto += f" RELATÓRIO GERENCIAL DO SETOR - {titulo_periodo}\n"
    texto += f"====================================================\n\n"
    texto += f"1. VOLUME DE PRODUÇÃO\n"
    texto += f"   - Total de processos concluídos (Despachados): {total_despachado}\n\n"
    texto += f"2. OTIMIZAÇÃO DE TEMPO\n"
    texto += f"   - Tempo médio de ciclo (Entrada ao Despacho): {tempo_str}\n\n"
    texto += f"3. DESTAQUE DE EFICIÊNCIA OPERACIONAL\n"
    texto += f"   - Colaborador mais produtivo: {mais_eficiente} ({ops_eficiente} atuações entre Expedição/Revisão)\n\n"
    texto += f"4. COMUNICAÇÃO E ALERTAS (Gargalos)\n"
    texto += f"   - Mais acionado no Mural de Avisos: {mais_avisado} ({qnt_avisos} alertas recebidos)\n\n"
    texto += f"5. DURAÇÃO DE FECHAMENTO DAS SESSÕES\n"
    texto += "\n".join(relatorio_sessoes) if relatorio_sessoes else "   - Dados insuficientes para cálculo."
    texto += "\n\n"
    texto += f"6. ESCALA DA EQUIPE\n"
    if ficou_de_fora: texto += f"   - Colaboradores sem atuações neste período: {', '.join(ficou_de_fora)}\n\n"
    else: texto += "   - Todos os colaboradores operacionais participaram da pauta no período.\n\n"
    texto += f"====================================================\n"
    texto += f"Documento gerado e auditado automaticamente pelo S.A.D.E.\n"
    texto += f"Para aprovação da Chefia: Jessyca\n"
    texto += f"===================================================="
    return True, texto
# ==========================================
# 3. FRONTEND: RENDERIZAÇÃO DA INTERFACE UI
# ==========================================
init_db()
EQUIPE_EXPEDICAO, EQUIPE_REVISAO, TODOS_NOMES = carregar_equipes()

st.title("⚖️ S.A.D.E. - Sistema de Automação de Distribuição e Expedição")

# ==========================================
# 📢 LETREIRO DE AVISOS (MURAL DINÂMICO)
# ==========================================
df_avisos = obter_avisos_pendentes()
if not df_avisos.empty:
    textos_aviso = []
    for _, row in df_avisos.iterrows():
        textos_aviso.append(f"🚨 <b>{row['usuario']}</b>: Processo <b>{row['numero_processo']}</b> ({row['nome_sessao']}) ➔ {row['mensagem']}")
    
    # Junta todos os avisos com um separador visual
    texto_marquee = " &nbsp;&nbsp;&nbsp;&nbsp; | &nbsp;&nbsp;&nbsp;&nbsp; ".join(textos_aviso)
    
    # Cria o letreiro animado em HTML
    st.markdown(f"""
        <marquee behavior="scroll" direction="left" scrollamount="8" 
                 style="background-color: #ff4b4b; color: white; padding: 10px; 
                        font-size: 18px; border-radius: 5px; margin-bottom: 20px; font-weight: 500;">
            {texto_marquee}
        </marquee>
    """, unsafe_allow_html=True)
# ==========================================

aba_inserir, aba_sessoes, aba_controle, aba_historico, aba_dados, aba_ferias, aba_ajuda = st.tabs([
    "📥 1. Inserir Novos",
    "🗂️ 2. Painel Ativo",
    "📊 3. Controle O.K.",
    "🗄️ 4. Histórico",
    "📈 5. Dados & Desempenho",
    "🌴 6. Férias & Afastamentos",
    "❓ 7. Ajuda & Glossário"
])

# VARIÁVEIS ESSENCIAIS 
nome_sessao_atual = datetime.now().strftime("%d/%m/%Y")
df_geral_status = carregar_dados_sqlite()
sessoes_finalizadas = []

if not df_geral_status.empty and 'despachado' in df_geral_status.columns:
    # 1. Força o tipo numérico no despachado para evitar erro matemático
    df_geral_status['despachado'] = pd.to_numeric(df_geral_status['despachado'], errors='coerce').fillna(0)
    
    # 2. Cria uma chave combinando TIPO e NOME para não misturar sessões do mesmo dia
    df_geral_status['chave_sessao'] = df_geral_status['tipo_sessao'] + " | " + df_geral_status['nome_sessao']
    
    sessoes_stats = df_geral_status.groupby('chave_sessao')['despachado'].agg(['count', 'sum']).reset_index()
    sessoes_finalizadas = sessoes_stats[sessoes_stats['count'] == sessoes_stats['sum']]['chave_sessao'].tolist()
# ------------------------------------------
# ABA 1: INSERÇÃO E DISTRIBUIÇÃO
# ------------------------------------------
with aba_inserir:
    st.header("Passo 1: Configurar a Sessão Atual")
    with st.container(border=True):
        tipo_sessao = st.selectbox("Destino (Tipo de Sessão)",
                                   ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa", "Urgente"])

        if tipo_sessao == "Urgente":
            st.info("🚨 **Modo Urgente:** Marca processos existentes como urgentes (funciona para todos os tipos).")
            expedidores_ativos, revisores_ativos = [], []
        else:
            opcoes_expedicao, opcoes_revisao = EQUIPE_EXPEDICAO.copy(), EQUIPE_REVISAO.copy()
            col3, col4 = st.columns(2)
            # Sem restrições ocultas, tudo na mão do usuário!
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
        
        # --- GERADOR DA PLANILHA MODELO ---
        df_modelo = pd.DataFrame({
            "Processo": ["12345/2026", "67890/2026", "11223/2026"],
            "Relator": ["Conselheiro A", "Conselheiro B", "Conselheiro C"]
        })
        csv_modelo = df_modelo.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📥 Baixar Planilha Modelo (CSV)",
            data=csv_modelo,
            file_name="modelo_importacao.csv",
            mime="text/csv",
            type="secondary"
        )
        # ----------------------------------

        arquivo_upload = st.file_uploader("Arraste sua planilha preenchida (.csv ou .xlsx)", type=["csv", "xlsx"])
        if arquivo_upload is not None:
            df_upload = pd.read_csv(arquivo_upload, encoding='utf-8-sig') if arquivo_upload.name.endswith('.csv') else pd.read_excel(arquivo_upload)
            
            # Mostra uma prévia dos dados para o usuário conferir
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
def color_urgentes(row): return ['color: #ff4b4b; font-weight: bold'] * len(row) if 'urgente_flag' in row and row['urgente_flag'] == 1 else [''] * len(row)

# ------------------------------------------
# ABA 2: PAINEL DAS SESSÕES ATIVAS
# ------------------------------------------
with aba_sessoes:
    sub_aba_ord, sub_aba_ordv, sub_aba_res, sub_aba_adm = st.tabs(["🏛️ Ordinária", "💻 Ordinária Virtual", "🔒 Reservada", "📁 Administrativa"])

    def exibir_tabela_interativa(df_filtrado, key_prefix, data_sessao, tipo_sessao_tb):
        titulo_placeholder = st.empty()
        cols_base = ['id', 'urgente', 'numero_processo', 'relator', 'expedicao', 'expedido_ok', 'revisao', 'revisado_ok']
        if tipo_sessao_tb == "Sessão Reservada": cols_base.extend(['enviado_email', 'enviado_mensageria', 'recebido'])
        cols_base.append('despachado')

        df_exibicao = df_filtrado[cols_base].copy()
        bool_cols = ['expedido_ok', 'revisado_ok', 'despachado']
        if tipo_sessao_tb == "Sessão Reservada": bool_cols.extend(['enviado_email', 'enviado_mensageria', 'recebido'])
        df_exibicao[bool_cols] = df_exibicao[bool_cols].astype(bool)

        rename_dict = {'numero_processo': 'Processo', 'urgente': 'urgente_flag', 'relator': 'Relator', 'expedicao': 'Expedição', 'expedido_ok': 'Expedido', 'revisao': 'Revisão', 'revisado_ok': 'Revisado', 'despachado': 'Despachado'}
        if tipo_sessao_tb == "Sessão Reservada": rename_dict.update({'enviado_email': 'E-mail', 'enviado_mensageria': 'Mensageria', 'recebido': 'Recebido'})

        df_exibicao = df_exibicao.rename(columns=rename_dict)
        styled_df = df_exibicao.style.apply(color_urgentes, axis=1)

        cfg_colunas = {"id": None, "urgente_flag": None, "Processo": st.column_config.TextColumn(disabled=True), "Relator": st.column_config.TextColumn(disabled=True), "Expedição": st.column_config.SelectboxColumn("Expedição", options=TODOS_NOMES, required=True), "Revisão": st.column_config.SelectboxColumn("Revisão", options=TODOS_NOMES, required=True)}
        if tipo_sessao_tb == "Sessão Reservada": cfg_colunas.update({"E-mail": st.column_config.CheckboxColumn("E-mail"), "Mensageria": st.column_config.CheckboxColumn("Mensageria"), "Recebido": st.column_config.CheckboxColumn("Recebido")})

        pendentes = len(df_exibicao[df_exibicao['Despachado'] == False])
        if pendentes > 0: titulo_placeholder.markdown(f"##### 📅 {data_sessao} | ⏳ {pendentes} Pendentes", unsafe_allow_html=True)
        else: titulo_placeholder.markdown(f"##### 📅 {data_sessao} | ✅ Concluído!", unsafe_allow_html=True)

        with st.form(key=f"form_{key_prefix}_{data_sessao}"):
            edited_df = st.data_editor(styled_df, column_config=cfg_colunas, hide_index=True, use_container_width=True, key=f"{key_prefix}_{data_sessao}")
            
            submit_button = st.form_submit_button("💾 Salvar Alterações desta Sessão", type="primary")

            if submit_button:
                alteracoes_feitas = 0
                mapa_banco = {
                    'Expedição': 'expedicao', 'Revisão': 'revisao',
                    'Expedido': 'expedido_ok', 'Revisado': 'revisado_ok', 'Despachado': 'despachado',
                    'E-mail': 'enviado_email', 'Mensageria': 'enviado_mensageria', 'Recebido': 'recebido'
                }
                
                for i in range(len(edited_df)):
                    linha_nova = edited_df.iloc[i].to_dict()
                    linha_antiga = df_exibicao.iloc[i].to_dict()
                    
                    if linha_nova != linha_antiga:
                        mudancas = {}
                        for col_tela, col_banco in mapa_banco.items():
                            if col_tela in linha_nova and linha_nova[col_tela] != linha_antiga.get(col_tela):
                                val = linha_nova[col_tela]
                                if col_tela in ['Expedido', 'Revisado', 'Despachado', 'E-mail', 'Mensageria', 'Recebido']:
                                    mudancas[col_banco] = 1 if val else 0
                                else:
                                    mudancas[col_banco] = val
                        
                        if mudancas:
                            atualizar_processo(int(linha_nova['id']), mudancas)
                            alteracoes_feitas += 1
                
                if alteracoes_feitas > 0:
                    st.toast(f"✅ {alteracoes_feitas} processo(s) atualizado(s) no banco de dados!")
                    time.sleep(1) 
                    st.rerun() 
                else:
                    st.toast("⚠️ Nenhuma alteração foi detectada.")

    with sub_aba_ord:
        df_ord = carregar_dados_sqlite("Sessão Ordinária")
        if not df_ord.empty:
            df_ord['chave_sessao'] = df_ord['tipo_sessao'] + " | " + df_ord['nome_sessao']
            for data in df_ord[~df_ord['chave_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_ord[df_ord['nome_sessao'] == data], "ord", data, "Sessão Ordinária")

    with sub_aba_ordv:
        df_ordv = carregar_dados_sqlite("Sessão Ordinária Virtual")
        if not df_ordv.empty:
            df_ordv['chave_sessao'] = df_ordv['tipo_sessao'] + " | " + df_ordv['nome_sessao']
            for data in df_ordv[~df_ordv['chave_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_ordv[df_ordv['nome_sessao'] == data], "ordv", data, "Sessão Ordinária Virtual")

    with sub_aba_res:
        df_res = carregar_dados_sqlite("Sessão Reservada")
        if not df_res.empty:
            df_res['chave_sessao'] = df_res['tipo_sessao'] + " | " + df_res['nome_sessao']
            for data in df_res[~df_res['chave_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_res[df_res['nome_sessao'] == data], "res", data, "Sessão Reservada")

    with sub_aba_adm:
        df_adm = carregar_dados_sqlite("Sessão Administrativa")
        if not df_adm.empty:
            df_adm['chave_sessao'] = df_adm['tipo_sessao'] + " | " + df_adm['nome_sessao']
            for data in df_adm[~df_adm['chave_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_adm[df_adm['nome_sessao'] == data], "adm", data, "Sessão Administrativa")

# ------------------------------------------
# ABA 3: CONTROLE DE CARGA E ÁREA ADMINISTRATIVA
# ------------------------------------------
with aba_controle:
    if not df_geral_status.empty:
        data_selecionada = st.selectbox("📅 Data da Sessão (OKs):", sorted(df_geral_status['nome_sessao'].unique(), reverse=True))
        df_filtrado = df_geral_status[df_geral_status['nome_sessao'] == data_selecionada]
        col_exp, col_rev = st.columns(2)
        with col_exp: st.dataframe(df_filtrado['expedicao'].value_counts().reset_index(), hide_index=True)
        with col_rev: st.dataframe(df_filtrado['revisao'].value_counts().reset_index(), hide_index=True)

    st.markdown("---")
    with st.container(border=True):
        st.subheader("🗑️ Remover Processo Específico (Saiu de Pauta)")
        col_rm1, col_rm2, col_rm3, col_rm4 = st.columns([2, 2, 2, 1])
        with col_rm1: proc_para_remover = st.text_input("Número Exato do Processo:")
        with col_rm2:
            datas_disp = sorted(df_geral_status['nome_sessao'].unique(), reverse=True) if not df_geral_status.empty else []
            data_sessao_remover = st.selectbox("Data da Sessão:", datas_disp)
        with col_rm3:
            motivo_remocao = st.selectbox("Motivo:", ["Fora de pauta", "Incluído errado", "Teste", "Outros"], key="motivo_proc")
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
    with st.expander("⚙️ Área Administrativa Avançada (Equipe e Banco de Dados)"):
        
        # --- PAINEL DO LETREIRO AQUI ---
        st.subheader("📢 Mural de Avisos (Letreiro)")
        col_av1, col_av2, col_av3 = st.columns([1, 1, 2])
        with col_av1:
            # CORREÇÃO APLICADA AQUI: ADIÇÃO DO ["Todos"]
            aviso_usuario = st.selectbox("Para quem?", ["Todos"] + TODOS_NOMES, key="aviso_usr")
        with col_av2:
            aviso_processo = st.text_input("Nº do Processo Ativo", key="aviso_proc")
        with col_av3:
            aviso_msg = st.text_input("Mensagem", placeholder="Ex: Tratar com urgência, falta anexo...", key="aviso_msg")
        
        if st.button("📢 Publicar no Letreiro", type="primary", use_container_width=True):
            if aviso_processo and aviso_msg:
                ok, msg = adicionar_aviso(aviso_usuario, aviso_processo, aviso_msg)
                if ok:
                    st.success(msg)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("⚠️ Preencha o número do processo e a mensagem para publicar.")
        st.markdown("---")
        # -------------------------------

       # --- NOMEAR / IDENTIFICAR SESSÃO ---
        st.subheader("🏷️ Identificar / Nomear Sessão")
        st.write("Vincule o número oficial para cada tipo de sessão individualmente.")
        
        col_sn1, col_sn2, col_sn3, col_sn4 = st.columns([2, 2, 1, 1.5])
        with col_sn1:
            sessoes_disp = sorted(df_geral_status['nome_sessao'].unique(), reverse=True) if not df_geral_status.empty else []
            sessao_alvo = st.selectbox("Data / Sessão Alvo:", sessoes_disp)
        with col_sn2:
            tipos_disp = ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa"]
            tipo_alvo = st.selectbox("Qual o Tipo de Sessão?", tipos_disp)
        with col_sn3:
            num_oficial = st.text_input("Número:", placeholder="Ex: 125")
        with col_sn4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🏷️ Confirmar", type="primary", use_container_width=True):
                if num_oficial and sessao_alvo:
                    # Extrai a data pura se a sessão já tiver sido renomeada antes
                    if " - " in sessao_alvo:
                        data_pura = sessao_alvo.split(" - ")[-1].strip()
                        novo_nome = f"Sessão {num_oficial} - {data_pura}"
                    else:
                        novo_nome = f"Sessão {num_oficial} - {sessao_alvo}"
                    
                    # Envia a data alvo, o novo nome e o TIPO exato que deve ser alterado
                    ok, msg = renomear_sessao(sessao_alvo, novo_nome, tipo_alvo)
                    if ok:
                        st.success(msg)
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("⚠️ Digite o número da pauta.")
        st.markdown("---")
        # -----------------------------------
                
        # --- RELATÓRIO GERENCIAL ---
        st.subheader("📄 Relatório Gerencial Mensal/Anual (Para Assinatura)")
        st.write("Gere um documento completo com métricas de desempenho para análise da Chefia.")
        col_m1, col_m2, col_m3 = st.columns([1, 1, 2])
        
        # O número 0 aciona a lógica do "Ano Inteiro" no backend
        meses_dict = {0: "🗓️ Anual (Ano Inteiro)", 1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
        mes_atual = datetime.now().month
        ano_atual = datetime.now().year
        
        with col_m1:
            mes_selecionado = st.selectbox("Período:", list(meses_dict.keys()), index=mes_atual, format_func=lambda x: meses_dict[x])
        with col_m2:
            ano_selecionado = st.selectbox("Ano:", range(2024, ano_atual + 1), index=ano_atual-2024)
        with col_m3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📊 Compilar Relatório", type="primary", use_container_width=True):
                ok, texto_relatorio = gerar_relatorio_gerencial(mes_selecionado, ano_selecionado)
                if ok:
                    st.success("Relatório gerado com sucesso!")
                    st.code(texto_relatorio, language="markdown")
                    
                    # Nomeia o arquivo do jeito certo dependendo se é Anual ou Mensal
                    nome_arquivo = f"Relatorio_Gerencial_{ano_selecionado}.txt" if mes_selecionado == 0 else f"Relatorio_Gerencial_{mes_selecionado:02d}_{ano_selecionado}.txt"
                    
                    st.download_button(
                        label="📥 Baixar Relatório (Arquivo de Texto)", 
                        data=texto_relatorio.encode('utf-8'), 
                        file_name=nome_arquivo, 
                        mime="text/plain",
                        type="secondary"
                    )
                else:
                    st.warning(texto_relatorio)
        st.markdown("---")
        # -------------------------------
        
        st.subheader("👥 Gestão de Colaboradores")
        acao_equipe = st.radio("Selecione a ação:", ["Adicionar Novo", "Editar Permissões", "Substituir Nome", "Remover Colaborador"], horizontal=True)

        if acao_equipe == "Adicionar Novo":
            col1, col2 = st.columns(2)
            novo_colab = col1.text_input("Nome do novo colaborador")
            faz_exp, faz_rev = col2.checkbox("Participa da Expedição", value=True), col2.checkbox("Participa da Revisão", value=True)
            if st.button("➕ Adicionar", type="primary", key="add_user"):
                ok, m = gerenciar_usuario('adicionar', novo_colab, expedicao=int(faz_exp), revisao=int(faz_rev))
                if ok: st.success(m); time.sleep(1); st.rerun()

        elif acao_equipe == "Editar Permissões":
            col1, col2, col3 = st.columns(3)
            colab_editar = col1.selectbox("Selecione o colaborador", TODOS_NOMES)
            faz_exp = col2.checkbox("Participa da Expedição", value=True, key="edit_exp")
            faz_rev = col3.checkbox("Participa da Revisão", value=True, key="edit_rev")
            if st.button("✏️ Atualizar Permissões", type="primary", key="edit_user"):
                ok, m = gerenciar_usuario('editar', colab_editar, expedicao=int(faz_exp), revisao=int(faz_rev))
                if ok: 
                    st.success(m)
                    time.sleep(1)
                    st.rerun()

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

        # --- INSERÇÃO DIRETA NO HISTÓRICO (RECUPERAÇÃO/MIGRAÇÃO) ---
        st.subheader("🕰️ Migração de Processos Direto para o Histórico")
        st.write("Insira processos antigos já finalizados. Eles pularão o Painel Ativo e irão direto para o Arquivo.")
        
        # --- GERADOR DA PLANILHA MODELO PARA HISTÓRICO ---
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
                sucessos = 0
                
                # Se enviou planilha (Em lote)
                if arquivo_hist is not None:
                    df_up = pd.read_csv(arquivo_hist, encoding='utf-8-sig') if arquivo_hist.name.endswith('.csv') else pd.read_excel(arquivo_hist)
                    barra = st.progress(0)
                    
                    for index, row in df_up.iterrows():
                        # 1. Puxa Processo e Relator e já limpa os dados
                        p_val = str(row['Processo']).strip() if pd.notna(row.get('Processo')) else ""
                        r_val = str(row.get('Relator', '')).strip() if pd.notna(row.get('Relator')) else ""
                        p_limpo, r_limpo = higienizar_dados(p_val, r_val)
                        
                        # 2. Puxa Expedidor e Revisor
                        exp_val = str(row.get('Expedidor', hist_exp)).strip() if pd.notna(row.get('Expedidor')) else hist_exp
                        rev_val = str(row.get('Revisor', hist_rev)).strip() if pd.notna(row.get('Revisor')) else hist_rev
                        
                        # 3. Puxa a Data e o Tipo
                        data_val = str(row.get('Data_Sessao', hist_sessao)).strip() if pd.notna(row.get('Data_Sessao')) else hist_sessao
                        tipo_val = str(row.get('Tipo_Sessao', hist_tipo)).strip() if pd.notna(row.get('Tipo_Sessao')) else hist_tipo
                        
                        # Formatação de segurança
                        if " " in data_val and "-" in data_val:
                            try:
                                data_val = datetime.strptime(data_val.split()[0], "%Y-%m-%d").strftime("%d/%m/%Y")
                            except: pass

                        if p_limpo and not processo_existe(p_limpo):
                            # Cria o carimbo de tempo usando a data real da sessão + um horário padrão de fechamento
                            data_historico = f"{data_val} 23:59:59"
                            try:
                                conn.client.table("processos").insert({
                                    "numero_processo": p_limpo, 
                                    "relator": r_limpo, 
                                    "tipo_sessao": tipo_val,     
                                    "nome_sessao": data_val,     
                                    "expedicao": exp_val, 
                                    "revisao": rev_val,   
                                    "data_entrada": data_historico, "data_expedido": data_historico, "data_revisado": data_historico, "data_conclusao": data_historico,
                                    "expedido_ok": 1, "revisado_ok": 1, "despachado": 1, "urgente": 0,
                                    "enviado_email": 0, "enviado_mensageria": 0, "recebido": 0
                                }).execute()
                                sucessos += 1
                            except Exception as e: 
                                st.error(f"❌ Erro ao tentar inserir o processo {p_limpo}: {e}")
                                
                        barra.progress((index + 1) / len(df_up))
                        
                # Se digitou manual (Um por vez)
                elif hist_proc:
                    p_limpo, r_limpo = higienizar_dados(hist_proc, hist_rel)
                    if not processo_existe(p_limpo):
                        try:
                            conn.client.table("processos").insert({
                                "numero_processo": p_limpo, "relator": r_limpo, "tipo_sessao": hist_tipo, 
                                "nome_sessao": hist_sessao, "expedicao": hist_exp, "revisao": hist_rev, 
                                "data_entrada": agora, "data_expedido": agora, "data_revisado": agora, "data_conclusao": agora,
                                "expedido_ok": 1, "revisado_ok": 1, "despachado": 1, "urgente": 0
                            }).execute()
                            sucessos += 1
                        except: pass
                    else: st.error("❌ Este processo já existe no sistema.")
                
                if sucessos > 0:
                    st.success(f"🎉 {sucessos} processos recuperados e enviados direto para o Histórico da pauta '{hist_sessao}'!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.warning("⚠️ Nenhum processo novo foi inserido.")
        st.markdown("---")
        
        st.subheader("🧹 Limpeza Seletiva do Sistema (Apagar Sessão)")
        col_tipo, col_data, col_motivo_sess, col_btn = st.columns([2, 2, 2, 1])
        with col_tipo: tipo_apagar = st.selectbox("Apagar de qual tipo?", ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa"])
        with col_data:
            datas_disp_apagar = df_geral_status[df_geral_status['tipo_sessao'] == tipo_apagar]['nome_sessao'].unique() if not df_geral_status.empty else []
            data_apagar = st.selectbox("Qual data?", sorted(datas_disp_apagar, reverse=True)) if len(datas_disp_apagar) > 0 else st.selectbox("Qual data?", ["Sem dados"])
        with col_motivo_sess:
            motivo_sessao = st.selectbox("Motivo da Exclusão:", ["Sessão Cancelada", "Fora de pauta", "Incluído errado", "Teste", "Outros"], key="motivo_sess")
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Apagar Sessão", type="primary", use_container_width=True) and data_apagar != "Sem dados":
                apagar_sessao_especifica(tipo_apagar, data_apagar, motivo_sessao)
                st.success(f"Sessão de {data_apagar} enviada para a lixeira com sucesso!")
                time.sleep(1.5)
                st.rerun()

# ------------------------------------------
# ABA 4: HISTÓRICO, EXCLUSÕES E AVISOS
# ------------------------------------------
with aba_historico:
    sub_aba_concluidas, sub_aba_lixeira, sub_aba_hist_avisos, sub_aba_hist_ferias = st.tabs([
        "✅ Arquivo: Concluídas", 
        "🗑️ Auditoria: Processos Excluídos",
        "📢 Auditoria: Histórico de Avisos",
        "📋 Auditoria: Férias e Ausências"
    ])
   
    # --- sub-aba 1: CONCLUÍDAS ---
   # --- sub-aba 1: CONCLUÍDAS ---
    with sub_aba_concluidas:
        st.subheader("Sessões 100% Concluídas")
        if sessoes_finalizadas:
            # 1. Filtra usando a nossa nova chave
            df_historico = df_geral_status[df_geral_status['chave_sessao'].isin(sessoes_finalizadas)].copy()
            df_historico_display = df_historico[['numero_processo', 'urgente', 'relator', 'expedicao', 'revisao', 'data_conclusao', 'tipo_sessao', 'nome_sessao']].copy()
            
            # 2. A LINHA QUE SUMIU VOLTOU AQUI (Renomeia as colunas pro visual):
            df_historico_display = df_historico_display.rename(columns={'numero_processo': 'Processo', 'urgente': 'urgente_flag', 'relator': 'Conselheiro', 'expedicao': 'Expedidor', 'revisao': 'Revisor', 'data_conclusao': 'Data/Hora Conclusão', 'tipo_sessao': 'Tipo de Sessão', 'nome_sessao': 'Data da Sessão'})
            
            with st.expander("🔎 Filtros de Busca Avançada", expanded=True):
                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                with col_f1:
                    datas_unicas = sorted(df_historico_display['Data da Sessão'].unique(), reverse=True)
                    filtro_sessao = st.multiselect("📅 Data da Sessão", options=datas_unicas)
                with col_f2:
                    filtro_usuario = st.multiselect("👥 Colaborador (Exp/Rev)", options=TODOS_NOMES)
                with col_f3:
                    filtro_processo = st.text_input("📄 Nº do Processo", placeholder="Ex: 12345")
                with col_f4:
                    filtro_relator = st.text_input("⚖️ Relator", placeholder="Nome...")

            df_filtrado_hist = df_historico_display.copy()
            if filtro_sessao: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Data da Sessão'].isin(filtro_sessao)]
            if filtro_usuario: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Expedidor'].isin(filtro_usuario) | df_filtrado_hist['Revisor'].isin(filtro_usuario)]
            if filtro_processo: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Processo'].astype(str).str.contains(filtro_processo, case=False, na=False)]
            if filtro_relator: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Conselheiro'].astype(str).str.contains(filtro_relator, case=False, na=False)]

            st.markdown(f"**📊 Resultados encontrados:** `{len(df_filtrado_hist)}` processos.")
            if not df_filtrado_hist.empty:
                styled_hist = df_filtrado_hist.iloc[::-1].style.apply(color_urgentes, axis=1)
                st.dataframe(styled_hist, hide_index=True, use_container_width=True, column_config={"urgente_flag": None})
            else: st.warning("Nenhum processo encontrado com esses filtros.")
        else: st.info("📭 O histórico está vazio. Nenhuma sessão foi 100% concluída ainda.")

    # --- sub-aba 2: LIXEIRA ---
    with sub_aba_lixeira:
        st.subheader("Registro de Exclusões (Auditoria de Pauta)")
        df_excluidos = carregar_excluidos()
        if not df_excluidos.empty:
            df_excluidos_display = df_excluidos.rename(columns={'numero_processo': 'Processo', 'relator': 'Relator', 'data_exclusao': 'Data/Hora da Exclusão', 'motivo': 'Motivo Declarado'})
            st.dataframe(df_excluidos_display[['Processo', 'Relator', 'Motivo Declarado', 'Data/Hora da Exclusão']].iloc[::-1], hide_index=True, use_container_width=True)
            csv_lixo = df_excluidos_display.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Baixar Relatório de Exclusões (CSV)", data=csv_lixo, file_name="auditoria_exclusoes.csv", mime='text/csv', type="secondary")
        else:
            st.success("✨ A lixeira está vazia. Nenhum processo foi apagado do sistema.")

    # --- sub-aba 3: HISTÓRICO DE AVISOS (A NOVA PLANILHA!) ---
    with sub_aba_hist_avisos:
        st.subheader("Histórico Completo de Avisos Publicados")
        df_hist_av = carregar_historico_avisos()
        
        if not df_hist_av.empty:
            df_hist_av_display = df_hist_av.rename(columns={
                'numero_processo': 'Processo',
                'usuario': 'Destinatário do Alerta',
                'mensagem': 'Comunicado / Ordem',
                'data_criacao': 'Data/Hora de Publicação',
                'status': 'Situação Atual'
            })
            
            # Reorganiza as colunas para ficar visualmente perfeito
            if 'Processo' in df_hist_av_display.columns:
                colunas_ordem = ['Processo', 'Destinatário do Alerta', 'Comunicado / Ordem', 'Data/Hora de Publicação', 'Situação Atual']
                st.dataframe(df_hist_av_display[colunas_ordem].iloc[::-1], hide_index=True, use_container_width=True)
                
                # Botão para baixar a planilha de auditoria de avisos
                csv_avisos = df_hist_av_display[colunas_ordem].to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Baixar Relatório de Avisos (CSV)", data=csv_avisos, file_name="auditoria_mural_avisos.csv", mime='text/csv', type="secondary")
        else:
            st.info("📢 Nenhum comunicado foi publicado no mural de avisos até o momento.")

      # --- sub-aba 4: AUDITORIA DE FÉRIAS E AUSÊNCIAS ---
    with sub_aba_hist_ferias:
        st.subheader("Histórico Geral de Afastamentos Encerrados")
        st.write("Registro cronológico de ausências que já foram concluídas (o colaborador já retornou ao trabalho).")
        
        df_af_hist = carregar_afastamentos()
        if not df_af_hist.empty:
            hoje = datetime.now().date()
            df_af_hist['dt_fim_compare'] = pd.to_datetime(df_af_hist['data_fim'], format="%d/%m/%Y").dt.date
            
            # Filtro Inteligente: A data de fim é menor que hoje? Se sim, o afastamento já passou!
            df_passadas = df_af_hist[df_af_hist['dt_fim_compare'] < hoje].copy()
            
            if not df_passadas.empty:
                df_passadas_display = df_passadas.rename(columns={
                    'usuario': 'Colaborador',
                    'tipo': 'Motivo Declarado',
                    'data_inicio': 'Data Inicial',
                    'data_fim': 'Data de Retorno'
                })
                
                # Exibe do mais recente para o mais antigo (.iloc[::-1])
                st.dataframe(df_passadas_display[['Colaborador', 'Motivo Declarado', 'Data Inicial', 'Data de Retorno']].iloc[::-1], hide_index=True, use_container_width=True)
                
                # Botão para baixar a planilha de auditoria
                csv_ferias = df_passadas_display[['Colaborador', 'Motivo Declarado', 'Data Inicial', 'Data de Retorno']].to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Baixar Relatório de Histórico de Ausências (CSV)", data=csv_ferias, file_name="auditoria_afastamentos_equipe.csv", mime='text/csv', type="secondary")
            else:
                st.info("Nenhum afastamento antigo arquivado no histórico até o momento.")
        else:
            st.info("Nenhum registro de afastamento encontrado no sistema.")
        
# ==========================================
# ABA 5: DADOS & DESEMPENHO (ANALYTICS)
# ==========================================
with aba_dados:
    st.header("📈 Dashboard Analítico e Distribuição Operacional")
    
    df_dados = carregar_dados_sqlite()
    
    if df_dados.empty or 'data_expedido' not in df_dados.columns: 
        st.info("📊 O banco de dados está vazio. Comece a inserir processos para gerar o dashboard.")
    else:
        # --- 1. PREPARAÇÃO E LIMPEZA DE DADOS ---
        # Parse seguro de datas para todos os formatos (com hora ou só data)
        for c in ['data_entrada', 'data_expedido', 'data_revisado', 'data_conclusao']:
            df_dados[c + '_dt'] = pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M:%S", errors='coerce').fillna(
                                  pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M", errors='coerce'))
        
        df_concluidos = df_dados[df_dados['despachado'] == 1].copy()
        
        # Filtro de Ouro: Pega só processos onde a Entrada é diferente da Conclusão
        # Isso ignora os processos antigos importados direto para o histórico (onde entrada = conclusao no mesmo segundo)
        df_tempo_real = df_concluidos[df_concluidos['data_entrada'] != df_concluidos['data_conclusao']].copy()
        
        # Cálculos matemáticos de tempo (em minutos)
        df_tempo_real['min_exp'] = (df_tempo_real['data_expedido_dt'] - df_tempo_real['data_entrada_dt']).dt.total_seconds() / 60
        df_tempo_real['min_rev'] = (df_tempo_real['data_revisado_dt'] - df_tempo_real['data_expedido_dt']).dt.total_seconds() / 60
        df_tempo_real['min_total'] = (df_tempo_real['data_conclusao_dt'] - df_tempo_real['data_entrada_dt']).dt.total_seconds() / 60

        def format_tempo(minutos):
            if pd.isna(minutos) or minutos < 0: return "N/A"
            return f"{int(minutos)} min" if int(minutos) < 60 else f"{int(minutos) // 60}h {int(minutos) % 60}m"

        # --- 2. SELETOR DE VISÃO GERAL OU INDIVIDUAL ---
        st.markdown("### Selecione o Perfil de Análise")
        visao_selecionada = st.selectbox("Escolha a Visão:", ["Todo o Setor (Global)"] + TODOS_NOMES, label_visibility="collapsed")
        st.markdown("---")

        # ==========================================================
        # VISÃO 1: GLOBAL DO SETOR
        # ==========================================================
        if visao_selecionada == "Todo o Setor (Global)":
            
            # BLOCO 1: VISÃO MACRO E URGÊNCIAS
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
            
            # BLOCO 2: CARGA DE TRABALHO
            st.markdown("### 🤝 Volume de Participação Operacional (Carga de Trabalho)")
            st.write("Análise da distribuição da volumetria entre a equipe, auxiliando na prevenção de gargalos e sobrecargas.")
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.markdown("#### 📦 Expedição") # Título adicionado
                exp_counts = df_concluidos['expedicao'].value_counts().reset_index()
                exp_counts.columns = ['Colaborador', 'Processos']
                if not exp_counts.empty:
                    # Gráfico de Rosca com legendas automáticas
                    fig_exp = px.pie(exp_counts, values='Processos', names='Colaborador', hole=0.5)
                    fig_exp.update_traces(textposition='inside', textinfo='percent+value')
                    fig_exp.update_layout(margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="rgba(0,0,0,0)", legend_title="Colaborador")
                    st.plotly_chart(fig_exp, use_container_width=True)
                else: st.info("Sem dados de expedição.")
                
            with col_g2:
                st.markdown("#### 🔍 Revisão") # Título adicionado
                rev_counts = df_concluidos['revisao'].value_counts().reset_index()
                rev_counts.columns = ['Colaborador', 'Processos']
                if not rev_counts.empty:
                    # Gráfico de Rosca com legendas automáticas
                    fig_rev = px.pie(rev_counts, values='Processos', names='Colaborador', hole=0.5)
                    fig_rev.update_traces(textposition='inside', textinfo='percent+value')
                    fig_rev.update_layout(margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="rgba(0,0,0,0)", legend_title="Colaborador")
                    st.plotly_chart(fig_rev, use_container_width=True)
                else: st.info("Sem dados de revisão.")

            st.markdown("---")

            # BLOCO 3: CADÊNCIA DE TRABALHO (TEMPOS MÉDIOS)
            st.markdown("### ⏱️ Cadência e Desempenho (Métricas Reais de Tempo)")
            st.caption("*As médias de tempo abaixo consideram apenas os processos operados ativamente no painel, ignorando importações em lote do histórico.*")
            
            c_t1, c_t2, c_t3 = st.columns(3)
            c_t1.metric("Média de Elaboração (Expedição)", format_tempo(df_tempo_real['min_exp'].mean()))
            c_t2.metric("Média de Conferência (Revisão)", format_tempo(df_tempo_real['min_rev'].mean()))
            c_t3.metric("Tempo de Ciclo (Entrada a Despacho)", format_tempo(df_tempo_real['min_total'].mean()))

            st.markdown("---")

            # BLOCO 4: RADAR ATIVO (SESSÕES EM ANDAMENTO)
            st.markdown("### 📡 Radar em Tempo Real (Painel Ativo)")
            
            sessoes_stats = df_dados.groupby('nome_sessao')['despachado'].agg(['count', 'sum']).reset_index()
            ativas_list = sessoes_stats[sessoes_stats['count'] > sessoes_stats['sum']]['nome_sessao'].tolist()
            df_ativos_reais = df_dados[df_dados['nome_sessao'].isin(ativas_list)].copy()

            if not df_ativos_reais.empty:
                # Mudamos para 5 colunas para caber o novo indicador
                col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
                
                # Conta processos urgentes que NÃO foram despachados ainda
                urg_pendentes = len(df_ativos_reais[(df_ativos_reais['urgente'] == 1) & (df_ativos_reais['despachado'] == 0)])
                
                col_r1.metric("📋 Total na Pauta Ativa", len(df_ativos_reais))
                col_r2.metric("⏳ Aguardando Elaboração", len(df_ativos_reais[df_ativos_reais['expedido_ok'] == 0]))
                col_r3.metric("🔍 Aguardando Conferência", len(df_ativos_reais[(df_ativos_reais['expedido_ok'] == 1) & (df_ativos_reais['revisado_ok'] == 0)]))
                col_r4.metric("✍️ Prontos p/ Despacho", len(df_ativos_reais[(df_ativos_reais['revisado_ok'] == 1) & (df_ativos_reais['despachado'] == 0)]))
                
                # Caixinha customizada em vermelho para dar destaque aos Urgentes
                with col_r5:
                    st.markdown(f"""
                    <div style='background-color: #ff4b4b; padding: 15px; border-radius: 8px; text-align: center; color: white; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);'>
                        <p style='margin: 0; font-size: 14px; font-weight: bold;'>🚨 Urgentes Restantes</p>
                        <h2 style='margin: 0; padding-top: 5px; color: white; font-weight: bold;'>{urg_pendentes}</h2>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("✨ Pauta limpa! Não há processos pendentes no radar ativo neste exato momento.")

        # ==========================================================
        # VISÃO 2: RAIO-X INDIVIDUAL
        # ==========================================================
        else:
            st.subheader(f"🔎 Perfil Operacional: {visao_selecionada}")
            
            # Verificação de Férias e Afastamentos Ativos
            try:
                ausentes = obter_colaboradores_ausentes_hoje()
            except:
                ausentes = []
                
            if visao_selecionada in ausentes:
                st.warning(f"📌 **Status no Dia de Hoje:** Afastamento Legítimo Ativo (Férias, Recesso ou Atestado). A carga de trabalho do colaborador encontra-se pausada no sistema de distribuição.", icon="🌴")
            else:
                st.info(f"📌 **Status no Dia de Hoje:** Ativo e Operacional.", icon="✅")
                
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
            
            st.markdown("#### ⏱️ Qualidade e Cadência (Tempos Médios de Resposta)")
            df_user_tempo_exp = df_tempo_real[df_tempo_real['expedicao'] == visao_selecionada]
            df_user_tempo_rev = df_tempo_real[df_tempo_real['revisao'] == visao_selecionada]
            
            cu1, cu2, cu3 = st.columns(3)
            cu1.metric("Tempo Médio de Elaboração (Expedição)", format_tempo(df_user_tempo_exp['min_exp'].mean()))
            cu2.metric("Tempo Médio de Conferência (Revisão)", format_tempo(df_user_tempo_rev['min_rev'].mean()))
            
            # Inteligência: Dupla mais frequente
            if not df_user_total.empty:
                parceiros = []
                parceiros.extend(df_user_exp['revisao'].tolist())
                parceiros.extend(df_user_rev['expedicao'].tolist())
                if parceiros:
                    dupla = pd.Series(parceiros).mode()[0]
                    cu3.metric("🤝 Parceiro Operacional Mais Frequente", dupla)
                else:
                    cu3.metric("🤝 Parceiro Operacional", "N/A")
            else:
                cu3.metric("🤝 Parceiro Operacional", "N/A")

# ------------------------------------------
# ABA 6: FÉRIAS E AFASTAMENTOS
# ------------------------------------------
with aba_ferias:
    st.header("🌴 Painel de Férias e Afastamentos Operacionais")
    st.write("Registre os períodos de ausência legítima da equipe para automatizar o bloqueio na distribuição de processos.")
    
    # Formulário de Inserção Manual
    with st.container(border=True):
        st.subheader("📝 Registrar Nova Ausência")
        with st.form("form_afastamento", clear_on_submit=True):
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            with col_f1:
                usr_afastado = st.selectbox("Colaborador:", TODOS_NOMES)
            with col_f2:
                d_inicio = st.date_input("Data de Início:", format="DD/MM/YYYY")
            with col_f3:
                d_fim = st.date_input("Data de Fim (Retorno):", format="DD/MM/YYYY")
            with col_f4:
                t_afastamento = st.selectbox("Tipo de Ausência:", ["Férias", "Recesso", "Atestado Médico"])
                
            if st.form_submit_button("🚀 Confirmar e Bloquear no Sistema", type="primary", use_container_width=True):
                if d_inicio > d_fim:
                    st.error("❌ Erro: A data de início não pode ser maior que a data de término.")
                else:
                    ini_str = d_inicio.strftime("%d/%m/%Y")
                    fim_str = d_fim.strftime("%d/%m/%Y")
                    ok, msg = salvar_afastamento(usr_afastado, ini_str, fim_str, t_afastamento)
                    if ok:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
                        
    st.markdown("---")
    st.subheader("📋 Quadro de Ausências Ativas (Quem está fora hoje)")
    df_af = carregar_afastamentos()
    
    if not df_af.empty:
        hoje = datetime.now().date()
        # Converte as strings temporariamente para formato de data para o Python calcular sozinho
        df_af['dt_inicio_compare'] = pd.to_datetime(df_af['data_inicio'], format="%d/%m/%Y").dt.date
        df_af['dt_fim_compare'] = pd.to_datetime(df_af['data_fim'], format="%d/%m/%Y").dt.date
        
        # Filtro Inteligente: O dia de hoje está entre o início e o fim da folga da pessoa?
        df_ativas = df_af[(hoje >= df_af['dt_inicio_compare']) & (hoje <= df_af['dt_fim_compare'])].copy()
        
        if not df_ativas.empty:
            df_ativas_display = df_ativas.rename(columns={
                'usuario': 'Colaborador Ausente',
                'tipo': 'Tipo / Motivo',
                'data_inicio': 'Data de Saída',
                'data_fim': 'Data de Retorno'
            })
            st.dataframe(df_ativas_display[['Colaborador Ausente', 'Tipo / Motivo', 'Data de Saída', 'Data de Retorno']], hide_index=True, use_container_width=True)
        else:
            st.success("✨ Excelente! Toda a equipe operacional está ativa e disponível hoje.")
    else:
        st.info("✨ Nenhum afastamento ativo registrado no momento.")

# ------------------------------------------
# ABA 7: AJUDA E GLOSSÁRIO
# ------------------------------------------
with aba_ajuda:
    st.header("📖 Manual do Usuário e Ajuda Detalhada - S.A.D.E.")
    st.write("Bem-vindo(a) ao guia passo a passo do Sistema de Automação de Distribuição e Expedição. Clique nos tópicos abaixo para entender como usar cada ferramenta. Este manual foi feito para ser simples e direto, para te ajudar no dia a dia!")

    with st.expander("📥 1. Como usar a Aba 1 (Inserir Novos) e Importar Planilhas"):
        st.markdown("""
        A primeira aba é onde o trabalho começa. Aqui você diz ao sistema quais processos entrarão na pauta do dia. Você tem duas opções:
        
        **Opção A: Digitar um por vez (Inserção Manual)**
        Ideal para quando chegarem poucos processos.
        1. Escolha o **Destino** (Ex: Sessão Ordinária).
        2. Digite o número da sessão (opcional).
        3. Selecione quem da equipe vai trabalhar hoje nas caixas de Expedição e Revisão.
        4. Digite o número do processo e o nome do Relator e clique no botão azul "Verificar e Processar".
        
        ---

        **Opção B: Importar Planilha (Para inserir muitos processos de uma vez)**
        Se você tem 10, 20 ou mais processos, não perca tempo digitando um por um. Use o método em lote! Siga este passo a passo com atenção:
        
        * **Passo 1:** Clique no botão cinza **"📥 Baixar Planilha Modelo"**. O computador vai salvar um arquivo no seu formato padrão (geralmente na sua pasta Downloads).
        * **Passo 2:** Abra esse arquivo no Excel (ou no programa de planilhas do seu computador). Você verá apenas duas colunas escritas: `Processo` e `Relator`.
        * **Passo 3:** Preencha com os seus dados! Apague os números de exemplo e cole a sua lista de processos na primeira coluna e os relatores na segunda.
        
        ⚠️ **Regras de Ouro do Excel para não dar erro no sistema:**
        * **NÃO** mude o nome das colunas lá em cima (deixe escrito exatamente "Processo" e "Relator").
        * **NÃO** deixe linhas totalmente em branco no meio da lista.
        * **NÃO** adicione outras colunas inventadas (como "Data", "Observação", etc). O sistema só quer saber do número e do relator.
        
        * **Passo 4:** Salve o arquivo no seu computador e feche o Excel.
        * **Passo 5:** Volte para o sistema na Aba 1, clique em **"Browse files"** (ou arraste o arquivo que você salvou para dentro da caixinha tracejada).
        * **Passo 6:** O sistema vai te mostrar uma "amostra" para você ver se os dados estão certos. Estando tudo OK, clique no botão azul **"🚀 Iniciar Importação"**. Em poucos segundos, todo o lote será distribuído para a equipe!
        """)

    with st.expander("🗂️ 2. Como usar a Aba 2 (Painel Ativo)"):
        st.markdown("""
        Esta é a mesa de trabalho digital da equipe. 
        
        * **Trabalho em Equipe:** Todo mundo pode ficar com essa tela aberta ao mesmo tempo no próprio computador.
        * **Marcando as Tarefas:** Conforme o documento for feito, marque a caixinha **"Expedido"**. O colega que revisar o documento marque **"Revisado"**.
        * **Mudando Nomes:** Se o sistema escalou a pessoa "A" para fazer um processo, mas a pessoa "B" vai fazer no lugar, é só clicar no nome da pessoa "A" na tabela e trocar na hora.
        * **Finalizando:** Quando o processo estiver 100% pronto, assinado e entregue, marque a caixa **"Despachado"**. 
        
        ⚠️ **IMPORTANTE:** Sempre que marcar as caixinhas, lembre-se de clicar no botão azul embaixo da tabela **"💾 Salvar Alterações desta Sessão"**. O processo que foi "Despachado" vai sumir da sua frente e será guardado em segurança no Histórico.
        """)

    with st.expander("📊 3. Como usar a Aba 3 (Controle, Letreiro e Correções)"):
        st.markdown("""
        Esta aba é a sala da Chefia e de quem precisa arrumar erros ou gerenciar a comunicação.
        
        * **📢 Mural de Avisos (Letreiro Vermelho):** Precisa dar um alerta para a equipe? Vá no Mural, escolha para quem é o recado, coloque o número do processo e a mensagem. O recado fica passando no topo da tela de todos. Quando a equipe despachar aquele processo na Aba 2, o recado some sozinho!
        * **🗑️ Remover Processo Específico:** Alguém importou um processo errado na Aba 1? Sem pânico. Digite o número dele aqui, a data e o motivo. Ele será retirado da equipe e enviado para a Lixeira de Auditoria.
        * **🏷️ Nomear Sessões:** É aqui que a chefia organiza a casa. Escolha a data de hoje, escolha o tipo (Ex: Sessão Reservada), e digite o número oficial da pauta (Ex: 45). Todas as tabelas da equipe vão ser atualizadas para esse nome oficial automaticamente.
        """)

    with st.expander("🗄️ 4. Abas 4 e 5 (Histórico e Desempenho Visual)"):
        st.markdown("""
        O sistema guarda e analisa o trabalho sozinho para você não ter que usar calculadoras.
        
        * **Aba 4 (Histórico):** É o "Arquivo Morto" digital. Quando todos os processos de uma sessão são despachados, eles vêm pra cá. Lá você pode pesquisar processos antigos, ver a "Lixeira" de processos apagados e ver o relatório de avisos que já saíram do letreiro.
        * **Aba 5 (Desempenho):** Onde os gráficos são gerados. O sistema cria um Radar em Tempo real para ver o que a equipe está fazendo agora, e também cria linhas de tendência mostrando se a equipe está demorando mais ou menos horas para fechar as sessões com o passar das semanas.
        """)

    with st.expander("📚 5. Glossário (O que significa cada termo?)"):
        st.markdown("""
        * **Processo Urgente:** Processos que furam a fila. Quando inseridos como urgentes, a linha deles fica **vermelha e em negrito** no Painel Ativo, chamando a atenção de todos.
        * **Expedição / Revisão:** O trabalho em disposição de fazer o documento e conferir. O sistema monitora a distribuição equilibrada e gerencia quem são os responsáveis de forma automatizada.
        * **Despachado:** O processo chegou ao fim da linha dentro do setor. Tarefa 100% concluída.
        """)

    # 👇 SEU NOVO ITEM MULTIDIMENSIONAL EXCLUSIVO AQUI 👇
    with st.expander("🧠 6. Como o S.A.D.E funciona (Dados & Desempenho)"):
        st.markdown("""
        Toda a inteligência e os gráficos do sistema são calculados de forma automática, baseados exclusivamente no ritmo de trabalho real do setor. O sistema funciona registrando os horários em que cada etapa é concluída no painel.
        
        ---

        #### 📡 Radar em Tempo Real (Painel Ativo)
        Mapeia a situação exata das pautas que estão acontecendo no dia:
        * **Volume de Trabalho:** Identifica quantos processos estão na mesa do setor no momento.
        * **Gargalos Operacionais:** Separa os processos por status para mostrar exatamente quantos ainda precisam ser iniciados, quantos aguardam revisão dos colegas e quantos estão finalizados, esperando apenas o envio da chefia.
        * **Gráfico de Barras:** Mostra a produtividade instantânea da equipe, somando quantas tarefas cada colaborador entregou ao longo do expediente atual.

        ---

        #### 🌎 Histórico e Médias de Tempo (Métricas Gerais)
        Assim que a chefia conclui e envia um processo, ele entra para a estatística global do setor. O sistema avalia três métricas essenciais:
        * **Tempo de Elaboração (Expedição):** Avalia quantas horas ou minutos a equipe leva para confeccionar a minuta inicial desde a hora em que o processo chegou.
        * **Tempo de Conferência (Revisão):** Mede a velocidade com que o revisor analisa e valida o documento criado pelo colega.
        * **Tempo de Ciclo Completo:** É a duração total da vida do documento no setor (da entrada ao envio final). Isso ajuda a comprovar a eficiência do setor para a Direção Geral.

        ---

        #### 📉 Evolução do Fechamento de Sessões (Gráfico de Tendência)
        Permite enxergar se o setor está se tornando mais rápido com o passar do tempo:
        * O sistema identifica o horário em que o **primeiro** processo de um lote foi colocado no sistema e o horário em que o **último** processo daquele mesmo lote foi finalizado.
        * Calculando o intervalo entre o primeiro e o último passo, o gráfico gera uma linha de tendência ao longo das semanas. Se a linha estiver descendo, comprova visualmente que a equipe está otimizando o tempo de resposta!
        """)
