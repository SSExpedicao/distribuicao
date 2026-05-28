import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime
import io
import time

# ==========================================
# 1. BACKEND: BANCO DE DADOS E LÓGICA
# ==========================================
DB_PATH = 'gestao_processos.db'

def higienizar_dados(processo, relator=""):
    # 1. Limpa o Processo (Tira espaços em branco e remove o -e do final)
    proc_limpo = str(processo).strip()
    
    # Se terminar com -e ou -E, o código "arranca" os dois últimos caracteres
    if proc_limpo.lower().endswith("-e"):
        proc_limpo = proc_limpo[:-2]
        
    # 2. Limpa e padroniza o Relator
    rel_limpo = str(relator).strip().upper() # Deixa tudo maiúsculo e sem espaços sobrando
    
    # Dicionário de conversão automática (De -> Para)
    mapa_relatores = {
        "RR": "GCRR",
        "AM": "GCAM",
        "PT": "GCPT",
        "AC": "GCAC",
        "IM": "GCIM",
        "MM": "GCMM",
        "VF": "GAVF"
    }
    
    # Se a sigla digitada estiver no nosso mapa, ele troca pela oficial completa
    if rel_limpo in mapa_relatores:
        rel_limpo = mapa_relatores[rel_limpo]
        
    return proc_limpo, rel_limpo
    
def init_db():
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()

        # 1. Tabela Processos
        c.execute('''CREATE TABLE IF NOT EXISTS processos (
                                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                                          numero_processo TEXT UNIQUE,
                                          relator TEXT,
                                          tipo_sessao TEXT,
                                          expedicao TEXT,
                                          revisao TEXT,
                                          data_entrada TEXT
                     )''')

        colunas = ['nome_sessao', 'expedido_ok', 'revisado_ok', 'despachado',
                   'data_conclusao', 'data_expedido', 'data_revisado', 'urgente',
                   'enviado_email', 'enviado_mensageria', 'recebido']

        for col in colunas:
            tipo = "INTEGER DEFAULT 0" if "ok" in col or col in ["despachado", "urgente", "enviado_email", "enviado_mensageria", "recebido"] else "TEXT"
            try: c.execute(f'''ALTER TABLE processos ADD COLUMN {col} {tipo}''')
            except sqlite3.OperationalError: pass

        # 2. Tabela Equipe
        c.execute('''CREATE TABLE IF NOT EXISTS equipe (
                                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                                       nome TEXT UNIQUE,
                                       expedicao INTEGER DEFAULT 0,
                                       revisao INTEGER DEFAULT 0
                     )''')

        # 3. Tabela Processos Excluídos (Auditoria)
        c.execute('''CREATE TABLE IF NOT EXISTS processos_excluidos (
                                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                                          numero_processo TEXT,
                                          relator TEXT,
                                          data_exclusao TEXT,
                                          motivo TEXT
                     )''')

        # 4. Tabela Avisos
        c.execute('''CREATE TABLE IF NOT EXISTS avisos (
                                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                                          usuario TEXT,
                                          numero_processo TEXT,
                                          mensagem TEXT,
                                          data_criacao TEXT
                     )''')
                     
        # Garante que a coluna 'ativo' exista na tabela de avisos
        try: c.execute("ALTER TABLE avisos ADD COLUMN ativo INTEGER DEFAULT 1")
        except sqlite3.OperationalError: pass

        # 5. Popula a equipe inicial se estiver vazia
        c.execute("SELECT COUNT(*) FROM equipe")
        if c.fetchone()[0] == 0:
            iniciais = [
                ("André", 1, 1), ("Elaine", 1, 1), ("Kátia", 1, 1),
                ("Luana C", 1, 1), ("Jessyca", 1, 1), ("Lu Fiorote", 1, 1),
                ("Mariana", 1, 1), ("Maurício", 1, 1)
            ]
            c.executemany("INSERT INTO equipe (nome, expedicao, revisao) VALUES (?, ?, ?)", iniciais)

def carregar_equipes():
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()
        c.execute("SELECT nome FROM equipe WHERE expedicao = 1")
        eq_exp = [row[0] for row in c.fetchall()]
        c.execute("SELECT nome FROM equipe WHERE revisao = 1")
        eq_rev = [row[0] for row in c.fetchall()]
        c.execute("SELECT nome FROM equipe")
        todos = [row[0] for row in c.fetchall()]
    return eq_exp, eq_rev, todos

