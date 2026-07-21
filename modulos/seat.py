# ==============================================================================
# ARQUIVO: modulos/seat.py
# MISSÃO: Setor de Edição e Triagem (Motor NIP, Pauta de Quarta e Distribuição)
# ==============================================================================

import streamlit as st
import pandas as pd
import re
import random
from datetime import datetime
from db_manager import conn, buscar_todos_paginado, carregar_equipes, obter_colaboradores_ausentes_hoje, extrair_texto_arquivo

# ------------------------------------------------------------------------------
# 1. MOTOR NIP — INTELIGÊNCIA ARTIFICIAL DE PURIFICAÇÃO E TELEPROMPTER
# ------------------------------------------------------------------------------
def aplicar_tranca_lgpd(texto):
    """Mascara CPFs no formato ***.XXX.XXX-** respeitando a LGPD."""
    padrao_cpf = r'\b(\d{3})\s*\.?\s*(\d{3})\s*\.?\s*(\d{3})\s*-?\s*(\d{2})\b'
    def mascarar(match):
        g2, g3 = match.group(2), match.group(3)
        return f"***.{g2}.{g3}-**"
    return re.sub(padrao_cpf, mascarar, texto)

def transpor_verbos_liturgicos(texto):
    """Converte verbos do subjuntivo para o infinitivo imperativo litúrgico do TCDF."""
    substituicoes = {
        r'\bconheça\b': 'conhecer',
        r'\bdetermine\b': 'determinar',
        r'\bdê ciência\b': 'dar ciência',
        r'\bautorize\b': 'autorizar',
        r'\breferende\b': 'referendar',
        r'\bacolha\b': 'acolher',
        r'\baprove\b': 'aprovar',
        r'\bconsidere\b': 'considerar',
        r'\bencaminhe\b': 'encaminhar',
        r'\bnotifique\b': 'notificar',
        r'\balerte\b': 'alertar',
        r'\bMPjTCDF\b': 'Ministério Público junto à Corte - MPjTCDF',
        r'\bRELATOR\b': 'Relator'
    }
    texto_trabalhado = texto
    for padrao, substituto in substituicoes.items():
        texto_trabalhado = re.sub(padrao, substituto, texto_trabalhado, flags=re.IGNORECASE)
    return texto_trabalhado

def aplicar_destaque_visual(texto):
    """Aplica negrito em prazos e termos críticos para o leitor do Plenário."""
    termos_destaque = [
        r'(prazo de \d+.*?dias(?: úteis)?)',
        r'\b(suspenda|suspensão)\b',
        r'\b(certame|licitação|pregão)\b',
        r'\b(imediato|imediatamente)\b',
        r'\b(medida cautelar|cautelarmente)\b'
    ]
    texto_destacado = texto
    for termo in termos_destaque:
        texto_destacado = re.sub(f'({termo})', r'**\1**', texto_destacado, flags=re.IGNORECASE)
    return texto_destacado.replace('****', '**')

