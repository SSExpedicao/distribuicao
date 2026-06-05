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
        res = conn.client.table("equipe").select("nome").limit(1).execute()
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
        resposta = conn.client.table("equipe").select("nome").order("nome").execute()
        todos = [linha['nome'] for linha in resposta.data]
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
        if motivo not in ["Incluído errado", "Teste"]:
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
        # REGRA 1: MEMÓRIA DE CARGA GLOBAL
        # O algoritmo olha para a mesa global para ver quem trabalhou mais no total
        res = conn.client.table("processos").select("expedicao").execute().data
        contagem = {nome: 0 for nome in opcoes}
        for row in res:
            exp = row.get('expedicao')
            if exp in contagem:
                contagem[exp] += 1
        
        # Acha a menor carga de trabalho entre os presentes
        menor_carga = min(contagem.values())
        # Filtra todos os que estão empatados com a menor carga para não favorecer ordem alfabética
        empatados = [nome for nome, carga in contagem.items() if carga == menor_carga]
        
        import random
        return random.choice(empatados)
    except:
        import random
        return random.choice(opcoes)

def obter_revisor(expedidor, nome_sessao, opcoes):
    # Regra Básica: Ninguém pode revisar o próprio processo
    opcoes_validas = [opt for opt in opcoes if opt != expedidor]
    if not opcoes_validas: return expedidor # Contingência (Sessão só com a Jessyca, por exemplo)
    if len(opcoes_validas) == 1: return opcoes_validas[0] # Contingência (Só sobrou 1 pessoa)
    
    try:
        res_sessao = conn.client.table("processos").select("expedicao, revisao").eq("nome_sessao", nome_sessao).execute().data
        
        # 1. CONSISTÊNCIA DE FLUXO (Se eu já mandei pra alguém hoje, continuo mandando pra ele)
        for row in res_sessao:
            e = row.get('expedicao')
            r = row.get('revisao')
            if e == expedidor and r in opcoes_validas:
                return r
                
        # 2. REGRA ANTI-CASAL (Se chegou aqui, é o 1º processo do expedidor na sessão)
        # Vamos descobrir quem já está mandando processo para o nosso Expedidor
        mandam_para_mim = set()
        for row in res_sessao:
            e = row.get('expedicao')
            r = row.get('revisao')
            if r == expedidor and e:
                mandam_para_mim.add(e)
        
        # Tira os "casais" das opções válidas para forçar o cruzamento
        opcoes_anti_casal = [opt for opt in opcoes_validas if opt not in mandam_para_mim]
        
        # Se por acaso todo mundo estiver bloqueado (ex: só tem 2 pessoas trabalhando hoje),
        # o sistema derruba a regra anti-casal para não travar a pauta.
        candidatos = opcoes_anti_casal if opcoes_anti_casal else opcoes_validas
        
        if len(candidatos) == 1: return candidatos[0]
        
        # 3. RODÍZIO HISTÓRICO GLOBAL (Quem me ajudou menos na vida inteira?)
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
        linhas.append("4. CONTROLE DE DISPONIBILIDADE E AFASTAMENTOS")
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
        linhas.append("\n====================================================")
        linhas.append("        FIM DO RELATÓRIO - AUDITORIA AUTOMÁTICA     ")
        linhas.append("====================================================")
        return True, "\n".join(linhas)
    except Exception as e:
        return False, f"Erro interno ao compilar relatório: {e}"

def salvar_novo_processo(numero_processo, relator, tipo_sessao, nome_sessao, expedidores, revisores):
    numero_processo, relator = higienizar_dados(numero_processo, relator)
    if processo_existe(numero_processo): return False, "❌ Processo já existe no sistema."
    ausentes_hoje = obter_colaboradores_ausentes_hoje()
    if tipo_sessao == "Sessão Reservada":
        expedidores = [e for e in expedidores if e not in ["Jessyca", "Luana C"]]
        revisores = [r for r in revisores if r not in ["Jessyca", "Luana C"]]
    elif tipo_sessao == "Sessão Administrativa":
        if "Jessyca" not in ausentes_hoje:
            expedidores = ["Jessyca"]
            revisores = ["Jessyca"]
        else:
            contingencia = [colab for colab in ["André", "Elaine"] if colab not in ausentes_hoje]
            if contingencia:
                expedidores = contingencia
                revisores = contingencia
            else: return False, "❌ ERRO: Jessyca está afastada e a equipe de contingência também está indisponível."

    expedidores_ativos = [e for e in expedidores if e not in ausentes_hoje]
    revisores_ativos = [r for r in revisores if r not in ausentes_hoje]
    if not expedidores_ativos or not revisores_ativos: return False, "❌ ERRO: Todos os colaboradores selecionados para esta escala estão afastados."
    
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
    except Exception as e: return False, f"❌ Erro ao salvar: {e}"

