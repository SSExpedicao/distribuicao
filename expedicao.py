import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import time
from st_supabase_connection import SupabaseConnection

# ========================================================
# 1. BACKEND: CONFIGURAÇÃO E CONEXÃO COM O SUPABASE (NUVEM)
# ========================================================
# Conecta automaticamente usando as credenciais salvas nos Secrets do Streamlit
conn = st.connection("supabase", type=SupabaseConnection)

def higienizar_dados(processo, relator=""):
    # 1. Limpa o Processo (Tira espaços em branco e remove o -e do final)
    proc_limpo = str(processo).strip()
    if proc_limpo.lower().endswith("-e"):
        proc_limpo = proc_limpo[:-2]
        
    # 2. Limpa e padroniza o Relator
    rel_limpo = str(relator).strip().upper()
    
    # Dicionário de conversão automática (De -> Para)
    mapa_relatores = {
        "RR": "GCRR", "AM": "GCAM", "PT": "GCPT", 
        "AC": "GCAC", "IM": "GCIM", "MM": "GCMM", "VF": "GAVF"
    }
    
    if rel_limpo in mapa_relatores:
        rel_limpo = mapa_relatores[rel_limpo]
        
    return proc_limpo, rel_limpo

def init_db():
    try:
        # Verifica se a tabela de equipe está vazia para realizar a carga inicial
        res = conn.table("equipe").select("id", count="exact").execute()
        if res.count == 0:
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
            conn.table("equipe").insert(iniciais).execute()
    except Exception as e:
        st.sidebar.error(f"Erro ao inicializar equipe no Supabase: {e}")

def carregar_equipes():
    try:
        eq_exp = [row['nome'] for row in conn.table("equipe").select("nome").eq("expedicao", 1).execute().data]
        eq_rev = [row['nome'] for row in conn.table("equipe").select("nome").eq("revisao", 1).execute().data]
        todos = [row['nome'] for row in conn.table("equipe").select("nome").execute().data]
        return eq_exp, eq_rev, todos
    except:
        return [], [], []

def gerenciar_usuario(acao, nome_atual, novo_nome=None, expedicao=0, revisao=0):
    try:
        if acao == 'adicionar':
            conn.table("equipe").insert({"nome": nome_atual, "expedicao": expedicao, "revisao": revisao}).execute()
        elif acao == 'remover':
            conn.table("equipe").delete().eq("nome", nome_atual).execute()
        elif acao == 'substituir':
            conn.table("equipe").update({"nome": novo_nome, "expedicao": expedicao, "revisao": revisao}).eq("nome", nome_atual).execute()
        elif acao == 'editar':
            conn.table("equipe").update({"expedicao": expedicao, "revisao": revisao}).eq("nome", nome_atual).execute()
        return True, "✅ Operação realizada com sucesso!"
    except Exception as e:
        return False, f"❌ Erro no banco de dados: {e}"

def renomear_sessao(nome_antigo, novo_nome, tipo_sessao_alvo):
    try:
        conn.table("processos").update({"nome_sessao": novo_nome}).eq("nome_sessao", nome_antigo).eq("tipo_sessao", tipo_sessao_alvo).execute()
        return True, f"✅ Número atualizado para: {novo_nome}"
    except Exception as e:
        return False, f"❌ Erro ao renomear: {e}"

def remover_processo(numero_processo, nome_sessao, motivo):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        resultado = conn.table("processos").select("id, relator").eq("numero_processo", numero_processo).eq("nome_sessao", nome_sessao).execute().data
        if not resultado:
            return False, f"❌ Processo '{numero_processo}' não encontrado na sessão do dia {nome_sessao}."
            
        id_proc, relator = resultado[0]['id'], resultado[0]['relator']
        
        # Envia para a lixeira em nuvem
        conn.table("processos_excluidos").insert({"numero_processo": numero_processo, "relator": relator, "data_exclusao": agora, "motivo": motivo}).execute()
        # Remove do painel ativo
        conn.table("processos").delete().eq("id", id_proc).execute()
        return True, f"✅ Processo '{numero_processo}' removido e enviado para o histórico de exclusões!"
    except Exception as e:
        return False, f"❌ Erro ao remover processo: {e}"

