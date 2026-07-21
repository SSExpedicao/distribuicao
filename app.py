import streamlit as st
import importlib
import sys
import os

# ==============================================================================
# 1. CONFIGURAÇÃO INICIAL E IDENTIDADE VISUAL (TCDF)
# ==============================================================================
st.set_page_config(
    page_title="Hub SS - Secretaria das Sessões",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo visual limpo e institucional sem distúrbios cognitivos
st.markdown("""
    <style>
        .main-header {
            font-size: 24px;
            font-weight: bold;
            color: #1E3A8A;
            border-bottom: 2px solid #1E3A8A;
            padding-bottom: 8px;
            margin-bottom: 20px;
        }
        .user-badge {
            background-color: #F3F4F6;
            padding: 8px 12px;
            border-radius: 6px;
            border-left: 4px solid #1E3A8A;
            font-size: 13px;
            margin-bottom: 15px;
        }
        .stButton>button {
            width: 100%;
            border-radius: 4px;
            font-weight: 500;
        }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. GESTÃO DE SESSÃO E MATRIZ DE SEGURANÇA (RBAC)
# ==============================================================================
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
if 'usuario_nome' not in st.session_state:
    st.session_state.usuario_nome = ""
if 'nivel_acesso' not in st.session_state:
    st.session_state.nivel_acesso = ""
if 'setor_lotação' not in st.session_state:
    st.session_state.setor_lotacao = ""
if 'modulo_ativo' not in st.session_state:
    st.session_state.modulo_ativo = ""

# Base de Usuários Inicial (Essa matriz será validada no banco de dados na versão final)
# Níveis: "Raiz" (Secretário/Sub/Assessor), "Gerente" (Chefia do Setor), "Operacional"
MATRIZ_USUARIOS = {
    "secretario": {"nome": "Secretário das Sessões", "senha": "admin", "nivel": "Raiz", "setor": "GAB"},
    "subsecretario": {"nome": "Subsecretário", "senha": "admin", "nivel": "Raiz", "setor": "GAB"},
    "assessor_esp": {"nome": "Assessor Especial", "senha": "admin", "nivel": "Raiz", "setor": "GAB"},
    "gerente_seat": {"nome": "Gerente SEAT", "senha": "seat123", "nivel": "Gerente", "setor": "SEAT"},
    "gerente_sexp": {"nome": "Gerente SEXP", "senha": "sexp123", "nivel": "Gerente", "setor": "SEXP"},
    "gerente_sercon": {"nome": "Gerente SERCON", "senha": "sercon123", "nivel": "Gerente", "setor": "SERCON"},
    "gerente_semand": {"nome": "Gerente SEMAND", "senha": "semand123", "nivel": "Gerente", "setor": "SEMAND"},
    "andre_sexp": {"nome": "André (Assessor)", "senha": "123", "nivel": "Operacional", "setor": "SEXP"},
    "elaine_seat": {"nome": "Elaine (Assessora)", "senha": "123", "nivel": "Operacional", "setor": "SEAT"}
}

def efetuar_login(usuario, senha):
    usr_limpo = str(usuario).strip().lower()
    if usr_limpo in MATRIZ_USUARIOS and MATRIZ_USUARIOS[usr_limpo]["senha"] == senha:
        dados = MATRIZ_USUARIOS[usr_limpo]
        st.session_state.autenticado = True
        st.session_state.usuario_nome = dados["nome"]
        st.session_state.nivel_acesso = dados["nivel"]
        st.session_state.setor_lotacao = dados["setor"]
        # Define o módulo inicial com base no setor do usuário
        st.session_state.modulo_ativo = dados["setor"] if dados["setor"] != "GAB" else "GAB"
        return True
    return False

def efetuar_logout():
    st.session_state.autenticado = False
    st.session_state.usuario_nome = ""
    st.session_state.nivel_acesso = ""
    st.session_state.setor_lotacao = ""
    st.session_state.modulo_ativo = ""
    st.rerun()

# ==============================================================================
# 3. TELA DE LOGIN (ACESSO RESTRITO)
# ==============================================================================
if not st.session_state.autenticado:
    col_vazia1, col_login, col_vazia2 = st.columns([1, 1.2, 1])
    
    with col_login:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<div class='main-header' style='text-align: center;'>🏛️ Tribunal de Contas do DF<br><span style='font-size: 18px; font-weight: normal;'>Secretaria das Sessões - Hub Operacional</span></div>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("#### 🔐 Autenticação Institucional")
            usr_input = st.text_input("Usuário de Rede / Matrícula:", placeholder="Ex: secretario, gerente_sexp, andre_sexp")
            pwd_input = st.text_input("Senha de Acesso:", type="password")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Entrar no Sistema", type="primary", use_container_width=True):
                if efetuar_login(usr_input, pwd_input):
                    st.success("Autenticado com sucesso! Carregando painel...")
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos. Verifique suas credenciais.")
        
        with st.expander("ℹ️ Ajuda de Credenciais (Ambiente de Teste)"):
            st.markdown("""
            * **Nível Raiz (Acesso Total):** `secretario` / Senha: `admin`
            * **Gerente Edição:** `gerente_seat` / Senha: `seat123`
            * **Gerente Expedição:** `gerente_sexp` / Senha: `sexp123`
            * **Operacional SEXP:** `andre_sexp` / Senha: `123`
            """)
    st.stop()

# ==============================================================================
# 4. BARRA LATERAL (ROTEADOR DE ANDARES E CONTROLE DE TRÁFEGO)
# ==============================================================================
with st.sidebar:
    st.markdown("### 🏛️ Hub Operacional SS")
    st.markdown(f"""
        <div class='user-badge'>
            <b>👤 {st.session_state.usuario_nome}</b><br>
            <span style='color: #4B5563;'>Lotação: <b>{st.session_state.setor_lotacao}</b> | Nível: <b>{st.session_state.nivel_acesso}</b></span>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("#### 🗺️ Navegação Operacional")
    
    # 1. VISÃO PANORÂMICA (GABINETE) - Liberado para Raiz e Gerentes
    if st.session_state.nivel_acesso in ["Raiz", "Gerente"]:
        if st.button("👑 GAB - Torre de Controle", type="primary" if st.session_state.modulo_ativo == "GAB" else "secondary"):
            st.session_state.modulo_ativo = "GAB"
            st.rerun()
            
    # 2. SEAT - SETOR DE EDIÇÃO E TRIAGEM
    if st.session_state.nivel_acesso == "Raiz" or st.session_state.setor_lotacao == "SEAT":
        if st.button("📝 SEAT - Edição & Triagem", type="primary" if st.session_state.modulo_ativo == "SEAT" else "secondary"):
            st.session_state.modulo_ativo = "SEAT"
            st.rerun()
            
    # 3. SEXP - SETOR DE EXPEDIÇÃO (S.A.D.E.)
    if st.session_state.nivel_acesso == "Raiz" or st.session_state.setor_lotacao == "SEXP":
        if st.button("📬 SEXP - Expedição (S.A.D.E.)", type="primary" if st.session_state.modulo_ativo == "SEXP" else "secondary"):
            st.session_state.modulo_ativo = "SEXP"
            st.rerun()
            
    # 4. SERCON - SETOR DE CONTAS E ACÓRDÃOS
    if st.session_state.nivel_acesso == "Raiz" or st.session_state.setor_lotacao == "SERCON":
        if st.button("⚖️ SERCON - Contas & Acórdãos", type="primary" if st.session_state.modulo_ativo == "SERCON" else "secondary"):
            st.session_state.modulo_ativo = "SERCON"
            st.rerun()
            
    # 5. SEMAND - EXPANSÃO FUTURA
    if st.session_state.nivel_acesso == "Raiz" or st.session_state.setor_lotacao == "SEMAND":
        if st.button("📁 SEMAND - Módulo Integrado", type="primary" if st.session_state.modulo_ativo == "SEMAND" else "secondary"):
            st.session_state.modulo_ativo = "SEMAND"
            st.rerun()

    st.markdown("---")
    if st.button("🚪 Sair do Sistema", type="secondary"):
        efetuar_logout()

# ==============================================================================
# 5. CARREGAMENTO DINÂMICO DOS MÓDULOS (EXECUÇÃO DESACOPLADA)
# ==============================================================================
modulo_alvo = st.session_state.modulo_ativo.lower()

try:
    # Garante que a pasta atual está no path do sistema
    if sys.path[0] != '': sys.path.insert(0, '')
    
    # Importa dinamicamente apenas o arquivo do setor ativo (ex: modulos.sexp)
    mod = importlib.import_module(f"modulos.{modulo_alvo}")
    
    # Se o módulo tiver uma função principal renderizar(), ela é chamada. 
    # Caso contrário, exibe aviso de estrutura em branco.
    if hasattr(mod, 'renderizar'):
        mod.renderizar()
    else:
        st.markdown(f"<div class='main-header'>🏢 Setor: {st.session_state.modulo_ativo}</div>", unsafe_allow_html=True)
        st.info(f"📌 **Módulo Conectado:** O arquivo `modulos/{modulo_alvo}.py` foi carregado com sucesso pela arquitetura central, mas ainda está em branco ou aguardando o código de renderização.")
        st.markdown("---")
        st.caption("Aguardando inserção do código operacional do setor...")

except ModuleNotFoundError:
    st.error(f"🚨 **Erro de Arquitetura:** O arquivo `modulos/{modulo_alvo}.py` não foi localizado. Verifique se o arquivo foi criado com esse nome exato dentro da pasta `modulos/` no seu GitHub.")
except Exception as e:
    st.error(f"⚠️ **Erro na execução do módulo {st.session_state.modulo_ativo}:** {str(e)}")