def carregar_dados_sqlite(tipo_sessao=None):
    try:
        if tipo_sessao: dados = conn.client.table("processos").select("*").eq("tipo_sessao", tipo_sessao).execute().data
        else: dados = conn.client.table("processos").select("*").execute().data
        return pd.DataFrame(dados)
    except: return pd.DataFrame()

def restaurar_backup(df_backup):
    try:
        conn.client.table("processos").delete().neq("numero_processo", "vazio").execute()
        df_backup = df_backup.astype(object).where(pd.notna(df_backup), None)
        records = df_backup.to_dict(orient="records")
        for r in records:
            if 'id' in r: del r['id']
            if 'created_at' in r: del r['created_at']
        conn.client.table("processos").insert(records).execute()
        return True, "✅ Dados restaurados com sucesso!"
    except Exception as e: return False, f"❌ Erro ao tentar restaurar: {e}"

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
        conn.client.table("afastamentos").insert({"usuario": usuario, "data_inicio": data_inicio, "data_fim": data_fim, "tipo": tipo}).execute()
        return True, "✅ Afastamento registrado com sucesso!"
    except Exception as e: return False, f"❌ Erro ao salvar no banco: {e}"

def carregar_afastamentos():
    try: return pd.DataFrame(conn.client.table("afastamentos").select("*").execute().data)
    except: return pd.DataFrame()

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

# GESTÃO DE SESSÃO (CONTROLE DE SENHA DA CHEFIA)
if 'gestor_autenticado' not in st.session_state:
    st.session_state.gestor_autenticado = False

aba_inserir, aba_sessoes, aba_historico, aba_gestao, aba_ajuda = st.tabs([
    "📥 1. Inserir Novos",
    "🗂️ 2. Painel Ativo",
    "🗄️ 3. Histórico",
    "⚙️ 4. Gestão Administrativa (Restrito)",
    "❓ 5. Ajuda & Glossário"
])

