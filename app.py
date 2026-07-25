"""
app.py
Roteador Central do Hub SS - Secretaria das Sessoes - TCDF

Arquitetura: Python + Streamlit + Supabase
Funcao: Porta de entrada do sistema. Autentica usuarios, aplica RBAC
        em 3 niveis (Raiz, Gerente, Operacional) e roteia para o
        modulo correspondente na pasta modulos/.

Principios:
- Nao conhece logica de negocio (Motor NIP, pautas, distribuicao)
- Apenas autentica, verifica permissoes e direciona
- Carregamento dinamico de modulos (importlib)
- Graceful degradation: se um modulo falha, o resto continua funcionando
"""

import streamlit as st
import importlib
from datetime import datetime

# ============================================================
# CONFIGURACAO DA PAGINA (deve ser o primeiro comando Streamlit)
# ============================================================
st.set_page_config(
    page_title="Hub SS - TCDF",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# IMPORTACAO DO GERENCIADOR DE BANCO
# ============================================================
import db_manager

# ============================================================
# INICIALIZACAO DO BANCO (semeadura automatica)
# ============================================================
def inicializar_banco():
    """
    Garante que o banco tenha usuarios iniciais e regras padrao.
    Executado uma vez por sessao.
    Seguro: se ja existirem registros, nao faz nada.
    """
    try:
        db_manager.semear_usuarios_iniciais()
        db_manager.semear_regras_padrao()
    except Exception as e:
        st.error(f"Erro ao inicializar banco: {e}")

# ============================================================
# DEFINICAO DE PERMISSOES POR CARGO (RBAC)
# ============================================================

# Modulos disponiveis no sistema (chave = nome do arquivo em modulos/)
MODULOS_SISTEMA = {
    "SEAT": {
        "arquivo": "seat",
        "descricao": "Edicao e Triagem",
        "icone": "📝",
    },
    "SEXP": {
        "arquivo": "sexp",
        "descricao": "Expedicao (S.A.D.E.)",
        "icone": "📤",
    },
    "SERCON": {
        "arquivo": "sercon",
        "descricao": "Contas, Acordaos e Cobrancas",
        "icone": "💰",
    },
    "SEMAND": {
        "arquivo": "semand",
        "descricao": "Mandados e Diligencias",
        "icone": "📋",
    },
    "GAB": {
        "arquivo": "gab",
        "descricao": "Torre de Controle (Gabinete)",
        "icone": "🏛️",
    },
}

def obter_modulos_permitidos(cargo: str, setor: str) -> list:
    """
    Define quais modulos o usuario pode ver na barra lateral,
    baseado no cargo e setor.

    RBAC em 3 niveis:
    - Raiz: ve todos os modulos
    - Gerente: ve seu modulo de lotacao + GAB (como espectador)
    - Operacional: ve apenas seu modulo de lotacao
    """
    if cargo == "raiz":
        return ["SEAT", "SEXP", "SERCON", "SEMAND", "GAB"]

    elif cargo == "gerente":
        # Gerente ve seu setor + GAB
        modulos = [setor] if setor in MODULOS_SISTEMA else []
        modulos.append("GAB")
        return modulos

    else:  # operacional
        return [setor] if setor in MODULOS_SISTEMA else []

# ============================================================
# TELA DE LOGIN
# ============================================================
def tela_login():
    """
    Renderiza a tela de login.
    Se autenticado, guarda dados do usuario em session_state.
    """
    st.markdown("## ⚖️ Hub SS - Secretaria das Sessoes")
    st.markdown("### Tribunal de Contas do Distrito Federal")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("#### 🔐 Acesso ao Sistema")

        with st.form("form_login"):
            email = st.text_input("E-mail", placeholder="seu.email@tcdf.gov.br")
            senha = st.text_input("Senha", type="password", placeholder="Digite sua senha")
            submit = st.form_submit_button("Entrar", use_container_width=True)

            if submit:
                if not email or not senha:
                    st.warning("Preencha e-mail e senha.")
                    return False

                usuario = db_manager.autenticar_usuario(email.strip(), senha.strip())

                if usuario:
                    st.session_state["usuario"] = usuario
                    st.session_state["logado"] = True
                    st.session_state["login_time"] = datetime.now()
                    st.rerun()
                else:
                    st.error("E-mail ou senha incorretos. Verifique suas credenciais.")
                    return False

        st.markdown("---")
        st.caption("Credenciais iniciais padrao:")
        st.caption("Secretario: secretario@tcdf.gov.br / tcdf2025")
        st.caption("Chefe SEAT: chefeseat@tcdf.gov.br / tcdf2025")
        st.caption("Assessor SEAT: assessorseat@tcdf.gov.br / tcdf2025")

    return False

# ============================================================
# BARRA LATERAL (NAV)
# ============================================================
def barra_lateral():
    """
    Renderiza a barra lateral com:
    - Info do usuario logado
    - Navegacao para modulos permitidos
    - Botao de logout
    """
    usuario = st.session_state.get("usuario", {})
    nome = usuario.get("nome", "Usuario")
    cargo = usuario.get("cargo", "operacional")
    setor = usuario.get("setor", "SEAT")

    # Traduzir cargo para exibicao
    cargo_exibicao = {
        "raiz": "Nivel Raiz",
        "gerente": "Chefe de Setor",
        "operacional": "Assessor/Estagiario",
    }.get(cargo, cargo)

    # --- Cabecalho do usuario ---
    st.sidebar.markdown(f"### 👤 {nome}")
    st.sidebar.markdown(f"**{cargo_exibicao}**")
    st.sidebar.markdown(f"Setor: **{setor}**")
    st.sidebar.markdown("---")

    # --- Navegacao ---
    modulos_permitidos = obter_modulos_permitidos(cargo, setor)

    if not modulos_permitidos:
        st.sidebar.warning("Nenhum modulo disponivel para seu perfil.")
        return None

    # Construir opcoes de navegacao
    opcoes = []
    chaves = []
    for modulo_key in modulos_permitidos:
        if modulo_key in MODULOS_SISTEMA:
            info = MODULOS_SISTEMA[modulo_key]
            opcoes.append(f"{info['icone']} {modulo_key} - {info['descricao']}")
            chaves.append(modulo_key)

    if not opcoes:
        st.sidebar.warning("Nenhum modulo disponivel.")
        return None

    escolha = st.sidebar.radio("Navegacao", opcoes, label_visibility="collapsed")

    # Extrair a chave do modulo selecionado
    indice = opcoes.index(escolha)
    modulo_selecionado = chaves[indice]

    # --- Rodape da sidebar ---
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Sessao iniciada: {st.session_state.get('login_time', datetime.now()).strftime('%d/%m/%Y %H:%M')}")

    if st.sidebar.button("🚪 Sair", use_container_width=True):
        # Limpar session_state
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    return modulo_selecionado

# ============================================================
# CARREGADOR DINAMICO DE MODULOS
# ============================================================
def carregar_modulo(nome_arquivo: str):
    """
    Importa dinamicamente um modulo da pasta modulos/.

    Args:
        nome_arquivo: Nome do arquivo sem extensao (ex: 'seat')

    Returns:
        Modulo importado, ou None se falhar
    """
    try:
        modulo = importlib.import_module(f"modulos.{nome_arquivo}")
        return modulo
    except ImportError as e:
        st.error(f"Modulo '{nome_arquivo}' nao encontrado. Verifique se o arquivo existe em modulos/.")
        st.exception(e)
        return None
    except Exception as e:
        st.error(f"Erro ao carregar modulo '{nome_arquivo}': {e}")
        st.exception(e)
        return None

# ============================================================
# RENDERIZAR MODULO
# ============================================================
def renderizar_modulo(modulo_key: str):
    """
    Carrega e renderiza o modulo selecionado.
    Passa os dados do usuario logado para o modulo.

    Args:
        modulo_key: Chave do modulo (ex: 'SEAT', 'SEXP')
    """
    info = MODULOS_SISTEMA.get(modulo_key)
    if not info:
        st.error("Modulo invalido.")
        return

    nome_arquivo = info["arquivo"]
    icone = info["icone"]
    descricao = info["descricao"]

    # Cabecalho do modulo
    st.markdown(f"## {icone} {modulo_key} - {descricao}")
    st.markdown("---")

    # Carregar modulo dinamicamente
    modulo = carregar_modulo(nome_arquivo)

    if modulo is None:
        st.info(f"O modulo **{modulo_key}** ainda nao foi implementado. Aguarde a proxima fase de desenvolvimento.")
        return

    # Verificar se o modulo tem a funcao 'renderizar'
    if hasattr(modulo, "renderizar"):
        # Passar dados do usuario para o modulo
        modulo.renderizar(st.session_state.get("usuario", {}))
    else:
        st.error(f"O modulo '{modulo_key}' nao tem a funcao 'renderizar'. Verifique a implementacao.")

# ============================================================
# FLUXO PRINCIPAL
# ============================================================
def main():
    """
    Fluxo principal da aplicacao.
    """
    # 1. Inicializar banco (semeadura)
    inicializar_banco()

    # 2. Verificar se esta logado
    if not st.session_state.get("logado", False):
        tela_login()
        return

    # 3. Barra lateral (navegacao)
    modulo_selecionado = barra_lateral()

    if modulo_selecionado is None:
        st.warning("Nenhum modulo selecionado.")
        return

    # 4. Renderizar modulo
    renderizar_modulo(modulo_selecionado)

# ============================================================
# EXECUCAO
# ============================================================
if __name__ == "__main__":
    main()