def apagar_sessao_especifica(tipo_sessao, nome_sessao, motivo):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        processos_sessao = conn.table("processos").select("numero_processo, relator").eq("tipo_sessao", tipo_sessao).eq("nome_sessao", nome_sessao).execute().data
        for proc in processos_sessao:
            conn.table("processos_excluidos").insert({"numero_processo": proc['numero_processo'], "relator": proc['relator'], "data_exclusao": agora, "motivo": motivo}).execute()
        
        conn.table("processos").delete().eq("tipo_sessao", tipo_sessao).eq("nome_sessao", nome_sessao).execute()
    except Exception as e:
        pass

def carregar_excluidos():
    try:
        dados = conn.table("processos_excluidos").select("*").execute().data
        return pd.DataFrame(dados)
    except:
        return pd.DataFrame()
        
def processo_existe(numero_processo):
    try:
        res = conn.table("processos").select("id", count="exact").eq("numero_processo", numero_processo).execute()
        return res.count > 0
    except:
        return False

def marcar_urgente(numero_processo):
    numero_processo, _ = higienizar_dados(numero_processo)
    try:
        res = conn.table("processos").select("id").eq("numero_processo", numero_processo).execute().data
        if not res:
            return False, f"❌ Processo {numero_processo} não encontrado. Insira-o na sua sessão normal primeiro."
        conn.table("processos").update({"urgente": 1}).eq("numero_processo", numero_processo).execute()
        return True, f"🚨 Processo {numero_processo} destacado como URGENTE!"
    except Exception as e:
        return False, f"❌ Erro ao marcar urgência: {e}"

def atualizar_processo(id_processo, mudancas):
    if not mudancas: return
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    payload = {}
    
    for col_banco, val in mudancas.items():
        payload[col_banco] = val
        if col_banco == 'expedido_ok':
            payload["data_expedido"] = agora if val == 1 else None
        elif col_banco == 'revisado_ok':
            payload["data_revisado"] = agora if val == 1 else None
        elif col_banco == 'despachado':
            payload["data_conclusao"] = agora if val == 1 else None
            
    try:
        conn.table("processos").update(payload).eq("id", id_processo).execute()
    except:
        pass

def obter_expedidor(elegiveis, nome_sessao):
    if not elegiveis: return "Nenhum escalado"
    contagem = {p: 0 for p in elegiveis}
    try:
        linhas = conn.table("processos").select("expedicao").not_.is_("expedicao", "null").eq("nome_sessao", nome_sessao).execute().data
        for row in linhas:
            if row.get('expedicao') in contagem:
                contagem[row['expedicao']] += 1
    except:
        pass
    return min(contagem, key=contagem.get)

