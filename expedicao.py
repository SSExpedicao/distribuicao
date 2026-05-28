import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import time
from st_supabase_connection import SupabaseConnection

# ==========================================
# 1. CONEXÃO COM O BANCO DE DADOS EM NUVEM
# ==========================================
# Puxa automaticamente as credenciais dos Secrets do Streamlit
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
        # Verifica se a equipe está vazia para povoar a primeira vez
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
        st.sidebar.error(f"Erro ao inicializar equipe padrão: {e}")

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
            return False, f"❌ Processo '{numero_processo}' não encontrado na sessão."
        
        id_proc, relator = resultado[0]['id'], resultado[0]['relator']
        conn.table("processos_excluidos").insert({"numero_processo": numero_processo, "relator": relator, "data_exclusao": agora, "motivo": motivo}).execute()
        conn.table("processos").delete().eq("id", id_proc).execute()
        return True, f"✅ Processo '{numero_processo}' removido e enviado para a lixeira!"
    except Exception as e:
        return False, f"❌ Erro ao remover: {e}"

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
        return pd.DataFrame(conn.table("processos_excluidos").select("*").execute().data)
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
            return False, f"❌ Processo {numero_processo} não encontrado ativo."
        conn.table("processos").update({"urgente": 1}).eq("numero_processo", numero_processo).execute()
        return True, f"🚨 Processo {numero_processo} destacado como URGENTE!"
    except Exception as e:
        return False, f"❌ Erro: {e}"

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
        
        candidatos = [r for r in revisores_ativos if r != expedidor]
        if not candidatos: return "Sem Revisor (Conflito)"

        melhor_cand = None
        menor_score = (float('inf'), float('inf'), float('inf'), float('inf'), float('inf'))

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
        return False, f"❌ Erro ao salvar: {e}"

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

init_db()
EQUIPE_EXPEDICAO, EQUIPE_REVISAO, TODOS_NOMES = carregar_equipes()

def adicionar_aviso(usuario, numero_processo, mensagem):
    try:
        res = conn.table("processos").select("despachado").eq("numero_processo", numero_processo).execute().data
        if not res: return False, f"❌ Processo '{numero_processo}' não encontrado."
        if res[0]['despachado'] == 1: return False, f"❌ Processo já concluído."
        
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
                if data_aviso == hoje: linhas_validas.append(row)
            else:
                linhas_validas.append(row)
        return pd.DataFrame(linhas_validas) if linhas_validas else pd.DataFrame(columns=df_avisos.columns)
    except:
        return pd.DataFrame()

def desativar_aviso(id_aviso):
    try: conn.table("avisos").update({"ativo": 0}).eq("id", int(id_aviso)).execute()
    except: pass

def carregar_historico_avisos():
    hoje = datetime.now().strftime("%d/%m/%Y")
    try:
        df_av = pd.DataFrame(conn.table("avisos").select("*").execute().data)
        df_proc = pd.DataFrame(conn.table("processos").select("numero_processo", "despachado").execute().data)
        if df_av.empty: return pd.DataFrame(columns=['numero_processo', 'usuario', 'mensagem', 'data_criacao', 'ativo', 'despachado', 'proc_existe', 'status'])
        
        df_proc['proc_existe'] = df_proc['numero_processo'] if not df_proc.empty else None
        df = pd.merge(df_av, df_proc, on='numero_processo', how='left')
        
        status_list = []
        for _, row in df.iterrows():
            data_aviso = row['data_criacao'].split()[0]
            if row['ativo'] == 0: status_list.append('❌ Desativado Manualmente')
            elif row['usuario'] == 'Todos' and data_aviso != hoje: status_list.append('⏳ Expirado Auto (23:59h)')
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
                     
    if df_periodo.empty: return False, f"Nenhum processo despachado em {titulo_periodo}."
        
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
    
    texto = f"====================================================\n RELATÓRIO GERENCIAL DO SETOR - {titulo_periodo}\n====================================================\n\n"
    texto += f"1. VOLUME DE PRODUÇÃO\n   - Total de processos concluídos: {total_despachado}\n\n"
    texto += f"2. OTIMIZAÇÃO DE TEMPO\n   - Tempo médio de ciclo: {tempo_str}\n\n"
    texto += f"3. DESTAQUE OPERACIONAL\n   - Mais produtivo: {mais_eficiente} ({ops_eficiente} atuações)\n\n"
    texto += f"====================================================\nDocumento auditado pelo S.A.D.E. | Chefia: Jessyca\n===================================================="
    return True, texto

