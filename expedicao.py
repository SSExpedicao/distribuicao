import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta
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
conn = st.connection("supabase", type=SupabaseConnection)

# ==========================================
# 3. DECLARAÇÃO DA FUNÇÃO INTELIGENTE
# ==========================================
def gerar_avisos_letreiro_automaticos():
    avisos_sistema = []
    
    # Agora usamos 'date' diretamente, sem o datetime. na frente
    hoje = date.today()
    hoje_str = hoje.strftime('%Y-%m-%d')
    
    # 1. Busca Trocas de Escala Ativas
    try:
        trocas = conn.client.table("trocas_escala").gte("data_nova", hoje_str).execute().data
        for t in trocas:
            # Usando 'datetime.strptime' (agora é a classe importada)
            d_orig = datetime.strptime(t['data_original'], '%Y-%m-%d').strftime('%d/%m')
            d_nova = datetime.strptime(t['data_nova'], '%Y-%m-%d').strftime('%d/%m')
            avisos_sistema.append(f"🔄 ESCALA: {t['usuario']} alterou seu dia presencial de {d_orig} para {d_nova}.")
    except:
        pass

    # 2. Busca Afastamentos (Férias e Atestados)
    try:
        afastamentos = conn.client.table("afastamentos").execute().data
        for a in afastamentos:
            dt_ini = datetime.strptime(a['data_inicio'], '%Y-%m-%d').date()
            dt_fim = datetime.strptime(a['data_fim'], '%Y-%m-%d').date()
            
            # Regra para Atestado Médico
            if a['tipo'] == "Atestado Médico" and dt_ini <= hoje <= dt_fim:
                retorno = (dt_fim + timedelta(days=1)).strftime('%d/%m')
                avisos_sistema.append(f"🩺 ATESTADO: {a['usuario']} afastado por motivos médicos. Retorno previsto: {retorno}.")
                
            # Regra para Férias
            elif a['tipo'] == "Férias" and hoje == dt_fim:
                avisos_sistema.append(f"🏖️ FÉRIAS: O colaborador {a['usuario']} regressará amanhã ao serviço!")
    except:
        pass
        
    return avisos_sistema


# ==========================================
# 4. CONSTRUÇÃO DA TELA (O Letreiro)
# ==========================================
st.title("🏛️ Sistema S.A.D.E.")

avisos_frequencia = gerar_avisos_letreiro_automaticos()

if avisos_frequencia:
    with st.container():
        for aviso in avisos_frequencia:
            if "🩺" in aviso:
                st.info(aviso)
            elif "🔄" in aviso:
                st.warning(aviso)
            else:
                st.success(aviso)

# ==========================================
# 2. BACKEND: CONEXÃO COM A NUVEM SUPABASE
# ==========================================
conn = st.connection("supabase", type=SupabaseConnection)

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
    # Ex: Digitou "andre" ou " ANDRÉ " -> Mapeia para "André"
    for nome_oficial in lista_oficial_nomes:
        if nome_norm == normalizar_texto(nome_oficial):
            return nome_oficial
            
    # 2. Se não achou exato, usa Inteligência de Similaridade (erros de digitação)
    # Cria uma lista das versões "limpas" dos nomes oficiais
    lista_norm = [normalizar_texto(n) for n in lista_oficial_nomes]
    
    # Busca nomes que tenham pelo menos 75% de semelhança com o que foi digitado
    # Ex: "Andte" ou "Eliane" (no lugar de Elaine)
    matches = difflib.get_close_matches(nome_norm, lista_norm, n=1, cutoff=0.75)
    
    if matches:
        # Achou um erro de digitação! Puxa o nome oficial correspondente.
        indice = lista_norm.index(matches[0])
        return lista_oficial_nomes[indice]
        
    # 3. É UM NOME TOTALMENTE NOVO (Ex: Douglas)
    # Se não parece com ninguém da equipe, o sistema aceita como um cara novo
    # e padroniza a primeira letra em maiúscula (Title Case)
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
    
def processo_existe(numero_processo, nome_sessao):
    try:
        # Agora o sistema verifica se o processo existe NAQUELA SESSÃO ESPECÍFICA, e não no banco todo.
        res = conn.client.table("processos").select("id", count="exact").eq("numero_processo", numero_processo).eq("nome_sessao", nome_sessao).execute()
        return res.count > 0
    except: return False

def marcar_urgente(numero_processo):
    numero_processo, _ = higienizar_dados(numero_processo)
    try:
        # Busca o processo, mas APENAS as versões que estão em andamento (despachado = 0)
        res = conn.client.table("processos").select("id").eq("numero_processo", numero_processo).eq("despachado", 0).execute().data
        if not res: return False, f"❌ Processo {numero_processo} não encontrado nas sessões ativas. Insira-o na sua pauta atual primeiro."
        
        # Se achar, marca todas as entradas ativas como urgentes
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
        
        # Puxa os ofícios despachados para o cruzamento de dados
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
            
        # 4. CONTROLE DE OFÍCIOS (MÓDULO NOVO INTEGRADO)
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
    
    # Atualizamos a trava de segurança para olhar apenas para a sessão atual
    if processo_existe(numero_processo, nome_sessao): 
        return False, f"❌ O processo já existe nesta mesma sessão ({nome_sessao})."
    
    # 1. Puxa a carga global APENAS para os membros que foram SELECIONADOS
    res_global = conn.client.table("processos").select("expedicao, revisao").in_("expedicao", expedidores_selecionados).execute().data
    
    # 2. Conta quanto cada um dos SELECIONADOS tem no total (Histórico Geral)
    contagem_exp = {nome: 0 for nome in expedidores_selecionados}
    for row in res_global:
        exp = row.get('expedicao')
        if exp in contagem_exp: contagem_exp[exp] += 1
    
    # Escolhe o expedidor com MENOS processos entre os SELECIONADOS
    responsavel_expedicao = min(contagem_exp, key=contagem_exp.get)
    
    # 3. Agora para o Revisor: 
    # Deve estar na lista de SELECIONADOS e ser diferente do expedidor escolhido
    candidatos_revisores = [nome for nome in revisores_selecionados if nome != responsavel_expedicao]
    
    res_rev_global = conn.client.table("processos").select("revisao").in_("revisao", candidatos_revisores).execute().data
    contagem_rev = {nome: 0 for nome in candidatos_revisores}
    for row in res_rev_global:
        rev = row.get('revisao')
        if rev in contagem_rev: contagem_rev[rev] += 1
    
    responsavel_revisao = min(contagem_rev, key=contagem_rev.get)
    
    # Inserção
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    conn.client.table("processos").insert({
        "numero_processo": numero_processo, "relator": relator, "tipo_sessao": tipo_sessao, 
        "nome_sessao": nome_sessao, "expedicao": responsavel_expedicao, "revisao": responsavel_revisao, 
        "data_entrada": data_atual, "expedido_ok": 0, "revisado_ok": 0, "despachado": 0, "urgente": 0
    }).execute()
    
    return True, f"✅ Distribuído! Exp: {responsavel_expedicao} | Rev: {responsavel_revisao}"