def gerenciar_usuario(acao, nome_atual, novo_nome=None, expedicao=0, revisao=0):
    try:
        with sqlite3.connect(DB_PATH) as conn_sq:
            c = conn_sq.cursor()
            if acao == 'adicionar': c.execute("INSERT INTO equipe (nome, expedicao, revisao) VALUES (?, ?, ?)", (nome_atual, expedicao, revisao))
            elif acao == 'remover': c.execute("DELETE FROM equipe WHERE nome = ?", (nome_atual,))
            elif acao == 'substituir': c.execute("UPDATE equipe SET nome = ?, expedicao = ?, revisao = ? WHERE nome = ?", (novo_nome, expedicao, revisao, nome_atual))
            elif acao == 'editar': c.execute("UPDATE equipe SET expedicao = ?, revisao = ? WHERE nome = ?", (expedicao, revisao, nome_atual))
        return True, "✅ Operação realizada com sucesso!"
    except sqlite3.IntegrityError: return False, "❌ Erro: Este usuário já existe."
    except Exception as e: return False, f"❌ Erro no banco de dados: {e}"

def renomear_sessao(nome_antigo, novo_nome, tipo_sessao_alvo):
    try:
        with sqlite3.connect(DB_PATH) as conn_sq:
            # A query agora exige o TIPO EXATO além do NOME/DATA antigo
            conn_sq.execute(
                "UPDATE processos SET nome_sessao = ? WHERE nome_sessao = ? AND tipo_sessao = ?", 
                (novo_nome, nome_antigo, tipo_sessao_alvo)
            )
        return True, f"✅ Número atualizado para: {novo_nome}"
    except Exception as e:
        return False, f"❌ Erro ao renomear: {e}"

def remover_processo(numero_processo, nome_sessao, motivo):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()
        # 1. Pega os dados antes de apagar
        c.execute("SELECT id, relator FROM processos WHERE numero_processo = ? AND nome_sessao = ?", (numero_processo, nome_sessao))
        resultado = c.fetchone()
        
        if not resultado:
            return False, f"❌ Processo '{numero_processo}' não encontrado na sessão do dia {nome_sessao}."
            
        id_proc, relator = resultado
        
        # 2. Salva na Lixeira
        c.execute("INSERT INTO processos_excluidos (numero_processo, relator, data_exclusao, motivo) VALUES (?, ?, ?, ?)",
                  (numero_processo, relator, agora, motivo))
                  
        # 3. Apaga do sistema ativo
        c.execute("DELETE FROM processos WHERE id = ?", (id_proc,))
    return True, f"✅ Processo '{numero_processo}' removido e enviado para o histórico de exclusões!"

def apagar_sessao_especifica(tipo_sessao, nome_sessao, motivo):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()
        
        # 1. Pega todos os processos dessa sessão
        c.execute("SELECT numero_processo, relator FROM processos WHERE tipo_sessao = ? AND nome_sessao = ?", (tipo_sessao, nome_sessao))
        processos_sessao = c.fetchall()

        # 2. Salva todos na Lixeira
        for proc in processos_sessao:
            c.execute("INSERT INTO processos_excluidos (numero_processo, relator, data_exclusao, motivo) VALUES (?, ?, ?, ?)",
                      (proc[0], proc[1], agora, motivo))

        # 3. Apaga a sessão do sistema ativo
        conn_sq.execute('DELETE FROM processos WHERE tipo_sessao = ? AND nome_sessao = ?', (tipo_sessao, nome_sessao))

def carregar_excluidos():
    with sqlite3.connect(DB_PATH) as conn_sq:
        df = pd.read_sql_query("SELECT * FROM processos_excluidos", conn_sq)
    return df
    
def processo_existe(numero_processo):
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()
        c.execute("SELECT COUNT(*) FROM processos WHERE numero_processo = ?", (numero_processo,))
        existe = c.fetchone()[0] > 0
    return existe