# ==========================================
# 2. RENDERIZAÇÃO DA INTERFACE FRONTEND
# ==========================================
st.set_page_config(page_title="Sistema de Sessões", layout="wide")
st.title("⚖️ S.A.D.E. - Sistema de Automação de Distribuição e Expedição")

# Letreiro Animado
df_avisos = obter_avisos_pendentes()
if not df_avisos.empty:
    textos_aviso = []
    for _, row in df_avisos.iterrows():
        textos_aviso.append(f"🚨 <b>{row['usuario']}</b>: Processo <b>{row['numero_processo']}</b> ({row['nome_sessao']}) ➔ {row['mensagem']}")
    texto_marquee = " &nbsp;&nbsp;&nbsp;&nbsp; | &nbsp;&nbsp;&nbsp;&nbsp; ".join(textos_aviso)
    st.markdown(f'<marquee behavior="scroll" direction="left" scrollamount="8" style="background-color: #ff4b4b; color: white; padding: 10px; font-size: 18px; border-radius: 5px; margin-bottom: 20px; font-weight: 500;">{texto_marquee}</marquee>', unsafe_allow_html=True)

aba_inserir, aba_sessoes, aba_controle, aba_historico, aba_dados, aba_ajuda = st.tabs([
    "📥 1. Inserir Novos", "🗂️ 2. Painel Ativo", "📊 3. Controle O.K.", "🗄️ 4. Histórico", "📈 5. Dados & Desempenho", "❓ 6. Ajuda & Glossário"
])

nome_sessao_atual = datetime.now().strftime("%d/%m/%Y")
df_geral_status = carregar_dados()
sessoes_finalizadas = []

if not df_geral_status.empty and 'despachado' in df_geral_status.columns:
    sessoes_stats = df_geral_status.groupby('nome_sessao')['despachado'].agg(['count', 'sum']).reset_index()
    sessoes_finalizadas = sessoes_stats[sessoes_stats['count'] == sessoes_stats['sum']]['nome_sessao'].tolist()

with aba_inserir:
    st.header("Passo 1: Configurar a Sessão Atual")
    with st.container(border=True):
        tipo_sessao = st.selectbox("Destino (Tipo de Sessão)", ["Sessão Ordinária", "Sessão Ordinária Virtual", "Sessão Reservada", "Sessão Administrativa", "Urgente"])
        if tipo_sessao == "Urgente":
            st.info("🚨 **Modo Urgente:** Destaca processos ativos.")
            expedidores_ativos, revisores_ativos = [], []
        else:
            col3, col4 = st.columns(2)
            with col3: expedidores_ativos = st.multiselect("👥 Quem fará a Expedição?", EQUIPE_EXPEDICAO, default=EQUIPE_EXPEDICAO)
            with col4: revisores_ativos = st.multiselect("👥 Quem fará a Revisão?", EQUIPE_REVISAO, default=EQUIPE_REVISAO)

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
                    if not expedidores_ativos or not revisores_ativos: st.error("❌ Escale a equipe.")
                    elif novo_processo and novo_relator:
                        ok, msg = salvar_novo_processo(novo_processo, novo_relator, tipo_sessao, nome_sessao_atual, expedidores_ativos, revisores_ativos)
                        st.success(msg) if ok else st.error(msg)

    elif modo_insercao == "Importar Planilha (Em lote)":
        df_modelo = pd.DataFrame({"Processo": ["12345/2026"], "Relator": ["Conselheiro A"]})
        st.download_button(label="📥 Baixar Planilha Modelo", data=df_modelo.to_csv(index=False).encode('utf-8'), file_name="modelo.csv", mime="text/csv")
        arquivo_upload = st.file_uploader("Suba sua planilha (.csv ou .xlsx)", type=["csv", "xlsx"])
        if arquivo_upload is not None:
            df_upload = pd.read_csv(arquivo_upload) if arquivo_upload.name.endswith('.csv') else pd.read_excel(arquivo_upload)
            st.dataframe(df_upload.head(3))
            if st.button("🚀 Iniciar Importação", type="primary"):
                barra = st.progress(0)
                sucessos = 0
                for index, row in df_upload.iterrows():
                    p_val = str(row['Processo']).strip() if pd.notna(row.get('Processo')) else ""
                    if tipo_sessao == "Urgente": ok, _ = marcar_urgente(p_val)
                    else:
                        r_val = str(row.get('Relator', '')).strip() if pd.notna(row.get('Relator')) else ""
                        ok, _ = salvar_novo_processo(p_val, r_val, tipo_sessao, nome_sessao_atual, expedidores_ativos, revisores_ativos)
                    if ok: sucessos += 1
                    barra.progress((index + 1) / len(df_upload))
                st.success(f"🎉 Concluído! {sucessos} processos inseridos.")