def carregar_dados_sqlite(tipo_sessao=None):
    try:
        if tipo_sessao: dados = conn.client.table("processos").select("*").eq("tipo_sessao", tipo_sessao).execute().data
        else: dados = conn.client.table("processos").select("*").execute().data
        return pd.DataFrame(dados)
    except: return pd.DataFrame()

def restaurar_backup(df_backup):
    try:
        # 1. Apaga tudo antes de restaurar
        conn.client.table("processos").delete().neq("numero_processo", "vazio").execute()
        
        # 2. Converte campos vazios (NaN) para None para o Supabase aceitar
        df_backup = df_backup.astype(object).where(pd.notna(df_backup), None)
        
        records = df_backup.to_dict(orient="records")
        
        # 3. Limpeza Blindada: Remove campos que são calculados ou do Supabase
        # O sistema só deve enviar para o Supabase as colunas que realmente existem na tabela
        for r in records:
            colunas_para_remover = ['id', 'created_at', 'chave_sessao', 'data_entrada_dt', 'data_expedido_dt', 'data_revisado_dt', 'data_conclusao_dt', 'status_num', 'pendente_flag']
            for col in colunas_para_remover:
                if col in r:
                    del r[col]
            
        # 4. Envia para o banco
        conn.client.table("processos").insert(records).execute()
        return True, "✅ Dados restaurados com sucesso!"
    except Exception as e: 
        return False, f"❌ Erro ao tentar restaurar: {e}"

def adicionar_aviso(usuario, numero_processo, mensagem):
    try:
        # Verifica se existe pelo menos uma entrada desse processo que ainda NÃO foi despachada
        res = conn.client.table("processos").select("id").eq("numero_processo", numero_processo).eq("despachado", 0).execute().data
        if not res: return False, f"❌ Processo '{numero_processo}' não está ativo em nenhuma sessão no momento (ou já foi concluído)."
        
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
        
        # CORREÇÃO PARA MÚLTIPLOS RITOS: Ordena para colocar as versões ativas (0) no topo
        # e remove duplicados, mantendo apenas a instância em andamento para o cruzamento.
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
        
        # CORREÇÃO PARA MÚLTIPLOS RITOS: Evita que o histórico de avisos multiplique as linhas
        # se o processo tiver passado várias vezes pelo banco de dados.
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
        # 1. Verifica se o processo está pendente no Painel Ativo
        res = conn.client.table("processos").select("id").eq("numero_processo", numero_processo).eq("despachado", 0).execute().data
        if not res: return False, f"❌ O processo {numero_processo} não foi encontrado nas sessões ativas ou já foi despachado."
        
        id_proc = res[0]['id']
        
        # 2. Salva a digital da chefia na auditoria
        conn.client.table("auditoria_chefia").insert({
            "numero_processo": numero_processo,
            "justificativa": justificativa,
            "usuario_chefia": usuario,
            "data_liberacao": agora
        }).execute()
        
        # 3. Força a finalização do processo passando por cima das travas
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
        # Busca ofícios ligados a este processo que AINDA NÃO foram despachados (0)
        res = conn.client.table("oficios").select("id", count="exact").eq("numero_processo", numero_processo).eq("oficio_despachado", 0).execute()
        return res.count > 0 # Retorna True se tiver alguma pendência
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

# GESTÃO DE SESSÃO (CONTROLE DE SENHA DA CHEFIA)
if 'gestor_autenticado' not in st.session_state:
    st.session_state.gestor_autenticado = False