def marcar_urgente(numero_processo):
    # 🪄 Limpa o número do processo (ignora o relator com o '_')
    numero_processo, _ = higienizar_dados(numero_processo)
    
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()
        c.execute("SELECT id FROM processos WHERE numero_processo = ?", (numero_processo,))
        if not c.fetchone():
            return False, f"❌ Processo {numero_processo} não encontrado. Insira-o na sua sessão normal primeiro."
        conn_sq.execute('UPDATE processos SET urgente = 1 WHERE numero_processo = ?', (numero_processo,))
    return True, f"🚨 Processo {numero_processo} destacado como URGENTE!"

def atualizar_processo(id_processo, mudancas):
    if not mudancas: return
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    with sqlite3.connect(DB_PATH) as conn_sq:
        colunas_set = []
        valores = []
        
        # Constrói o comando do banco de dados SOB DEMANDA, só com o que mudou
        for col_banco, val in mudancas.items():
            colunas_set.append(f"{col_banco} = ?")
            valores.append(val)
            
            # Se marcou uma caixinha de status, carimba a data automaticamente
            if col_banco == 'expedido_ok':
                colunas_set.append("data_expedido = ?")
                valores.append(agora if val == 1 else None)
            elif col_banco == 'revisado_ok':
                colunas_set.append("data_revisado = ?")
                valores.append(agora if val == 1 else None)
            elif col_banco == 'despachado':
                colunas_set.append("data_conclusao = ?")
                valores.append(agora if val == 1 else None)

        query = f"UPDATE processos SET {', '.join(colunas_set)} WHERE id = ?"
        valores.append(id_processo)
        conn_sq.execute(query, tuple(valores))

def obter_expedidor(elegiveis, nome_sessao):
    if not elegiveis: return "Nenhum escalado"
    contagem = {p: 0 for p in elegiveis}
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()
        c.execute("SELECT expedicao, COUNT(*) FROM processos WHERE expedicao IS NOT NULL AND nome_sessao = ? GROUP BY expedicao", (nome_sessao,))
        for row in c.fetchall():
            if row[0] in contagem: contagem[row[0]] = row[1]
    return min(contagem, key=contagem.get)

def obter_revisor(expedidor, nome_sessao, revisores_ativos):
    if not revisores_ativos: return "Nenhum escalado"
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()
        c.execute("SELECT revisao FROM processos WHERE expedicao = ? AND nome_sessao = ? LIMIT 1", (expedidor, nome_sessao))
        resultado = c.fetchone()
        if resultado and resultado[0] in revisores_ativos:
            return resultado[0]

        candidatos = [r for r in revisores_ativos if r != expedidor]
        if not candidatos: return "Sem Revisor (Conflito)"

        melhor_cand = None
        menor_score = (float('inf'), float('inf'), float('inf'), float('inf'), float('inf'))

        for cand in candidatos:
            c.execute("SELECT COUNT(DISTINCT expedicao) FROM processos WHERE revisao = ? AND nome_sessao = ?", (cand, nome_sessao))
            parcerias_sessao = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM processos WHERE expedicao = ? AND revisao = ? AND nome_sessao = ?", (cand, expedidor, nome_sessao))
            is_reciprocal = 1 if c.fetchone()[0] > 0 else 0
            c.execute("SELECT COUNT(*) FROM processos WHERE revisao = ? AND nome_sessao = ?", (cand, nome_sessao))
            carga_sessao = c.fetchone()[0]
            c.execute("SELECT COUNT(DISTINCT nome_sessao) FROM processos WHERE expedicao = ? AND revisao = ? AND nome_sessao != ?", (expedidor, cand, nome_sessao))
            vezes_parceiro = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM processos WHERE revisao = ?", (cand,))
            carga_total = c.fetchone()[0]

            score = (parcerias_sessao, is_reciprocal, carga_sessao, vezes_parceiro, carga_total)
            if score < menor_score:
                menor_score = score
                melhor_cand = cand

    return melhor_cand

