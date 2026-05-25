import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
import time

# ==========================================
# 1. BACKEND: BANCO DE DADOS E LÓGICA
# ==========================================
DB_PATH = 'gestao_processos.db'

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()

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

        c.execute('''CREATE TABLE IF NOT EXISTS equipe (
                                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                                       nome TEXT UNIQUE,
                                       expedicao INTEGER DEFAULT 0,
                                       revisao INTEGER DEFAULT 0
                     )''')
                     
        # --- NOVA TABELA: LIXEIRA / AUDITORIA ---
        c.execute('''CREATE TABLE IF NOT EXISTS processos_excluidos (
                                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                                          numero_processo TEXT,
                                          relator TEXT,
                                          data_exclusao TEXT,
                                          motivo TEXT
                     )''')

        # --- NOVA TABELA: MURAL DE AVISOS ---
        c.execute('''CREATE TABLE IF NOT EXISTS avisos (
                                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                                          usuario TEXT,
                                          numero_processo TEXT,
                                          mensagem TEXT,
                                          data_criacao TEXT
                     )''')
        
        c.execute("SELECT COUNT(*) FROM equipe")
        if c.fetchone()[0] == 0:
            iniciais = [
                ("André", 1, 1), ("Elaine", 1, 1), ("Kátia", 1, 1),
                ("Luana C", 1, 1), ("Jessyca", 1, 1), ("Lu Fiorote", 1, 1),
                ("Mariana", 1, 1), ("Maurício", 1, 1)
            ]
            c.executemany("INSERT INTO equipe (nome, expedicao, revisao) VALUES (?, ?, ?)", iniciais)

def carregar_equipes():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT nome FROM equipe WHERE expedicao = 1")
        eq_exp = [row[0] for row in c.fetchall()]
        c.execute("SELECT nome FROM equipe WHERE revisao = 1")
        eq_rev = [row[0] for row in c.fetchall()]
        c.execute("SELECT nome FROM equipe")
        todos = [row[0] for row in c.fetchall()]
    return eq_exp, eq_rev, todos

def gerenciar_usuario(acao, nome_atual, novo_nome=None, expedicao=0, revisao=0):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            if acao == 'adicionar': c.execute("INSERT INTO equipe (nome, expedicao, revisao) VALUES (?, ?, ?)", (nome_atual, expedicao, revisao))
            elif acao == 'remover': c.execute("DELETE FROM equipe WHERE nome = ?", (nome_atual,))
            elif acao == 'substituir': c.execute("UPDATE equipe SET nome = ?, expedicao = ?, revisao = ? WHERE nome = ?", (novo_nome, expedicao, revisao, nome_atual))
            elif acao == 'editar': c.execute("UPDATE equipe SET expedicao = ?, revisao = ? WHERE nome = ?", (expedicao, revisao, nome_atual))
        return True, "✅ Operação realizada com sucesso!"
    except sqlite3.IntegrityError: return False, "❌ Erro: Este usuário já existe."
    except Exception as e: return False, f"❌ Erro no banco de dados: {e}"

def remover_processo(numero_processo, nome_sessao, motivo):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
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
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        
        # 1. Pega todos os processos dessa sessão
        c.execute("SELECT numero_processo, relator FROM processos WHERE tipo_sessao = ? AND nome_sessao = ?", (tipo_sessao, nome_sessao))
        processos_sessao = c.fetchall()

        # 2. Salva todos na Lixeira
        for proc in processos_sessao:
            c.execute("INSERT INTO processos_excluidos (numero_processo, relator, data_exclusao, motivo) VALUES (?, ?, ?, ?)",
                      (proc[0], proc[1], agora, motivo))

        # 3. Apaga a sessão do sistema ativo
        conn.execute('DELETE FROM processos WHERE tipo_sessao = ? AND nome_sessao = ?', (tipo_sessao, nome_sessao))

def carregar_excluidos():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM processos_excluidos", conn)
    return df
    
def processo_existe(numero_processo):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM processos WHERE numero_processo = ?", (numero_processo,))
        existe = c.fetchone()[0] > 0
    return existe

def marcar_urgente(numero_processo):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM processos WHERE numero_processo = ?", (numero_processo,))
        if not c.fetchone():
            return False, f"❌ Processo {numero_processo} não encontrado. Insira-o na sua sessão normal primeiro."
        conn.execute('UPDATE processos SET urgente = 1 WHERE numero_processo = ?', (numero_processo,))
    return True, f"🚨 Processo {numero_processo} destacado como URGENTE!"