aba_inserir, aba_sessoes, aba_oficios, aba_oficios_relatorio, aba_historico, aba_gestao, aba_ajuda = st.tabs([
    "📥 1. Inserir Novos",
    "🗂️ 2. Painel Ativo",
    "✉️ 2.5. Controle de Ofícios",
    "📄 2.7. Relatório de Expedição", # <-- Nova Aba adicionada
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
        
        # --- INÍCIO DA CORREÇÃO DE AGRUPAMENTO DE SESSÕES ---
        hoje = datetime.now().strftime("%d/%m/%Y")
        sessoes_ativas = []
        if not df_geral_status.empty:
            # Puxa o nome de todas as sessões que estão em andamento no momento
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
        # --- FIM DA CORREÇÃO ---

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
    # ... O resto do seu código de inserção continua igual a partir daqui ...
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
    # --- NOVO FILTRO INTELIGENTE E SAUDAÇÃO ---
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
    
    # Mensagem personalizada baseada na seleção
    if colab_painel != "👁️ Ver Todos os Processos do Setor":
        st.markdown(f"👋 **Bom trabalho, {colab_painel}!** Exibindo estritamente as demandas onde você é o Expedidor ou o Revisor.")
    
    st.markdown("---")
    
    # Cria as sub-abas logo abaixo do filtro
    sub_aba_ord, sub_aba_ordv, sub_aba_res, sub_aba_adm = st.tabs(["🏛️ Ordinária", "💻 Ordinária Virtual", "🔒 Reservada", "📁 Administrativa"])
    
    def exibir_tabela_interativa(df_filtrado, key_prefix, data_sessao, tipo_sessao_tb):
        titulo_placeholder = st.empty()
        
        # Garante colunas de quarentena
        if 'precisa_correcao' not in df_filtrado.columns: df_filtrado['precisa_correcao'] = 0
        if 'motivo_correcao' not in df_filtrado.columns: df_filtrado['motivo_correcao'] = ""
        
        # Preparação da coluna de status para o editor
        df_exibicao = df_filtrado.copy()
        
        # Criamos a coluna 'Revisado_Display' para o Selectbox
        def definir_status_revisao(row):
            if row['precisa_correcao'] == 1: return "❌ Corrigir (Quarentena)"
            if row['revisado_ok'] == 1: return "OK - Liberado"
            return "Pendente"

        df_exibicao['Revisado_Display'] = df_exibicao.apply(definir_status_revisao, axis=1)

        # Seleção de colunas para exibição
        cols_exibir = ['id', 'urgente', 'numero_processo', 'relator', 'expedicao', 'expedido_ok', 'revisao', 'Revisado_Display', 'despachado']
        df_exib = df_exibicao[cols_exibir].copy()
        
        # Renomeação para o usuário
        rename_dict = {'numero_processo': 'Processo', 'expedido_ok': 'Expedido', 'revisado_ok': 'Revisado_OK', 'despachado': 'Despachado'}
        df_exib = df_exib.rename(columns=rename_dict)
        
        # Configuração do Editor
        cfg_colunas = {
            "id": None, 
            "urgente": None,
            "Processo": st.column_config.TextColumn(disabled=True), 
            "Relator": st.column_config.TextColumn(disabled=True), 
            "Expedição": st.column_config.SelectboxColumn("Expedição", options=TODOS_NOMES),
            "Revisão": st.column_config.SelectboxColumn("Revisão", options=TODOS_NOMES),
            "Revisado_Display": st.column_config.SelectboxColumn("Status Revisão", options=["Pendente", "OK - Liberado", "❌ Corrigir (Quarentena)"]),
            "Despachado": st.column_config.CheckboxColumn("Despachado")
        }

        with st.form(key=f"form_{key_prefix}_{data_sessao}"):
            edited_df = st.data_editor(
                df_exib, 
                column_config=cfg_colunas, 
                hide_index=True, 
                use_container_width=True,
                key=f"editor_{key_prefix}_{data_sessao}"
            )
            submit_button = st.form_submit_button("💾 Salvar Alterações desta Sessão", type="primary")

            if submit_button:
                alteracoes_feitas = 0
                bloqueio_ativo = False
                
                for i in range(len(edited_df)):
                    linha_nova = edited_df.iloc[i]
                    linha_antiga = df_exib.iloc[i]
                    
                    if not linha_nova.equals(linha_antiga):
                        mudancas = {}
                        
                        # Lógica da Revisão (A nova trava/liberação)
                        if linha_nova['Revisado_Display'] == "OK - Liberado":
                            mudancas['revisado_ok'] = 1
                            mudancas['precisa_correcao'] = 0
                        elif linha_nova['Revisado_Display'] == "❌ Corrigir (Quarentena)":
                            mudancas['revisado_ok'] = 0
                            mudancas['precisa_correcao'] = 1
                        else: # Pendente
                            mudancas['revisado_ok'] = 0
                            mudancas['precisa_correcao'] = 0

                        # Lógica do Despacho (Mantendo a trava mestre)
                        if linha_nova['Despachado'] == True and linha_antiga['Despachado'] == False:
                            if tipo_sessao_tb in ["Sessão Ordinária", "Sessão Ordinária Virtual"]:
                                isento = conn.client.table("processos").select("precisa_correcao").eq("numero_processo", linha_nova['Processo']).execute().data
                                if not (isento and isento[0].get('precisa_correcao') == 2):
                                    if not tem_oficio_cadastrado(linha_nova['Processo']) or verificar_oficios_pendentes(linha_nova['Processo']):
                                        st.error(f"🚨 ERRO: Processo {linha_nova['Processo']} possui pendências de ofício!")
                                        bloqueio_ativo = True
                                        continue
                        
                        mudancas['despachado'] = 1 if linha_nova['Despachado'] else 0
                        mudancas['expedicao'] = linha_nova['Expedição']
                        mudancas['revisao'] = linha_nova['Revisão']
                        
                        atualizar_processo(int(linha_nova['id']), mudancas)
                        alteracoes_feitas += 1
                
                if alteracoes_feitas > 0 and not bloqueio_ativo:
                    st.rerun()
                elif bloqueio_ativo:
                    st.warning("⚠️ Algumas alterações foram bloqueadas.")

    with sub_aba_ord:
        df_ord = carregar_dados_sqlite("Sessão Ordinária")
        if not df_ord.empty:
            # Aplica o filtro se o usuário selecionar um nome específico
            if colab_painel != "👁️ Ver Todos os Processos do Setor":
                df_ord = df_ord[(df_ord['expedicao'] == colab_painel) | (df_ord['revisao'] == colab_painel)]
            
            # Descobre quais sessões ativas realmente têm processos desse colaborador
            sessoes_com_processos = [data for data in df_ord['nome_sessao'].unique() if f"Sessão Ordinária | {str(data).strip()}" not in sessoes_finalizadas]
            
            if sessoes_com_processos:
                for data in sessoes_com_processos:
                    exibir_tabela_interativa(df_ord[df_ord['nome_sessao'] == data], "ord", data, "Sessão Ordinária")
            else:
                st.success("✨ Você não possui nenhum processo pendente nesta sub-aba!")

    with sub_aba_ordv:
        df_ordv = carregar_dados_sqlite("Sessão Ordinária Virtual")
        if not df_ordv.empty:
            if colab_painel != "👁️ Ver Todos os Processos do Setor":
                df_ordv = df_ordv[(df_ordv['expedicao'] == colab_painel) | (df_ordv['revisao'] == colab_painel)]
                
            sessoes_com_processos = [data for data in df_ordv['nome_sessao'].unique() if f"Sessão Ordinária Virtual | {str(data).strip()}" not in sessoes_finalizadas]
            
            if sessoes_com_processos:
                for data in sessoes_com_processos:
                    exibir_tabela_interativa(df_ordv[df_ordv['nome_sessao'] == data], "ordv", data, "Sessão Ordinária Virtual")
            else:
                st.success("✨ Você não possui nenhum processo pendente nesta sub-aba!")

    with sub_aba_res:
        df_res = carregar_dados_sqlite("Sessão Reservada")
        if not df_res.empty:
            if colab_painel != "👁️ Ver Todos os Processos do Setor":
                df_res = df_res[(df_res['expedicao'] == colab_painel) | (df_res['revisao'] == colab_painel)]
                
            sessoes_com_processos = [data for data in df_res['nome_sessao'].unique() if f"Sessão Reservada | {str(data).strip()}" not in sessoes_finalizadas]
            
            if sessoes_com_processos:
                for data in sessoes_com_processos:
                    exibir_tabela_interativa(df_res[df_res['nome_sessao'] == data], "res", data, "Sessão Reservada")
            else:
                st.success("✨ Você não possui nenhum processo pendente nesta sub-aba!")

    with sub_aba_adm:
        df_adm = carregar_dados_sqlite("Sessão Administrativa")
        if not df_adm.empty:
            if colab_painel != "👁️ Ver Todos os Processos do Setor":
                df_adm = df_adm[(df_adm['expedicao'] == colab_painel) | (df_adm['revisao'] == colab_painel)]
                
            sessoes_com_processos = [data for data in df_adm['nome_sessao'].unique() if f"Sessão Administrativa | {str(data).strip()}" not in sessoes_finalizadas]
            
            if sessoes_com_processos:
                for data in sessoes_com_processos:
                    exibir_tabela_interativa(df_adm[df_adm['nome_sessao'] == data], "adm", data, "Sessão Administrativa")
            else:
                st.success("✨ Você não possui nenhum processo pendente nesta sub-aba!")

# ------------------------------------------
# ABA 2.5: CONTROLE DE OFÍCIOS E QUARENTENA
# ------------------------------------------
with aba_oficios:
    st.header("✉️ Controle e Expedição de Ofícios")
    
    # Puxa os dados brutos (apenas ativos de Ord/Virtual)
    df_ativos_base = df_geral_status[(df_geral_status['despachado'] == 0) & (df_geral_status['tipo_sessao'].isin(['Sessão Ordinária', 'Sessão Ordinária Virtual']))].copy()
    
    if df_ativos_base.empty:
        st.success("✨ Pauta limpa! Nenhum processo aguardando ofícios no momento.")
    else:
        st.subheader("🔍 1. Filtros de Seleção da Mesa")
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            tipo_sessao_filtro = st.selectbox("Qual a Sessão?", ["Sessão Ordinária", "Sessão Ordinária Virtual"])
            
        with col_f2:
            quem_expede_global = st.selectbox("Quem está expedindo?", TODOS_NOMES)
            
        # Filtra o dataframe com base na sessão escolhida no primeiro filtro
        df_ativos_filtrado = df_ativos_base[df_ativos_base['tipo_sessao'] == tipo_sessao_filtro]
        
        with col_f3:
            if not df_ativos_filtrado.empty:
                proc_selecionado = st.selectbox("Nº do Processo:", df_ativos_filtrado['numero_processo'].tolist())
            else:
                st.info("Nenhum processo pendente nesta sessão.")
                proc_selecionado = None
                
        st.markdown("---")

        # Só abre o restante da tela se o usuário conseguir selecionar um processo válido
        if proc_selecionado:
            
            # Alerta de Quarentena e Botão de Liberação
            proc_data = df_ativos_filtrado[df_ativos_filtrado['numero_processo'] == proc_selecionado].iloc[0]
            if proc_data.get('precisa_correcao') == 1:
                st.error(f"🚨 PROCESSO EM QUARENTENA | Motivo apontado pelo Revisor: **{proc_data.get('motivo_correcao')}**")
                if st.button("✅ Correção Realizada (Retirar da Quarentena)", type="primary"):
                    conn.client.table("processos").update({"precisa_correcao": 0, "motivo_correcao": ""}).eq("numero_processo", proc_selecionado).execute()
                    st.success("Processo corrigido e liberado para a mesa principal!")
                    time.sleep(1.5)
                    st.rerun()
            
           # 2. Formulário Interativo de Cadastro
            st.subheader("➕ 2. Cadastrar Novo Ofício ou Memorando")
            
            # Nova Categoria incluindo Memorando
            col_o1, col_o2 = st.columns(2)
            with col_o1: 
                cat_oficio = st.selectbox("Categoria:", ["Jurisdicionado", "Não Jurisdicionado", "Memorando (Envio Interno)"])
            with col_o2: 
                if cat_oficio == "Não Jurisdicionado":
                    tipo_nao_jur = st.selectbox("Especificação:", ["Representante", "Direto para Empresa"])
                else:
                    tipo_nao_jur = ""
                    st.write("") # Espaçamento invisível para alinhar
            
            # Botão de Isenção (A grande solução para processos sem ofício)
            if st.button("🚫 Isentar este processo de ofícios/memorandos", use_container_width=True):
                # Usamos o código 2 para representar ISENTO
                conn.client.table("processos").update({"precisa_correcao": 2}).eq("numero_processo", proc_selecionado).execute()
                st.success("✅ Processo marcado como ISENTO. Já pode ser despachado!")
                time.sleep(1)
                st.rerun()

            st.markdown("---")

            # O Cérebro do Autocomplete
            lista_dest = obter_lista_destinatarios(cat_oficio)
            opcoes_dest = ["-- Selecionar Existente --"] + lista_dest + ["➕ Cadastrar Novo Destinatário..."]
            dest_selecionado = st.selectbox("Nome do Destinatário (Busca Automática):", opcoes_dest)
            
            dest_final = dest_selecionado
            if dest_selecionado == "➕ Cadastrar Novo Destinatário...":
                dest_final = st.text_input("Digite o nome oficial (O sistema vai aprender este nome para a próxima):")
                
            num_oficio = st.text_input("Nº do Ofício ou Memorando (Ex: 125/2026):")
            
            # Aplicação da Regra Automática
            if cat_oficio == "Jurisdicionado":
                fluxo_doc = "Original no Protocolo | Clone no Processo"
            elif cat_oficio == "Memorando (Envio Interno)":
                fluxo_doc = "Envio Interno (Via Única)"
            else:
                fluxo_doc = "Original no Processo | Clone no Protocolo"
                
            st.info(f"💡 **Regra de Vias Aplicada:** {fluxo_doc}")
            
            if st.button("💾 Adicionar Ofício/Memorando", type="primary", use_container_width=True):
                if dest_final and dest_final != "-- Selecionar Existente --" and num_oficio:
                    # Envia a variável 'quem_expede_global' definida nos filtros do topo
                    ok, m = adicionar_oficio(proc_selecionado, num_oficio, cat_oficio, tipo_nao_jur, dest_final, 1, fluxo_doc, quem_expede_global)
                    # Reseta a isenção caso um ofício seja adicionado (processo volta a precisar de despacho)
                    conn.client.table("processos").update({"precisa_correcao": 0}).eq("numero_processo", proc_selecionado).execute()
                    
                    if ok: 
                        st.success(m)
                        time.sleep(1)
                        st.rerun()
                    else: st.error(m)
                else:
                    st.warning("⚠️ Preencha o Destinatário e o Número do Ofício.")
                    
            st.markdown("---")
            
            # 3. Painel de Baixa dos Ofícios (Checkbox)
            st.subheader("📋 3. Ofícios Gerados para este Processo")
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
# ABA 2.7: RELATÓRIO DE EXPEDIÇÃO INDIVIDUAL (COM FILTRO DE SESSÃO)
# ------------------------------------------
with aba_oficios_relatorio:
    st.header("📄 Relatório de Expedição Individual")
    
    # Dividimos o topo igualmente para os dois filtros
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        colab_rel = st.selectbox("Selecione o Colaborador (Expedidor):", TODOS_NOMES, key="rel_colab")
        
    if colab_rel:
        # 1. Busca os processos ATIVOS onde o usuário é o EXPEDIDOR e puxa o NOME DA SESSÃO junto
        try:
            dados_processos = conn.client.table("processos").select("numero_processo, precisa_correcao, nome_sessao").eq("expedicao", colab_rel).eq("despachado", 0).execute().data
            df_proc_ativos = pd.DataFrame(dados_processos)
        except:
            df_proc_ativos = pd.DataFrame()
            
        if not df_proc_ativos.empty:
            # Puxa apenas as sessões onde o colaborador tem pendências reais agora
            sessoes_ativas_colab = df_proc_ativos['nome_sessao'].unique().tolist()
            
            # Filtro Inteligente de Sessão
            with col_r2:
                sessao_selecionada = st.selectbox("Filtre por Sessão:", ["Todas as Sessões"] + sessoes_ativas_colab, key="rel_sessao")
                
            # Aplica o filtro na tabela antes de gerar a visualização
            if sessao_selecionada != "Todas as Sessões":
                df_proc_ativos = df_proc_ativos[df_proc_ativos['nome_sessao'] == sessao_selecionada]
                
            lista_processos = df_proc_ativos['numero_processo'].unique().tolist()
            
            # 2. Busca os ofícios/memorandos apenas dos processos filtrados
            try:
                dados_oficios = conn.client.table("oficios").select("*").in_("numero_processo", lista_processos).execute().data
                df_oficios_ativos = pd.DataFrame(dados_oficios)
            except:
                df_oficios_ativos = pd.DataFrame()
            
            st.subheader(f"📋 Checklist de Trabalho")
            if sessao_selecionada == "Todas as Sessões":
                st.write(f"Exibindo **todas as pendências globais** de {colab_rel}.")
            else:
                st.write(f"Exibindo apenas processos da **{sessao_selecionada}**.")
            st.markdown("---")
            
            # Varre a lista de processos filtrados do colaborador
            for proc in lista_processos:
                status_proc = df_proc_ativos[df_proc_ativos['numero_processo'] == proc]['precisa_correcao'].values[0]
                
                with st.expander(f"📦 Processo: {proc}"):
                    if status_proc == 2:
                        st.success("🚫 Este processo foi marcado como ISENTO de ofícios/memorandos.")
                    
                    elif not df_oficios_ativos.empty and proc in df_oficios_ativos['numero_processo'].values:
                        oficios_proc = df_oficios_ativos[df_oficios_ativos['numero_processo'] == proc]
                        
                        df_ofic = oficios_proc[oficios_proc['categoria'] != "Memorando (Envio Interno)"]
                        df_memo = oficios_proc[oficios_proc['categoria'] == "Memorando (Envio Interno)"]
                        
                        if not df_ofic.empty:
                            st.markdown("**✉️ Ofícios Cadastrados:**")
                            for _, row in df_ofic.iterrows():
                                status_envio = "✅ Despachado no SADE" if row.get('oficio_despachado') == 1 else "⏳ Pendente de Envio"
                                st.write(f"- Nº {row['numero_oficio']} | Destino: {row['destinatario']} ({row['categoria']}) -> *{status_envio}*")
                        
                        if not df_memo.empty:
                            st.markdown("**📝 Memorandos Cadastrados:**")
                            for _, row in df_memo.iterrows():
                                status_envio = "✅ Despachado no SADE" if row.get('oficio_despachado') == 1 else "⏳ Pendente de Envio"
                                st.write(f"- Nº {row['numero_oficio']} | Destino: {row['destinatario']} -> *{status_envio}*")
                    else:
                        st.warning("⏳ Nenhum documento cadastrado para este processo ainda. Cadastre na Aba 2.5.")
        else:
            with col_r2:
                st.selectbox("Filtre por Sessão:", ["Nenhuma pendência"], disabled=True)
            st.info(f"✨ Excelente! **{colab_rel}** não possui processos ativos aguardando despacho.")

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
                # Mudamos para 5 colunas para caber o novo filtro
                col_f1, col_t1, col_f2, col_f3, col_f4 = st.columns(5)
                
                with col_f1:
                    datas_unicas = sorted(df_historico_display['Data da Sessão'].unique(), reverse=True)
                    filtro_sessao = st.multiselect("📅 Data da Sessão", options=datas_unicas)
                
                # --- NOVO FILTRO DE TIPO DE SESSÃO AQUI ---
                with col_t1:
                    tipos_unicos = sorted(df_historico_display['Tipo de Sessão'].dropna().unique())
                    filtro_tipo = st.multiselect("📌 Tipo de Sessão", options=tipos_unicos)
                # ------------------------------------------
                
                with col_f2:
                    filtro_usuario = st.multiselect("👥 Colaborador", options=TODOS_NOMES)
                with col_f3:
                    filtro_processo = st.text_input("📄 Nº do Processo", placeholder="Ex: 12345")
                with col_f4:
                    filtro_relator = st.text_input("⚖️ Relator", placeholder="Nome...")

            # Atualizando a lógica de cruzamento para incluir o novo filtro
            df_filtrado_hist = df_historico_display.copy()
            if filtro_sessao: df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['Data da Sessão'].isin(filtro_sessao)]
            
            # --- ATIVANDO A BUSCA DO NOVO FILTRO ---
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
            # --- NOVO: MÓDULO DE LIBERAÇÃO FORÇADA PELA CHEFIA ---
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
            # -----------------------------------------------------
            
            # (O restante do código que já existia no sub_controle continua normal daqui para baixo)
            if not df_geral_status.empty:
                data_selecionada = st.selectbox("📅 Data da Sessão (OKs):", sorted(df_geral_status['nome_sessao'].unique(), reverse=True), key="chave_data_oks_gestao")
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
                                exp_bruto = str(row.get('Expedidor', hist_exp)).strip() if pd.notna(row.get('Expedidor')) else hist_exp
                                rev_bruto = str(row.get('Revisor', hist_rev)).strip() if pd.notna(row.get('Revisor')) else hist_rev
                                exp_val = higienizar_colaborador(exp_bruto, TODOS_NOMES)
                                rev_val = higienizar_colaborador(rev_bruto, TODOS_NOMES)
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
                # Conversão e tratamento de datas e tempos
                for c in ['data_entrada', 'data_expedido', 'data_revisado', 'data_conclusao']:
                    df_dados[c + '_dt'] = pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M:%S", errors='coerce').fillna(
                                          pd.to_datetime(df_dados[c], format="%d/%m/%Y %H:%M", errors='coerce'))
                
                df_concluidos = df_dados[df_dados['despachado'] == 1].copy()
                df_ativos = df_dados[df_dados['despachado'] == 0].copy()
                df_tempo_real = df_concluidos[df_concluidos['data_entrada'] != df_concluidos['data_conclusao']].copy()
                
                # CORREÇÃO: Forçamos a criação das colunas sempre, evitando o KeyError
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
                    
                    # --- CARD ROW 1: PROCESSOS GERAIS ---
                    col1, col2, col3, col4 = st.columns(4)
                    total_despachados = len(df_concluidos)
                    total_sessoes = df_concluidos['nome_sessao'].nunique()
                    media_proc_sessao = round(total_despachados / total_sessoes) if total_sessoes > 0 else 0
                    total_urgentes = len(df_concluidos[df_concluidos['urgente'] == 1])
                    col1.metric("📦 Total Despachados", total_despachados)
                    col2.metric("🏛️ Sessões Realizadas", total_sessoes)
                    col3.metric("⚖️ Média Proc./Sessão", media_proc_sessao)
                    col4.metric("🔥 Urgências Atendidas", total_urgentes)
                    
                    # --- CARD ROW 2: INTELIGÊNCIA DE OFÍCIOS ---
                    try:
                        df_oficios_analytics = pd.DataFrame(conn.client.table("oficios").select("*").execute().data)
                    except:
                        df_oficios_analytics = pd.DataFrame()

                    if not df_oficios_analytics.empty:
                        df_ofic_despachados = df_oficios_analytics[df_oficios_analytics['oficio_despachado'] == 1]
                        total_oficios = len(df_ofic_despachados)
                        proc_com_oficios = df_ofic_despachados['numero_processo'].nunique()
                        media_ofic_proc = round(total_oficios / proc_com_oficios, 1) if proc_com_oficios > 0 else 0
                        ofic_jur = len(df_ofic_despachados[df_ofic_despachados['categoria'] == 'Jurisdicionado'])
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        col_of1, col_of2, col_of3, col_of4 = st.columns(4)
                        col_of1.metric("✉️ Ofícios Expedidos", total_oficios)
                        col_of2.metric("📊 Média Ofícios/Processo", media_ofic_proc)
                        col_of3.metric("🏛️ Ofic. Jurisdicionados", ofic_jur)
                        col_of4.metric("🏢 Ofic. Não Jurisdic.", total_oficios - ofic_jur)
                    
                    # --- MONITORAMENTO EM TEMPO REAL E RETRABALHO ---
                    st.markdown("---")
                    col_ret1, col_ret2 = st.columns([1, 1])
                    
                    with col_ret1:
                        st.markdown("#### 🚨 Retrabalho (Quarentena Ativa)")
                        if 'precisa_correcao' in df_dados.columns:
                            df_erros_ativos = df_dados[(df_dados['precisa_correcao'] == 1) & (df_dados['despachado'] == 0)]
                            total_erros_ativos = len(df_erros_ativos)
                            if total_erros_ativos > 0:
                                st.error(f"⚠️ Existem {total_erros_ativos} processo(s) na quarentena.")
                                erros_por_user = df_erros_ativos['expedicao'].value_counts().reset_index()
                                erros_por_user.columns = ['Expedidor', 'Pendências']
                                st.dataframe(erros_por_user, hide_index=True, use_container_width=True)
                            else:
                                st.success("🎉 Zero processos na quarentena! Trabalho com 100% de precisão.")
                    
                    with col_ret2:
                        st.markdown("#### 📡 Radar Ativo (Mesa Agora)")
                        sessoes_stats = df_dados.groupby('nome_sessao')['despachado'].agg(['count', 'sum']).reset_index()
                        ativas_list = sessoes_stats[sessoes_stats['count'] > sessoes_stats['sum']]['nome_sessao'].tolist()
                        df_ativos_reais = df_dados[df_dados['nome_sessao'].isin(ativas_list) & (df_dados['despachado'] == 0)].copy()
                        
                        if not df_ativos_reais.empty:
                            urg_pendentes = len(df_ativos_reais[df_ativos_reais['urgente'] == 1])
                            st.warning(f"📋 Pauta Ativa com {len(df_ativos_reais)} processos em andamento.")
                            st.markdown(f"**⏳ Aguardando Elaboração:** {len(df_ativos_reais[df_ativos_reais['expedido_ok'] == 0])}")
                            st.markdown(f"**🔍 Aguardando Conferência:** {len(df_ativos_reais[(df_ativos_reais['expedido_ok'] == 1) & (df_ativos_reais['revisado_ok'] == 0)])}")
                            st.markdown(f"**🚨 Urgentes pendentes:** {urg_pendentes}")
                        else:
                            st.success("✨ Pauta limpa! Sem pendências urgentes ou ordinárias no radar.")

                    # =========================================================
                    # 🧠 ABAS INTERATIVAS DE INVESTIGAÇÃO DE DADOS (BI GLOBAL)
                    # =========================================================
                    st.markdown("---")
                    st.markdown("### 📊 Central de Análise de Comportamento e Desempenho")
                    
                    tab_sinergia, tab_cadencia, tab_urgencias, tab_score = st.tabs([
                        "🤝 Participação e Sinergia", 
                        "⏱️ Gargalos e Cadência", 
                        "🔥 Índice de Urgências", 
                        "⭐ Score de Elite"
                    ])
                    
                    with tab_sinergia:
                        st.markdown("#### 🤝 Volume de Participação Operacional e Matriz de Sinergia")
                        col_g1, col_g2 = st.columns(2)
                        with col_g1:
                            st.markdown("##### 📦 Distribuição de Expedição") 
                            exp_counts = df_concluidos['expedicao'].value_counts().reset_index()
                            exp_counts.columns = ['Colaborador', 'Processos']
                            if not exp_counts.empty:
                                fig_exp = px.pie(exp_counts, values='Processos', names='Colaborador', hole=0.4)
                                fig_exp.update_traces(textposition='inside', textinfo='percent+value')
                                st.plotly_chart(fig_exp, use_container_width=True)
                        with col_g2:
                            st.markdown("##### 🔍 Distribuição de Revisão") 
                            rev_counts = df_concluidos['revisao'].value_counts().reset_index()
                            rev_counts.columns = ['Colaborador', 'Processos']
                            if not rev_counts.empty:
                                fig_rev = px.pie(rev_counts, values='Processos', names='Colaborador', hole=0.4)
                                fig_rev.update_traces(textposition='inside', textinfo='percent+value')
                                st.plotly_chart(fig_rev, use_container_width=True)
                        
                        st.markdown("##### 📊 Matriz de Colaboração (Raio-X de Soft Skills)")
                        matriz = df_concluidos.groupby(['expedicao', 'revisao']).size().reset_index(name='Despachos Juntos')
                        if not matriz.empty:
                            fig_matriz = px.density_heatmap(matriz, x='revisao', y='expedicao', z='Despachos Juntos', text_auto=True, color_continuous_scale='Viridis')
                            fig_matriz.update_layout(xaxis_title="Quem Revisou", yaxis_title="Quem Expediu")
                            st.plotly_chart(fig_matriz, use_container_width=True)

                    with tab_cadencia:
                        st.markdown("#### ⏱️ Análise de Gargalos Operacionais e Tempos Médios")
                        c_t1, c_t2, c_t3 = st.columns(3)
                        c_t1.metric("Média de Elaboração", format_tempo(df_tempo_real['min_exp'].mean()) if not df_tempo_real.empty else "N/A")
                        c_t2.metric("Média de Conferência", format_tempo(df_tempo_real['min_rev'].mean()) if not df_tempo_real.empty else "N/A")
                        c_t3.metric("Tempo de Ciclo Total", format_tempo(df_tempo_real['min_total'].mean()) if not df_tempo_real.empty else "N/A")
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        col_grg1, col_grg2 = st.columns(2)
                        with col_grg1:
                            st.markdown("**Tempo Médio na Elaboração por Usuário (Minutos)**")
                            t_exp = df_tempo_real[df_tempo_real['min_exp'] >= 0].groupby('expedicao')['min_exp'].mean().reset_index()
                            t_exp.columns = ['Colaborador', 'Média (Min)']
                            if not t_exp.empty:
                                st.plotly_chart(px.bar(t_exp, x='Colaborador', y='Média (Min)', color='Média (Min)', color_continuous_scale='Reds'), use_container_width=True)
                        with col_grg2:
                            st.markdown("**Tempo Médio na Revisão por Usuário (Minutos)**")
                            t_rev = df_tempo_real[df_tempo_real['min_rev'] >= 0].groupby('revisao')['min_rev'].mean().reset_index()
                            t_rev.columns = ['Colaborador', 'Média (Min)']
                            if not t_rev.empty:
                                st.plotly_chart(px.bar(t_rev, x='Colaborador', y='Média (Min)', color='Média (Min)', color_continuous_scale='Blues'), use_container_width=True)

                    with tab_urgencias:
                        st.markdown("#### 🚨 Distribuição Crítica e Índice de Urgentes")
                        urg_df = df_concluidos[df_concluidos['urgente'] == 1].groupby('expedicao').size().reset_index(name='Urgências Resolvidas')
                        if not urg_df.empty:
                            fig_urg = px.pie(urg_df, values='Urgências Resolvidas', names='expedicao', hole=0.4, color_discrete_sequence=px.colors.sequential.YlOrRd_r)
                            fig_urg.update_traces(textposition='inside', textinfo='percent+label+value')
                            st.plotly_chart(fig_urg, use_container_width=True)
                        else:
                            st.info("Nenhum processo urgente foi finalizado no período analisado.")

                    with tab_score:
                        st.markdown("#### ⭐ Score de Elite S.A.D.E. (Qualidade & Proatividade)")
                        st.write("Métrica de desempenho unificada: Velocidade setorial + bônus por urgências solucionadas - penalidades por erros atuais na quarentena.")
                        
                        if not df_tempo_real.empty:
                            media_setor_exp = df_tempo_real['min_exp'].mean()
                            scores_list = []
                            
                            for colab in TODOS_NOMES:
                                df_colab = df_concluidos[df_concluidos['expedicao'] == colab]
                                vol_total = len(df_colab)
                                
                                if vol_total > 0:
                                    df_colab_tempo = df_tempo_real[df_tempo_real['expedicao'] == colab]
                                    tempo_colab = df_colab_tempo['min_exp'].mean() if not df_colab_tempo.empty else 9999
                                    
                                    # 1. Componente Proatividade/Velocidade (Até 50 pts)
                                    score_vel = 50 if tempo_colab <= media_setor_exp else 30
                                    
                                    # 2. Componente de Carga Crítica (Até 30 pts)
                                    urg_colab = len(df_colab[df_colab['urgente'] == 1])
                                    score_urg = min((urg_colab / vol_total) * 100, 30)
                                    
                                    # 3. Penalidade de Qualidade em Tempo Real (Quarentena)
                                    erros_ativos = len(df_dados[(df_dados['expedicao'] == colab) & (df_dados['precisa_correcao'] == 1) & (df_dados['despachado'] == 0)])
                                    penalidade = erros_ativos * 15
                                    
                                    # Equação Final unificada
                                    nota = 20 + score_vel + score_urg - penalidade
                                    nota = max(0, min(100, round(nota, 1)))
                                    
                                    scores_list.append({'Colaborador': colab, 'Score Performance': nota, 'Erros em Aberto': erros_ativos})
                            
                            if scores_list:
                                df_scores = pd.DataFrame(scores_list).sort_values(by='Score Performance', ascending=False)
                                fig_score = px.bar(df_scores, x='Score Performance', y='Colaborador', orientation='h',
                                                   text='Score Performance', color='Score Performance', color_continuous_scale='RdYlGn')
                                fig_score.update_layout(yaxis={'categoryorder':'total ascending'}, plot_bgcolor="rgba(0,0,0,0)")
                                st.plotly_chart(fig_score, use_container_width=True)
                                st.dataframe(df_scores.style.background_gradient(cmap='RdYlGn', subset=['Score Performance']), hide_index=True, use_container_width=True)
                        else:
                            st.info("Dados de cadência insuficientes para calcular o Score de Elite neste momento.")

                else:
                    # ---------------------------------------------------------
                    # PERFIL OPERACIONAL INDIVIDUAL (MANTIDO INTEGRALMENTE)
                    # ---------------------------------------------------------
                    st.subheader(f"🔎 Perfil Operacional: {visao_selecionada}")
                    try: ausentes = obter_colaboradores_ausentes_hoje()
                    except: ausentes = []
                    
                    if visao_selecionada in ausentes: 
                        st.warning(f"📌 **Status:** Afastamento Legítimo Ativo.", icon="🌴")
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
                    
                    st.markdown("#### ⏱️ Qualidade e Cadência")
                    df_user_tempo_exp = df_tempo_real[df_tempo_real['expedicao'] == visao_selecionada] if not df_tempo_real.empty else pd.DataFrame()
                    df_user_tempo_rev = df_tempo_real[df_tempo_real['revisao'] == visao_selecionada] if not df_tempo_real.empty else pd.DataFrame()
                    
                    cu1, cu2, cu3 = st.columns(3)
                    cu1.metric("Tempo Médio de Elaboração", format_tempo(df_user_tempo_exp['min_exp'].mean()) if not df_user_tempo_exp.empty else "N/A")
                    cu2.metric("Tempo Médio de Conferência", format_tempo(df_user_tempo_rev['min_rev'].mean()) if not df_user_tempo_rev.empty else "N/A")
                    
                    if not df_user_total.empty:
                        parceiros = []
                        parceiros.extend(df_user_exp['revisao'].tolist())
                        parceiros.extend(df_user_rev['expedicao'].tolist())
                        if parceiros:
                            dupla = pd.Series(parceiros).mode()[0]
                            cu3.metric("🤝 Parceiro Mais Frequente", dupla)
                        else: cu3.metric("🤝 Parceiro Operacional", "N/A")
                    else: 
                        cu3.metric("🤝 Parceiro Operacional", "N/A")