def obter_revisor(expedidor, nome_sessao, revisores_ativos):
    if not revisores_ativos: return "Nenhum escalado"
    try:
        linhas_sessao = conn.table("processos").select("expedicao, revisao").eq("nome_sessao", nome_sessao).execute().data
        df_sessao = pd.DataFrame(linhas_sessao) if linhas_sessao else pd.DataFrame(columns=['expedicao', 'revisao'])
        
        linhas_total = conn.table("processos").select("revisao").execute().data
        df_total = pd.DataFrame(linhas_total) if linhas_total else pd.DataFrame(columns=['revisao'])
        
        # Regra de conflito: Revisor não pode ser o próprio expedidor
        candidatos = [r for r in revisores_ativos if r != expedidor]
        if not candidatos: return "Sem Revisor (Conflito)"

        melhor_cand = None
        menor_score = (float('inf'), float('inf'), float('inf'), float('inf'), float('inf'))

        # Lógica Complexa de Score para Distribuição Justa Equilibrada
        for cand in candidatos:
            parcerias_sessao = len(df_sessao[df_sessao['revisao'] == cand]['expedicao'].unique()) if 'revisao' in df_sessao.columns else 0
            is_reciprocal = 1 if not df_sessao.empty and len(df_sessao[(df_sessao['expedicao'] == cand) & (df_sessao['revisao'] == expedidor)]) > 0 else 0
            carga_sessao = len(df_sessao[df_sessao['revisao'] == cand]) if 'revisao' in df_sessao.columns else 0
            vezes_parceiro = 0 
            carga_total = len(df_total[df_total['revisao'] == cand]) if 'revisao' in df_total.columns else 0

            score = (parcerias_sessao, is_reciprocal, carga_sessao, vezes_parceiro, carga_total)
            if score < menor_score:
                menor_score = score
                melhor_cand = cand
                
        return melhor_cand
    except:
        candidatos = [r for r in revisores_ativos if r != expedidor]
        return candidatos[0] if candidatos else "Nenhum escalado"

def salvar_novo_processo(numero_processo, relator, tipo_sessao, nome_sessao, expedidores, revisores):
    numero_processo, relator = higienizar_dados(numero_processo, relator)
    if processo_existe(numero_processo): 
        return False, "❌ Processo já existe no sistema."
    if not expedidores or not revisores: 
        return False, "❌ ERRO: Selecione ao menos um Expedidor e um Revisor."

    responsavel_expedicao = obter_expedidor(expedidores, nome_sessao)
    responsavel_revisao = obter_revisor(responsavel_expedicao, nome_sessao, revisores)
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    try:
        conn.table("processos").insert({
            "numero_processo": numero_processo, "relator": relator, "tipo_sessao": tipo_sessao, 
            "nome_sessao": nome_sessao, "expedicao": responsavel_expedicao, "revisao": responsavel_revisao, 
            "data_entrada": data_atual, "expedido_ok": 0, "revisado_ok": 0, "despachado": 0, "urgente": 0
        }).execute()
        return True, f"✅ Distribuído! Expedição: **{responsavel_expedicao}** | Revisão: **{responsavel_revisao}**"
    except Exception as e:
        return False, f"❌ Erro ao salvar processo: {e}"

def carregar_dados(tipo_sessao=None):
    try:
        if tipo_sessao:
            dados = conn.table("processos").select("*").eq("tipo_sessao", tipo_sessao).execute().data
        else:
            dados = conn.table("processos").select("*").execute().data
        return pd.DataFrame(dados)
    except:
        return pd.DataFrame()

def restaurar_backup(df_backup):
    try:
        conn.table("processos").delete().neq("numero_processo", "vazio").execute()
        records = df_backup.to_dict(orient="records")
        for r in records:
            if 'id' in r: del r['id']
            if 'created_at' in r: del r['created_at']
        conn.table("processos").insert(records).execute()
        return True, "✅ Dados restaurados com sucesso!"
    except Exception as e:
        return False, f"❌ Erro ao restaurar: {e}"

def adicionar_aviso(usuario, numero_processo, mensagem):
    try:
        res = conn.table("processos").select("despachado").eq("numero_processo", numero_processo).execute().data
        if not res:
            return False, f"❌ Processo '{numero_processo}' não encontrado no sistema."
        if res[0]['despachado'] == 1:
            return False, f"❌ O processo '{numero_processo}' já foi concluído/despachado."
        
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        conn.table("avisos").insert({"usuario": usuario, "numero_processo": numero_processo, "mensagem": mensagem, "data_criacao": agora, "ativo": 1}).execute()
        return True, "✅ Aviso publicado no letreiro!"
    except Exception as e:
        return False, f"❌ Erro: {e}"