def atualizar_processo(id_processo, expedicao, revisao, expedido, revisado, despachado,
                       mudou_exp, mudou_rev, mudou_desp, email=False, mensageria=False, recebido=False):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''UPDATE processos 
                        SET expedicao = ?, revisao = ?, expedido_ok = ?, revisado_ok = ?, 
                            despachado = ?, enviado_email = ?, enviado_mensageria = ?, recebido = ? 
                        WHERE id = ?''', 
                     (expedicao, revisao, int(expedido), int(revisado), int(despachado), 
                      int(email), int(mensageria), int(recebido), id_processo))

        if mudou_exp:
            if expedido: conn.execute('UPDATE processos SET data_expedido = ? WHERE id = ?', (agora, id_processo))
            else: conn.execute('UPDATE processos SET data_expedido = NULL WHERE id = ?', (id_processo,))

        if mudou_rev:
            if revisado: conn.execute('UPDATE processos SET data_revisado = ? WHERE id = ?', (agora, id_processo))
            else: conn.execute('UPDATE processos SET data_revisado = NULL WHERE id = ?', (id_processo,))

        if mudou_desp:
            if despachado: conn.execute('UPDATE processos SET data_conclusao = ? WHERE id = ?', (agora, id_processo))
            else: conn.execute('UPDATE processos SET data_conclusao = NULL WHERE id = ?', (id_processo,))

def obter_expedidor(elegiveis, nome_sessao):
    if not elegiveis: return "Nenhum escalado"
    contagem = {p: 0 for p in elegiveis}
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT expedicao, COUNT(*) FROM processos WHERE expedicao IS NOT NULL AND nome_sessao = ? GROUP BY expedicao", (nome_sessao,))
        for row in c.fetchall():
            if row[0] in contagem: contagem[row[0]] = row[1]
    return min(contagem, key=contagem.get)

def obter_revisor(expedidor, nome_sessao, revisores_ativos):
    if not revisores_ativos: return "Nenhum escalado"
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
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
    if processo_existe(numero_processo): return False, "❌ Processo já existe no sistema."
    exp_seguros, rev_seguros = [e for e in expedidores], [r for r in revisores]

    if not exp_seguros or not rev_seguros: return False, "❌ ERRO: Selecione ao menos um Expedidor e um Revisor."

    responsavel_expedicao = obter_expedidor(exp_seguros, nome_sessao)
    responsavel_revisao = obter_revisor(responsavel_expedicao, nome_sessao, rev_seguros)
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''INSERT INTO processos (numero_processo, relator, tipo_sessao, nome_sessao, expedicao, revisao, data_entrada, 
                                               expedido_ok, revisado_ok, despachado, urgente, enviado_email, enviado_mensageria, recebido) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0)''', 
                     (numero_processo, relator, tipo_sessao, nome_sessao, responsavel_expedicao, responsavel_revisao, data_atual))
    return True, f"✅ Distribuído! Expedição: **{responsavel_expedicao}** | Revisão: **{responsavel_revisao}**"

def carregar_dados(tipo_sessao=None):
    with sqlite3.connect(DB_PATH) as conn:
        if tipo_sessao: df = pd.read_sql_query(f"SELECT * FROM processos WHERE tipo_sessao = '{tipo_sessao}'", conn)
        else: df = pd.read_sql_query("SELECT * FROM processos", conn)
    return df

def restaurar_backup(df_backup):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('DELETE FROM processos')
            df_backup.to_sql('processos', conn, if_exists='append', index=False)
        return True, "✅ Dados restaurados com sucesso! O sistema voltou ao estado do backup."
    except Exception as e:
        return False, f"❌ Erro ao tentar restaurar os dados: {e}"

init_db()
EQUIPE_EXPEDICAO, EQUIPE_REVISAO, TODOS_NOMES = carregar_equipes()

def adicionar_aviso(usuario, numero_processo, mensagem):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        # Verifica se o processo existe e se não está despachado
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
    # Puxa os avisos apenas se o processo correspondente estiver com despachado = 0
    with sqlite3.connect(DB_PATH) as conn:
        query = '''
            SELECT a.usuario, a.numero_processo, p.nome_sessao, a.mensagem 
            FROM avisos a
            JOIN processos p ON a.numero_processo = p.numero_processo
            WHERE p.despachado = 0
        '''
        df_avisos = pd.read_sql_query(query, conn)
    return df_avisos

# ==========================================
# 2. FRONTEND: INTERFACE DO USUÁRIO
# ==========================================
st.set_page_config(page_title="Sistema de Sessões", layout="wide")
st.title("⚖️ Sistema Automático de Distribuição de Processos para Expedição")