def salvar_novo_processo(numero_processo, relator, tipo_sessao, nome_sessao, expedidores, revisores):
    numero_processo, relator = higienizar_dados(numero_processo, relator)
    
    if processo_existe(numero_processo): 
        return False, "❌ Processo já existe no sistema."
  
    if not expedidores or not revisores: 
        return False, "❌ ERRO: Selecione ao menos um Expedidor e um Revisor."

    responsavel_expedicao = obter_expedidor(expedidores, nome_sessao)
    responsavel_revisao = obter_revisor(responsavel_expedicao, nome_sessao, revisores)
    
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn_sq:
        conn_sq.execute('''INSERT INTO processos (numero_processo, relator, tipo_sessao, nome_sessao, expedicao, revisao, data_entrada, 
                                               expedido_ok, revisado_ok, despachado, urgente, enviado_email, enviado_mensageria, recebido) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0)''', 
                     (numero_processo, relator, tipo_sessao, nome_sessao, responsavel_expedicao, responsavel_revisao, data_atual))
                     
    return True, f"✅ Distribuído! Expedição: **{responsavel_expedicao}** | Revisão: **{responsavel_revisao}**"

def carregar_dados_sqlite(tipo_sessao=None):
    with sqlite3.connect(DB_PATH) as conn_sq:
        if tipo_sessao: df = pd.read_sql_query(f"SELECT * FROM processos WHERE tipo_sessao = '{tipo_sessao}'", conn_sq)
        else: df = pd.read_sql_query("SELECT * FROM processos", conn_sq)
    return df

def restaurar_backup(df_backup):
    try:
        with sqlite3.connect(DB_PATH) as conn_sq:
            conn_sq.execute('DELETE FROM processos')
            df_backup.to_sql('processos', conn_sq, if_exists='append', index=False)
        return True, "✅ Dados restaurados com sucesso! O sistema voltou ao estado do backup."
    except Exception as e:
        return False, f"❌ Erro ao tentar restaurar os dados: {e}"

init_db()
EQUIPE_EXPEDICAO, EQUIPE_REVISAO, TODOS_NOMES = carregar_equipes()

def adicionar_aviso(usuario, numero_processo, mensagem):
    with sqlite3.connect(DB_PATH) as conn_sq:
        c = conn_sq.cursor()
        c.execute("SELECT despachado FROM processos WHERE numero_processo = ?", (numero_processo,))
        res = c.fetchone()
        if not res:
            return False, f"❌ Processo '{numero_processo}' não encontrado no sistema."
        if res[0] == 1:
            return False, f"❌ O processo '{numero_processo}' já foi concluído/despachado."
        
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        c.execute("INSERT INTO avisos (usuario, numero_processo, mensagem, data_criacao) VALUES (?, ?, ?, ?)",
                  (usuario, numero_processo, mensagem, agora))
    return True, "✅ Aviso publicado no letreiro!"

def obter_avisos_pendentes():
    hoje = datetime.now().strftime("%d/%m/%Y")
    with sqlite3.connect(DB_PATH) as conn_sq:
        query = '''
            SELECT a.id, a.usuario, a.numero_processo, p.nome_sessao, a.mensagem, a.data_criacao 
            FROM avisos a
            LEFT JOIN processos p ON a.numero_processo = p.numero_processo
            WHERE a.ativo = 1 AND (a.numero_processo = '' OR p.despachado = 0)
        '''
        df_avisos = pd.read_sql_query(query, conn_sq)
    
    if df_avisos.empty:
        return df_avisos
        
    linhas_validas = []
    for index, row in df_avisos.iterrows():
        data_aviso = row['data_criacao'].split()[0]
        
        if row['usuario'] == 'Todos':
            if data_aviso == hoje:
                linhas_validas.append(row)
        else:
            linhas_validas.append(row)
            
    return pd.DataFrame(linhas_validas) if linhas_validas else pd.DataFrame(columns=df_avisos.columns)

def desativar_aviso(id_aviso):
    with sqlite3.connect(DB_PATH) as conn_sq:
        conn_sq.execute("UPDATE avisos SET ativo = 0 WHERE id = ?", (id_aviso,))