def obter_avisos_pendentes():
    hoje = datetime.now().strftime("%d/%m/%Y")
    try:
        df_av = pd.DataFrame(conn.table("avisos").select("*").eq("ativo", 1).execute().data)
        df_proc = pd.DataFrame(conn.table("processos").select("numero_processo", "nome_sessao", "despachado").execute().data)
        if df_av.empty: return pd.DataFrame()
        if df_proc.empty: df_proc = pd.DataFrame(columns=['numero_processo', 'nome_sessao', 'despachado'])
        
        df_avisos = pd.merge(df_av, df_proc, on='numero_processo', how='left')
        df_avisos = df_avisos[(df_avisos['numero_processo'] == '') | (df_avisos['despachado'] == 0)]
        
        linhas_validas = []
        for index, row in df_avisos.iterrows():
            data_aviso = row['data_criacao'].split()[0]
            if row['usuario'] == 'Todos':
                if data_aviso == hoje: 
                    linhas_validas.append(row)
            else:
                linhas_validas.append(row)
        return pd.DataFrame(linhas_validas) if linhas_validas else pd.DataFrame(columns=df_avisos.columns)
    except:
        return pd.DataFrame()

def desativar_aviso(id_aviso):
    try:
        conn.table("avisos").update({"ativo": 0}).eq("id", int(id_aviso)).execute()
    except:
        pass

def carregar_historico_avisos():
    hoje = datetime.now().strftime("%d/%m/%Y")
    try:
        df_av = pd.DataFrame(conn.table("avisos").select("*").execute().data)
        df_proc = pd.DataFrame(conn.table("processos").select("numero_processo", "despachado").execute().data)
        if df_av.empty: 
            return pd.DataFrame(columns=['numero_processo', 'usuario', 'mensagem', 'data_criacao', 'ativo', 'despachado', 'proc_existe', 'status'])
        
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
    except:
        return pd.DataFrame(columns=['numero_processo', 'usuario', 'mensagem', 'data_criacao', 'ativo', 'despachado', 'proc_existe', 'status'])

def gerar_relatorio_gerencial(mes, ano):
    df_proc = carregar_dados()
    df_av = carregar_historico_avisos()
    _, _, equipe_total = carregar_equipes()
    equipe_operacional = [n for n in equipe_total if n.lower() != 'jessyca']
    
    if df_proc.empty: return False, "Banco de dados de processos vazio."
    
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
            
    if len(sessoes_periodo) > 15:
        relatorio_sessoes.append(f"   - ... e mais {len(sessoes_periodo) - 15} sessões geridas com sucesso ao longo do período.")
            
    df_av['data_dt'] = pd.to_datetime(df_av['data_criacao'], format="%d/%m/%Y %H:%M:%S", errors='coerce')
    if mes == 0:
        df_av_periodo = df_av[(df_av['data_dt'].dt.year == ano)]
    else:
        df_av_periodo = df_av[(df_av['data_dt'].dt.month == mes) & (df_av['data_dt'].dt.year == ano)]
        
    avisos_count = {}
    for colab in equipe_operacional:
        avisos_count[colab] = len(df_av_periodo[df_av_periodo['usuario'] == colab])
        
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
    if ficou_de_fora:
        texto += f"   - Colaboradores sem atuações neste período: {', '.join(ficou_de_fora)}\n\n"
    else:
        texto += "   - Todos os colaboradores operacionais participaram da pauta no período.\n\n"
    texto += f"====================================================\n"
    texto += f"Documento gerado e auditado automaticamente pelo S.A.D.E.\n"
    texto += f"Para aprovação da Chefia: Jessyca\n"
    texto += f"===================================================="
    return True, texto

# Executa cargas e sincroniza dados globais na inicialização do script Python
init_db()
EQUIPE_EXPEDICAO, EQUIPE_REVISAO, TODOS_NOMES = carregar_equipes()

