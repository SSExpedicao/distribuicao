# ==============================================================================
# ARQUIVO: modulos/seat.py
# MISSÃO: Setor de Edição e Triagem (Motor NIP, Pauta de Quarta e Distribuição)
# ==============================================================================

import streamlit as st
import pandas as pd
import re
import random
from datetime import datetime, timedelta
from db_manager import conn, buscar_todos_paginado, carregar_equipes, obter_colaboradores_ausentes_hoje

# ------------------------------------------------------------------------------
# 1. MOTOR NIP — INTELIGÊNCIA ARTIFICIAL DE PURIFICAÇÃO E TELEPROMPTER
# ------------------------------------------------------------------------------
def aplicar_tranca_lgpd(texto):
    """Mascara CPFs no formato ***.XXX.XXX-** respeitando a LGPD."""
    # Regex flexível para capturar CPFs com ou sem pontos/espaços errados
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
    # Limpa marcações duplas de negrito que possam acontecer
    return texto_destacado.replace('****', '**')

def processar_motor_nip(texto_bruto):
    """
    Árvore de Decisão Trifásica do Motor NIP:
    Tipo 1: Voto Comum | Tipo 2: Referendo Monocrático | Tipo 3: Sustentação Oral
    """
    if not texto_bruto or texto_bruto.strip() == "":
        return "", "VAZIO", []

    texto_limpo = texto_bruto.strip()
    gatilhos_detectados = []
    
    # --------------------------------------------------------------------------
    # VERIFICAÇÃO TIPO 3: SUSTENTAÇÃO ORAL (BYPASS TOTAL DE EDIÇÃO)
    # --------------------------------------------------------------------------
    if re.search(r'SUSTENTAÇÃO ORAL', texto_limpo, re.IGNORECASE) and re.search(r'É o relatório\.', texto_limpo, re.IGNORECASE):
        if not re.search(r'\b(VOTO|DECIDO)\b', texto_limpo[(len(texto_limpo)-500):], re.IGNORECASE):
            return texto_limpo, "TIPO_3_SUSTENTACAO", ["SUSTENTACAO_ORAL"]

    # --------------------------------------------------------------------------
    # VERIFICAÇÃO TIPO 2: DESPACHO SINGULAR / REFERENDO MONOCRÁTICO
    # --------------------------------------------------------------------------
    e_referendo = re.search(r'(referende o Despacho Singular|ad referendum|Despacho Singular nº)', texto_limpo, re.IGNORECASE)
    
    if e_referendo:
        # Extrai o recheio do Despacho (entre DECIDO e VOTO/Relatei)
        match_despacho = re.search(r'(?:DECIDO|decidir)(.*?)(?:Relatei\.|VOTO)', texto_limpo, re.DOTALL | re.IGNORECASE)
        recheio_despacho = match_despacho.group(1).strip() if match_despacho else ""
        
        # Limpa o recheio sem quebrar os algarismos romanos internos
        recheio_despacho = re.sub(r'\s+', ' ', recheio_despacho)
        recheio_despacho = aplicar_tranca_lgpd(recheio_despacho)
        recheio_despacho = aplicar_destaque_visual(recheio_despacho)
        
        # Verifica se há ordens complementares no Voto (Referendo Composto vs Simples)
        match_voto_extra = re.search(r'VOTO no sentido de que.*?:(.*)$', texto_limpo, re.DOTALL | re.IGNORECASE)
        voto_final = match_voto_extra.group(1).strip() if match_voto_extra else ""
        
        # Se tiver itens além de referendar, é Tipo 2 Composto (numeração arábica 1), 2))
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
            # Referendo Simples: Preâmbulo no passado, sem numeração externa
            preambulo = "**O Tribunal, por unanimidade, referendou o mencionado despacho singular, proferido nos seguintes termos:** "
            teleprompter = f"{preambulo}\"{recheio_despacho}\""
            return teleprompter.strip(), "TIPO_2_SIMPLES", []

    # --------------------------------------------------------------------------
    # VERIFICAÇÃO TIPO 1: VOTO COMUM DE PLENÁRIO (BUSCA REVERSA)
    # --------------------------------------------------------------------------
    # Corta o relatório buscando a âncora final de deliberação
    match_voto = re.search(r'(?:VOTO no sentido de que|ACORDAM|decidiu:)(.*?)$', texto_limpo, re.DOTALL | re.IGNORECASE)
    bloco_deliberativo = match_voto.group(1).strip() if match_voto else texto_limpo
    
    # Transposição litúrgica e limpeza LGPD
    bloco_deliberativo = transpor_verbos_liturgicos(bloco_deliberativo)
    bloco_deliberativo = aplicar_tranca_lgpd(bloco_deliberativo)
    bloco_deliberativo = aplicar_destaque_visual(bloco_deliberativo)
    
    # Formatação contínua (Teleprompter sem parágrafos)
    bloco_deliberativo = re.sub(r'\s+', ' ', bloco_deliberativo)
    
    # Converte incisos Romanos externos em formatação padrão em negrito
    bloco_deliberativo = re.sub(r'\b([I|V|X]+)\s*[\.-]\s*', r'**\1 -** ', bloco_deliberativo)
    
    preambulo = "**O Tribunal, por unanimidade, de acordo com o voto do Relator, decidiu:** "
    if not bloco_deliberativo.startswith("**I"):
        teleprompter = preambulo + "**I -** " + bloco_deliberativo
    else:
        teleprompter = preambulo + bloco_deliberativo
        
    return teleprompter.strip(), "TIPO_1_COMUM", []

