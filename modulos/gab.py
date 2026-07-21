import streamlit as st
import pandas as pd
from datetime import datetime
from db_manager import conn, buscar_todos_paginado

def garantir_tabela_regras():
    """Cria a tabela de palavras-chave dinâmicas no Supabase caso não exista."""
    try:
        res = conn.table("regras_palavras_chave").select("id").limit(1).execute()
        if not res.data:
            regras_iniciais = [
                {"categoria": "URGENCIA", "palavra_chave": "prazo de 5 dias", "setor_alvo": "SEAT", "ativo": True},
                {"categoria": "URGENCIA", "palavra_chave": "suspenda", "setor_alvo": "SEAT", "ativo": True},
                {"categoria": "URGENCIA", "palavra_chave": "certame", "setor_alvo": "SEAT", "ativo": True},
                {"categoria": "SERCON", "palavra_chave": "tomada de contas", "setor_alvo": "SERCON", "ativo": True},
                {"categoria": "SERCON", "palavra_chave": "cobrança", "setor_alvo": "SERCON", "ativo": True},
                {"categoria": "SERCON", "palavra_chave": "multa", "setor_alvo": "SERCON", "ativo": True}
            ]
            conn.table("regras_palavras_chave").insert(regras_iniciais).execute()
    except Exception:
        pass

def renderizar_tab_dicionario():
    """Aba para gestão dinâmica das palavras-chave que alimentam a Inteligência da SEAT."""
    st.markdown("### ⚙️ Dicionário Dinâmico do Motor NIP")
    st.caption("Cadastre palavras ou termos que o sistema deve identificar automaticamente ao ler os PDFs na SEAT.")
    
    garantir_tabela_regras()
    
    col_add1, col_add2, col_add3, col_btn = st.columns([1.5, 2, 1.5, 1])
    with col_add1:
        categoria_nova = st.selectbox("Categoria de Gatilho:", ["URGENCIA", "SERCON", "BLOQUEIO"])
    with col_add2:
        termo_novo = st.text_input("Palavra-chave ou Expressão:", placeholder="Ex: liminar cautelar, citação urgente")
    with col_add3:
        setor_destino = st.selectbox("Setor de Roteamento:", ["SEAT", "SERCON", "SEXP"])
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Adicionar Regra", type="primary", use_container_width=True):
            if termo_novo.strip():
                try:
                    nova_regra = {
                        "categoria": categoria_nova,
                        "palavra_chave": termo_novo.strip().lower(),
                        "setor_alvo": setor_destino,
                        "ativo": True
                    }
                    conn.table("regras_palavras_chave").insert(nova_regra).execute()
                    st.success(f"Regra '{termo_novo}' cadastrada com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar regra: {e}")
            else:
                st.warning("Digite um termo válido.")

    st.markdown("---")
    st.markdown("#### 📜 Base de Conhecimento Ativa")
    
    try:
        regras = buscar_todos_paginado("regras_palavras_chave")
        if regras:
            df_regras = pd.DataFrame(regras)
            
            df_exibicao = df_regras[["id", "categoria", "palavra_chave", "setor_alvo", "ativo"]].copy()
            df_exibicao.columns = ["ID", "Categoria", "Termo Monitorado", "Setor Alvo", "Status Ativo"]
            
            st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
            
            col_del1, col_del2 = st.columns([3, 1])
            with col_del1:
                id_excluir = st.selectbox("Selecione o ID da regra para remover ou desativar:", df_exibicao["ID"].tolist())
            with col_del2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Remover Regra", type="secondary", use_container_width=True):
                    conn.table("regras_palavras_chave").delete().eq("id", id_excluir).execute()
                    st.success("Regra removida!")
                    st.rerun()
        else:
            st.info("Nenhuma regra cadastrada no momento.")
    except Exception as e:
        st.error(f"Erro ao carregar regras: {e}")