def processar_motor_nip(texto_bruto):
    """
    Árvore de Decisão Trifásica do Motor NIP:
    Tipo 1: Voto Comum | Tipo 2: Referendo Monocrático | Tipo 3: Sustentação Oral
    """
    if not texto_bruto or texto_bruto.strip() == "":
        return "", "VAZIO", []

    texto_limpo = texto_bruto.strip()
    
    # --------------------------------------------------------------------------
    # VERIFICAÇÃO TIPO 3: SUSTENTAÇÃO ORAL (BYPASS TOTAL DE EDIÇÃO)
    # --------------------------------------------------------------------------
    if re.search(r'SUSTENTAÇÃO ORAL', texto_limpo, re.IGNORECASE) and re.search(r'É o relatório\.', texto_limpo, re.IGNORECASE):
        if not re.search(r'\b(VOTO|DECIDO)\b', texto_limpo[(len(texto_limpo)-500):], re.IGNORECASE):
            return texto_limpo, "TIPO_3_SUSTENTACAO", ["SUSTENTACAO_ORAL"]

    # --------------------------------------------------------------------------
    # VERIFICAÇÃO TIPO 2: DESPACHO SINGULAR / REFERENDO MONOCRÁTICO
    # --------------------------------------------------------------------------
    e_referendo = re.search(r'(referende o(?: mencionado)? Despacho Singular|ad referendum[a-z\s,]*DECIDO|referendar o Despacho Singular)', texto_limpo, re.IGNORECASE)
    
    if e_referendo:
        match_despacho = re.search(r'(?:DECIDO|decidir)(.*?)(?:Relatei\.|VOTO)', texto_limpo, re.DOTALL | re.IGNORECASE)
        recheio_despacho = match_despacho.group(1).strip() if match_despacho else ""
        
        recheio_despacho = re.sub(r'\s+', ' ', recheio_despacho)
        recheio_despacho = aplicar_tranca_lgpd(recheio_despacho)
        recheio_despacho = aplicar_destaque_visual(recheio_despacho)
        
        match_voto_extra = re.search(r'VOTO no sentido de que.*?:(.*)$', texto_limpo, re.DOTALL | re.IGNORECASE)
        voto_final = match_voto_extra.group(1).strip() if match_voto_extra else ""
        
        itens_extras = [i.strip() for i in re.split(r'\b[I|V|X]+[\s|-]+|\b\d+\)\s*', voto_final) if i.strip() and not re.search(r'referende o Despacho', i, re.IGNORECASE)]
        
        if len(itens_extras) > 0:
            preambulo = "**O Tribunal, por unanimidade, de acordo com o voto do Relator, decidiu:** "
            item_1 = f"**1)** referendar o mencionado despacho singular, proferido nos seguintes termos: \"{recheio_despacho}\"; "
            
            itens_formatados = []
            for idx, item in enumerate(itens_extras, start=2):
                item_transp = transpor_verbos_liturgicos(item)
                item_transp = aplicar_tranca_lgpd(item_transp)
                item_transp = re.sub(r'\s+', ' ', item_transp)
                itens_formatados.append(f"**{idx})** {item_transp.rstrip(';')}; ")
                
            teleprompter = preambulo + item_1 + "".join(itens_formatados)
            return teleprompter.strip(), "TIPO_2_COMPOSTO", []
        else:
            preambulo = "**O Tribunal, por unanimidade, referendou o mencionado despacho singular, proferido nos seguintes termos:** "
            teleprompter = f"{preambulo}\"{recheio_despacho}\""
            return teleprompter.strip(), "TIPO_2_SIMPLES", []

    # --------------------------------------------------------------------------
    # VERIFICAÇÃO TIPO 1: VOTO COMUM DE PLENÁRIO (BUSCA REVERSA)
    # --------------------------------------------------------------------------
    match_voto = re.search(r'(?:VOTO no sentido de que|ACORDAM|decidiu:)(.*?)$', texto_limpo, re.DOTALL | re.IGNORECASE)
    bloco_deliberativo = match_voto.group(1).strip() if match_voto else texto_limpo
    
    bloco_deliberativo = transpor_verbos_liturgicos(bloco_deliberativo)
    bloco_deliberativo = aplicar_tranca_lgpd(bloco_deliberativo)
    bloco_deliberativo = aplicar_destaque_visual(bloco_deliberativo)
    bloco_deliberativo = re.sub(r'\s+', ' ', bloco_deliberativo)
    bloco_deliberativo = re.sub(r'\b([I|V|X]+)\s*[\.-]\s*', r'**\1 -** ', bloco_deliberativo)
    
    preambulo = "**O Tribunal, por unanimidade, de acordo com o voto do Relator, decidiu:** "
    if not bloco_deliberativo.startswith("**I"):
        teleprompter = preambulo + "**I -** " + bloco_deliberativo
    else:
        teleprompter = preambulo + bloco_deliberativo
        
    return teleprompter.strip(), "TIPO_1_COMUM", []

def varrer_regras_inteligentes(texto):
    """Cruza o texto editado com a base de regras do GAB para detectar Urgência ou SERCON."""
    alertas = []
    try:
        regras = buscar_todos_paginado("regras_palavras_chave")
        if not regras: return alertas
        
        texto_minusculo = str(texto).lower()
        for r in regras:
            if not r.get("ativo", True): continue
            palavra = str(r["palavra_chave"]).lower().strip()
            if palavra and palavra in texto_minusculo:
                alertas.append({
                    "categoria": r["categoria"],
                    "palavra": palavra,
                    "setor_alvo": r["setor_alvo"]
                })
    except Exception as e:
        st.error(f"Erro no radar de palavras-chave: {e}")
    return alertas