# ==========================================
# 2. FRONTEND: RENDERIZAÇÃO DA INTERFACE UI
# ==========================================
st.set_page_config(page_title="Sistema de Sessões", layout="wide")
st.title("⚖️ S.A.D.E. - Sistema de Automação de Distribuição e Expedição")

# 📢 LETREIRO DE AVISOS (MURAL DINÂMICO)
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

# Criação das Abas Principais
aba_inserir, aba_sessoes, aba_controle, aba_historico, aba_dados, aba_ajuda = st.tabs([
    "📥 1. Inserir Novos", "🗂️ 2. Painel Ativo", "📊 3. Controle O.K.", "🗄️ 4. Histórico", "📈 5. Dados & Desempenho", "❓ 6. Ajuda & Glossário"
])

nome_sessao_atual = datetime.now().strftime("%d/%m/%Y")
df_geral_status = carregar_dados()
sessoes_finalizadas = []

if not df_geral_status.empty and 'despachado' in df_geral_status.columns:
    sessoes_stats = df_geral_status.groupby('nome_sessao')['despachado'].agg(['count', 'sum']).reset_index()
    sessoes_finalizadas = sessoes_stats[sessoes_stats['count'] == sessoes_stats['sum']]['nome_sessao'].tolist()

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
            df_upload = pd.read_csv(arquivo_upload) if arquivo_upload.name.endswith('.csv') else pd.read_excel(arquivo_upload)
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