# O seu "with" já deve estar na linha 1937, algo como "with sub_ferias:"
       with sub_ferias:
            st.subheader("🗓️ Gestão de Frequência e Escala Presencial")

            # Matriz de Escala Padrão
            ESCALA_PRESENCIAL = {
                "Segunda-Feira": ["André", "Lu Fiorote", "Maurício", "Kátia", "Luanna C"],
                "Terça-Feira": ["André", "Jessyca", "Lu Fiorote", "Kátia", "Elaine", "Luanna C"],
                "Quarta-Feira": ["André", "Jessyca", "Lu Fiorote", "Mariana", "Elaine", "Luanna C"],
                "Quinta-Feira": ["Lu Fiorote", "Maurício", "Mariana", "Kátia", "Elaine", "Luanna C"],
                "Sexta-Feira": ["Jessyca", "Lu Fiorote", "Maurício", "Mariana", "Luanna C"]
            }
            dias_conversao = {0: "Segunda-Feira", 1: "Terça-Feira", 2: "Quarta-Feira", 3: "Quinta-Feira", 4: "Sexta-Feira"}

            # --- PAINEL UNIFICADO ---
            col_esq, col_dir = st.columns([1, 1])

            with col_esq:
                st.markdown("### 🏖️ Registrar Afastamento")
                # Inputs de afastamento (reativos para disparar o alerta)
                usr_afastado = st.selectbox("Colaborador:", TODOS_NOMES, key="af_user_unique")
                t_afastamento = st.selectbox("Tipo de Ausência:", ["Férias", "Recesso", "Atestado Médico"], key="af_tipo_unique")
                d_inicio = st.date_input("Data de Início:", format="DD/MM/YYYY", key="af_ini_unique")
                d_fim = st.date_input("Data de Fim (Retorno):", format="DD/MM/YYYY", key="af_fim_unique")

                # Lógica de Alerta de Apagão
                dias_com_dois = []
                dias_com_um = []
                pode_salvar = True

                if d_inicio <= d_fim:
                    df_af_atual = carregar_afastamentos()
                    periodo = pd.date_range(start=d_inicio, end=d_fim)
                    
                    for dia in periodo:
                        if dia.weekday() in [5, 6]: continue
                        dia_semana_pt = dias_conversao[dia.weekday()]
                        equipe_dia = ESCALA_PRESENCIAL[dia_semana_pt].copy()
                        
                        if usr_afastado in equipe_dia: equipe_dia.remove(usr_afastado)
                        
                        # Remove quem já está afastado no período
                        if not df_af_atual.empty:
                            for _, row in df_af_atual.iterrows():
                                try:
                                    ini = pd.to_datetime(row['data_inicio'], format="%d/%m/%Y").date()
                                    fim = pd.to_datetime(row['data_fim'], format="%d/%m/%Y").date()
                                    if ini <= dia.date() <= fim:
                                        if row['usuario'] in equipe_dia: equipe_dia.remove(row['usuario'])
                                except: pass
                        
                        total = len(equipe_dia)
                        if total == 2: dias_com_dois.append(f"{dia.strftime('%d/%m')} - Restam: {', '.join(equipe_dia)}")
                        elif total <= 1: dias_com_um.append(f"{dia.strftime('%d/%m')} - Resta: {', '.join(equipe_dia) if equipe_dia else 'NENHUM'}")

                if dias_com_dois: st.warning(f"⚠️ **Atenção:** Nos dias abaixo teremos apenas 2 servidores:\n" + "\n".join([f"- {d}" for d in dias_com_dois]))
                if dias_com_um: 
                    st.error(f"🚨 **Risco de Apagão (1 ou 0 servidores):**\n" + "\n".join([f"- {d}" for d in dias_com_um]))
                    pode_salvar = st.checkbox("❗ Confirmo o risco de escala reduzida e desejo prosseguir.", value=False)

                if st.button("🚀 Confirmar e Bloquear", type="primary", use_container_width=True, disabled=not pode_salvar):
                    ok, msg = salvar_afastamento(usr_afastado, d_inicio.strftime("%d/%m/%Y"), d_fim.strftime("%d/%m/%Y"), t_afastamento)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)

            with col_dir:
                st.markdown("### 🔄 Troca de Escala Pontual")
                with st.form("form_troca_escala", clear_on_submit=True):
                    tr_user = st.selectbox("Colaborador:", TODOS_NOMES, key="tr_u_unique")
                    tr_data_original = st.date_input("Dia Original:", key="tr_do_unique")
                    tr_data_nova = st.date_input("Novo Dia Presencial:", key="tr_dn_unique")
                    
                    if st.form_submit_button("Mudar Dia Presencial", type="secondary", use_container_width=True):
                        conn.client.table("trocas_escala").insert({
                            "usuario": tr_user, 
                            "data_original": tr_data_original.strftime('%Y-%m-%d'), 
                            "data_nova": tr_data_nova.strftime('%Y-%m-%d'),
                            "data_registro": datetime.date.today().strftime('%Y-%m-%d')
                        }).execute()
                        st.success("✅ Troca registrada!")
                        time.sleep(1); st.rerun()

            st.markdown("---")
            st.markdown("### 📋 Quadro de Ausências Ativas (Quem está fora hoje)")
            # [Manter aqui o dataframe de visualização das ausências que já tínhamos]
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
# ABA 5: AJUDA E GLOSSÁRIO (MANUAL DEFINITIVO)
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

    with st.expander("✉️ 2.5. Controle de Ofícios (Fábrica de Documentos)"):
        st.markdown("""
        * **Controle:** Cadastro de Jurisdicionados, Não Jurisdicionados e Memorandos. O sistema usa "Autocomplete" para sugerir destinatários recorrentes.
        * **Trava de Segurança:** Processos da Ordinária/Virtual **não podem ser despachados** sem antes ter seus ofícios cadastrados e marcados como despachados (ou o processo ser marcado como "Isento").
        * **Isenção:** Se um processo não requer nenhum documento oficial, clique no botão "🚫 Isentar este processo" para o sistema liberar o despacho final.
        """)

    with st.expander("📄 2.7. Relatório de Expedição (O Checklist Final)"):
        st.markdown("""
        ### O que é esta aba?
        É a sua lista de tarefas dinâmica. Ela mostra tudo o que você já fez no S.A.D.E. e que agora precisa ser efetivamente protocolado (passado a limpo) no sistema oficial do Tribunal.

        ### Como usar na prática:
        1. **Filtre seu Nome:** Selecione seu nome no primeiro campo para carregar seus processos ativos como Expedidor.
        2. **Filtre a Sessão (Opcional):** Para não se perder em uma lista gigante, use o segundo campo para focar apenas em uma sessão específica de cada vez.
        3. **Consulte e Copie:** Abra o menu expansível de cada processo para ver exatamente quais Ofícios e Memorandos você preparou e para quem eles devem ser enviados.
        4. **A Mágica do Sistema:** Após você copiar os dados e realizar o protocolo no Tribunal, volte na Aba 2 e marque aquele processo como "Despachado". **Ele sumirá automaticamente desta lista do Relatório!** O objetivo do seu dia é deixar essa tela vazia.
        """)

    with st.expander("🗄️ 3. Histórico e Auditoria"):
        st.markdown("""
        * **Arquivo:** Sessões 100% concluídas.
        * **Lixeira:** Processos excluídos com registro do motivo.
        * **Histórico de Avisos:** Consulta de comunicados que já rodaram no Letreiro.
        * **Férias e Ausências:** Exibe quem da equipe está afastado. **Regra:** O sistema cruza os dados do cadastro de afastamentos com as datas de distribuição; se um colaborador estiver em período de afastamento, o sistema ignora o nome dele no sorteio automático, evitando que ele receba trabalho enquanto está ausente.
        """)

    with st.expander("⚙️ 4. Gestão Administrativa (Manual de Operações Críticas)"):
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

    with st.expander("🤝 4.5. Entendendo a Matriz de Colaboração (Raio-X de Soft Skills)"):
        st.markdown("""
        ### O que é esse gráfico colorido na Aba 4?
        É um **Gráfico de Calor de Densidade (Heatmap)**. Ele serve para mapear o comportamento prático, o entrosamento e a sinergia da equipe através do cruzamento de dados de produção. Ele ajuda a tirar o "achismo" na hora de gerenciar as pessoas do setor.

        ### Como ler o gráfico:
        * **Quem está na vertical (Eixo Y):** São os nomes de quem atuou como **Expedidor** (quem redigiu os documentos iniciais).
        * **Quem está na horizontal (Eixo X):** São os nomes de quem atuou como **Revisor** (quem conferiu o trabalho).
        * **Os Quadrados Numerados:** Cada quadrado representa o encontro de dois colaboradores. O número indica quantos processos aquela dupla específica finalizou e despachou com sucesso juntos.

        ### O significado das cores (O Termômetro Operacional):
        * **🟣 Tons de Roxo/Azul Escuro (Frio):** Baixo ou nenhum volume de processos finalizados por essa dupla. Indica que eles trabalham pouco juntos ou que o fluxo trava quando se cruzam.
        * **🟡 Tons de Verde Claro/Amarelo (Quente):** Alto volume de processos concluídos com sucesso. É a representação visual de uma **Dupla de Ouro**.

        ### Como usar isso estrategicamente na Gestão:
        1. **Mapeamento de Sinergia:** Quadrados amarelos mostram colaboradores com excelente comunicação e entrosamento natural. Em dias de pico ou crise no Tribunal, direcione as pautas críticas para essas duplas para garantir velocidade.
        2. **Identificação de Gargalos Invisíveis:** Se dois colaboradores produzem muito individualmente, mas o quadrado onde eles se cruzam está sempre escuro, pode haver um desalinhamento de critérios ou de comunicação entre eles que precisa de mediação ou treinamento.
        3. **Líderes Ocultos (O Coringa):** Fique atento ao Revisor que consegue manter quadrados claros/verdes com quase todos os expedidores da equipe. Essa pessoa possui alta adaptabilidade e inteligência emocional, sendo ideal para treinar novos membros ou assumir substituições de liderança.
        """)

    with st.expander("📚 Glossário de Termos"):
        st.markdown("""
        * **Modo Nuclear:** Limpeza total do sistema.
        * **Isenção:** Processo marcado com status 2, dispensado de ofícios.
        * **Quarentena:** Estado de bloqueio administrativo para processos com erros.
        * **Sessão:** Unidade lógica de organização (Lotes de trabalho).
        """)