def color_urgentes(row):
    return ['color: #ff4b4b; font-weight: bold'] * len(row) if 'urgente_flag' in row and row['urgente_flag'] == 1 else [''] * len(row)

with aba_sessoes:
    sub_aba_ord, sub_aba_ordv, sub_aba_res, sub_aba_adm = st.tabs(["🏛️ Ordinária", "💻 Ordinária Virtual", "🔒 Reservada", "📁 Administrativa"])
    
    def exibir_tabela_interativa(df_filtrado, key_prefix, data_sessao, tipo_sessao_tb):
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
        
        st.markdown(f"##### 📅 {data_sessao}")
        with st.form(key=f"form_{key_prefix}_{data_sessao}"):
            edited_df = st.data_editor(styled_df, column_config=cfg_colunas, hide_index=True, use_container_width=True, key=f"editor_{key_prefix}_{data_sessao}")
            if st.form_submit_button("💾 Salvar Alterações"):
                alteracoes = 0
                mapa_banco = {'Expedição': 'expedicao', 'Revisão': 'revisao', 'Expedido': 'expedido_ok', 'Revisado': 'revisado_ok', 'Despachado': 'despachado', 'E-mail': 'enviado_email', 'Mensageria': 'enviado_mensageria', 'Recebido': 'recebido'}
                for i in range(len(edited_df)):
                    l_nova = edited_df.iloc[i].to_dict()
                    l_antiga = df_exibicao.iloc[i].to_dict()
                    if l_nova != l_antiga:
                        mudancas = {}
                        for c_tela, c_banco in mapa_banco.items():
                            if c_tela in l_nova and l_nova[c_tela] != l_antiga.get(c_tela):
                                mudancas[c_banco] = 1 if type(l_nova[c_tela]) == bool and l_nova[c_tela] else (0 if type(l_nova[c_tela]) == bool else l_nova[c_tela])
                        if mudancas:
                            atualizar_processo(int(l_nova['id']), mudancas)
                            alteracoes += 1
                if alteracoes > 0:
                    st.success("Banco de dados atualizado!")
                    time.sleep(0.5)
                    st.rerun()

    with sub_aba_ord:
        df_ord = carregar_dados("Sessão Ordinária")
        if not df_ord.empty:
            for d in df_ord[~df_ord['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_ord[df_ord['nome_sessao'] == d], "ord", d, "Sessão Ordinária")
    with sub_aba_ordv:
        df_ordv = carregar_dados("Sessão Ordinária Virtual")
        if not df_ordv.empty:
            for d in df_ordv[~df_ordv['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_ordv[df_ordv['nome_sessao'] == d], "ordv", d, "Sessão Ordinária Virtual")
    with sub_aba_res:
        df_res = carregar_dados("Sessão Reservada")
        if not df_res.empty:
            for d in df_res[~df_res['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_res[df_res['nome_sessao'] == d], "res", d, "Sessão Reservada")
    with sub_aba_adm:
        df_adm = carregar_dados("Sessão Administrativa")
        if not df_adm.empty:
            for d in df_adm[~df_adm['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_adm[df_adm['nome_sessao'] == d], "adm", d, "Sessão Administrativa")

with aba_controle:
    if not df_geral_status.empty:
        d_sel = st.selectbox("📅 Data da Sessão (OKs):", sorted(df_geral_status['nome_sessao'].unique(), reverse=True))
        df_f = df_geral_status[df_geral_status['nome_sessao'] == d_sel]
        c_e, c_r = st.columns(2)
        c_e.dataframe(df_f['expedicao'].value_counts().reset_index(), hide_index=True)
        c_r.dataframe(df_f['revisao'].value_counts().reset_index(), hide_index=True)

    st.markdown("---")
    with st.container(border=True):
        st.subheader("🗑️ Remover Processo Específico")
        c_rm1, c_rm2, c_rm3, c_rm4 = st.columns([2, 2, 2, 1])
        with c_rm1: proc_rm = st.text_input("Número Exato:")
        with c_rm2: d_disp = sorted(df_geral_status['nome_sessao'].unique(), reverse=True) if not df_geral_status.empty else []
        with c_rm2: sessao_rm = st.selectbox("Sessão:", d_disp, key="sess_rm")
        with c_rm3: mot_rm = st.selectbox("Motivo:", ["Fora de pauta", "Incluído errado"], key="mot_proc_rm")
        with c_rm4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("❌ Remover", type="primary"):
                if proc_rm and sessao_rm:
                    ok, m = remover_processo(proc_rm, sessao_rm, mot_rm)
                    st.success(m) if ok else st.error(m)
                    time.sleep(0.5); st.rerun()

    with st.expander("⚙️ Área Administrativa Avançada"):
        st.subheader("📢 Mural de Avisos")
        ca1, ca2, ca3 = st.columns([1, 1, 2])
        with ca1: av_usr = st.selectbox("Para quem?", TODOS_NOMES)
        with ca2: av_prc = st.text_input("Nº Processo Ativo")
        with ca3: av_msg = st.text_input("Mensagem")
        if st.button("📢 Publicar Alerta"):
            if av_prc and av_msg:
                ok, m = adicionar_aviso(av_usr, av_prc, av_msg)
                st.success(m) if ok else st.error(m)
                time.sleep(0.5); st.rerun()

        st.subheader("📄 Relatório Gerencial")
        cm1, cm2, cm3 = st.columns([1, 1, 2])
        with cm1: m_sel = st.selectbox("Mês:", list(range(0, 13)))
        with cm2: a_sel = st.selectbox("Ano:", [2024, 2025, 2026])
        with cm3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📊 Compilar Relatório"):
                ok, t = gerar_relatorio_gerencial(m_sel, a_sel)
                if ok: st.code(t, language="markdown")
                else: st.warning(t)

with aba_historico:
    s_concluidas, s_lixeira, s_avisos = st.tabs(["✅ Concluidas", "🗑️ Lixeira", "📢 Histórico Avisos"])
    with s_concluidas:
        if sessoes_finalizadas:
            st.dataframe(df_geral_status[df_geral_status['nome_sessao'].isin(sessoes_finalizadas)], hide_index=True)
    with s_lixeira:
        st.dataframe(carregar_excluidos(), hide_index=True)
    with s_avisos:
        st.dataframe(carregar_historico_avisos(), hide_index=True)

with aba_dados:
    st.subheader("📈 Gráficos de Produção")
    if not df_geral_status.empty and 'expedido_ok' in df_geral_status.columns:
        st.metric("Total de Processos Cadastrados", len(df_geral_status))
        fig = px.histogram(df_geral_status, x="expedicao", color="tipo_sessao", barmode="group", title="Distribuição por Expedidor")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados suficientes para gráficos.")

with aba_ajuda:
    st.write("Consulte o manual interno clicando nos expanders das abas acima se necessário.")