# ------------------------------------------------------------------------------
# 2. INTERFACE OPERACIONAL — ABA 1: OFICINA NIP (EDIÇÃO EXPANDIDA 700PX)
# ------------------------------------------------------------------------------
def renderizar_oficina_nip():
    st.markdown("### 🛠️ Oficina NIP — Núcleo de Integração Processual")
    st.caption("O Motor NIP aplica Busca Reversa, corta relatórios antigos, transpõe verbos e aplica a tranca LGPD em milissegundos.")
    
    col_up, col_info = st.columns([1.5, 1])
    with col_up:
        arquivo = st.file_uploader("📂 Carregar Documento (PDF, DOCX ou TXT):", type=["pdf", "docx", "txt"], key="nip_file_upload")
    with col_info:
        st.markdown("<br>", unsafe_allow_html=True)
        num_processo = st.text_input("Nº do Processo / Relator:", placeholder="Ex: 00600-00006383/2026-07-e - GCRR", key="nip_proc_val")
        btn_executar = st.button("🚀 Processar Purificação Litúrgica", type="primary", use_container_width=True)
        
    if btn_executar:
        if not arquivo:
            st.error("🚨 Nenhum arquivo selecionado. Por favor, carregue o PDF ou DOCX do processo.")
            return
        if not num_processo.strip():
            st.warning("⚠️ Informe o número do processo para cadastrar a edição.")
            return
            
        with st.spinner("🧠 Executando Busca Reversa, Tranca LGPD e Transposição de Verbos..."):
            try:
                texto_bruto = extrair_texto_arquivo(arquivo)
                if not texto_bruto:
                    st.error("🚨 Não foi possível ler o arquivo. Verifique se o documento não está protegido por senha ou digitalizado sem OCR.")
                    return
                
                texto_puro, tipo_doc, flags_nip = processar_motor_nip(texto_bruto)
                alertas_radar = varrer_regras_inteligentes(texto_puro)
                
                st.session_state.nip_original = texto_bruto
                st.session_state.nip_editado = texto_puro
                st.session_state.nip_tipo = tipo_doc
                st.session_state.nip_alertas = alertas_radar
                st.session_state.nip_num_proc = num_processo.strip()
                st.session_state.nip_ativo = True
                
                st.success(f"✨ Processamento Concluído! Classificação automática: **{tipo_doc}**")
            except Exception as e:
                st.error(f"🚨 Erro interno no processamento NIP: {e}")
                return

    # EXIBIÇÃO COMPARATIVA EM TELA CHEIA (ALTURA DE 700PX)
    if st.session_state.get("nip_ativo"):
        st.markdown("---")
        
        # Alertas de Roteamento (Encruzilhada SERCON vs SEXP ou Urgência)
        alertas = st.session_state.get("nip_alertas", [])
        if alertas:
            setores_dest = [a["setor_alvo"] for a in alertas]
            if "SERCON" in setores_dest:
                st.error("🚨 **GATILHO DE EXCLUSÃO MÚTUA ATIVADO:** O radar identificou matéria contábil (Cobrança/TCE/Multa). Este processo deverá ser encaminhado **EXCLUSIVAMENTE para a SERCON**.")
            elif "SEAT" in setores_dest or any(a["categoria"] == "URGENCIA" for a in alertas):
                st.warning("⚡ **ALERTA DE URGÊNCIA:** Prazos curtos ou liminar detectados. O processo receberá selo prioritário na distribuição.")
                
        col_orig, col_edit = st.columns(2)
        with col_orig:
            st.markdown("#### 📄 Texto Bruto Extraído (Original)")
            st.text_area("Confira o teor antes do corte do relatório:", value=st.session_state.get("nip_original", ""), height=700, key="txt_nip_original_700")
            
        with col_edit:
            st.markdown("#### 📺 Teleprompter Purificado (Editado)")
            texto_editado_atual = st.text_area("Faça a conferência fina ou ajuste manual na liturgia:", value=st.session_state.get("nip_editado", ""), height=700, key="txt_nip_editado_700")
            
            # Botão para salvar alterações manuais na conferência
            col_save, col_down = st.columns([1, 1])
            with col_save:
                if st.button("💾 Confirmar Edição na Memória", type="primary", use_container_width=True):
                    st.session_state.nip_editado = texto_editado_atual
                    st.success("✔ Ajustes manuais gravados!")
            with col_down:
                st.download_button(
                    "📥 Baixar Teleprompter (TXT)",
                    data=texto_editado_atual,
                    file_name=f"VOTO_EDITADO_{st.session_state.get('nip_num_proc', 'PROCESSO').replace('/', '_')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

# ------------------------------------------------------------------------------
# 3. INTERFACE OPERACIONAL — ABA 2: DISTRIBUIÇÃO EQUALITÁRIA & PAUTA
# ------------------------------------------------------------------------------
def renderizar_pauta_ativa():
    st.markdown("### 📋 Pauta Ativa e Distribuição Equalitária sem Auto-Revisão")
    st.caption("Selecione os colaboradores presentes na sessão e distribua a pauta com divisão matemática exata. Marque as caixas para concluir tarefas.")
    
    # BOX 1: GERADOR DE DISTRIBUIÇÃO EM LOTE EQUALITÁRIA
    with st.expander("⚖️ Gerar Distribuição Equalitária de Lote para a Sessão", expanded=False):
        _, _, todos_colabs = carregar_equipes()
        ausentes = obter_colaboradores_ausentes_hoje()
        disponiveis = [c for c in todos_colabs if c not in ausentes]
        
        st.markdown("#### 1️⃣ Selecione os Colaboradores Participantes do Rodízio Hoje:")
        colabs_selecionados = st.multiselect("Equipe Escalada para Edição e Revisão:", disponiveis, default=disponiveis, key="multi_colab_dist")
        
        if len(colabs_selecionados) < 2:
            st.warning("⚠️ Selecione pelo menos 2 colaboradores para garantir a regra de Não Auto-Revisão (A edita, B/C/D revisa).")
        else:
            st.markdown("#### 2️⃣ Inserir Processos para Distribuição:")
            with st.form("form_distribuicao_igualitaria"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    lote_txt = st.text_area("Lista de Processos (Cole 1 número de processo por linha):", placeholder="00600-00001111/2026-00\n00600-00002222/2026-00\n00600-00003333/2026-00", height=150)
                with c2:
                    rel_lote = st.selectbox("Relator Predominante:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT"])
                    ses_lote = st.selectbox("Sessão Alvo:", ["Sessão Ordinária", "Ordinária Virtual", "Sessão Administrativa", "Sessão Reservada"])
                    urg_lote = st.checkbox("🚨 Todos são Urgentes?")
                    
                if st.form_submit_button("⚖️ Executar Distribuição Equalitária", type="primary"):
                    linhas_processos = [p.strip() for p in lote_txt.split("\n") if p.strip()]
                    if not linhas_processos:
                        st.warning("⚠️ Cole pelo menos 1 número de processo na caixa de texto.")
                    else:
                        num_colabs = len(colabs_selecionados)
                        novos_registros = []
                        
                        for idx, proc in enumerate(linhas_processos):
                            # Sorteio Equalitário circular (Garante divisão exata)
                            editor_atribuido = colabs_selecionados[idx % num_colabs]
                            
                            # Exclusão Mútua: O Revisor NUNCA pode ser o próprio Editor
                            opcoes_revisor = [c for c in colabs_selecionados if c != editor_atribuido]
                            revisor_atribuido = random.choice(opcoes_revisor)
                            
                            novos_registros.append({
                                "processo": proc,
                                "relator": rel_lote,
                                "sessao": ses_lote,
                                "editor": editor_atribuido,
                                "revisor": revisor_atribuido,
                                "editado_ok": 0,
                                "revisado_ok": 0,
                                "urgente": 1 if urg_lote else 0,
                                "status": "Em Edição",
                                "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                            })
                            
                        try:
                            conn.table("pauta_seat").insert(novos_registros).execute()
                            st.success(f"✨ Sucesso! {len(novos_registros)} processos foram distribuídos com perfeição entre os {num_colabs} colaboradores.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"🚨 Erro na gravação do lote no Supabase: {e}")

    st.markdown("---")
    st.markdown("#### 📋 Pauta de Julgamento (Controle com Checagem em Tempo Real)")
    
    try:
        dados_seat = buscar_todos_paginado("pauta_seat")
        if not dados_seat:
            st.info("✨ Nenhuma pendência na pauta ativa da SEAT no momento.")
            return
            
        df_seat = pd.DataFrame(dados_seat)
        df_ativos = df_seat[~df_seat["status"].isin(["Revisado - Enviado SEXP", "Concluído"])]
        
        if df_ativos.empty:
            st.success("✨ Todos os processos da SEAT já foram editados, revisados e roteados para a SEXP!")
            return
            
        st.markdown(f"**Volume em Edição/Revisão:** `{len(df_ativos)} processo(s)`")
        
        # TABELA ERGONÔMICA COM CAIXAS DE SELEÇÃO INSTANTÂNEAS
        for idx, row in df_ativos.iterrows():
            id_reg = row.get("id")
            e_urgente = row.get("urgente", 0) == 1
            edit_ok = row.get("editado_ok", 0) == 1
            rev_ok = row.get("revisado_ok", 0) == 1
            
            with st.container(border=True):
                c_proc, c_resp, c_check_ed, c_check_rev, c_gatilho = st.columns([2.2, 1.8, 1.2, 1.2, 1.6])
                
                with c_proc:
                    badge = "🚨 **[URGENTE]** <br>" if e_urgente else ""
                    st.markdown(f"{badge}**`{row.get('processo', 'S/N')}`**", unsafe_allow_html=True)
                    st.caption(f"Relator: **{row.get('relator', 'GAB')}** | {row.get('sessao', 'Ordinária')}")
                    
                with c_resp:
                    st.markdown(f"📝 **Editor:** `{row.get('editor', 'N/A')}`")
                    st.markdown(f"🛡️ **Revisor:** `{row.get('revisor', 'N/A')}`")
                    
                with c_check_ed:
                    st.markdown("<br>", unsafe_allow_html=True)
                    # Checkbox interativo de Edição
                    nova_edicao = st.checkbox("✔ Editado", value=edit_ok, key=f"chk_ed_{id_reg}")
                    if nova_edicao != edit_ok:
                        conn.table("pauta_seat").update({
                            "editado_ok": 1 if nova_edicao else 0,
                            "status": "Em Revisão" if nova_edicao else "Em Edição"
                        }).eq("id", id_reg).execute()
                        st.rerun()
                        
                with c_check_rev:
                    st.markdown("<br>", unsafe_allow_html=True)
                    # Checkbox interativo de Revisão
                    nova_revisao = st.checkbox("✔ Revisado", value=rev_ok, key=f"chk_rev_{id_reg}", disabled=not edit_ok)
                    if nova_revisao != rev_ok:
                        conn.table("pauta_seat").update({
                            "revisado_ok": 1 if nova_revisao else 0,
                            "status": "Aguardando Envio SEXP" if nova_revisao else "Em Revisão"
                        }).eq("id", id_reg).execute()
                        st.rerun()
                        
                with c_gatilho:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if rev_ok:
                        if st.button("🚀 Enviar p/ SEXP", key=f"btn_send_{id_reg}", type="primary", use_container_width=True):
                            # Gatilho de Ponte Automática SEAT -> SEXP
                            conn.table("pauta_seat").update({"status": "Revisado - Enviado SEXP"}).eq("id", id_reg).execute()
                            
                            try:
                                exp, revs, todos = carregar_equipes()
                                aus = obter_colaboradores_ausentes_hoje()
                                disp_exp = [c for c in exp if c not in aus] if exp else ["André"]
                                disp_rev = [c for c in revs if c not in aus] if revs else ["Elaine"]
                                
                                A_exp = random.choice(disp_exp)
                                B_rev = random.choice([r for r in disp_rev if r != A_exp]) if len(disp_rev) > 1 else A_exp
                                
                                ponte_sexp = {
                                    "processo": row.get("processo"),
                                    "relator": row.get("relator"),
                                    "sessao": row.get("sessao"),
                                    "expedidor": A_exp,
                                    "revisor": B_rev,
                                    "status": "Aguardando Homologação Chefia",
                                    "urgente": row.get("urgente", 0),
                                    "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                                }
                                conn.table("pauta_sexp").insert(ponte_sexp).execute()
                                st.success("🚀 Roteado para o S.A.D.E.!")
                            except Exception as e:
                                st.error(f"Erro na ponte SEXP: {e}")
                            st.rerun()
                    else:
                        st.caption("⏳ Conclua a edição e revisão para habilitar o envio.")

    except Exception as e:
        st.error(f"🚨 Erro na leitura da Pauta da SEAT: {e}")

# ------------------------------------------------------------------------------
# 4. INTERFACE OPERACIONAL — ABA 3: DESPACHOS SINGULARES & SUSTENTAÇÃO ORAL
# ------------------------------------------------------------------------------
def renderizar_pauta_quarta():
    st.markdown("### 📅 Pauta de Quarta-Feira (Despachos Singulares & Sustentação Oral)")
    st.caption("Decisões monocráticas (qui-ter) e defesas orais agendadas. Entram automaticamente na pauta prioritária do Plenário.")
    
    col_ds, col_so = st.columns(2)
    with col_ds:
        with st.container(border=True):
            st.markdown("#### 📜 Despachos Singulares (DS)")
            with st.form("form_ds_seat"):
                ds_num = st.text_input("Nº do Processo (DS):", placeholder="00600-00000000/2026-00")
                ds_rel = st.selectbox("Relator do Despacho:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT"], key="rel_ds_seat")
                ds_stat = st.radio("Status no Plenário:", ["✅ Confirmado em Pauta", "🚫 Retirado / Adiado"], horizontal=True)
                if st.form_submit_button("📌 Cadastrar Despacho Singular", type="primary"):
                    if ds_num.strip():
                        try:
                            reg = {
                                "processo": ds_num.strip(),
                                "relator": ds_rel,
                                "tipo_pauta": "Despacho Singular",
                                "status": "Confirmado" if "Confirmado" in ds_stat else "Retirado",
                                "sessao_alvo": "Próxima Quarta-Feira",
                                "data_registro": datetime.now().strftime("%d/%m/%Y")
                            }
                            conn.table("pauta_quarta").insert(reg).execute()
                            st.success("Despacho Singular inserido na pauta de Quarta!")
                        except Exception as e:
                            st.error(f"Erro ao salvar: {e}")
                    else:
                        st.warning("Informe o processo.")

    with col_so:
        with st.container(border=True):
            st.markdown("#### 🗣️ Sustentações Orais (SO)")
            with st.form("form_so_seat"):
                so_num = st.text_input("Nº do Processo (SO):", placeholder="00600-00000000/2026-00")
                so_adv = st.text_input("Advogado / Orador:", placeholder="Dr(a). Nome do Advogado")
                so_dt = st.date_input("Data da Sessão do Plenário:")
                so_stat = st.radio("Status do Orador:", ["✅ Confirmado (Pauta Prioritária)", "🚫 Retirado"], horizontal=True)
                if st.form_submit_button("🎙️ Agendar Sustentação Oral", type="primary"):
                    if so_num.strip():
                        try:
                            reg = {
                                "processo": so_num.strip(),
                                "relator": so_adv if so_adv else "Orador não informado",
                                "tipo_pauta": "Sustentação Oral",
                                "status": "Confirmado" if "Confirmado" in so_stat else "Retirado",
                                "sessao_alvo": so_dt.strftime("%d/%m/%Y"),
                                "data_registro": datetime.now().strftime("%d/%m/%Y")
                            }
                            conn.table("pauta_quarta").insert(reg).execute()
                            st.success("Sustentação Oral agendada com prioridade!")
                        except Exception as e:
                            st.error(f"Erro ao salvar: {e}")
                    else:
                        st.warning("Informe o processo.")

    st.markdown("---")
    st.markdown("#### 👁️ Painel Consolidado de Quarta-Feira")
    try:
        dados_q = buscar_todos_paginado("pauta_quarta")
        if dados_q:
            df_q = pd.DataFrame(dados_q)
            st.dataframe(df_q[["processo", "tipo_pauta", "relator", "sessao_alvo", "status"]], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum Despacho Singular ou Sustentação Oral catalogado para a próxima sessão.")
    except Exception:
        st.info("Tabela de Quarta-Feira aguardando registros.")

# ------------------------------------------------------------------------------
# 5. INTERFACE OPERACIONAL — ABA 4: ESCALA ALTERNADA DE DUPLAS (DODF)
# ------------------------------------------------------------------------------
def renderizar_tab_publicacao():
    st.markdown("### 📰 Escala Alternada de Duplas para Publicação no DODF")
    st.caption("O gerador intercala rigorosamente a equipe em duplas alternando entre as sessões de Quarta-Feira e publicações de Sexta-Feira.")
    
    col_gerar, col_tabela = st.columns([1.2, 1.8])
    with col_gerar:
        with st.container(border=True):
            st.markdown("#### 🔄 Gerar Novo Ciclo Mensal")
            mes_alvo = st.selectbox("Mês de Referência:", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])
            
            if st.button("🚀 Gerar Escala Alternada (Quarta / Sexta)", type="primary", use_container_width=True):
                try:
                    _, _, todos = carregar_equipes()
                    ausentes = obter_colaboradores_ausentes_hoje()
                    ativos = [c for c in todos if c not in ausentes]
                    
                    if len(ativos) < 2:
                        st.warning("⚠️ É necessário pelo menos 2 colaboradores ativos para formar duplas no DODF.")
                    else:
                        # Algoritmo de revezamento alternado
                        escala_gerada = []
                        dias_ciclo = ["Quarta-Feira (1ª Sessão)", "Sexta-Feira (1ª Publicação)", "Quarta-Feira (2ª Sessão)", "Sexta-Feira (2ª Publicação)", "Quarta-Feira (3ª Sessão)", "Sexta-Feira (3ª Publicação)"]
                        
                        num_a = len(ativos)
                        for idx, dia in enumerate(dias_ciclo):
                            colab1 = ativos[(idx * 2) % num_a]
                            colab2 = ativos[((idx * 2) + 1) % num_a]
                            escala_gerada.append({
                                "mes": mes_alvo,
                                "dia_semana": dia,
                                "dupla": f"{colab1} & {colab2}"
                            })
                            
                        conn.table("escala_publicacao").insert(escala_gerada).execute()
                        st.success(f"✨ Escala de {mes_alvo} gerada e revezada com sucesso!")
                        st.rerun()
                except Exception as e:
                    st.error(f"🚨 Erro ao gerar escala: {e}")
                    
    with col_tabela:
        st.markdown("#### 📋 Escala Ativa do DODF")
        try:
            dados_esc = buscar_todos_paginado("escala_publicacao")
            if dados_esc:
                df_esc = pd.DataFrame(dados_esc)
                st.dataframe(df_esc[["mes", "dia_semana", "dupla"]], use_container_width=True, hide_index=True)
                
                # Opção para limpar escala anterior
                if st.button("🗑️ Limpar Toda a Escala", type="secondary"):
                    for item in dados_esc:
                        conn.table("escala_publicacao").delete().eq("id", item["id"]).execute()
                    st.rerun()
            else:
                st.info("Nenhuma escala de publicação gerada para este mês.")
        except Exception as e:
            st.error(f"Erro ao ler escala: {e}")

# ------------------------------------------------------------------------------
# 6. FUNÇÃO PRINCIPAL DO MÓDULO (PONTO DE ENTRADA DO ROTEADOR)
# ------------------------------------------------------------------------------
def run():
    st.markdown("<div class='main-header'>📝 SEAT — Setor de Edição e Triagem</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Purificação Litúrgica de Votos (Motor NIP), Pauta do Plenário e Distribuição Equalitária sem Auto-Revisão</div>", unsafe_allow_html=True)
    
    t_nip, t_ativa, t_quarta, t_pub, t_ferias = st.tabs([
        "🛠️ Oficina NIP (Tela 700px)",
        "📋 Pauta Ativa & Distribuição",
        "📅 Pauta de Quarta (DS / SO)",
        "📰 Escala DODF (Quarta/Sexta)",
        "🏝️ Afastamentos (Leitura)"
    ])
    
    with t_nip:
        renderizar_oficina_nip()
    with t_ativa:
        renderizar_pauta_ativa()
    with t_quarta:
        renderizar_pauta_quarta()
    with t_pub:
        renderizar_tab_publicacao()
    with t_ferias:
        st.markdown("### 🏝️ Quadro Visual de Afastamentos (Modo Leitura)")
        st.caption("Colaboradores listados abaixo são automaticamente excluídos do sorteio equalitário da Pauta Ativa.")
        try:
            afast = buscar_todos_paginado("afastamentos")
            if afast:
                df_af = pd.DataFrame(afast)
                st.dataframe(df_af[["usuario", "motivo", "data_inicio", "data_fim"]], use_container_width=True, hide_index=True)
            else:
                st.success("✨ Toda a equipe da SEAT está ativa e disponível para o rodízio!")
        except Exception:
            st.info("Quadro de férias sem registros ativos no momento.")

if __name__ == "__main__":
    run()
