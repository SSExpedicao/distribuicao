"""
app.py
Roteador Central do Hub SS - Secretaria das Sessoes - TCDF

Arquitetura: Python + Streamlit + Supabase
Funcao: Porta de entrada do sistema. Autentica usuarios por matricula + senha,
        aplica RBAC em 5 niveis (Criador, Raiz, Secretaria, Gerente, Operacional)
        e roteia para o modulo correspondente na pasta modulos/.

Principios:
- Nao conhece logica de negocio (Motor NIP, pautas, distribuicao)
- Apenas autentica, verifica permissoes e direciona
- Carregamento dinamico de modulos (importlib)
- Graceful degradation: se um modulo falha, o resto continua funcionando
- Passa modo_edicao para cada modulo (True = pode editar, False = so visualizar)
"""

import streamlit as st
import importlib
from datetime import datetime

# ============================================================
# CONFIGURACAO DA PAGINA
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
# INICIALIZACAO DO BANCO
# ============================================================
def inicializar_banco():
    """Garante que o banco tenha usuarios iniciais e regras padrao."""
    try:
        db_manager.semear_usuarios_iniciais()
        db_manager.semear_regras_padrao()
    except Exception as e:
        st.error(f"Erro ao inicializar banco: {e}")

# ============================================================
# DEFINICAO DE MODULOS DO SISTEMA
# ============================================================
MODULOS_SISTEMA = {
    "GAB": {
        "arquivo": "gab",
        "descricao": "Torre de Controle (Gabinete)",
        "icone": "🏛️",
    },
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
}

# ============================================================
# RBAC: PERMISSOES POR CARGO
# ============================================================

def obter_modulos_permitidos(cargo: str, setor: str) -> list:
    """
    Define quais modulos o usuario ve na barra lateral.

    RBAC em 5 niveis:
    - Criador: todos os modulos
    - Raiz: todos os modulos (GAB primeiro, depois setores)
    - Secretaria: todos os modulos (visualizacao + gestao de usuarios no GAB)
    - Gerente: GAB + seu setor
    - Operacional: apenas seu setor
    """
    if cargo in ("criador", "raiz", "secretaria"):
        return ["GAB", "SEAT", "SEXP", "SERCON", "SEMAND"]

    elif cargo == "gerente":
        modulos = ["GAB"]
        if setor in MODULOS_SISTEMA and setor != "GAB":
            modulos.append(setor)
        return modulos

    else:  # operacional
        return [setor] if setor in MODULOS_SISTEMA else []

def obter_modo_edicao(cargo: str, modulo_key: str, setor_usuario: str) -> bool:
    """
    Determina se o usuario pode editar no modulo atual.

    Regras:
    - Criador: sempre True (teste e correcao em todos os modulos)
    - Raiz: True apenas no GAB. Setores: somente visualizacao
    - Secretaria: True apenas no GAB (gestao de colaboradores). Setores: visualizacao
    - Gerente: True no GAB e no seu setor. Outros setores: visualizacao
    - Operacional: True no seu setor (com restricoes a definir por etapa)
    """
    if cargo == "criador":
        return True

    if cargo == "raiz":
        return modulo_key == "GAB"

    if cargo == "secretaria":
        return modulo_key == "GAB"

    if cargo == "gerente":
        return modulo_key == "GAB" or modulo_key == setor_usuario

    # operacional
    return modulo_key == setor_usuario