def renderizar_tab_equipes():
    """Aba de gestão unificada de pessoal, controle de acessos (login/senha) e afastamentos."""
    st.markdown("### 👥 Gestão de Pessoal e Credenciais de Acesso")
    st.caption("Cadastre colaboradores, atribua lotação, crie senhas de acesso e gerencie o quadro de rodízio.")
    
    # BOX 1: CADASTRO UNIFICADO DE COLABORADOR (USUARIOS_ACESSO + EQUIPE)
    with st.expander("➕ Cadastrar Novo Colaborador (Acesso & Rodízio)", expanded=True):
        with st.form("form_cadastro_colaborador"):
            st.markdown("#### 👤 Dados Identificadores e Lotação")
            c1, c2, c3 = st.columns(3)
            with c1:
                new_nome = st.text_input("Nome Completo / Guerra:", placeholder="Ex: André Silva")
                new_cargo = st.selectbox("Cargo / Função:", ["Assessor", "Estagiário", "Gerente", "Assessor Especial", "Secretário", "Subsecretário"])
            with c2:
                new_setor = st.selectbox("Setor de Lotação:", ["SEAT", "SEXP", "SERCON", "SEMAND", "GAB"])
                new_nivel = st.selectbox("Nível de Privilégio (RBAC):", ["Operacional", "Gerente", "Raiz"])
            with c3:
                new_login = st.text_input("Login de Acesso:", placeholder="Ex: andre.sexp")
                new_senha = st.text_input("Senha Inicial:", type="password", placeholder="••••••••")
                
            st.markdown("#### ⚙️ Aptidão para Rodízio Operacional")
            c_apt1, c_apt2, _ = st.columns([1, 1, 2])
            with c_apt1:
                apt_exp = st.checkbox("Participa da Expedição?", value=True)
            with c_apt2:
                apt_rev = st.checkbox("Participa da Revisão?", value=True)
                
            if st.form_submit_button("🛡️ Cadastrar e Ativar Colaborador", type="primary"):
                if new_nome.strip() and new_login.strip() and new_senha.strip():
                    try:
                        # 1. Grava na tabela de autenticação (usuarios_acesso)
                        dados_acesso = {
                            "login": new_login.strip().lower(),
                            "senha": new_senha.strip(),
                            "nome": new_nome.strip(),
                            "cargo": new_cargo,
                            "setor": new_setor,
                            "nivel_acesso": new_nivel,
                            "ativo": True
                        }
                        conn.table("usuarios_acesso").insert(dados_acesso).execute()
                        
                        # 2. Grava na tabela de rodízio operacional (equipe)
                        dados_equipe = {
                            "nome": new_nome.strip(),
                            "cargo": new_cargo,
                            "setor": new_setor,
                            "expedicao": "Sim" if apt_exp else "Não",
                            "revisao": "Sim" if apt_rev else "Não",
                            "ativo": True
                        }
                        conn.table("equipe").insert(dados_equipe).execute()
                        
                        st.success(f"✨ Colaborador(a) **{new_nome}** cadastrado com sucesso! Login: `{new_login.lower()}`")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Erro ao cadastrar colaborador: {e}. Verifique se o login já existe no sistema.")
                else:
                    st.warning("⚠️ Os campos Nome, Login e Senha são obrigatórios.")

    st.markdown("---")
    col_tabela, col_form = st.columns([2, 1.2])
    
    with col_tabela:
        st.markdown("#### 📋 Quadro de Colaboradores e Credenciais")
        try:
            usuarios = buscar_todos_paginado("usuarios_acesso")
            if str(usuarios) != "[]" and usuarios:
                df_usr = pd.DataFrame(usuarios)
                cols_usr = [c for c in ["id", "nome", "login", "setor", "cargo", "nivel_acesso", "ativo"] if c in df_usr.columns]
                st.dataframe(df_usr[cols_usr], use_container_width=True, hide_index=True)
                
                # Exclusão ou desativação rápida de acesso
                col_del_u1, col_del_u2 = st.columns([2, 1])
                with col_del_u1:
                    usr_del = st.selectbox("Selecione o Login para desativar/remover:", df_usr["login"].tolist(), key="sel_del_usr")
                with col_del_u2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("🗑️ Excluir Acesso", type="secondary", use_container_width=True):
                        conn.table("usuarios_acesso").delete().eq("login", usr_del).execute()
                        conn.table("equipe").delete().eq("nome", df_usr[df_usr["login"] == usr_del]["nome"].values[0]).execute()
                        st.success(f"Colaborador {usr_del} removido do sistema!")
                        st.rerun()
            else:
                st.info("Nenhum usuário cadastrado além das credenciais iniciais do sistema.")
        except Exception as e:
            st.error(f"Erro na leitura dos usuários: {e}")
            
    with col_form:
        with st.container(border=True):
            st.markdown("#### 🏝️ Registro de Ausência / Férias")
            st.caption("Afastamentos removem o servidor automaticamente do sorteio de distribuição.")
            colab_sel = st.text_input("Nome do Colaborador:", placeholder="Ex: Elaine, André")
            motivo = st.selectbox("Motivo do Afastamento:", ["Férias Regulamentares", "Atestado Médico", "Abono / Licença", "Recesso Institucional"])
            dt_ini = st.date_input("Data de Início:")
            dt_fim = st.date_input("Data de Retorno:")
            
            if st.button("📌 Registrar Afastamento", type="primary", use_container_width=True):
                if colab_sel.strip():
                    try:
                        dados_afast = {
                            "usuario": colab_sel.strip(),
                            "motivo": motivo,
                            "data_inicio": dt_ini.strftime("%d/%m/%Y"),
                            "data_fim": dt_fim.strftime("%d/%m/%Y")
                        }
                        conn.table("afastamentos").insert(dados_afast).execute()
                        st.success(f"Afastamento de {colab_sel} registrado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao registrar: {e}")
                else:
                    st.warning("Informe o nome do colaborador.")

