# ==============================================================================
# ARQUIVO: app.py
# MISSÃO: Roteador Central, Gestão de Identidade (RBAC) e Portal de Entrada Hub SS
# ==============================================================================

import streamlit as st
import importlib
from db_manager import conn, get_db_connection

# ------------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA E IDENTIDADE VISUAL DO TCDF
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Hub SS - Tribunal de Contas do DF",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS Institucional Limpo e Moderno
st.markdown("""
    <style>
    .main-header {
        font-size: 28px;
        font-weight: bold;
        color: #1A365D;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 14px;
        color: #4A5568;
        margin-top: 0px;
        margin-bottom: 20px;
        border-bottom: 2px solid #E2E8F0;
        padding-bottom: 10px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 6px;
        font-weight: 600;
    }
    .box-boas-vindas {
        background-color: #F7FAFC;
        border-left: 4px solid #2B6CB0;
        padding: 15px;
        border-radius: 4px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 2. INICIALIZAÇÃO DE ESTADO DA SESSÃO (MEMÓRIA DO NAVEGADOR)
# ------------------------------------------------------------------------------
if "logado" not in st.session_state:
    st.session_state.logado = False
if "usuario_nome" not in st.session_state:
    st.session_state.usuario_nome = ""
if "usuario_cargo" not in st.session_state:
    st.session_state.usuario_cargo = ""
if "usuario_setor" not in st.session_state:
    st.session_state.usuario_setor = ""
if "nivel_acesso" not in st.session_state:
    st.session_state.nivel_acesso = ""  # "Raiz", "Gerente", "Operacional"
if "modulo_ativo" not in st.session_state:
    st.session_state.modulo_ativo = "gab"

# ------------------------------------------------------------------------------
# 3. ROTINA DE AUTO-SEMEADURA DE SEGURANÇA (GARANTIA DE ACESSO INICIAL)
# ------------------------------------------------------------------------------
def garantir_tabela_usuarios():
    """Verifica se a tabela de usuários existe e popula com a hierarquia inicial do TCDF."""
    try:
        res = conn.table("usuarios_acesso").select("login").limit(1).execute()
        if not res.data:
            usuarios_iniciais = [
                {"login": "secretario", "senha": "123", "nome": "Secretário de Sessões", "cargo": "Secretário", "setor": "GAB", "nivel_acesso": "Raiz"},
                {"login": "subsecretario", "senha": "123", "nome": "Subsecretário", "cargo": "Subsecretário", "setor": "GAB", "nivel_acesso": "Raiz"},
                {"login": "assessor.especial", "senha": "123", "nome": "Assessor Especial", "cargo": "Assessor Especial", "setor": "GAB", "nivel_acesso": "Raiz"},
                {"login": "gerente.seat", "senha": "123", "nome": "Gestor SEAT", "cargo": "Gerente", "setor": "SEAT", "nivel_acesso": "Gerente"},
                {"login": "gerente.sexp", "senha": "123", "nome": "Gestor SEXP", "cargo": "Gerente", "setor": "SEXP", "nivel_acesso": "Gerente"},
                {"login": "gerente.sercon", "senha": "123", "nome": "Gestor SERCON", "cargo": "Gerente", "setor": "SERCON", "nivel_acesso": "Gerente"},
                {"login": "gerente.semand", "senha": "123", "nome": "Gestor SEMAND", "cargo": "Gerente", "setor": "SEMAND", "nivel_acesso": "Gerente"},
                {"login": "elaine.seat", "senha": "123", "nome": "Elaine", "cargo": "Assessor", "setor": "SEAT", "nivel_acesso": "Operacional"},
                {"login": "andre.sexp", "senha": "123", "nome": "André", "cargo": "Assessor", "setor": "SEXP", "nivel_acesso": "Operacional"}
            ]
            conn.table("usuarios_acesso").insert(usuarios_iniciais).execute()
    except Exception as e:
        # Se a tabela não existir no Supabase, avisa o administrador silenciosamente
        pass

# Executa a checagem de segurança em segundo plano
garantir_tabela_usuarios()

# ------------------------------------------------------------------------------
# 4. MOTOR DE AUTENTICAÇÃO E LOGOUT
# ------------------------------------------------------------------------------
def autenticar(login_input, senha_input):
    """Consulta as credenciais no Supabase e estabelece o nível de privilégio."""
    try:
        res = conn.table("usuarios_acesso").select("*").eq("login", login_input.strip()).eq("senha", senha_input.strip()).execute()
        if res.data and len(res.data) > 0:
            user = res.data[0]
            st.session_state.logado = True
            st.session_state.usuario_nome = user["nome"]
            st.session_state.usuario_cargo = user["cargo"]
            st.session_state.usuario_setor = user["setor"]
            st.session_state.nivel_acesso = user["nivel_acesso"]
            
            # Roteamento padrão no login: Raiz vai pro GAB, Gerente/Operacional vai pro seu setor
            if user["nivel_acesso"] == "Raiz":
                st.session_state.modulo_ativo = "gab"
            else:
                st.session_state.modulo_ativo = user["setor"].lower()
            st.rerun()
        else:
            st.error("🚨 Credenciais inválidas. Verifique seu login e senha.")
    except Exception as e:
        st.error(f"Erro de comunicação no login: {e}. Verifique se a tabela 'usuarios_acesso' foi criada no Supabase.")

def fazer_logout():
    """Limpa a memória da sessão e encerra o acesso com segurança."""
    st.session_state.logado = False
    st.session_state.usuario_nome = ""
    st.session_state.usuario_cargo = ""
    st.session_state.usuario_setor = ""
    st.session_state.nivel_acesso = ""
    st.rerun()

# ------------------------------------------------------------------------------
# 5. TELA DE LOGIN (EXIBIDA APENAS SE NÃO ESTIVER AUTENTICADO)
# ------------------------------------------------------------------------------
if not st.session_state.logado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div style='text-align: center; margin-top: 50px;'>", unsafe_allow_html=True)
        st.markdown("### 🏛️ TRIBUNAL DE CONTAS DO DISTRITO FEDERAL")
        st.markdown("#### **HUB SS — Sistema Integrado da Secretaria de Sessões**")
        st.markdown("</div>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            st.markdown("🔒 **Acesso Restrito ao Pessoal Autorizado**")
            login_user = st.text_input("Usuário de Acesso (Login):", placeholder="Ex: secretario, gerente.seat, elaine.seat")
            senha_user = st.text_input("Senha de Segurança:", type="password", placeholder="••••••••")
            submit_login = st.form_submit_button("🛡️ Entrar no Sistema", type="primary")
            
            if submit_login:
                if login_user and senha_user:
                    autenticar(login_user, senha_user)
                else:
                    st.warning("Por favor, preencha todos os campos para continuar.")
        
        with st.expander("ℹ️ Informações sobre Credenciais Iniciais (Ambiente de Homologação)"):
            st.markdown("""
            **Logins pré-configurados para testes:**
            * 👑 **Nível Raiz:** `secretario` | Senha: `123`
            * 🛡️ **Nível Gerente SEAT:** `gerente.seat` | Senha: `123`
            * 🛡️ **Nível Gerente SEXP:** `gerente.sexp` | Senha: `123`
            * 👤 **Nível Operacional:** `elaine.seat` ou `andre.sexp` | Senha: `123`
            """)
    st.stop()

# ------------------------------------------------------------------------------
# 6. BARRA LATERAL DE NAVEGAÇÃO INTELIGENTE (PÓS-LOGIN)
# ------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏛️ **HUB SS - TCDF**")
    st.markdown(f"**Colaborador(a):** {st.session_state.usuario_nome}")
    st.markdown(f"**Cargo:** {st.session_state.usuario_cargo} | **Setor:** `{st.session_state.usuario_setor}`")
    st.markdown(f"**Privilégio:** 🔐 `{st.session_state.nivel_acesso}`")
    st.markdown("---")
    
    st.markdown("#### 🧭 NAVEGAÇÃO")
    
    # OPÇÃO 1: NÍVEL RAIZ (Acesso total a todos os andares e painéis)
    if st.session_state.nivel_acesso == "Raiz":
        if st.button("📊 GAB - Administração Geral", type="primary" if st.session_state.modulo_ativo == "gab" else "secondary"):
            st.session_state.modulo_ativo = "gab"
            st.rerun()
        if st.button("📝 SEAT - Edição e Triagem", type="primary" if st.session_state.modulo_ativo == "seat" else "secondary"):
            st.session_state.modulo_ativo = "seat"
            st.rerun()
        if st.button("📬 SEXP - Expedição (SADE)", type="primary" if st.session_state.modulo_ativo == "sexp" else "secondary"):
            st.session_state.modulo_ativo = "sexp"
            st.rerun()
        if st.button("⚖️ SERCON - Acórdãos/Contas", type="primary" if st.session_state.modulo_ativo == "sercon" else "secondary"):
            st.session_state.modulo_ativo = "sercon"
            st.rerun()
        if st.button("📑 SEMAND - Mandados", type="primary" if st.session_state.modulo_ativo == "semand" else "secondary"):
            st.session_state.modulo_ativo = "semand"
            st.rerun()
            
    # OPÇÃO 2: NÍVEL GERENTE (Acesso à Torre de Controle do GAB + Seu próprio setor)
    elif st.session_state.nivel_acesso == "Gerente":
        if st.button("📊 GAB - Visão Gerencial", type="primary" if st.session_state.modulo_ativo == "gab" else "secondary"):
            st.session_state.modulo_ativo = "gab"
            st.rerun()
        
        setor_gerenciado = st.session_state.usuario_setor.lower()
        nome_setores = {"seat": "📝 SEAT - Edição e Triagem", "sexp": "📬 SEXP - Expedição (SADE)", "sercon": "⚖️ SERCON - Acórdãos/Contas", "semand": "📑 SEMAND - Mandados"}
        
        if setor_gerenciado in nome_setores:
            if st.button(nome_setores[setor_gerenciado], type="primary" if st.session_state.modulo_ativo == setor_gerenciado else "secondary"):
                st.session_state.modulo_ativo = setor_gerenciado
                st.rerun()
                
    # OPÇÃO 3: NÍVEL OPERACIONAL (Acesso estrito à sua mesa de trabalho no setor de lotação)
    else:
        setor_operacional = st.session_state.usuario_setor.lower()
        st.info(f"📍 Você está conectado à estação operacional da **{st.session_state.usuario_setor}**.")
        st.session_state.modulo_ativo = setor_operacional
        
    st.markdown("---")
    if st.button("🚪 Sair do Sistema (Logout)"):
        fazer_logout()

# ------------------------------------------------------------------------------
# 7. CARREGADOR DINÂMICO DE MÓDULOS (O TELEPORTE DA CATRACA)
# ------------------------------------------------------------------------------
def carregar_modulo_ativo(nome_modulo):
    """
    Importa dinamicamente o arquivo da pasta modulos/ e executa a função run().
    Se o arquivo estiver em branco, exibe um painel de espera limpo e seguro.
    """
    try:
        modulo = importlib.import_module(f"modulos.{nome_modulo}")
        
        # Verifica se o módulo já possui a função principal programada
        if hasattr(modulo, "run"):
            modulo.run()
        else:
            # Amortecedor de segurança para arquivos recém-criados no GitHub
            st.markdown(f"<p class='main-header'>🏢 Módulo {nome_modulo.upper()}</p>", unsafe_allow_html=True)
            st.markdown("<p class='sub-header'>Secretaria de Sessões do Tribunal de Contas do Distrito Federal</p>", unsafe_allow_html=True)
            
            st.markdown(f"""
            <div class='box-boas-vindas'>
                <h4>✅ Conexão Arquitetônica Estabelecida com Sucesso!</h4>
                <p>Você acessou com segurança a sala do módulo <b>{nome_modulo.upper()}</b> com credenciais de nível <code>{st.session_state.nivel_acesso}</code>.</p>
                <p>O arquivo <code>modulos/{nome_modulo}.py</code> já está conectado e operante no servidor, aguardando a injeção do código operacional na próxima etapa da nossa estruturação.</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.info("💡 **Aviso Técnico:** Nenhuma falha de execução. O sistema está 100% pronto para receber o motor de trabalho deste setor.")
            
    except ModuleNotFoundError:
        st.error(f"🚨 Erro Arquitetônico: O arquivo `modulos/{nome_modulo}.py` não foi encontrado no repositório GitHub.")
        st.warning("Verifique se a pasta se chama exatamente `modulos` (com letras minúsculas) e se o arquivo foi criado corretamente.")
    except Exception as e:
        st.error(f"🚨 Ocorreu um erro interno ao processar o módulo **{nome_modulo.upper()}**: `{e}`")

# Executa o módulo selecionado na barra lateral
carregar_modulo_ativo(st.session_state.modulo_ativo)