# ==========================================
# 2. FRONTEND: INTERFACE DO USUÁRIO
# ==========================================
st.set_page_config(page_title="Sistema de Sessões", layout="wide")
st.title("⚖️ Sistema Automático de Distribuição de Processos para Expedição")

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

# VARIÁVEIS ESSENCIAIS (Isso aqui que estava faltando e dando o erro vermelho!)
nome_sessao_atual = datetime.now().strftime("%d/%m/%Y")
df_geral_status = carregar_dados()
sessoes_finalizadas = []

if not df_geral_status.empty:
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

def color_urgentes(row): return ['color: #ff4b4b; font-weight: bold'] * len(row) if row['urgente_flag'] == 1 else [''] * len(row)

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

        # --- NOVA LÓGICA DE FORMULÁRIO AQUI (SEM REFRESH AUTOMÁTICO) ---
        with st.form(key=f"form_{key_prefix}_{data_sessao}"):
            edited_df = st.data_editor(styled_df, column_config=cfg_colunas, hide_index=True, use_container_width=True, key=f"{key_prefix}_{data_sessao}")
            
            # Botão para processar tudo de uma vez
            submit_button = st.form_submit_button("💾 Salvar Alterações desta Sessão", type="primary")

            if submit_button:
                alteracoes_feitas = 0
                for i in range(len(edited_df)):
                    if edited_df.iloc[i].to_dict() != df_exibicao.iloc[i].to_dict():
                        atualizar_processo(
                            int(edited_df.iloc[i]['id']), edited_df.iloc[i]['Expedição'], edited_df.iloc[i]['Revisão'],
                            edited_df.iloc[i]['Expedido'], edited_df.iloc[i]['Revisado'], edited_df.iloc[i]['Despachado'],
                            edited_df.iloc[i]['Expedido'] != df_exibicao.iloc[i]['Expedido'],
                            edited_df.iloc[i]['Revisado'] != df_exibicao.iloc[i]['Revisado'],
                            edited_df.iloc[i]['Despachado'] != df_exibicao.iloc[i]['Despachado'],
                            email=edited_df.iloc[i].get('E-mail', False), mensageria=edited_df.iloc[i].get('Mensageria', False), recebido=edited_df.iloc[i].get('Recebido', False)
                        )
                        alteracoes_feitas += 1
                
                if alteracoes_feitas > 0:
                    st.toast(f"✅ {alteracoes_feitas} processo(s) atualizado(s) no banco de dados!")
                    time.sleep(1) # Pausa rápida para exibir a notificação
                    st.rerun() # Atualiza a tela para remover os despachados
                else:
                    st.toast("⚠️ Nenhuma alteração foi detectada.")
        # ---------------------------------------------------------------

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
# ABA 4: HISTÓRICO DE SESSÕES FINALIZADAS E EXCLUÍDOS
# ------------------------------------------
with aba_historico:
    sub_aba_concluidas, sub_aba_lixeira = st.tabs(["✅ Arquivo: Concluídas", "🗑️ Auditoria: Processos Excluídos"])

    # --- ABA DAS CONCLUÍDAS (O que já estava pronto) ---
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

    # --- ABA DA LIXEIRA (A novidade) ---
    with sub_aba_lixeira:
        st.subheader("Registro de Exclusões (Auditoria)")
        df_excluidos = carregar_excluidos()
        
        if not df_excluidos.empty:
            df_excluidos_display = df_excluidos.rename(columns={
                'numero_processo': 'Processo',
                'relator': 'Relator',
                'data_exclusao': 'Data/Hora da Exclusão',
                'motivo': 'Motivo Declarado'
            })
            
            # Mostra a tabela invertida (mais recentes primeiro)
            st.dataframe(df_excluidos_display[['Processo', 'Relator', 'Motivo Declarado', 'Data/Hora da Exclusão']].iloc[::-1], hide_index=True, use_container_width=True)
            
            # Botão extra para baixar o relatório da lixeira
            csv_lixo = df_excluidos_display.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Baixar Relatório de Exclusões (CSV)", data=csv_lixo, file_name="auditoria_exclusoes.csv", mime='text/csv', type="secondary")
        else:
            st.success("✨ A lixeira está vazia. Nenhum processo foi apagado do sistema.")