# ============================================================
# TELA DE LOGIN
# ============================================================
def tela_login():
    """Renderiza a tela de login com matricula + senha."""
    st.markdown("## ⚖️ Hub SS - Secretaria das Sessoes")
    st.markdown("### Tribunal de Contas do Distrito Federal")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("#### 🔐 Acesso ao Sistema")

        with st.form("form_login"):
            matricula = st.text_input("Matrícula", placeholder="Digite sua matrícula")
            senha = st.text_input("Senha", type="password", placeholder="tcdf.ssXXXX")
            submit = st.form_submit_button("Entrar", use_container_width=True)

            if submit:
                if not matricula or not senha:
                    st.warning("Preencha matrícula e senha.")
                    return False

                usuario = db_manager.autenticar_usuario(matricula, senha)

                if usuario:
                    st.session_state["usuario"] = usuario
                    st.session_state["logado"] = True
                    st.session_state["login_time"] = datetime.now()
                    st.rerun()
                else:
                    st.error("Matrícula ou senha incorretos. Verifique suas credenciais.")
                    return False

        st.markdown("---")
        st.caption("**Credenciais de teste:**")
        st.caption("Criador: mat. `1918` / senha `tcdf.ss2025`")
        st.caption("Raiz: mat. `1001` / senha `tcdf.ss2025`")
        st.caption("Secretaria: mat. `2001` / senha `tcdf.ss2025`")
        st.caption("Gerente SEAT: mat. `3001` / senha `tcdf.ss2025`")
        st.caption("Operacional SEAT: mat. `4001` / senha `tcdf.ss2025`")

    return False

# ============================================================
# BARRA LATERAL
# ============================================================
def barra_lateral():
    """Renderiza a barra lateral com info do usuario e navegacao."""
    usuario = st.session_state.get("usuario", {})
    nome = usuario.get("nome", "Usuario")
    cargo = usuario.get("cargo", "operacional")
    setor = usuario.get("setor", "SEAT")
    vinculo = usuario.get("vinculo", "servidor")

    # Traduzir cargo para exibicao
    cargo_exibicao = {
        "criador": "👑 Criador",
        "raiz": "🔴 Nivel Raiz",
        "secretaria": "🟠 Secretaria",
        "gerente": "🟡 Chefe de Setor",
        "operacional": "🟢 Operacional",
    }.get(cargo, cargo)

    # Traduzir vinculo
    vinculo_exibicao = {
        "servidor": "Servidor",
        "terceirizado": "Terceirizado",
        "estagiario": "Estagiario",
    }.get(vinculo, vinculo)

    # Cabecalho do usuario
    st.sidebar.markdown(f"### 👤 {nome}")
    st.sidebar.markdown(f"**{cargo_exibicao}**")
    st.sidebar.markdown(f"Setor: **{setor}**")
    if cargo == "operacional":
        st.sidebar.markdown(f"Vinculo: **{vinculo_exibicao}**")
    st.sidebar.markdown("---")

    # Navegacao
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

    # Indicador de modo (edicao vs visualizacao)
    modo_edicao = obter_modo_edicao(cargo, modulo_selecionado, setor)
    if not modo_edicao and modulo_selecionado != "GAB":
        st.sidebar.info("👁️ Modo visualizacao (somente leitura)")

    # Rodape da sidebar
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Sessao iniciada: {st.session_state.get('login_time', datetime.now()).strftime('%d/%m/%Y %H:%M')}")

    if st.sidebar.button("🚪 Sair", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    return modulo_selecionado

# ============================================================
# CARREGADOR DINAMICO DE MODULOS
# ============================================================
def carregar_modulo(nome_arquivo: str):
    """Importa dinamicamente um modulo da pasta modulos/."""
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
    Passa os dados do usuario e o modo (edicao ou visualizacao) para o modulo.
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
        st.info(f"O modulo **{modulo_key}** ainda nao foi implementado. Aguarde a proxima fase.")
        return

    # Verificar se o modulo tem a funcao 'renderizar'
    if hasattr(modulo, "renderizar"):
        usuario = st.session_state.get("usuario", {})
        cargo = usuario.get("cargo", "operacional")
        setor = usuario.get("setor", "SEAT")
        modo_edicao = obter_modo_edicao(cargo, modulo_key, setor)

        # Passar usuario e modo_edicao para o modulo
        modulo.renderizar(usuario, modo_edicao)
    else:
        st.error(f"O modulo '{modulo_key}' nao tem a funcao 'renderizar'.")

# ============================================================
# FLUXO PRINCIPAL
# ============================================================
def main():
    """Fluxo principal da aplicacao."""
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