def carregar_historico_avisos():
    hoje = datetime.now().strftime("%d/%m/%Y")
    with sqlite3.connect(DB_PATH) as conn_sq:
        query = '''
            SELECT a.numero_processo, a.usuario, a.mensagem, a.data_criacao, a.ativo,
                   p.despachado, p.numero_processo AS proc_existe
            FROM avisos a
            LEFT JOIN processos p ON a.numero_processo = p.numero_processo
        '''
        df = pd.read_sql_query(query, conn_sq)
        
    if df.empty:
        return pd.DataFrame(columns=['numero_processo', 'usuario', 'mensagem', 'data_criacao', 'ativo', 'despachado', 'proc_existe', 'status'])
        
    status_list = []
    for _, row in df.iterrows():
        data_aviso = row['data_criacao'].split()[0]
        
        if row['ativo'] == 0:
            status_list.append('❌ Desativado Manualmente')
        elif row['usuario'] == 'Todos' and data_aviso != hoje:
            status_list.append('⏳ Expirado Automaticamente (23:59h)')
        elif row['numero_processo'] != '' and row['despachado'] == 1:
            status_list.append('✅ Concluído (Despachado)')
        elif row['numero_processo'] != '' and pd.isna(row['proc_existe']):
            status_list.append('❌ Processo Removido')
        else:
            status_list.append('⏳ Ativo no Letreiro')
            
    df['status'] = status_list
    return df
    
def gerar_relatorio_gerencial(mes, ano):
    df_proc = carregar_dados_sqlite()
    df_av = carregar_historico_avisos()
    _, _, equipe_total = carregar_equipes()
    
    equipe_operacional = [n for n in equipe_total if n.lower() != 'jessyca']
    
    df_proc['data_conclusao_dt'] = pd.to_datetime(df_proc['data_conclusao'], format="%d/%m/%Y %H:%M:%S", errors='coerce')
    df_proc['data_entrada_dt'] = pd.to_datetime(df_proc['data_entrada'], format="%d/%m/%Y %H:%M:%S", errors='coerce')
    
    if mes == 0:
        df_periodo = df_proc[(df_proc['data_conclusao_dt'].dt.year == ano) & (df_proc['despachado'] == 1)].copy()
        titulo_periodo = f"ANO COMPLETO DE {ano}"
    else:
        df_periodo = df_proc[(df_proc['data_conclusao_dt'].dt.month == mes) & (df_proc['data_conclusao_dt'].dt.year == ano) & (df_proc['despachado'] == 1)].copy()
        titulo_periodo = f"{mes:02d}/{ano}"
                     
    if df_periodo.empty:
        return False, f"Nenhum processo foi despachado no período selecionado ({titulo_periodo})."
        
    total_despachado = len(df_periodo)
    
    df_periodo['tempo_min'] = (df_periodo['data_conclusao_dt'] - df_periodo['data_entrada_dt']).dt.total_seconds() / 60
    tempo_medio = df_periodo['tempo_min'].mean()
    tempo_str = f"{int(tempo_medio)} minutos" if pd.notna(tempo_medio) else "N/A"
    
    desempenho = {}
    for colab in equipe_operacional:
        exp_count = len(df_periodo[df_periodo['expedicao'] == colab])
        rev_count = len(df_periodo[df_periodo['revisao'] == colab])
        if (exp_count + rev_count) > 0:
            desempenho[colab] = exp_count + rev_count
            
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
    
# ==========================================
# 2. FRONTEND: INTERFACE DO USUÁRIO
# ==========================================
st.set_page_config(page_title="Sistema de Sessões", layout="wide")
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

aba_inserir, aba_sessoes, aba_controle, aba_historico, aba_dados, aba_ajuda = st.tabs([
    "📥 1. Inserir Novos",
    "🗂️ 2. Painel Ativo",
    "📊 3. Controle O.K.",
    "🗄️ 4. Histórico",
    "📈 5. Dados & Desempenho",
    "❓ 6. Ajuda & Glossário"
])