# ------------------------------------------------------------------------------
# 2. RADAR INTELIGENTE DE PALAVRAS-CHAVE E DESVIOS DE ROTA
# ------------------------------------------------------------------------------
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
# 3. INTERFACE OPERACIONAL — ABA 1: OFICINA NIP (EDIÇÃO & TRIAGEM)
# ------------------------------------------------------------------------------
def renderizar_oficina_nip():
    st.markdown("### 🛠️ Oficina NIP — Núcleo de Integração Processual")
    st.caption("Cole o texto bruto do voto ou importe o documento. O Motor NIP purificará a liturgia e fará a triagem de destino em milissegundos.")
    
    col_in, col_out = st.columns([1, 1])
    
    with col_in:
        st.markdown("#### 📥 Entrada de Documento Bruto")
        num_proc_nip = st.text_input("Nº do Processo / Relator:", placeholder="Ex: 00600-00006383/2026-07-e - GCRR", key="nip_proc")
        texto_bruto = st.text_area("Texto do Relatório e Voto (Cole aqui o conteúdo do PDF):", height=380, placeholder="Cole aqui o texto extraído do sistema e-TCDF...")
        btn_processar = st.button("⚡ Processar no Motor NIP", type="primary", use_container_width=True)
        
    with col_out:
        st.markdown("#### 📤 Teleprompter Contínuo (Pronto para o Plenário)")
        
        if btn_processar and texto_bruto:
            texto_editado, tipo_doc, flags = processar_motor_nip(texto_bruto)
            
            # 1. BYPASS DE SUSTENTAÇÃO ORAL
            if tipo_doc == "TIPO_3_SUSTENTACAO":
                st.warning("🗣️ **SUSTENTAÇÃO ORAL DETECTADA!**")
                st.info("Este documento é estritamente expositivo e não requer edição litúrgica nem corte de relatório. Ele deve ser roteado imediatamente para a Pauta Prioritária de Urgências.")
                
                with st.form("form_urg_sustentacao"):
                    proc_alvo = st.text_input("Confirmar Nº do Processo:", value=num_proc_nip)
                    if st.form_submit_button("🚀 Enviar Direto para Pauta de Urgências", type="primary"):
                        try:
                            novo_urgente = {
                                "processo": proc_alvo.strip() if proc_alvo else "Não informado",
                                "relator": "GAB",
                                "sessao": "Sessão Ordinária",
                                "urgente": 1,
                                "status": "Aprovado - Sustentação Oral",
                                "observacao": "🗣️ Sustentação Oral agendada - Pauta Prioritária",
                                "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                            }
                            conn.client.table("pauta_seat").insert(novo_urgente).execute()
                            st.success("✅ Processo catalogado na Pauta de Urgências com sucesso!")
                        except Exception as e:
                            st.error(f"Erro ao salvar urgência: {e}")
                return

            # 2. EXIBIÇÃO DO TELEPROMPTER PURIFICADO
            badge_tipo = {"TIPO_1_COMUM": "🔵 Voto Comum de Plenário", "TIPO_2_COMPOSTO": "🟣 Referendo Monocrático (Composto)", "TIPO_2_SIMPLES": "🟣 Referendo Monocrático (Simples)"}.get(tipo_doc, "⚪ Documento Processado")
            st.markdown(f"**Classificação Automática:** `{badge_tipo}`")
            
            with st.container(border=True):
                st.markdown(texto_editado)
                
            st.text_area("Cópia Rápida (Texto Limpo para Área de Transferência):", value=texto_editado, height=150)
            
            # 3. RADAR DE ALERTAS E DESVIOS DE ROTA (URGÊNCIA OU SERCON)
            alertas_encontrados = varrer_regras_inteligentes(texto_editado)
            
            if alertas_encontrados:
                st.markdown("---")
                for al in alertas_encontrados:
                    if al["setor_alvo"] == "SERCON" or al["categoria"] == "SERCON":
                        st.error(f"⚖️ **ALERTA DE DESVIO SERCON DETECTADO!** [Palavra-chave: `{al['palavra']}`]")
                        st.caption("A matéria envolve Tomada de Contas, Cobrança ou Multa. Pela Regra de Exclusão Mútua, este processo não irá para a expedição de ofícios da SEXP.")
                        
                        if st.button(f"🚀 Homologar Desvio Exclusivo para a SERCON ({num_proc_nip})", key=f"btn_sercon_{random.randint(1,999)}"):
                            try:
                                reg_sercon = {
                                    "processo": num_proc_nip if num_proc_nip else "Sem número",
                                    "relator": "GAB",
                                    "motivo_gatilho": f"Palavra detectada: {al['palavra']}",
                                    "status": "Pendente Análise Contábil",
                                    "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                                }
                                conn.client.table("pauta_sercon").insert(reg_sercon).execute()
                                st.success("🎯 Processo roteado exclusivamente para a SERCON! Bloqueio para SEXP ativado.")
                            except Exception as e:
                                st.error(f"Erro ao enviar para SERCON: {e}")
                                
                    elif al["categoria"] == "URGENCIA":
                        st.warning(f"🚨 **GATILHO DE URGÊNCIA DETECTADO!** [Palavra-chave: `{al['palavra']}`]")
                        if st.button(f"⚡ Catalogar na Lista de Urgentes da Sessão", key=f"btn_urg_{random.randint(1,999)}"):
                            try:
                                reg_urg = {
                                    "processo": num_proc_nip if num_proc_nip else "Sem número",
                                    "relator": "GAB",
                                    "sessao": "Sessão Ordinária",
                                    "urgente": 1,
                                    "status": "Triado - Urgente",
                                    "observacao": f"Gatilho NIP: {al['palavra']}",
                                    "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                                }
                                conn.client.table("pauta_seat").insert(reg_urg).execute()
                                st.success("⚡ Processo inserido com prioridade máxima na pauta!")
                            except Exception as e:
                                st.error(f"Erro ao salvar urgência: {e}")
        else:
            st.info("👈 Cole o texto bruto ao lado e clique em Processar para visualizar o resultado purificado.")

# ------------------------------------------------------------------------------
# 4. INTERFACE OPERACIONAL — ABA 2: DISTRIBUIÇÃO E PAUTA ATIVA
# ------------------------------------------------------------------------------
def renderizar_pauta_ativa():
    st.markdown("### 📋 Pauta Ativa e Distribuição Equalitária")
    st.caption("Distribuição aleatória sem auto-revisão. Ao marcar 'Revisado OK', o processo é roteado automaticamente para a mesa de homologação da SEXP.")
    
    col_dist1, col_dist2 = st.columns([2, 1])
    
    with col_dist1:
        with st.expander("➕ Inserir Novo Processo na Pauta da SEAT", expanded=False):
            with st.form("form_add_seat"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    p_num = st.text_input("Nº do Processo:")
                    p_rel = st.selectbox("Relator:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT"])
                with c2:
                    p_ses = st.selectbox("Sessão:", ["Sessão Ordinária", "Ordinária Virtual", "Sessão Administrativa", "Sessão Reservada"])
                    p_urg = st.checkbox("🚨 É Processo Urgente?")
                with c3:
                    expedidores, revisores, todos_colabs = carregar_equipes()
                    ausentes = obter_colaboradores_ausentes_hoje()
                    disponiveis = [c for c in todos_colabs if c not in ausentes]
                    
                    # Garantia de não auto-revisão no sorteio inicial
                    editor_sel = st.selectbox("Editor Atribuído:", disponiveis if disponiveis else ["Equipe Vazia"])
                    opcoes_revisor = [c for c in disponiveis if c != editor_sel]
                    revisor_sel = st.selectbox("Revisor Atribuído:", opcoes_revisor if opcoes_revisor else ["Equipe Vazia"])
                    
                if st.form_submit_button("📥 Distribuir Processo", type="primary"):
                    if p_num.strip():
                        try:
                            novo_seat = {
                                "processo": p_num.strip(),
                                "relator": p_rel,
                                "sessao": p_ses,
                                "editor": editor_sel,
                                "revisor": revisor_sel,
                                "editado_ok": 0,
                                "revisado_ok": 0,
                                "urgente": 1 if p_urg else 0,
                                "status": "Em Edição",
                                "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                            }
                            conn.client.table("pauta_seat").insert(novo_seat).execute()
                            st.success("Processo distribuído com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao distribuir: {e}")
                    else:
                        st.warning("Informe o número do processo.")

    st.markdown("---")
    
    # Filtros de visualização de pauta
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        filtro_sessao = st.multiselect("Filtrar por Sessão:", ["Sessão Ordinária", "Ordinária Virtual", "Sessão Administrativa", "Sessão Reservada"], default=["Sessão Ordinária", "Ordinária Virtual"])
    with col_f2:
        filtro_urgente = st.toggle("🚨 Mostrar Apenas Urgentes")
        
    try:
        dados_seat = buscar_todos_paginado("pauta_seat")
        if not dados_seat:
            st.info("Nenhum processo na pauta ativa da SEAT.")
            return
            
        df_seat = pd.DataFrame(dados_seat)
        
        # Aplicação dos filtros
        if filtro_sessao and "sessao" in df_seat.columns:
            df_seat = df_seat[df_seat["sessao"].isin(filtro_sessao)]
        if filtro_urgente and "urgente" in df_seat.columns:
            df_seat = df_seat[df_seat["urgente"] == 1]
            
        if df_seat.empty:
            st.warning("Nenhum processo corresponde aos filtros selecionados.")
            return

        st.markdown(f"**Total de Processos Listados:** `{len(df_seat)}`")
        
        # Exibição iterativa para permitir marcação dos botões de OK
        for idx, row in df_seat.iterrows():
            with st.container(border=True):
                c_info, c_status, c_acao = st.columns([2.5, 1.5, 1.5])
                with c_info:
                    badge_urg = "🚨 **URGENTE** | " if row.get("urgente") == 1 else ""
                    st.markdown(f"### {badge_urg}`{row.get('processo', 'S/N')}`")
                    st.markdown(f"**Relator:** `{row.get('relator', 'GAB')}` | **Sessão:** {row.get('sessao', 'Ordinária')}")
                    st.caption(f"Editor: **{row.get('editor', 'N/A')}** ➔ Revisor: **{row.get('revisor', 'N/A')}** | Entrada: {row.get('data_entrada', '')}")
                    
                with c_status:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st_ed = "✅ Editado" if row.get("editado_ok") == 1 else "⏳ Pendente Edição"
                    st_rev = "✅ Revisado" if row.get("revisado_ok") == 1 else "⏳ Pendente Revisão"
                    st.markdown(f"**Edição:** {st_ed}<br>**Revisão:** {st_rev}", unsafe_allow_html=True)
                    
                with c_acao:
                    st.markdown("<br>", unsafe_allow_html=True)
                    # Botão 1: Marcar Edição OK
                    if row.get("editado_ok") == 0:
                        if st.button("📝 Concluir Edição", key=f"btn_ed_{row.get('id', idx)}", use_container_width=True):
                            conn.client.table("pauta_seat").update({"editado_ok": 1, "status": "Em Revisão"}).eq("id", row.get("id")).execute()
                            st.success("Edição concluída!")
                            st.rerun()
                            
                    # Botão 2: Marcar Revisão OK + Gatilho Automático para a SEXP
                    elif row.get("revisado_ok") == 0:
                        if st.button("🛡️ Concluir Revisão (Mandar p/ SEXP)", key=f"btn_rev_{row.get('id', idx)}", type="primary", use_container_width=True):
                            # 1. Atualiza na SEAT
                            conn.client.table("pauta_seat").update({"revisado_ok": 1, "status": "Revisado - Enviado SEXP"}).eq("id", row.get("id")).execute()
                            
                            # 2. Transfere automaticamente para a Pauta da SEXP (S.A.D.E.)
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
                                conn.client.table("pauta_sexp").insert(ponte_sexp).execute()
                                st.success("🚀 Revisão concluída! Processo enviada automaticamente para homologação na SEXP.")
                            except Exception as e:
                                st.warning(f"Revisado na SEAT, mas falha no envio automático para SEXP: {e}")
                            st.rerun()
                    else:
                        st.success("✨ Processo Finalizado na SEAT")

    except Exception as e:
        st.error(f"Erro ao processar pauta ativa: {e}")

# ------------------------------------------------------------------------------
# 5. INTERFACE OPERACIONAL — ABA 3: DESPACHOS SINGULARES & SUSTENTAÇÃO ORAL
# ------------------------------------------------------------------------------
def renderizar_pauta_quarta():
    st.markdown("### 📅 Pauta de Quarta-Feira (Despachos Singulares & Sustentação Oral)")
    st.caption("Controle de decisões monocráticas e defesas orais. Processos confirmados entram automaticamente no radar de prioridades da sessão do Plenário.")
    
    col_ds, col_so = st.columns(2)
    
    with col_ds:
        with st.container(border=True):
            st.markdown("#### 📜 Despachos Singulares (DS)")
            st.caption("Decisões emitidas entre quinta e terça que irão a referendo na quarta-feira.")
            
            with st.form("form_ds"):
                ds_num = st.text_input("Nº do Processo (DS):")
                ds_rel = st.selectbox("Relator DO Despacho:", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT"], key="ds_rel")
                ds_status = st.radio("Status de Pauta:", ["✅ Confirmado em Pauta", "🚫 Retirado de Pauta"], horizontal=True)
                
                if st.form_submit_button("📌 Registrar Despacho Singular", type="primary"):
                    if ds_num.strip():
                        try:
                            reg_ds = {
                                "processo": ds_num.strip(),
                                "relator": ds_rel,
                                "tipo_pauta": "Despacho Singular",
                                "status": "Confirmado" if "Confirmado" in ds_status else "Retirado",
                                "sessao_alvo": "Próxima Quarta-Feira",
                                "data_registro": datetime.now().strftime("%d/%m/%Y")
                            }
                            conn.client.table("pauta_quarta").insert(reg_ds).execute()
                            st.success("Despacho Singular catalogado!")
                        except Exception as e:
                            st.error(f"Erro ao salvar DS: {e}")
                    else:
                        st.warning("Informe o processo.")

    with col_so:
        with st.container(border=True):
            st.markdown("#### 🗣️ Sustentações Orais (SO)")
            st.caption("Advogados e interessados com defesa oral agendada no Plenário.")
            
            with st.form("form_so"):
                so_num = st.text_input("Nº do Processo (SO):")
                so_adv = st.text_input("Advogado / Orador:", placeholder="Dr(a). Nome do Advogado - OAB/DF")
                so_data = st.date_input("Data Específica da Sessão:")
                so_status = st.radio("Status do Agendamento:", ["✅ Confirmado (Pauta Prioritária)", "🚫 Retirado / Adiado"], horizontal=True)
                
                if st.form_submit_button("🎙️ Agendar Sustentação Oral", type="primary"):
                    if so_num.strip():
                        try:
                            reg_so = {
                                "processo": so_num.strip(),
                                "relator": so_adv if so_adv else "Orador não informado",
                                "tipo_pauta": "Sustentação Oral",
                                "status": "Confirmado" if "Confirmado" in so_status else "Retirado",
                                "sessao_alvo": so_data.strftime("%d/%m/%Y"),
                                "data_registro": datetime.now().strftime("%d/%m/%Y")
                            }
                            conn.client.table("pauta_quarta").insert(reg_so).execute()
                            st.success("Sustentação Oral agendada com sucesso!")
                        except Exception as e:
                            st.error(f"Erro ao salvar SO: {e}")
                    else:
                        st.warning("Informe o processo.")

    st.markdown("---")
    st.markdown("#### 👁️ Painel Consolidado do Plenário")
    try:
        pauta_q = buscar_todos_paginado("pauta_quarta")
        if pauta_q:
            df_q = pd.DataFrame(pauta_q)
            st.dataframe(df_q[["processo", "tipo_pauta", "relator", "sessao_alvo", "status"]], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum Despacho ou Sustentação Oral agendado para a próxima sessão.")
    except Exception:
        st.info("Tabela de Pauta do Plenário aguardando primeiros registros.")

# ------------------------------------------------------------------------------
# 6. INTERFACE OPERACIONAL — ABA 4: RODÍZIO DE DUPLAS DE PUBLICAÇÃO
# ------------------------------------------------------------------------------
def renderizar_tab_publicacao():
    st.markdown("### 📰 Escala de Duplas de Publicação no DODF")
    st.caption("O sistema gera ciclos automáticos para o mês (Quarta e Sexta), repetindo a ordem ou permitindo trocas manuais da gerência.")
    
    col_gerar, col_escala = st.columns([1, 2])
    
    with col_gerar:
        with st.container(border=True):
            st.markdown("#### 🔄 Gerar Novo Ciclo")
            m_ref = st.selectbox("Mês de Referência:", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])
            if st.button("🚀 Gerar Rodízio Automático do Mês", type="primary", use_container_width=True):
                try:
                    _, _, todos = carregar_equipes()
                    if len(todos) >= 2:
                        duplas = [
                            {"mes": m_ref, "dia_semana": "Quarta-Feira (Sessão)", "dupla": f"{todos[0]} & {todos[1]}"},
                            {"mes": m_ref, "dia_semana": "Sexta-Feira", "dupla": f"{todos[2 % len(todos)]} & {todos[3 % len(todos)]}"},
                            {"mes": m_ref, "dia_semana": "Quarta-Feira (Seguinte)", "dupla": f"{todos[4 % len(todos)]} & {todos[5 % len(todos)]}"}
                        ]
                        conn.client.table("escala_publicacao").insert(duplas).execute()
                        st.success(f"Ciclo de {m_ref} gerado com sucesso!")
                        st.rerun()
                    else:
                        st.warning("É necessário pelo menos 2 colaboradores na equipe para gerar duplas.")
                except Exception as e:
                    st.error(f"Erro ao gerar escala: {e}")
                    
    with col_escala:
        st.markdown("#### 📋 Escala Ativa de Publicação")
        try:
            escala = buscar_todos_paginado("escala_publicacao")
            if escala:
                df_esc = pd.DataFrame(escala)
                st.dataframe(df_esc[["mes", "dia_semana", "dupla"]], use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma escala de publicação gerada para este período.")
        except Exception:
            st.info("Tabela de escala aguardando inicialização.")

# ------------------------------------------------------------------------------
# 7. FUNÇÃO PRINCIPAL DO MÓDULO (PONTO DE ENTRADA DO ROTEADOR)
# ------------------------------------------------------------------------------
def run():
    st.markdown("<div style='font-size: 26px; font-weight: bold; color: #1E3A8A;'>📝 SEAT — Setor de Edição e Triagem</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size: 14px; color: #4B5563; margin-bottom: 20px; border-bottom: 2px solid #E5E7EB; padding-bottom: 8px;'>Purificação Litúrgica de Votos, Pauta do Plenário e Distribuição Equalitária</div>", unsafe_allow_html=True)
    
    tab_nip, tab_ativa, tab_quarta, tab_pub, tab_ferias = st.tabs([
        "🛠️ Oficina NIP (Motor AI)",
        "📋 Pauta Ativa & Distribuição",
        "📅 Pauta de Quarta (DS / SO)",
        "📰 Duplas de Publicação",
        "🏝️ Quadro de Férias / Ausências"
    ])
    
    with tab_nip:
        renderizar_oficina_nip()
    with tab_ativa:
        renderizar_pauta_ativa()
    with tab_quarta:
        renderizar_pauta_quarta()
    with tab_pub:
        renderizar_tab_publicacao()
    with tab_ferias:
        st.markdown("### 🏝️ Quadro Visual de Afastamentos")
        st.caption("Colaboradores listados abaixo são automaticamente excluídos do sorteio de distribuição de novos processos.")
        try:
            afast = buscar_todos_paginado("afastamentos")
            if afast:
                df_af = pd.DataFrame(afast)
                st.dataframe(df_af[["usuario", "motivo", "data_inicio", "data_fim"]], use_container_width=True, hide_index=True)
            else:
                st.success("✨ Nenhum colaborador de férias ou afastado no momento. Equipe 100% disponível!")
        except Exception:
            st.info("Quadro de férias sem registros ativos.")

if __name__ == "__main__":
    run()