def color_urgentes(row): 
    return ['color: #ff4b4b; font-weight: bold'] * len(row) if 'urgente_flag' in row and row['urgente_flag'] == 1 else [''] * len(row)

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
            edited_df = st.data_editor(styled_df, column_config=cfg_colunas, hide_index=True, use_container_width=True, key=f"ed_{key_prefix}_{data_sessao}")
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
                                if col_tela in ['Expedido', 'Revisado', 'Despachado', 'E-mail', 'Mensageria', 'Recebido']:
                                    mudancas[col_banco] = 1 if val else 0
                                else:
                                    mudancas[col_banco] = val
                        if mudancas:
                            atualizar_processo(int(linha_nova['id']), mudancas)
                            alteracoes_feitas += 1
                if alteracoes_feitas > 0:
                    st.toast(f"✅ {alteracoes_feitas} processo(s) atualizado(s) no banco de dados!")
                    time.sleep(0.5)
                    st.rerun()

    with sub_aba_ord:
        df_ord = carregar_dados("Sessão Ordinária")
        if not df_ord.empty:
            for data in df_ord[~df_ord['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_ord[df_ord['nome_sessao'] == data], "ord", data, "Sessão Ordinária")
    with sub_aba_ordv:
        df_ordv = carregar_dados("Sessão Ordinária Virtual")
        if not df_ordv.empty:
            for data in df_ordv[~df_ordv['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_ordv[df_ordv['nome_sessao'] == data], "ordv", data, "Sessão Ordinária Virtual")
    with sub_aba_res:
        df_res = carregar_dados("Sessão Reservada")
        if not df_res.empty:
            for data in df_res[~df_res['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_res[df_res['nome_sessao'] == data], "res", data, "Sessão Reservada")
    with sub_aba_adm:
        df_adm = carregar_dados("Sessão Administrativa")
        if not df_adm.empty:
            for data in df_adm[~df_adm['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_adm[df_adm['nome_sessao'] == data], "adm", data, "Sessão Administrativa")

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
        with col_rm3: motivo_remocao = st.selectbox("Motivo:", ["Fora de pauta", "Incluído errado", "Teste", "Outros"], key="motivo_proc")
        with col_rm4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("❌ Remover", type="primary", use_container_width=True):
                if proc_para_remover and data_sessao_remover:
                    ok, m = remover_processo(proc_para_remover, data_sessao_remover, motivo_remocao)
                    if ok:
                        st.success(m)
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error(m)

    st.markdown("---")
    with st.expander("⚙️ Área Administrativa Avançada (Equipe e Banco de Dados)"):
        st.subheader("📢 Mural de Avisos (Letreiro)")
        col_av1, col_av2, col_av3 = st.columns([1, 1, 2])
        with col_av1: aviso_usuario = st.selectbox("Para quem?", TODOS_NOMES, key="aviso_usr")
        with col_av2: aviso_processo = st.text_input("Nº do Processo Ativo", key="aviso_proc")
        with col_av3: aviso_msg = st.text_input("Mensagem", placeholder="Ex: Tratar com urgência...", key="aviso_msg")
        
        if st.button("📢 Publicar no Letreiro", type="primary", use_container_width=True):
            if aviso_processo and aviso_msg:
                ok, msg = adicionar_aviso(aviso_usuario, aviso_processo, aviso_msg)
                if ok:
                    st.success(msg)
                    time.sleep(0.5)
                    st.rerun()
                else: st.error(msg)
            else: st.warning("⚠️ Preencha o número do processo e a mensagem.")

        st.markdown("---")
        st.subheader("🏷️ Identificar / Nomear Sessão")
        col_sn1, col_sn2, col_sn3, col_sn4 = st.columns([2, 2, 1, 1.5])
        with col_sn1: sessao_alvo = st.selectbox("Data / Sessão Alvo:", datas_disp if not df_geral_status.empty else [])
        with col_sn2: tipo_alvo = st.selectbox("Qual o Tipo de Sessão?", ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa"])
        with col_sn3: num_oficial = st.text_input("Número:", placeholder="Ex: 125")
        with col_sn4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🏷️ Confirmar", type="primary", use_container_width=True):
                if num_oficial and sessao_alvo:
                    novo_nome = f"Sessão {num_oficial} - {sessao_alvo.split(' - ')[-1].strip()}" if " - " in sessao_alvo else f"Sessão {num_oficial} - {sessao_alvo}"
                    ok, msg = renomear_sessao(sessao_alvo, novo_nome, tipo_alvo)
                    if ok:
                        st.success(msg)
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error(msg)

        st.markdown("---")
        st.subheader("📄 Relatório Gerencial Mensal/Anual")
        col_m1, col_m2, col_m3 = st.columns([1, 1, 2])
        meses_dict = {0: "Anual (Ano Inteiro)", 1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
        
        with col_m1: mes_selecionado = st.selectbox("Período:", list(meses_dict.keys()), index=datetime.now().month, format_func=lambda x: meses_dict[x])
        with col_m2: ano_selecionado = st.selectbox("Ano:", range(2024, datetime.now().year + 1), index=len(range(2024, datetime.now().year + 1)) - 1)
        with col_m3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📊 Compilar Relatório", type="primary", use_container_width=True):
                ok, texto_relatorio = gerar_relatorio_gerencial(mes_selecionado, ano_selecionado)
                if ok:
                    st.success("Relatório gerado com sucesso!")
                    st.code(texto_relatorio, language="markdown")
                    st.download_button(label="📥 Baixar Relatório (TXT)", data=texto_relatorio.encode('utf-8'), file_name=f"Relatorio_{mes_selecionado}_{ano_selecionado}.txt", mime="text/plain")
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
                if ok: st.success(m); time.sleep(0.5); st.rerun()

        elif acao_equipe == "Editar Permissões":
            col1, col2, col3 = st.columns(3)
            colab_editar = col1.selectbox("Selecione o colaborador", TODOS_NOMES)
            faz_exp = col2.checkbox("Participa da Expedição", value=True, key="edit_exp")
            faz_rev = col3.checkbox("Participa da Revisão", value=True, key="edit_rev")
            if st.button("✏️ Atualizar Permissões", type="primary", key="edit_user"):
                ok, m = gerenciar_usuario('editar', colab_editar, expedicao=int(faz_exp), revisao=int(faz_rev))
                if ok: st.success(m); time.sleep(0.5); st.rerun()

        elif acao_equipe == "Substituir Nome":
            col1, col2, col3 = st.columns(3)
            colab_atual = col1.selectbox("Quem vai sair?", TODOS_NOMES)
            novo_nome = col2.text_input("Qual o nome de quem vai entrar?")
            faz_exp, faz_rev = col3.checkbox("Entra na Expedição?", value=True), col3.checkbox("Entra na Revisão?", value=True)
            if st.button("🔄 Substituir", type="primary", key="subst_user"):
                ok, m = gerenciar_usuario('substituir', colab_atual, novo_nome=novo_nome, expedicao=int(faz_exp), revisao=int(faz_rev))
                if ok: st.success(m); time.sleep(0.5); st.rerun()

        elif acao_equipe == "Remover Colaborador":
            colab_remover = st.selectbox("Selecione quem será removido", TODOS_NOMES)
            if st.button("🗑️ Remover Definitivamente", type="primary", key="rem_user"):
                ok, m = gerenciar_usuario('remover', colab_remover)
                if ok: st.success(m); time.sleep(0.5); st.rerun()

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
                    df_up = pd.read_csv(arquivo_backup)
                    ok, msg = restaurar_backup(df_up)
                    if ok: st.success(msg); time.sleep(0.5); st.rerun()
                    else: st.error(msg)

        st.markdown("---")
        st.subheader("🧹 Limpeza Seletiva do Sistema (Apagar Sessão)")
        col_tipo, col_data, col_motivo_sess, col_btn = st.columns([2, 2, 2, 1])
        with col_tipo: tipo_apagar = st.selectbox("Apagar de qual tipo?", ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa"])
        with col_data:
            datas_disp_apagar = df_geral_status[df_geral_status['tipo_sessao'] == tipo_apagar]['nome_sessao'].unique() if not df_geral_status.empty else []
            data_apagar = st.selectbox("Qual data?", sorted(datas_disp_apagar, reverse=True)) if len(datas_disp_apagar) > 0 else st.selectbox("Qual data?", ["Sem dados"])
        with col_motivo_sess: motivo_sessao = st.selectbox("Motivo da Exclusão:", ["Sessão Cancelada", "Fora de pauta", "Incluído errado"], key="motivo_sess")
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Apagar Sessão", type="primary", use_container_width=True) and data_apagar != "Sem dados":
                apagar_sessao_especifica(tipo_apagar, data_apagar, motivo_sessao)
                st.success(f"Sessão de {data_apagar} apagada com sucesso!")
                time.sleep(0.5); st.rerun()

# ------------------------------------------
# ABA 4: HISTÓRICO, EXCLUSÕES E AVISOS
# ------------------------------------------
with aba_historico:
    s_concluidas, s_lixeira, s_avisos = st.tabs(["✅ Arquivo: Concluídas", "🗑️ Auditoria: Processos Excluídos", "📢 Auditoria: Histórico de Avisos"])
    
    with s_concluidas:
        st.subheader("Sessões 100% Concluídas")
        if sessoes_finalizadas:
            df_historico = df_geral_status[df_geral_status['nome_sessao'].isin(sessoes_finalizadas)].copy()
            df_hist_disp = df_historico[['numero_processo', 'urgente', 'relator', 'expedicao', 'revisao', 'data_conclusao', 'tipo_sessao', 'nome_sessao']].rename(
                columns={'numero_processo': 'Processo', 'urgente': 'urgente_flag', 'relator': 'Conselheiro', 'expedicao': 'Expedidor', 'revisao': 'Revisor', 'data_conclusao': 'Data/Hora Conclusão', 'tipo_sessao': 'Tipo de Sessão', 'nome_sessao': 'Data da Sessão'}
            )
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            with col_f1: filtro_sessao = st.multiselect("📅 Data da Sessão", options=sorted(df_hist_disp['Data da Sessão'].unique(), reverse=True))
            with col_f2: filtro_usuario = st.multiselect("👥 Colaborador", options=TODOS_NOMES)
            with col_f3: filtro_processo = st.text_input("📄 Nº do Processo")
            with col_f4: filtro_relator = st.text_input("⚖️ Relator")

            df_fil = df_hist_disp.copy()
            if filtro_sessao: df_fil = df_fil[df_fil['Data da Sessão'].isin(filtro_sessao)]
            if filtro_usuario: df_fil = df_fil[df_fil['Expedidor'].isin(filtro_usuario) | df_fil['Revisor'].isin(filtro_usuario)]
            if filtro_processo: df_fil = df_fil[df_fil['Processo'].astype(str).str.contains(filtro_processo, case=False, na=False)]
            if filtro_relator: df_fil = df_fil[df_fil['Conselheiro'].astype(str).str.contains(filtro_relator, case=False, na=False)]

            st.dataframe(df_fil.iloc[::-1].style.apply(color_urgentes, axis=1), hide_index=True, use_container_width=True, column_config={"urgente_flag": None})
        else: st.info("📭 Nenhuma sessão foi 100% concluída ainda.")

    with s_lixeira:
        st.subheader("Registro de Exclusões (Auditoria de Pauta)")
        df_ex = carregar_excluidos()
        if not df_ex.empty:
            st.dataframe(df_ex.rename(columns={'numero_processo': 'Processo', 'relator': 'Relator', 'data_exclusao': 'Data/Hora Exclusão', 'motivo': 'Motivo'}), hide_index=True, use_container_width=True)
        else: st.success("✨ A lixeira está vazia.")

    with s_avisos:
        st.subheader("Histórico Completo de Avisos Publicados")
        df_hi_av = carregar_historico_avisos()
        if not df_hi_av.empty:
            st.dataframe(df_hi_av.rename(columns={'numero_processo': 'Processo', 'usuario': 'Destinatário', 'mensagem': 'Comunicado', 'data_criacao': 'Data/Hora Publicação', 'status': 'Situação'}), hide_index=True, use_container_width=True)

# ------------------------------------------
# ABA 5: DADOS & DESEMPENHO (ANALYTICS)
# ------------------------------------------
with aba_dados:
    st.subheader("📈 Analytics e Radar Operacional")
    if not df_geral_status.empty and 'data_expedido' in df_geral_status.columns:
        df_dados = df_geral_status.copy()
        for c in ['data_entrada', 'data_expedido', 'data_revisado', 'data_conclusao']:
            df_dados[c + '_dt'] = pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M:%S", errors='coerce')
        
        df_dados['minutos_total'] = (df_dados['data_conclusao_dt'] - df_dados['data_entrada_dt']).dt.total_seconds() / 60
        st.metric("Total de Processos Cadastrados de Forma Segura", len(df_dados))
        
        fig = px.histogram(df_dados, x="expedicao", color="tipo_sessao", barmode="group", title="Volume de Distribuição por Colaborador")
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("📊 Insira e conclua processos para gerar métricas de desempenho.")

# ------------------------------------------
# ABA 6: AJUDA E GLOSSÁRIO
# ------------------------------------------
with aba_ajuda:
    st.header("📖 Manual do Usuário e Ajuda Detalhada - S.A.D.E.")
    with st.expander("📥 1. Inserir Novos e Importar Planilhas"):
        st.markdown("Instruções de como preencher e baixar a planilha modelo do Excel, respeitando as colunas obrigatórias.")
    with st.expander("🗂️ 2. Painel Ativo de Trabalho"):
        st.markdown("Como atualizar os status de Expedido, Revisado e Despachado, lembrando sempre de salvar as alterações.")
    with st.expander("📊 3. Área Administrativa Avançada"):
        st.markdown("Gerenciamento de letreiros, lixeira de auditoria e geração automatizada de relatórios em formato TXT para a chefia.")