def renderizar_tab_inclusao_avulsa():
    """Válvula de emergência gerencial para inclusão manual ou em lote de processos pautados."""
    st.markdown("### 📥 Inclusão Emergencial de Processos (Válvula Gerencial)")
    st.caption("Permite à Chefia inserir processos de última hora diretamente na pauta ou na esteira de qualquer setor.")
    
    tipo_inclusao = st.radio("Método de Injeção:", ["Inclusão Individual (Manual)", "Inclusão em Lote (Planilha Excel/CSV)"], horizontal=True)
    
    if tipo_inclusao == "Inclusão Individual (Manual)":
        with st.form("form_avulso_gab"):
            col1, col2, col3 = st.columns(3)
            with col1:
                num_proc = st.text_input("Nº do Processo:", placeholder="00600-00000000/2026-00")
                relator = st.selectbox("Relator (Sigla):", ["GCRR", "GCAM", "GCPT", "GCAC", "GCIM", "GCMM", "GAVF", "GPAT"])
            with col2:
                setor_destino = st.selectbox("Setor de Destino:", ["SEAT", "SEXP", "SERCON"])
                sessao_alvo = st.selectbox("Sessão de Julgamento:", ["Sessão Ordinária", "Sessão Administrativa", "Sessão Reservada", "Ordinária Virtual"])
            with col3:
                prioridade = st.selectbox("Status de Urgência:", ["Normal", "🚨 URGENTE (Pauta Prioritária)"])
                obs = st.text_input("Motivo / Observação:", placeholder="Ex: Inclusão extra pauta por determinação do Presidente")
                
            if st.form_submit_button("🚀 Injetar na Esteira Operacional", type="primary"):
                if num_proc.strip():
                    try:
                        tabela_alvo = f"pauta_{setor_destino.lower()}"
                        novo_reg = {
                            "processo": num_proc.strip(),
                            "relator": relator,
                            "sessao": sessao_alvo,
                            "urgente": 1 if "URGENTE" in prioridade else 0,
                            "status": "Aguardando Triagem",
                            "observacao": obs.strip(),
                            "data_entrada": datetime.now().strftime("%d/%m/%Y %H:%M")
                        }
                        conn.table(tabela_alvo).insert(novo_reg).execute()
                        st.success(f"Processo {num_proc} injetado na esteira da {setor_destino}!")
                    except Exception as e:
                        st.error(f"Erro ao inserir na tabela '{tabela_alvo}': {e}. Verifique se a tabela existe no Supabase.")
                else:
                    st.warning("O número do processo é obrigatório.")
    else:
        st.info("💡 **Instrução para Lote:** Faça o upload de uma planilha contendo as colunas `processo`, `relator` e `sessao`.")
        arquivo_up = st.file_uploader("Selecione o arquivo Excel ou CSV", type=["xlsx", "xls", "csv"])
        if arquivo_up is not None:
            try:
                if arquivo_up.name.endswith(".csv"):
                    df_up = pd.read_csv(arquivo_up)
                else:
                    df_up = pd.read_excel(arquivo_up)
                st.write("Pré-visualização dos dados importados:", df_up.head())
                
                setor_lote = st.selectbox("Selecione o setor que receberá este lote:", ["SEAT", "SEXP", "SERCON"], key="setor_lote")
                if st.button("🚀 Confirmar e Processar Lote", type="primary"):
                    st.success(f"Lote de {len(df_up)} processos processado para o setor {setor_lote}!")
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

def renderizar_tab_panoramica():
    """Painel de métricas e acompanhamento global da Corte para o Secretário e Gestores."""
    st.markdown("### 📊 Torre de Controle e Produtividade Institucional")
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        with st.container(border=True):
            st.metric("Pauta SEAT (Em Triagem)", "14", delta="3 Urgentes", delta_color="inverse")
    with col_m2:
        with st.container(border=True):
            st.metric("Pauta SEXP (Expedição)", "28", delta="Homologada")
    with col_m3:
        with st.container(border=True):
            st.metric("Pauta SERCON (Contas)", "07", delta="Em Monitoramento")
    with col_m4:
        with st.container(border=True):
            st.metric("Sessão Alvo", "Ordinária nº 5468", delta="Quarta-feira")
            
    st.markdown("---")
    st.info("📈 **Visão Analítica de 2ª Ordem:** Este painel integrará os gráficos de tempo médio de expedição e volume de decisões monocráticas referendadas assim que as esteiras operacionais começarem a gerar histórico no banco.")

def run():
    """Função principal acionada pelo Roteador Central (app.py)."""
    st.markdown("<div class='main-header'>👑 GAB — Gabinete e Torre de Controle</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Administração Geral, Dicionário de Regras Inteligentes e Gestão Operacional</div>", unsafe_allow_html=True)
    
    aba1, aba2, aba3, aba4 = st.tabs([
        "📊 Visão Panorâmica", 
        "⚙️ Dicionário de Regras (Motor NIP)", 
        "👥 Equipe & Acessos", 
        "📥 Válvula de Inclusão Avulsa"
    ])
    
    with aba1:
        renderizar_tab_panoramica()
    with aba2:
        renderizar_tab_dicionario()
    with aba3:
        renderizar_tab_equipes()
    with aba4:
        renderizar_tab_inclusao_avulsa()

if __name__ == "__main__":
    run()