# VARIÁVEIS ESSENCIAIS 
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
                mapa_banco = {'Expedição': 'expedicao', 'Revisão': 'revisao', 'Expedido': 'expedido_ok', 'Revisado': 'revisado_ok', 'Despachado': 'despachado', 'E-mail': 'enviado_email', 'Mensageria': 'enviado_mensageria', 'Recebido': 'recebido'}
                for i in range(len(edited_df)):
                    linha_nova = edited_df.iloc[i].to_dict()
                    linha_antiga = df_exibicao.iloc[i].to_dict()
                    if linha_nova != linha_antiga:
                        mudancas = {}
                        for col_tela, col_banco in mapa_banco.items():
                            if col_tela in linha_nova and linha_nova[col_tela] != linha_antiga.get(col_tela):
                                val = linha_nova[col_tela]
                                if col_tela in ['Expedido', 'Revisado', 'Despachado', 'E-mail', 'Mensageria', 'Recebido']: mudancas[col_banco] = 1 if val else 0
                                else: mudancas[col_banco] = val
                        if mudancas:
                            atualizar_processo(int(linha_nova['id']), mudancas)
                            alteracoes_feitas += 1
                if alteracoes_feitas > 0:
                    st.toast(f"✅ {alteracoes_feitas} processo(s) atualizado(s) no banco!")
                    time.sleep(1) 
                    st.rerun() 
                else: st.toast("⚠️ Nenhuma alteração detectada.")

    with sub_aba_ord:
        df_ord = carregar_dados_sqlite("Sessão Ordinária")
        if not df_ord.empty:
            for data in df_ord['nome_sessao'].unique():
                chave = f"Sessão Ordinária | {str(data).strip()}"
                if chave not in sessoes_finalizadas:
                    exibir_tabela_interativa(df_ord[df_ord['nome_sessao'] == data], "ord", data, "Sessão Ordinária")

    with sub_aba_ordv:
        df_ordv = carregar_dados_sqlite("Sessão Ordinária Virtual")
        if not df_ordv.empty:
            for data in df_ordv['nome_sessao'].unique():
                chave = f"Sessão Ordinária Virtual | {str(data).strip()}"
                if chave not in sessoes_finalizadas:
                    exibir_tabela_interativa(df_ordv[df_ordv['nome_sessao'] == data], "ordv", data, "Sessão Ordinária Virtual")

    with sub_aba_res:
        df_res = carregar_dados_sqlite("Sessão Reservada")
        if not df_res.empty:
            for data in df_res['nome_sessao'].unique():
                chave = f"Sessão Reservada | {str(data).strip()}"
                if chave not in sessoes_finalizadas:
                    exibir_tabela_interativa(df_res[df_res['nome_sessao'] == data], "res", data, "Sessão Reservada")

    with sub_aba_adm:
        df_adm = carregar_dados_sqlite("Sessão Administrativa")
        if not df_adm.empty:
            for data in df_adm['nome_sessao'].unique():
                chave = f"Sessão Administrativa | {str(data).strip()}"
                if chave not in sessoes_finalizadas:
                    exibir_tabela_interativa(df_adm[df_adm['nome_sessao'] == data], "adm", data, "Sessão Administrativa")

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

                st.subheader("🏷️ Identificar / Nomear Sessão")
                st.write("Vincule o número oficial para cada tipo de sessão individualmente.")
                col_sn1, col_sn2, col_sn3, col_sn4 = st.columns([2, 2, 1, 1.5])
                with col_sn1:
                    sessoes_disp = sorted(df_geral_status['nome_sessao'].unique(), reverse=True) if not df_geral_status.empty else []
                    sessao_alvo = st.selectbox("Data / Sessão Alvo:", sessoes_disp)
                with col_sn2: tipo_alvo = st.selectbox("Qual o Tipo de Sessão?", ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa"])
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
                        sucessos = 0
                        
                        if arquivo_hist is not None:
                            if arquivo_hist.name.endswith('.csv'):
                                try:
                                    # Tenta ler no padrão universal da internet (UTF-8)
                                    df_up = pd.read_csv(arquivo_hist, encoding='utf-8-sig')
                                except UnicodeDecodeError:
                                    # Se quebrar (salvo pelo Excel no Windows), volta a fita e lê como Latin-1
                                    arquivo_hist.seek(0)
                                    df_up = pd.read_csv(arquivo_hist, encoding='latin-1', sep=';')
                                    # Prevenção: Se a tabela ficar com 1 coluna só, é porque o separador era vírgula
                                    if len(df_up.columns) == 1:
                                        arquivo_hist.seek(0)
                                        df_up = pd.read_csv(arquivo_hist, encoding='latin-1', sep=',')
                            else:
                                # Se for XLSX, lê normal
                                df_up = pd.read_excel(arquivo_hist)
                            barra = st.progress(0)
                            
                            for index, row in df_up.iterrows():
                                p_val = str(row['Processo']).strip() if pd.notna(row.get('Processo')) else ""
                                r_val = str(row.get('Relator', '')).strip() if pd.notna(row.get('Relator')) else ""
                                p_limpo, r_limpo = higienizar_dados(p_val, r_val)
                                
                                exp_val = str(row.get('Expedidor', hist_exp)).strip() if pd.notna(row.get('Expedidor')) else hist_exp
                                rev_val = str(row.get('Revisor', hist_rev)).strip() if pd.notna(row.get('Revisor')) else hist_rev
                                
                                data_val = str(row.get('Data_Sessao', hist_sessao)).strip() if pd.notna(row.get('Data_Sessao')) else hist_sessao
                                tipo_val = str(row.get('Tipo_Sessao', hist_tipo)).strip() if pd.notna(row.get('Tipo_Sessao')) else hist_tipo
                                
                                if " " in data_val and "-" in data_val:
                                    try:
                                        data_val = datetime.strptime(data_val.split()[0], "%Y-%m-%d").strftime("%d/%m/%Y")
                                    except: pass

                                if p_limpo and not processo_existe(p_limpo):
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
                                
                        elif hist_proc:
                            p_limpo, r_limpo = higienizar_dados(hist_proc, hist_rel)
                            if not processo_existe(p_limpo):
                                try:
                                    conn.client.table("processos").insert({
                                        "numero_processo": p_limpo, "relator": r_limpo, "tipo_sessao": hist_tipo, 
                                        "nome_sessao": hist_sessao, "expedicao": hist_exp, "revisao": hist_rev, 
                                        "data_entrada": agora, "data_expedido": agora, "data_revisado": agora, "data_conclusao": agora,
                                        "expedido_ok": 1, "revisado_ok": 1, "despachado": 1, "urgente": 0,
                                        "enviado_email": 0, "enviado_mensageria": 0, "recebido": 0
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
                df_tempo_real['min_exp'] = (df_tempo_real['data_expedido_dt'] - df_tempo_real['data_entrada_dt']).dt.total_seconds() / 60
                df_tempo_real['min_rev'] = (df_tempo_real['data_revisado_dt'] - df_tempo_real['data_expedido_dt']).dt.total_seconds() / 60
                df_tempo_real['min_total'] = (df_tempo_real['data_conclusao_dt'] - df_tempo_real['data_entrada_dt']).dt.total_seconds() / 60

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
# ABA 5: AJUDA E GLOSSÁRIO
# ------------------------------------------
with aba_ajuda:
    st.header("📖 Manual do Usuário S.A.D.E.")
    st.markdown("""
    **Seja muito bem-vindo(a)!** Este manual foi escrito especialmente para ajudar você no dia a dia. Pense no S.A.D.E. (Sistema de Automação de Distribuição e Expedição) como um grande **balcão virtual**. Em vez de termos pilhas de pastas e papéis em cima das mesas físicas, o sistema organiza quem faz o quê no computador, garantindo que ninguém fique sobrecarregado e nenhum prazo seja perdido.
    
    Clique nos títulos abaixo (nas setinhas) para ler a explicação passo a passo de cada etapa do seu trabalho:
    """)
    
    with st.expander("📥 ABA 1: Como dar entrada em novos processos (Inserir)"):
        st.markdown("""
        Aqui é a **Recepção** do setor. É onde você avisa ao sistema que chegou trabalho novo. Você tem duas formas de fazer isso:
        
        **Opção 1: Digitar um por vez (Inserção Manual)**
        *(Ideal para quando chegam poucos processos no dia)*
        1. **Destino:** Escolha para qual "caixa" esse processo vai (Ex: Sessão Ordinária, Reservada, etc.). Se for um processo absurdamente urgente, escolha a opção "Urgente" na lista.
        2. **Equipe:** O sistema já marca automaticamente o nome de todo mundo que está trabalhando hoje. Se alguém não for participar dessa remessa específica, basta clicar no 'x' ao lado do nome da pessoa para tirá-la do sorteio.
        3. **Dados:** Digite o número do processo e o nome do Relator nas caixinhas em branco.
        4. **Concluir:** Clique no botão azul **"Verificar e Processar"**. O sistema vai fazer um sorteio justo e entregar esse processo imediatamente para a "Mesa de Trabalho" da equipe.
        
        ---
        
        **Opção 2: Importar Planilha (Para colocar vários de uma vez)**
        *(Ideal para aquele dia de pico, em que chegam 20, 30 processos juntos)*
        1. Clique no botão cinza **"Baixar Planilha Modelo"**. Isso vai salvar um arquivo no seu computador.
        2. Abra esse arquivo no seu Excel. Você vai ver duas palavras lá em cima: `Processo` e `Relator`.
        3. **Regra de Ouro:** Não mude essas palavras e não crie colunas novas. Apenas apague os números de exemplo e copie/cole a sua lista de processos ali embaixo.
        4. Salve a planilha e feche o Excel.
        5. Volte para o S.A.D.E., clique na área tracejada e escolha o arquivo que você acabou de salvar.
        6. Clique no botão azul **"Iniciar Importação"**. O sistema vai ler a planilha e distribuir tudo sozinho em segundos!
        """)

    with st.expander("🗂️ ABA 2: Como trabalhar nos processos (A Mesa de Trabalho)"):
        st.markdown("""
        Esta é a sua **Mesa de Trabalho Diária** (Painel Ativo). Todo o setor visualiza esta mesma tela simultaneamente. Cada linha que aparece na tabela é um processo que aguarda uma ação da equipe.
        
        **O que significam as caixinhas para marcar?**
        * 🔲 **Expedido:** Você deve marcar esta caixinha assim que terminar de redigir/montar o documento inicial.
        * 🔲 **Revisado:** O colega responsável por conferir o seu trabalho deve marcar esta caixinha quando terminar de ler e concordar que a minuta está correta.
        * 🔲 **Despachado:** Marque esta caixinha **APENAS** quando o processo estiver 100% pronto, assinado e finalizado no sistema oficial. 
        
        **⚠️ O BOTÃO MAIS IMPORTANTE DO SISTEMA:**
        Sempre que você marcar ou desmarcar qualquer uma dessas caixinhas, você **precisa** descer até o fim da tabela e clicar no botão azul **"💾 Salvar Alterações desta Sessão"**. 
        *Se você não clicar neste botão de salvar, o sistema não vai guardar o seu serviço e a caixinha vai desmarcar sozinha!*
        
        **O que acontece depois que eu marco "Despachado" e salvo?**
        O processo é considerado finalizado com sucesso. Para manter a tela limpa e organizada, ele **desaparece** da Mesa de Trabalho e é enviado magicamente para a gaveta do "Histórico".
        """)

    with st.expander("🗄️ ABA 3: Onde vão parar os processos prontos? (Histórico)"):
        st.markdown("""
        Esta tela funciona como o **Arquivo Morto** e a **Memória** do setor. O que você encontra aqui?
        
        * **✅ Arquivo: Concluídas:** Lembra dos processos que você despachou na Aba 2? Quando **todos** os processos de uma mesma sessão/data forem finalizados pela equipe, o lote inteiro vem para cá. Você pode usar os campos de busca para rastrear aquele processo antigo feito meses atrás.
        * **🗑️ Auditoria: Processos Excluídos:** Se a chefia precisar apagar um processo do sistema por algum erro grave, ele não evapora. Ele fica registrado nesta lixeira de segurança, mostrando o número e o motivo da exclusão para controle interno.
        """)

    with st.expander("⚙️ ABA 4: O que é a Gestão Administrativa?"):
        st.markdown("""
        Esta aba é exclusiva para o funcionamento interno do setor e atua como a **Sala da Chefia**. Por conter dados sensíveis, ela é protegida por senha (🔒). 
        
        **Apenas gestores autorizados entram aqui para:**
        * Apagar processos que foram cadastrados por engano.
        * Enviar os "Alertas Vermelhos" (Letreiro) para comunicar urgências à equipe.
        * Cadastrar quem entrou de Férias ou apresentou Atestado Médico (assim o sistema "sabe" que aquela pessoa não está trabalhando e para de enviar processos para o nome dela).
        * Visualizar gráficos automáticos de produtividade para apresentar à diretoria.
        """)

    with st.expander("📚 DICIONÁRIO DO SISTEMA (Termos Explicados)"):
        st.markdown("""
        Ouviu alguma palavra no sistema e ficou em dúvida? A resposta está aqui:
        
        * **Expedidor:** É a pessoa que "inicia" o trabalho. Quem lê o processo original, redige a minuta ou monta a primeira versão do documento.
        * **Revisor:** É a pessoa que age como um controle de qualidade. Ela recebe o que o Expedidor fez, confere se há erros de digitação ou leis aplicadas incorretamente, e só então libera o documento.
        * **Processo Urgente:** São os processos que "furam a fila". Quando a recepção cadastra um processo como urgente, a linha dele na sua tela fica com a letra mais grossa (negrito) e na cor **vermelha**. Ao ver o vermelho, pare o que está fazendo e dê prioridade máxima.
        * **Letreiro (Mural de Avisos):** É aquela faixa vermelha que fica correndo da direita para a esquerda no topo da sua tela, igual em noticiário de TV. É usado pela chefia para recados rápidos (Ex: *"Processo X aguardando anexo"*). Quando a equipe despachar o processo citado, o aviso some sozinho do letreiro!
        * **Sessão:** No nosso sistema, "Sessão" é a palavra que usamos para organizar os "Lotes" ou "Pastas" do dia. Agrupamos os processos em sessões para manter o trabalho organizado por datas ou reuniões.
        """)