# ------------------------------------------
# ABA 5: DADOS & DESEMPENHO (ANALYTICS)
# ------------------------------------------
with aba_dados:
    st.subheader("📈 Relatórios de Agilidade e Desempenho")
    df_dados = carregar_dados()
    
    if df_dados.empty or 'data_expedido' not in df_dados.columns: 
        st.info("📊 Comece a despachar processos no Painel Ativo para gerar estatísticas.")
    else:
        # Função para converter as strings em datas reais
        def parse_datas(df_in):
            for c in ['data_entrada', 'data_expedido', 'data_revisado', 'data_conclusao']:
                # Tenta o formato com segundos, se falhar, tenta sem segundos
                df_in[c + '_dt'] = pd.to_datetime(df_in[c], format="%d/%m/%Y %H:%M:%S", errors='coerce').fillna(pd.to_datetime(df_in[c], format="%d/%m/%Y %H:%M", errors='coerce'))
            return df_in
            
        df_dados = parse_datas(df_dados)
        
        # Cálculos de tempo (em minutos)
        df_dados['minutos_expedicao'] = (df_dados['data_expedido_dt'] - df_dados['data_entrada_dt']).dt.total_seconds() / 60
        df_dados['minutos_revisao'] = (df_dados['data_revisado_dt'] - df_dados['data_expedido_dt']).dt.total_seconds() / 60
        df_dados['minutos_total'] = (df_dados['data_conclusao_dt'] - df_dados['data_entrada_dt']).dt.total_seconds() / 60

        def format_tempo(minutos):
            if pd.isna(minutos) or minutos < 0: return "N/A"
            return f"{int(minutos)} min" if int(minutos) < 60 else f"{int(minutos) // 60}h {int(minutos) % 60}m"

        # --- 1. MÉDIAS GERAIS (TODAS AS SESSÕES) ---
        st.markdown("### 🌎 Visão Geral (Todo o Histórico)")
        df_exp = df_dados.dropna(subset=['minutos_expedicao'])
        df_rev = df_dados.dropna(subset=['minutos_revisao'])
        df_conc = df_dados.dropna(subset=['minutos_total'])

        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Média Geral - Expedição", format_tempo(df_exp['minutos_expedicao'].mean()) if not df_exp.empty else "N/A")
        with col2: st.metric("Média Geral - Revisão", format_tempo(df_rev['minutos_revisao'].mean()) if not df_rev.empty else "N/A")
        with col3: st.metric("Média Geral - Ciclo (Até Despacho)", format_tempo(df_conc['minutos_total'].mean()) if not df_conc.empty else "N/A")
        with col4: st.metric("Total Geral de Processos Despachados", len(df_dados[df_dados['despachado'] == 1]))

        st.markdown("---")

        # --- 2. DESEMPENHO DETALHADO POR SESSÃO ---
        st.markdown("### 📅 Desempenho Detalhado por Sessão")
        
        # Filtro para escolher a sessão
        sessoes_disponiveis = sorted(df_dados['nome_sessao'].unique(), reverse=True)
        sessao_sel = st.selectbox("Selecione a Sessão para análise:", sessoes_disponiveis)
        
        # Filtrar o DataFrame apenas para a sessão escolhida
        df_s = df_dados[df_dados['nome_sessao'] == sessao_sel]
        
        # Cálculo: Tempo total que a sessão demorou para ser finalizada
        inicio_sessao = df_s['data_entrada_dt'].min()
        fim_sessao = df_s['data_conclusao_dt'].max()
        
        duracao_sessao = None
        if pd.notna(inicio_sessao) and pd.notna(fim_sessao):
            duracao_sessao = (fim_sessao - inicio_sessao).total_seconds() / 60
            
        st.info(f"⏳ **Tempo Total da Sessão ({sessao_sel}):** {format_tempo(duracao_sessao)} *(Calculado do 1º processo inserido até o último ser despachado)*")

        st.markdown("<br>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        
        # Tabela de Expedição
        with col_a:
            st.markdown("#### 🛡️ Desempenho: Equipe de Expedição")
            if not df_s.empty:
                # Agrupando por quem fez a expedição
                exp_stats = df_s.groupby('expedicao').agg(
                    Processos=('id', 'count'),
                    Despachados=('expedido_ok', 'sum'),
                    Tempo_Medio=('minutos_expedicao', 'mean')
                ).reset_index()
                
                # Formatando os números para visualização
                exp_stats['Tempo_Medio'] = exp_stats['Tempo_Medio'].apply(format_tempo)
                exp_stats = exp_stats.rename(columns={'expedicao': 'Colaborador', 'Processos': 'Volume Total', 'Despachados': 'Concluídos', 'Tempo_Medio': 'Média/Processo'})
                
                st.dataframe(exp_stats, hide_index=True, use_container_width=True)

        # Tabela de Revisão
        with col_b:
            st.markdown("#### 🔍 Desempenho: Equipe de Revisão")
            if not df_s.empty:
                # Agrupando por quem fez a revisão
                rev_stats = df_s.groupby('revisao').agg(
                    Processos=('id', 'count'),
                    Despachados=('revisado_ok', 'sum'),
                    Tempo_Medio=('minutos_revisao', 'mean')
                ).reset_index()
                
                # Formatando os números para visualização
                rev_stats['Tempo_Medio'] = rev_stats['Tempo_Medio'].apply(format_tempo)
                rev_stats = rev_stats.rename(columns={'revisao': 'Colaborador', 'Processos': 'Volume Total', 'Despachados': 'Concluídos', 'Tempo_Medio': 'Média/Processo'})
                
                st.dataframe(rev_stats, hide_index=True, use_container_width=True)

# ------------------------------------------
# ABA 6: AJUDA E GLOSSÁRIO
# ------------------------------------------
with aba_ajuda:
    st.header("📖 Manual do Usuário e Glossário")
    st.write("Bem-vindo(a) ao guia rápido do sistema! Clique nos tópicos abaixo para entender como usar cada ferramenta e o que significa cada termo.")

    with st.expander("🚀 Como começar (Passos Básicos)"):
        st.markdown("""
        O sistema foi feito para ser simples. Siga sempre esta ordem:
        1. **Aba 1 (Inserir Novos):** Escolha o tipo da sessão, marque ou desmarque livremente os nomes de quem vai trabalhar no dia nas caixinhas, e insira os processos (digitando um a um ou jogando uma planilha inteira). O sistema divide o trabalho sozinho!
        2. **Aba 2 (Painel Ativo):** Vá para a aba da sessão que você acabou de criar. É aqui que o trabalho acontece. Conforme a equipe avança, marque as caixinhas de concluído.
        3. **Fim do dia:** Quando todas as caixinhas de um processo estiverem marcadas, ele some do painel e vai direto para a **Aba 4 (Histórico)**.
        """)

    with st.expander("🗂️ Como usar o Painel Ativo (Marcando tarefas)"):
        st.markdown("""
        Na Aba 2, você verá uma tabela interativa. Você pode clicar diretamente nela para:
        * **Mudar Responsável:** Se alguém precisar sair, clique no nome da pessoa e troque pelo colega.
        * **Marcar "Expedido" e "Revisado":** Conforme o documento for feito, marque a caixa. O sistema anota a hora exata.
        * **Sessão Reservada:** Tem caixas extras. Você pode marcar se já enviou o E-mail, enviou pela Mensageria e se o recibo retornou (Recebido).
        * **Marcar "Despachado":** É a última caixa. Significa que o processo está 100% pronto.
        """)

    with st.expander("🚨 Socorro! Inseri um processo errado ou ele saiu de pauta."):
        st.markdown("""
        Sem pânico! Vá até a **Aba 3 (Controle O.K.)**, encontre a área **"Remover Processo Específico"**. 

        Digite o número exato do processo e o dia da sessão, depois clique em Remover. O processo será apagado daquele dia e você poderá inseri-lo de novo na data correta.
        """)

    with st.expander("📚 Glossário de Termos do Sistema"):
        st.markdown("""
        * **Expedição:** É a primeira etapa. Quem está escalado aqui é responsável por pegar o processo cru e preparar os documentos iniciais.
        * **Revisão:** É a segunda etapa (dupla conferência). Quem revisa valida o trabalho da expedição. O sistema garante que ninguém revise o próprio processo.
        * **Processo Urgente:** Processos que precisam passar na frente da fila. Se aparecer um no meio do dia, vá na Aba 1, escolha "Urgente" e digite o número. A linha dele vai ficar **em negrito e vermelha** no Painel Ativo para chamar a atenção de todos.
        * **Sessão Ordinária / Virtual / Reservada / Administrativa:** O sistema distribui automaticamente os processos da sessão entre os colegas que você selecionou no Passo 1, garantindo o melhor equilíbrio de carga.
        * **Despachado:** Termo final. O documento está assinado e pronto. Quando marcado, o processo encerra seu ciclo.
        """)

    with st.expander("💾 Limpeza e Segurança dos Dados"):
        st.markdown("""
        No final da **Aba 3 (Controle)**, existe uma área "Avançada" que só o gestor deve usar:
        * **Backup:** Gera um arquivo Excel (CSV) de tudo que já foi feito na história do sistema. É recomendado baixar uma vez por semana por segurança.
        * **Restaurar Sistema:** Se por algum motivo o servidor reiniciar, basta subir o arquivo CSV do backup para recuperar toda a base de dados em segundos.
        * **Limpeza Seletiva:** Se uma sessão inteira for cancelada, você pode selecionar a data específica e apagar só ela do banco de dados, mantendo o resto intacto.
        """)