# VARIÁVEIS ESSENCIAIS 
nome_sessao_atual = datetime.now().strftime("%d/%m/%Y")
df_geral_status = carregar_dados_sqlite()
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
            df_upload = pd.read_csv(arquivo_upload) if arquivo_upload.name.endswith('.csv') else pd.read_excel(arquivo_upload)
            
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
            for data in df_ord[~df_ord['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_ord[df_ord['nome_sessao'] == data], "ord", data, "Sessão Ordinária")

    with sub_aba_ordv:
        df_ordv = carregar_dados_sqlite("Sessão Ordinária Virtual")
        if not df_ordv.empty:
            for data in df_ordv[~df_ordv['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_ordv[df_ordv['nome_sessao'] == data], "ordv", data, "Sessão Ordinária Virtual")

    with sub_aba_res:
        df_res = carregar_dados_sqlite("Sessão Reservada")
        if not df_res.empty:
            for data in df_res[~df_res['nome_sessao'].isin(sessoes_finalizadas)]['nome_sessao'].unique(): exibir_tabela_interativa(df_res[df_res['nome_sessao'] == data], "res", data, "Sessão Reservada")

    with sub_aba_adm:
        df_adm = carregar_dados_sqlite("Sessão Administrativa")
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
            aviso_usuario = st.selectbox("Para quem?", TODOS_NOMES, key="aviso_usr")
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
                        df_upload = pd.read_csv(arquivo_backup)
                        ok, msg = restaurar_backup(df_upload)
                        if ok:
                            st.success(msg)
                            time.sleep(1.5)
                            st.rerun()
                        else: st.error(msg)
                    except Exception as e: st.error(f"Erro ao ler o arquivo: {e}")

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
    sub_aba_concluidas, sub_aba_lixeira, sub_aba_hist_avisos = st.tabs([
        "✅ Arquivo: Concluídas", 
        "🗑️ Auditoria: Processos Excluídos",
        "📢 Auditoria: Histórico de Avisos"
    ])

    # --- sub-aba 1: CONCLUÍDAS ---
    with sub_aba_concluidas:
        st.subheader("Sessões 100% Concluídas")
        if sessoes_finalizadas:
            df_historico = df_geral_status[df_geral_status['nome_sessao'].isin(sessoes_finalizadas)].copy()
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
# ==========================================
# ABA 5: DADOS & DESEMPENHO (ANALYTICS)
# ==========================================
with aba_dados:
    st.subheader("📈 Analytics e Radar Operacional")
    df_dados = carregar_dados_sqlite()
    
    if df_dados.empty or 'data_expedido' not in df_dados.columns: 
        st.info("📊 Comece a inserir e despachar processos no Painel Ativo para gerar estatísticas.")
    else:
        # 1. Tratamento das Datas
        def parse_datas(df_in):
            for c in ['data_entrada', 'data_expedido', 'data_revisado', 'data_conclusao']:
                df_in[c + '_dt'] = pd.to_datetime(df_in[c], format="%d/%m/%Y %H:%M:%S", errors='coerce').fillna(pd.to_datetime(df_in[c], format="%d/%m/%Y %H:%M", errors='coerce'))
            return df_in
            
        df_dados = parse_datas(df_dados)
        
        df_dados['minutos_expedicao'] = (df_dados['data_expedido_dt'] - df_dados['data_entrada_dt']).dt.total_seconds() / 60
        df_dados['minutos_revisao'] = (df_dados['data_revisado_dt'] - df_dados['data_expedido_dt']).dt.total_seconds() / 60
        df_dados['minutos_total'] = (df_dados['data_conclusao_dt'] - df_dados['data_entrada_dt']).dt.total_seconds() / 60

        def format_tempo(minutos):
            if pd.isna(minutos) or minutos < 0: return "N/A"
            return f"{int(minutos)} min" if int(minutos) < 60 else f"{int(minutos) // 60}h {int(minutos) % 60}m"

        # ========================================================
        # 📡 CAMADA 1: RADAR EM TEMPO REAL (PAINEL ATIVO)
        # ========================================================
        st.markdown("### 📡 Radar em Tempo Real (Sessões em Andamento)")
        
        # Filtra a base para pegar SÓ o que ainda está no Painel Ativo
        df_ativos = df_dados[~df_dados['nome_sessao'].isin(sessoes_finalizadas)].copy()
        
        if not df_ativos.empty:
            # Conta o status exato de cada processo agora
            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            col_r1.metric("📋 Total na Pauta", len(df_ativos))
            col_r2.metric("⏳ Faltam Expedir", len(df_ativos[df_ativos['expedido_ok'] == 0]))
            col_r3.metric("🔍 Faltam Revisar", len(df_ativos[(df_ativos['expedido_ok'] == 1) & (df_ativos['revisado_ok'] == 0)]))
            col_r4.metric("✍️ Prontos p/ Despachar", len(df_ativos[(df_ativos['revisado_ok'] == 1) & (df_ativos['despachado'] == 0)]))
            
            st.markdown("#### 🏃‍♂️ Quem está produzindo agora? (Tarefas feitas na pauta ativa)")
            
            # Puxa quem já fez tarefas nas sessões que estão abertas
            exp_ativos = df_ativos[df_ativos['expedido_ok'] == 1]['expedicao'].value_counts().reset_index()
            exp_ativos.columns = ['Colaborador', 'Volume']
            exp_ativos['Função'] = 'Expedição'

            rev_ativos = df_ativos[df_ativos['revisado_ok'] == 1]['revisao'].value_counts().reset_index()
            rev_ativos.columns = ['Colaborador', 'Volume']
            rev_ativos['Função'] = 'Revisão'

            df_prod_ativos = pd.concat([exp_ativos, rev_ativos])
            
            if not df_prod_ativos.empty:
                # O Gráfico de barras agrupadas usando Plotly
                fig_ativos = px.bar(
                    df_prod_ativos, x='Colaborador', y='Volume', color='Função',
                    barmode='group', text_auto=True, color_discrete_sequence=['#FF4B4B', '#FF8C8C']
                )
                fig_ativos.update_layout(xaxis_title="", yaxis_title="Tarefas Concluídas", margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ativos, use_container_width=True)
            else:
                st.info("A equipe ainda não concluiu nenhuma etapa nas sessões ativas.")
        else:
            st.success("✨ Pauta limpa! Não há processos pendentes no momento.")

        st.markdown("---")

        # ========================================================
        # 🌎 CAMADA 2: HISTÓRICO E TENDÊNCIAS (SESSÕES CONCLUÍDAS)
        # ========================================================
        st.markdown("### 🌎 Histórico: Médias e Evolução")
        
        df_concluidos = df_dados[df_dados['despachado'] == 1].copy()
        
        if not df_concluidos.empty:
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Média Geral - Expedição", format_tempo(df_concluidos['minutos_expedicao'].mean()))
            with col2: st.metric("Média Geral - Revisão", format_tempo(df_concluidos['minutos_revisao'].mean()))
            with col3: st.metric("Média Geral - Ciclo", format_tempo(df_concluidos['minutos_total'].mean()))
            with col4: st.metric("Total de Processos Finalizados", len(df_concluidos))

            st.markdown("#### 📉 Evolução do Tempo de Fechamento de Sessão")
            
            # Agrupa as sessões finalizadas para criar a linha de tendência
            sessoes_tempo = df_concluidos.groupby('nome_sessao').agg(
                inicio=('data_entrada_dt', 'min'),
                fim=('data_conclusao_dt', 'max')
            ).reset_index()

            sessoes_tempo['Duração (min)'] = (sessoes_tempo['fim'] - sessoes_tempo['inicio']).dt.total_seconds() / 60
            sessoes_tempo = sessoes_tempo.dropna(subset=['Duração (min)'])

            if not sessoes_tempo.empty:
                sessoes_tempo['Data_Sort'] = pd.to_datetime(sessoes_tempo['nome_sessao'], format="%d/%m/%Y", errors='coerce')
                sessoes_tempo = sessoes_tempo.sort_values('Data_Sort')

                fig_line = px.line(
                    sessoes_tempo, x='nome_sessao', y='Duração (min)', markers=True,
                    line_shape="spline", color_discrete_sequence=['#FF4B4B']
                )
                fig_line.update_traces(marker=dict(size=8, line=dict(width=2, color='DarkSlateGrey')))
                fig_line.update_layout(xaxis_title="Data da Sessão", yaxis_title="Tempo Total (Minutos)", margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="rgba(0,0,0,0)")

                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("Feche uma sessão completa para gerar a linha de tendência.")
        else:
            st.info("Nenhum processo foi finalizado ainda para calcular o histórico.")

# ------------------------------------------
# ABA 6: AJUDA E GLOSSÁRIO
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
        * **Marcando as Tarefas:** Conforme o documento for feito, marque a caixinha **"Expedido"**. O colega que revisar o documento marca **"Revisado"**.
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
        * **Expedição / Revisão:** O trabalho em dupla de fazer o documento e conferir. O robô do sistema é inteligente e bloqueia tentativas da mesma pessoa expedir e revisar o próprio documento.
        * **Despachado:** O processo chegou ao fim da linha dentro do setor. Tarefa 100% concluída.
        """)
