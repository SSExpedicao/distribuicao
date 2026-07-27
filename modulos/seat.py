"""
modulos/seat.py - SEAT: Edicao e Triagem
Secretaria das Sessoes - TCDF

Sub-etapa 1A+1B: Pauta Ativa com sessoes + Distribuicao Equalitaria

Correcoes aplicadas:
- Delimitador CSV auto-detectado (; ou ,)
- Remocao do sufixo -e do numero do processo
- Adicao do prefixo GC nas iniciais do relator (exceto GAVF / Subst.)

Fluxo de status:
  inclusao -> em_edicao -> em_revisao -> encaminhado

RBAC:
- modo_edicao=True: pode incluir, distribuir, alterar status, editar atribuicoes
- modo_edicao=False: somente visualizacao
"""

import streamlit as st
import csv
import io
import unicodedata
from datetime import datetime, date
import db_manager

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False

# ============================================================
# CONSTANTES
# ============================================================

STATUS_FLOW = {
    "inclusao": {
        "label": "Inclusao",
        "proximo": "em_edicao",
        "acao_proximo": "Iniciar Edicao",
    },
    "em_edicao": {
        "label": "Em Edicao",
        "proximo": "em_revisao",
        "acao_proximo": "Enviar para Revisao",
    },
    "em_revisao": {
        "label": "Em Revisao",
        "proximo": "encaminhado",
        "acao_proximo": "Encaminhar para SEXP",
    },
    "encaminhado": {
        "label": "Encaminhado",
        "proximo": None,
        "acao_proximo": None,
    },
}

TIPOS_SESSAO = [
    "Ordinaria",
    "Ordinaria Virtual",
    "Reservada",
    "Administrativa",
    "Urgente",
]

# ============================================================
# FUNCOES AUXILIARES: NORMALIZACAO E HIGIENIZACAO
# ============================================================

def _normalizar_texto(texto: str) -> str:
    """
    Normaliza texto para comparacao:
    minusculas, sem acentos, sem espacos extras.
    """
    if not texto:
        return ""
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = ' '.join(texto.split())
    return texto

def _normalizar_tipo_sessao(tipo: str) -> str:
    """
    Normaliza o tipo de sessao do CSV para corresponder aos valores padrao.
    Aceita variacoes como 'ordinaria', 'Ordinaria', 'ORDINARIA'.
    """
    if not tipo:
        return ""
    tipo_norm = _normalizar_texto(tipo)
    for tipo_padrao in TIPOS_SESSAO:
        if _normalizar_texto(tipo_padrao) == tipo_norm:
            return tipo_padrao
    return tipo.strip()

def _higienizar_numero_processo(numero: str) -> str:
    """
    Limpa o numero do processo:
    - Remove o sufixo -e (processo eletronico) do final
    
    Exemplo: 00600-00007999/2022-63-e -> 00600-00007999/2022-63
    """
    if not numero:
        return numero
    numero = numero.strip()
    if numero.lower().endswith("-e"):
        numero = numero[:-2]
    return numero

def _higienizar_relator(relator: str) -> str:
    """
    Formata o nome do relator:
    - Adiciona o prefixo GC antes das iniciais
    - Excecao: GAVF / Subst. e variantes sao mantidos como estao
    
    Exemplos:
      AM -> GCAM
      GAVF / Subst. -> GAVF / Subst. (mantido)
      GAVF / Subst -> GAVF / Subst (mantido)
    """
    if not relator:
        return relator
    relator = relator.strip()
    
    # Excecao: se ja contem GAVF ou Subst, manter como esta
    relator_upper = relator.upper()
    if "GAVF" in relator_upper or "SUBST" in relator_upper:
        return relator
    
    # Se ja comeca com GC, nao duplicar
    if relator_upper.startswith("GC"):
        return relator
    
    # Adicionar prefixo GC
    return f"GC{relator}"

def _higienizar_colaborador(nome_digitado: str, nomes_oficiais: list) -> str:
    """
    Faz matching inteligente entre nome digitado e nome oficial da equipe.
    Tolerante a variacoes de escrita (acentos, maiusculas, espacos).
    """
    if not nome_digitado or not nomes_oficiais:
        return nome_digitado or ""

    alvo = _normalizar_texto(nome_digitado)

    # 1. Match exato normalizado
    for oficial in nomes_oficiais:
        if _normalizar_texto(oficial) == alvo:
            return oficial

    # 2. Match por primeiro nome + ultimo nome
    partes_alvo = alvo.split()
    for oficial in nomes_oficiais:
        partes_oficial = _normalizar_texto(oficial).split()
        if len(partes_alvo) >= 2 and len(partes_oficial) >= 2:
            if partes_alvo[0] == partes_oficial[0] and partes_alvo[-1] == partes_oficial[-1]:
                return oficial

    # 3. Match por primeiro nome
    for oficial in nomes_oficiais:
        partes_oficial = _normalizar_texto(oficial).split()
        if partes_oficial and partes_alvo and partes_oficial[0] == partes_alvo[0]:
            return oficial

    return nome_digitado

def _formatar_data(data_iso: str) -> str:
    """Converte data ISO para DD/MM/YYYY HH:MM."""
    if not data_iso:
        return "-"
    try:
        dt = datetime.fromisoformat(str(data_iso).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(data_iso) if data_iso else "-"

def _formatar_data_curta(data_iso: str) -> str:
    """Converte data ISO para DD/MM/YYYY."""
    if not data_iso:
        return "-"
    try:
        dt = datetime.fromisoformat(str(data_iso).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(data_iso) if data_iso else "-"

# ============================================================
# FUNCOES AUXILIARES: EQUIPE E AFASTAMENTOS
# ============================================================

def _obter_equipe_seat() -> list:
    """Retorna lista de nomes dos membros ativos da equipe SEAT."""
    membros = db_manager.listar_equipe(setor="SEAT", apenas_ativos=True)
    return [m.get("nome", "") for m in membros if m.get("nome")]

def _obter_afastados() -> list:
    """Retorna lista de nomes de membros atualmente afastados."""
    return db_manager.listar_nomes_afastados()

def _obter_disponiveis() -> list:
    """Retorna membros disponiveis para distribuicao: equipe ativa - afastados."""
    equipe = _obter_equipe_seat()
    afastados = _obter_afastados()

    afastados_norm = set(_normalizar_texto(a) for a in afastados)

    disponiveis = []
    for nome in equipe:
        if _normalizar_texto(nome) not in afastados_norm:
            disponiveis.append(nome)

    return disponiveis

# ============================================================
# FUNCOES AUXILIARES: DUPLICIDADE
# ============================================================

def _verificar_duplicidade(processo_numero: str, numero_sessao: str, dia_sessao: str) -> bool:
    """Verifica se um processo ja esta cadastrado na mesma sessao/dia."""
    if not processo_numero or not numero_sessao or not dia_sessao:
        return False

    resultados = db_manager.buscar_todos("pauta_seat", filtros={
        "processo_numero": processo_numero,
        "numero_sessao": numero_sessao,
        "dia_sessao": dia_sessao,
    })
    return len(resultados) > 0

# ============================================================
# FUNCOES AUXILIARES: DISTRIBUICAO
# ============================================================

def _contar_atribuicoes(nomes: list, campo: str) -> dict:
    """Conta quantos processos estao atribuidos a cada nome como editor ou revisor."""
    todos_processos = db_manager.buscar_todos("pauta_seat")
    contador = {nome: 0 for nome in nomes}

    for proc in todos_processos:
        nome_atribuido = proc.get(campo)
        if nome_atribuido and nome_atribuido in contador:
            contador[nome_atribuido] += 1

    return contador

def _distribuir_processos(processos: list, editores: list, revisores: list) -> dict:
    """
    Algoritmo de distribuicao equalitaria para SEAT.
    
    Diferenca do SEXP:
    - No SEAT, todo mundo revisa todo mundo.
    - Editor PODE ser o mesmo que revisor (sem restricao).
    - Apenas balanceia a carga igualmente entre os disponiveis.
    """
    if not processos or not editores or not revisores:
        return {}

    contador_editor = _contar_atribuicoes(editores, "editor")
    contador_revisor = _contar_atribuicoes(revisores, "revisor")

    atribuicoes = {}

    for processo in processos:
        proc_id = processo.get("id")
        if not proc_id:
            continue

        # Editor: membro com menos atribuicoes
        editor = min(editores, key=lambda n: contador_editor[n])
        contador_editor[editor] += 1

        # Revisor: membro com menos atribuicoes (pode ser o mesmo do editor)
        revisor = min(revisores, key=lambda n: contador_revisor[n])
        contador_revisor[revisor] += 1

        atribuicoes[proc_id] = (editor, revisor)

    return atribuicoes

# ============================================================
# FUNCOES AUXILIARES: PARSING CSV
# ============================================================

def _detectar_delimitador(texto: str) -> str:
    """
    Detecta o delimitador do CSV automaticamente.
    Suporta ; (padrao brasileiro) e , (padrao internacional).
    Usa csv.Sniffer primeiro, com fallback para verificacao manual.
    """
    primeira_linha = texto.split('\n')[0] if texto else ""
    
    # Tentar com Sniffer (mais robusto)
    try:
        dialect = csv.Sniffer().sniff(primeira_linha, delimiters=';,')
        return dialect.delimiter
    except Exception:
        pass
    
    # Fallback: verificacao manual
    count_ponto_virgula = primeira_linha.count(';')
    count_virgula = primeira_linha.count(',')
    
    if count_ponto_virgula > count_virgula:
        return ';'
    elif count_virgula > 0:
        return ','
    else:
        return ';'  # Default brasileiro

def _parse_csv(arquivo) -> list:
    """
    Faz parse de um arquivo CSV e retorna lista de processos higienizados.

    Correcoes:
    - Remove BOM (Byte Order Mark) de arquivos salvos no Windows
    - Mostra colunas detectadas para debug
    - Aceita variacoes de nomes de coluna
    """
    if arquivo is None:
        return []

    # Ler conteudo
    conteudo = arquivo.read()

    # Decodificar - usar utf-8-sig para remover BOM automaticamente
    try:
        texto = conteudo.decode('utf-8-sig')
    except (UnicodeDecodeError, AttributeError):
        try:
            texto = conteudo.decode('latin-1')
        except Exception:
            texto = str(conteudo)

    # Remover BOM manualmente como fallback
    texto = texto.lstrip('\ufeff')

    # Detectar delimitador
    delimiter = _detectar_delimitador(texto)

    # Parse
    reader = csv.DictReader(io.StringIO(texto), delimiter=delimiter)

    # Debug: mostrar colunas detectadas
    if reader.fieldnames:
        st.caption(f"Colunas detectadas: {', '.join(reader.fieldnames)} | Delimitador: '{delimiter}'")

    processos = []
    for row in reader:
        if not row:
            continue

        # Normalizar nomes de coluna (lowercase, sem espacos, sem BOM)
        row_norm = {}
        for k, v in row.items():
            if k and v:
                # Remover BOM e normalizar nome da coluna
                chave = k.replace('\ufeff', '').lower().strip()
                row_norm[chave] = v.strip()

        # Buscar coluna de processo (aceita variacoes)
        processo_numero = (
            row_norm.get('processo_numero')
            or row_norm.get('processo')
            or row_norm.get('numero')
            or row_norm.get('n_processo')
            or row_norm.get('numero_processo')
            or row_norm.get('n_processo')
            or ""
        )

        # Buscar coluna de relator (opcional)
        relator = (
            row_norm.get('relator')
            or row_norm.get('relatora')
            or row_norm.get('relator(a)')
            or row_norm.get('rel')
            or None
        )

        # Buscar coluna de tipo de sessao
        tipo_sessao = (
            row_norm.get('tipo_sessao')
            or row_norm.get('tipo')
            or row_norm.get('sessao')
            or row_norm.get('tipo_sessao')
            or row_norm.get('tipo_ses')
            or ""
        )

        if processo_numero and tipo_sessao:
            processos.append({
                'processo_numero': _higienizar_numero_processo(processo_numero),
                'relator': _higienizar_relator(relator) if relator else None,
                'tipo_sessao': _normalizar_tipo_sessao(tipo_sessao),
            })

    return processos

# ============================================================
# TAB 1: PAUTA ATIVA
# ============================================================

def _incluir_processo_manual(modo_edicao: bool):
    """Formulario para incluir processo manualmente, um por vez."""
    st.markdown("### Incluir Processo")
    with st.form("form_incluir_manual"):
        col1, col2 = st.columns(2)
        with col1:
            processo_numero = st.text_input(
                "Numero do Processo *",
                placeholder="Ex: 00600-00007999/2022-63-e",
            )
            numero_sessao = st.text_input(
                "Numero da Sessao *",
                placeholder="Ex: 123/2026",
            )
        with col2:
            tipo_sessao = st.selectbox(
                "Tipo de Sessao *",
                options=TIPOS_SESSAO,
                index=0,
            )
            dia_sessao = st.date_input(
                "Dia da Sessao *",
                value=date.today(),
            )
        col3, col4 = st.columns(2)
        with col3:
            relator = st.text_input(
                "Relator (opcional)",
                placeholder="Ex: AM ou GAVF / Subst.",
            )
        with col4:
            observacoes = st.text_input(
                "Observacoes (opcional)",
                placeholder="Info adicional",
            )
        submit = st.form_submit_button("Incluir na Pauta", use_container_width=True)
        if submit:
            if not processo_numero.strip() or not numero_sessao.strip():
                st.error("Numero do processo e numero da sessao sao obrigatorios.")
                return
            # Higienizar dados antes de salvar
            numero_limpo = _higienizar_numero_processo(processo_numero.strip())
            relator_limpo = _higienizar_relator(relator.strip()) if relator else None
            dia_iso = dia_sessao.isoformat()
            # Verificar duplicidade
            if _verificar_duplicidade(numero_limpo, numero_sessao.strip(), dia_iso):
                st.error(
                    f"Duplicidade: o processo {numero_limpo} ja esta cadastrado "
                    f"na sessao {numero_sessao} de {_formatar_data_curta(dia_iso)}."
                )
                return
            dados = {
                "processo_numero": numero_limpo,
                "numero_sessao": numero_sessao.strip(),
                "dia_sessao": dia_iso,
                "tipo_sessao": tipo_sessao,
                "relator": relator_limpo,
                "status": "inclusao",
                "observacoes": observacoes.strip() if observacoes else "",
            }
            resultado = db_manager.inserir("pauta_seat", dados)
            if resultado:
                # GATILHO DS: identifica despacho singular pendente
                _identificar_ds_apos_inclusao(numero_limpo, resultado.get("id"))
                st.success(f"Processo {numero_limpo} incluido na pauta SEAT.")
                if relator and relator_limpo != relator.strip():
                    st.caption(f"Relator formatado: {relator.strip()} -> {relator_limpo}")
                if processo_numero.strip() != numero_limpo:
                    st.caption(f"Numero limpo: {processo_numero.strip()} -> {numero_limpo}")
                st.rerun()
            else:
                st.error("Erro ao incluir processo. Verifique a conexao com o banco.")

def _incluir_processo_lote(modo_edicao: bool):
    """Upload de arquivo CSV com multiplos processos."""
    st.markdown("### Incluir em Lote (CSV)")
    st.caption(
        "Formato esperado: colunas `processo_numero`, `relator` (opcional), `tipo_sessao`.\n\n"
        "Delimitador automatico: aceita `;` (padrao BR) ou `,`.\n\n"
        "O sistema remove o sufixo `-e` do numero do processo e adiciona `GC` "
        "antes das iniciais do relator (exceto GAVF / Subst.)."
    )
    arquivo = st.file_uploader(
        "Selecionar arquivo CSV",
        type=['csv'],
        key="csv_upload_seat",
    )
    if arquivo is None:
        return
    # Parse do CSV
    processos_csv = _parse_csv(arquivo)
    if not processos_csv:
        st.error(
            "Nenhum processo valido encontrado no arquivo. "
            "Verifique se as colunas `processo_numero` e `tipo_sessao` existem e estao preenchidas."
        )
        return
    # Detectar tipos de sessao unicos no arquivo
    tipos_encontrados = sorted(set(p['tipo_sessao'] for p in processos_csv if p['tipo_sessao']))
    st.success(
        f"CSV carregado: {len(processos_csv)} processos encontrados, "
        f"{len(tipos_encontrados)} tipo(s) de sessao."
    )
    # Mostrar preview dos dados higienizados
    with st.expander("Preview dos dados (apos higienizacao)", expanded=False):
        for p in processos_csv[:10]:
            st.write(
                f"- Processo: {p['processo_numero']} | "
                f"Relator: {p.get('relator', '-') or '-'} | "
                f"Tipo: {p['tipo_sessao']}"
            )
        if len(processos_csv) > 10:
            st.caption(f"... e mais {len(processos_csv) - 10} processo(s).")
    # Formulario para numero e data de cada tipo de sessao
    st.markdown("### Informacoes das Sessoes")
    st.markdown("Preencha o numero e a data para cada tipo de sessao encontrado no arquivo:")
    session_info = {}
    for i, tipo in enumerate(tipos_encontrados):
        st.markdown(f"**{tipo}**")
        col_n, col_d = st.columns(2)
        with col_n:
            numero = st.text_input(
                "Numero da Sessao *",
                placeholder=f"Ex: 123/2026",
                key=f"csv_sessao_num_{i}",
            )
        with col_d:
            dia = st.date_input(
                "Data da Sessao *",
                value=date.today(),
                key=f"csv_sessao_dia_{i}",
            )
        session_info[tipo] = {
            'numero': numero.strip(),
            'dia': dia.isoformat(),
        }
        st.markdown("---")
    # Botao de confirmacao
    if st.button("Confirmar e Inserir", type="primary", key="csv_confirmar"):
        erros_validacao = []
        for tipo, info in session_info.items():
            if not info['numero']:
                erros_validacao.append(f"Numero da sessao para {tipo} e obrigatorio.")
        if erros_validacao:
            for erro in erros_validacao:
                st.error(erro)
            return
        inseridos = 0
        duplicados = 0
        erros = 0
        lista_duplicados = []
        for proc in processos_csv:
            tipo = proc['tipo_sessao']
            info = session_info.get(tipo)
            if not info:
                erros += 1
                continue
            if _verificar_duplicidade(proc['processo_numero'], info['numero'], info['dia']):
                lista_duplicados.append(
                    f"{proc['processo_numero']} (sessao {info['numero']} de {_formatar_data_curta(info['dia'])})"
                )
                duplicados += 1
                continue
            dados = {
                "processo_numero": proc['processo_numero'],
                "numero_sessao": info['numero'],
                "dia_sessao": info['dia'],
                "tipo_sessao": tipo,
                "relator": proc.get('relator'),
                "status": "inclusao",
            }
            resultado = db_manager.inserir("pauta_seat", dados)
            if resultado:
                # GATILHO DS: identifica despacho singular pendente
                _identificar_ds_apos_inclusao(proc['processo_numero'], resultado.get("id"))
                inseridos += 1
            else:
                erros += 1
        st.success(
            f"Importacao concluida: {inseridos} inseridos, "
            f"{duplicados} duplicados, {erros} erros."
        )
        if lista_duplicados:
            with st.expander(f"Ver {len(lista_duplicados)} processo(s) duplicado(s)"):
                for dup in lista_duplicados:
                    st.warning(f"Duplicado: {dup}")
        if inseridos > 0:
            st.rerun()

def _avancar_status(id_processo: int, status_atual: str):
    """Avanca o status do processo para a proxima etapa."""
    info_status = STATUS_FLOW.get(status_atual)
    if not info_status or not info_status["proximo"]:
        return

    proximo_status = info_status["proximo"]
    dados_update = {"status": proximo_status}

    if proximo_status == "encaminhado":
        dados_update["data_conclusao"] = datetime.now().isoformat()

    resultado = db_manager.atualizar("pauta_seat", id_processo, dados_update)

    if resultado:
        st.success(f"Processo movido para: {STATUS_FLOW[proximo_status]['label']}")
        st.rerun()
    else:
        st.error("Erro ao atualizar status do processo.")

def _voltar_status(id_processo: int, status_atual: str):
    """Volta o status do processo para a etapa anterior."""
    ordem = ["inclusao", "em_edicao", "em_revisao", "encaminhado"]
    indice = ordem.index(status_atual)
    if indice > 0:
        status_anterior = ordem[indice - 1]
        dados_update = {"status": status_anterior}
        if status_atual == "encaminhado":
            dados_update["data_conclusao"] = None

        resultado = db_manager.atualizar("pauta_seat", id_processo, dados_update)
        if resultado:
            st.success(f"Processo retornado para: {STATUS_FLOW[status_anterior]['label']}")
            st.rerun()

def _remover_processo(id_processo: int, numero: str):
    """Remove um processo da pauta com confirmacao."""
    chave_confirm = f"confirmar_remocao_{id_processo}"
    if st.session_state.get(chave_confirm):
        resultado = db_manager.deletar("pauta_seat", id_processo)
        if resultado:
            st.success(f"Processo {numero} removido da pauta.")
            del st.session_state[chave_confirm]
            st.rerun()
        else:
            st.error("Erro ao remover processo.")
            del st.session_state[chave_confirm]
            st.rerun()
    else:
        st.session_state[chave_confirm] = True
        st.warning(f"Confirme a remocao do processo {numero} clicando novamente.")
        st.rerun()

def _marcar_editado(id_processo: int, valor: bool):
    """Marca/desmarca o checkbox de editado e atualiza o status automaticamente."""
    processo = db_manager.buscar_por_id("pauta_seat", id_processo)
    if not processo:
        return

    revisado = processo.get("revisado", False)

    if valor and revisado:
        novo_status = "encaminhado"
    elif valor and not revisado:
        novo_status = "em_revisao"
    elif not valor:
        novo_status = "em_edicao"
    else:
        novo_status = "em_edicao"

    db_manager.atualizar("pauta_seat", id_processo, {
        "editado": valor,
        "status": novo_status,
    })
    st.rerun()

def _marcar_revisado(id_processo: int, valor: bool):
    """Marca/desmarca o checkbox de revisado e atualiza o status automaticamente."""
    processo = db_manager.buscar_por_id("pauta_seat", id_processo)
    if not processo:
        return

    editado = processo.get("editado", False)

    if valor and editado:
        novo_status = "encaminhado"
    elif valor and not editado:
        novo_status = "encaminhado"
    elif not valor and editado:
        novo_status = "em_revisao"
    else:
        novo_status = "em_edicao"

    db_manager.atualizar("pauta_seat", id_processo, {
        "revisado": valor,
        "status": novo_status,
    })
    st.rerun()

def _salvar_comentario(id_processo: int, comentario: str):
    """Salva o comentario de um processo."""
    db_manager.atualizar("pauta_seat", id_processo, {
        "comentario": comentario.strip(),
    })
    st.success("Comentario salvo.")
    st.rerun()


def renderizar_sidebar(usuario: dict, modo_edicao: bool = False):
    """
    Renderiza tabelas de carga na barra lateral.
    - Filtra apenas as sessoes mais recentes de cada tipo
    - Exclui Urgente (rito diferente)
    - Mostra apenas membros que participaram da distribuicao
    - Operacionais: veem apenas seus proprios dados
    - Gerente e acima: veem todos os membros que participaram
    """
    import pandas as pd

    cargo_usuario = usuario.get("cargo", "operacional")
    nome_usuario = usuario.get("nome", "")
    filtrar_por_usuario = (cargo_usuario == "operacional" and nome_usuario)

    todos_processos = db_manager.buscar_todos("pauta_seat")
    if not todos_processos:
        return

    datas_recentes = {}
    for p in todos_processos:
        tipo = p.get("tipo_sessao", "")
        dia = p.get("dia_sessao")
        if not tipo or not dia:
            continue
        if "urgente" in _normalizar_texto(tipo):
            continue
        dia_str = str(dia)[:10]
        tipo_key = _normalizar_texto(tipo)
        if tipo_key not in datas_recentes or dia_str > datas_recentes[tipo_key]:
            datas_recentes[tipo_key] = dia_str

    if not datas_recentes:
        return

    processos_recentes = []
    for p in todos_processos:
        tipo = p.get("tipo_sessao", "")
        dia = p.get("dia_sessao")
        if not tipo or not dia:
            continue
        dia_str = str(dia)[:10]
        tipo_key = _normalizar_texto(tipo)
        if tipo_key in datas_recentes and dia_str == datas_recentes[tipo_key]:
            processos_recentes.append(p)

    if not processos_recentes:
        return

    nomes_participantes = set()
    for p in processos_recentes:
        editor = (p.get("editor") or "").strip()
        revisor = (p.get("revisor") or "").strip()
        if editor:
            nomes_participantes.add(_normalizar_texto(editor))
        if revisor:
            nomes_participantes.add(_normalizar_texto(revisor))

    if not nomes_participantes:
        return

    equipe = _obter_equipe_seat()
    equipe_participante = []
    for nome in equipe:
        if _normalizar_texto(nome) in nomes_participantes:
            equipe_participante.append(nome)

    if not equipe_participante:
        return

    if filtrar_por_usuario:
        nome_norm = _normalizar_texto(nome_usuario)
        equipe_filtrada = [n for n in equipe_participante if _normalizar_texto(n) == nome_norm]
    else:
        equipe_filtrada = equipe_participante

    dados_edicao = []
    dados_revisao = []
    for nome in equipe_filtrada:
        nome_norm = _normalizar_texto(nome)
        qtd_editar = 0
        faltam_editar = 0
        qtd_revisar = 0
        faltam_revisar = 0
        for p in processos_recentes:
            editor_p = _normalizar_texto(p.get("editor", "") or "")
            revisor_p = _normalizar_texto(p.get("revisor", "") or "")
            editado_p = bool(p.get("editado", False))
            revisado_p = bool(p.get("revisado", False))
            if editor_p == nome_norm:
                qtd_editar += 1
                if not editado_p:
                    faltam_editar += 1
            if revisor_p == nome_norm:
                qtd_revisar += 1
                if not revisado_p:
                    faltam_revisar += 1
        dados_edicao.append({"Resp.": nome, "Qtd": qtd_editar, "Faltam": faltam_editar})
        dados_revisao.append({"Resp.": nome, "Qtd": qtd_revisar, "Faltam": faltam_revisar})

    if not dados_edicao:
        return

    df_ed = pd.DataFrame(dados_edicao)
    df_rev = pd.DataFrame(dados_revisao)

    if not filtrar_por_usuario:
        df_ed = pd.concat([df_ed, pd.DataFrame([{"Resp.": "Total", "Qtd": df_ed["Qtd"].sum(), "Faltam": df_ed["Faltam"].sum()}])], ignore_index=True)
        df_rev = pd.concat([df_rev, pd.DataFrame([{"Resp.": "Total", "Qtd": df_rev["Qtd"].sum(), "Faltam": df_rev["Faltam"].sum()}])], ignore_index=True)

    # TUDO DENTRO DA SIDEBAR
    with st.sidebar:
        st.markdown("**Edicao**")
        st.dataframe(df_ed, hide_index=True, use_container_width=True, height=len(df_ed) * 35 + 40)
        st.markdown("**Revisao**")
        st.dataframe(df_rev, hide_index=True, use_container_width=True, height=len(df_rev) * 35 + 40)

def _renderizar_sidebar_ds(usuario: dict):
    """
    Mostra os ultimos 5 DS e 5 Sustentacoes Orais na sidebar.
    Apenas criador, raiz e gerente.
    """
    import pandas as pd

    cargo = usuario.get("cargo", "operacional")
    if cargo not in ("criador", "raiz", "gerente"):
        return

    todos_ds = db_manager.buscar_todos(
        "despachos_ds",
        ordem_coluna="created_at",
        ordem_desc=True,
    )

    if not todos_ds:
        return

    ds_lista = [d for d in todos_ds if d.get("tipo") == "Despacho Singular"][:5]
    so_lista = [d for d in todos_ds if d.get("tipo") == "Sustentacao Oral"][:5]

    with st.sidebar:
        st.markdown("---")

        if ds_lista:
            st.markdown("##### Despachos Singulares (Recentes)")
            dados_ds = []
            for ds in ds_lista:
                oficios = db_manager.buscar_todos(
                    "oficios_ds",
                    filtros={"despacho_id": ds["id"]},
                )
                dados_ds.append({
                    "Processo": ds.get("processo_numero", ""),
                    "Relator": ds.get("relator", "-") or "-",
                    "Docs": len(oficios),
                })
            df_ds = pd.DataFrame(dados_ds)
            st.dataframe(
                df_ds,
                hide_index=True,
                use_container_width=True,
                height=len(df_ds) * 35 + 40,
            )

        if so_lista:
            st.markdown("##### Sustentacao Oral (Recentes)")
            dados_so = []
            for so in so_lista:
                dados_so.append({
                    "Processo": so.get("processo_numero", ""),
                    "Relator": so.get("relator", "-") or "-",
                    "Confirmada": "Sim" if so.get("recebido_confirmado") else "Nao",
                })
            df_so = pd.DataFrame(dados_so)
            st.dataframe(
                df_so,
                hide_index=True,
                use_container_width=True,
                height=len(df_so) * 35 + 40,
            )

def _renderizar_card_processo(processo: dict, modo_edicao: bool):
    """Renderiza um card individual de processo na pauta ativa."""
    id_proc = processo.get("id")
    numero = processo.get("processo_numero", "")
    numero_sessao = processo.get("numero_sessao", "") or "-"
    dia_sessao = _formatar_data_curta(processo.get("dia_sessao"))
    tipo_sessao = processo.get("tipo_sessao", "") or "-"
    relator = processo.get("relator", "") or "-"
    editor = processo.get("editor", "") or "-"
    revisor = processo.get("revisor", "") or "-"
    editado = processo.get("editado", False)
    revisado = processo.get("revisado", False)
    comentario = processo.get("comentario", "") or ""
    data_entrada = _formatar_data(processo.get("data_entrada"))

    with st.container():
        # Linha 1: Processo + Relator
        col_proc, col_rel = st.columns([3, 2])
        with col_proc:
            st.markdown(f"### {numero}")
        with col_rel:
            st.markdown(f"**Relator:** {relator}")

        # Linha 2: Sessao + Tipo + Data
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"**Sessao:** {numero_sessao}")
        with col2:
            st.markdown(f"**Tipo:** {tipo_sessao}")
        with col3:
            st.markdown(f"**Data:** {dia_sessao}")

        # Linha 3: Editor + Revisor
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Editor:** {editor}")
        with col2:
            st.markdown(f"**Revisor:** {revisor}")

        # Linha 4: Checkboxes Editado / Revisado
        if modo_edicao:
            col_chk1, col_chk2 = st.columns(2)
            with col_chk1:
                novo_editado = st.checkbox(
                    "Editado", value=editado, key=f"chk_editado_{id_proc}"
                )
                if novo_editado != editado:
                    _marcar_editado(id_proc, novo_editado)
            with col_chk2:
                novo_revisado = st.checkbox(
                    "Revisado", value=revisado, key=f"chk_revisado_{id_proc}"
                )
                if novo_revisado != revisado:
                    _marcar_revisado(id_proc, novo_revisado)
        else:
            col_chk1, col_chk2 = st.columns(2)
            with col_chk1:
                st.markdown(f"{'☑' if editado else '☐'} Editado")
            with col_chk2:
                st.markdown(f"{'☑' if revisado else '☐'} Revisado")

        # Linha 5: Comentario (caixa de texto livre)
        if modo_edicao:
            novo_comentario = st.text_area(
                "Comentario",
                value=comentario,
                placeholder="Deixe um comentario sobre o processo...",
                height=60,
                key=f"comentario_{id_proc}",
            )
            if st.button("Salvar Comentario", key=f"btn_comentario_{id_proc}"):
                if novo_comentario.strip() != comentario:
                    _salvar_comentario(id_proc, novo_comentario)
        else:
            if comentario:
                st.markdown(f"**Comentario:** {comentario}")
            else:
                st.caption("Sem comentario.")

        # Rodape
        st.caption(f"Entrada: {data_entrada}")

        # Botao de remover
        if modo_edicao:
            if st.button("Remover", key=f"remover_{id_proc}"):
                _remover_processo(id_proc, numero)

        st.markdown("---")


def _renderizar_pauta_ativa(modo_edicao: bool, usuario: dict = None):
    """Renderiza a aba de Pauta Ativa com filtros e lista de processos."""

    # Determinar se precisa filtrar por usuario
    cargo_usuario = usuario.get("cargo", "operacional") if usuario else "operacional"
    nome_usuario = usuario.get("nome", "") if usuario else ""
    filtrar_por_usuario = (cargo_usuario == "operacional" and nome_usuario)

    col_f1, col_f2, col_f3 = st.columns(3)
    # ... resto da função permanece igual ...

    with col_f1:
        busca = st.text_input(
            "Buscar por numero do processo",
            placeholder="Digite o numero...",
            key="busca_pauta_seat",
        )

    with col_f2:
        status_opcoes = ["todos"] + list(STATUS_FLOW.keys())
        status_labels = {"todos": "Todos os Status"}
        status_labels.update({k: v["label"] for k, v in STATUS_FLOW.items()})
        filtro_status = st.selectbox(
            "Filtrar por status",
            options=status_opcoes,
            format_func=lambda x: status_labels[x],
            key="filtro_status_seat",
        )

    with col_f3:
        filtro_tipo = st.selectbox(
            "Filtrar por tipo de sessao",
            options=["todos"] + TIPOS_SESSAO,
            key="filtro_tipo_seat",
        )

    if modo_edicao:
        tab_manual, tab_lote = st.tabs(["Inclusao Manual", "Inclusao em Lote (CSV)"])

        with tab_manual:
            _incluir_processo_manual(modo_edicao)

        with tab_lote:
            _incluir_processo_lote(modo_edicao)

    filtros = {}
    if filtro_status != "todos":
        filtros["status"] = filtro_status
    if filtro_tipo != "todos":
        filtros["tipo_sessao"] = filtro_tipo

    processos = db_manager.buscar_todos(
        "pauta_seat",
        filtros=filtros if filtros else None,
        ordem_coluna="created_at",
        ordem_desc=True,
    )

    # Filtro de busca por numero (client-side)
    if busca.strip():
        busca_lower = busca.strip().lower()
        processos = [p for p in processos if busca_lower in (p.get("processo_numero", "") or "").lower()]

    # FILTRAR POR USUARIO: operacionais so veem seus processos
    if filtrar_por_usuario:
        nome_norm = _normalizar_texto(nome_usuario)
        processos = [
            p for p in processos
            if _normalizar_texto(p.get("editor", "")) == nome_norm
            or _normalizar_texto(p.get("revisor", "")) == nome_norm
        ]

    # Contadores
    col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns(5)
    with col_c1:
        st.metric("Total", len(processos))
    with col_c2:
        st.metric("Inclusao", len([p for p in processos if p.get("status") == "inclusao"]))
    with col_c3:
        st.metric("Em Edicao", len([p for p in processos if p.get("status") == "em_edicao"]))
    with col_c4:
        st.metric("Em Revisao", len([p for p in processos if p.get("status") == "em_revisao"]))
    with col_c5:
        st.metric("Encaminhados", len([p for p in processos if p.get("status") == "encaminhado"]))

    st.markdown("---")

    if not processos:
        if filtrar_por_usuario:
            st.info(f"Nenhum processo atribuido a voce ({nome_usuario}).")
        else:
            st.info("Nenhum processo encontrado na pauta SEAT.")
    else:
        if filtrar_por_usuario:
            st.markdown(f"### Meus Processos ({len(processos)})")
        else:
            st.markdown(f"### Pauta Ativa ({len(processos)} processo{'s' if len(processos) != 1 else ''})")
        for processo in processos:
            _renderizar_card_processo(processo, modo_edicao)

# ============================================================
# TAB 2: DISTRIBUICAO
# ============================================================

def _renderizar_distribuicao(modo_edicao: bool, usuario: dict = None):
    """Renderiza a aba de Distribuicao Equalitaria."""

    # Determinar se precisa filtrar por usuario
    cargo_usuario = usuario.get("cargo", "operacional") if usuario else "operacional"
    nome_usuario = usuario.get("nome", "") if usuario else ""
    filtrar_por_usuario = (cargo_usuario == "operacional" and nome_usuario)

    todos_processos = db_manager.buscar_todos(
        "pauta_seat",
        ordem_coluna="created_at",
        ordem_desc=True,
    )

    # FILTRAR POR USUARIO: operacionais so veem seus processos
    if filtrar_por_usuario:
        nome_norm = _normalizar_texto(nome_usuario)
        todos_processos = [
            p for p in todos_processos
            if _normalizar_texto(p.get("editor", "")) == nome_norm
            or _normalizar_texto(p.get("revisor", "")) == nome_norm
        ]

    sessoes_nao_distribuidas = {}
    sessoes_distribuidas = {}

    for p in todos_processos:
        numero_sessao = p.get("numero_sessao", "") or "Sem sessao"
        dia_sessao = _formatar_data_curta(p.get("dia_sessao"))
        tipo_sessao = p.get("tipo_sessao", "") or "Sem tipo"
        chave = f"{tipo_sessao} | Sessao {numero_sessao} | {dia_sessao}"

        if p.get("editor") or p.get("revisor"):
            if chave not in sessoes_distribuidas:
                sessoes_distribuidas[chave] = []
            sessoes_distribuidas[chave].append(p)
        else:
            if chave not in sessoes_nao_distribuidas:
                sessoes_nao_distribuidas[chave] = []
            sessoes_nao_distribuidas[chave].append(p)

    # --- SECAO 1: DISTRIBUIR ---
    st.markdown("### Distribuir Processos")

    if not sessoes_nao_distribuidas:
        st.info("Nao ha processos pendentes de distribuicao.")
    elif not modo_edicao:
        st.info("Modo visualizacao. A distribuicao pode ser executada apenas por gerentes ou superior.")
    else:
        disponiveis = _obter_disponiveis()

        if len(disponiveis) < 1:
            st.error(
                "Nao ha membros disponiveis para distribuir. "
                f"Atualmente ha {len(disponiveis)} membro(s) disponivel(is)."
            )
        else:
            chaves_distribuir = list(sessoes_nao_distribuidas.keys())
            sessao_sel = st.radio(
                "Selecione a sessao para distribuir",
                options=chaves_distribuir,
                key="dist_radio_distribuir",
            )

            processos_para_distribuir = sessoes_nao_distribuidas[sessao_sel]
            st.write(f"**{len(processos_para_distribuir)} processo(s)** para distribuir nesta sessao.")

            with st.expander("Ver processos", expanded=False):
                for p in processos_para_distribuir:
                    st.write(f"- {p.get('processo_numero', '')} | Relator: {p.get('relator', '-') or '-'}")

            st.markdown("### Selecionar Membros")
            st.caption("Desmarque os membros que nao devem participar desta distribuicao. No SEAT, todo mundo revisa todo mundo.")

            col_ed, col_rev = st.columns(2)

            editores_selecionados = []
            revisores_selecionados = []

            with col_ed:
                st.markdown("##### Editores")
                for membro in disponiveis:
                    if st.checkbox(membro, value=True, key=f"dist_ed_{membro}"):
                        editores_selecionados.append(membro)

            with col_rev:
                st.markdown("##### Revisores")
                for membro in disponiveis:
                    if st.checkbox(membro, value=True, key=f"dist_rev_{membro}"):
                        revisores_selecionados.append(membro)

            afastados = _obter_afastados()
            if afastados:
                with st.expander(f"{len(afastados)} membro(s) afastado(s) (excluido(s) automaticamente)"):
                    for nome in afastados:
                        st.write(f"- {nome}")

            st.markdown("---")
            if st.button("Distribuir", type="primary", use_container_width=True, key="dist_btn_distribuir"):
                if not editores_selecionados or not revisores_selecionados:
                    st.error("Selecione pelo menos 1 editor e 1 revisor.")
                else:
                    with st.spinner("Distribuindo processos..."):
                        atribuicoes = _distribuir_processos(
                            processos_para_distribuir,
                            editores_selecionados,
                            revisores_selecionados,
                        )

                    if atribuicoes:
                        salvos = 0
                        for proc_id, (editor, revisor) in atribuicoes.items():
                            resultado = db_manager.atualizar("pauta_seat", proc_id, {
                                "editor": editor,
                                "revisor": revisor,
                            })
                            if resultado:
                                salvos += 1

                        st.success(f"{salvos} processo(s) distribuido(s) com sucesso!")
                        st.rerun()
                    else:
                        st.warning("Nenhum processo foi distribuido. Verifique as condicoes.")

    st.markdown("---")

    # --- SECAO 2: EDITAR DISTRIBUICAO ---
    st.markdown("### Editar Distribuicao")

    if not sessoes_distribuidas:
        st.info("Nao ha processos distribuidos para editar.")
    else:
        chaves_editar = list(sessoes_distribuidas.keys())
        sessao_editar = st.radio(
            "Selecione a sessao para editar",
            options=chaves_editar,
            key="dist_radio_editar",
        )

        processos_distribuidos = sessoes_distribuidas[sessao_editar]
        disponiveis = _obter_equipe_seat()

        if not disponiveis:
            st.warning("Nao ha membros da equipe cadastrados.")
        else:
            if PANDAS_OK and modo_edicao:
                # Ordem correta: Processo - Relator - Editor - Editado - Revisor - Revisado - Comentario
                df_dados = []
                for p in processos_distribuidos:
                    df_dados.append({
                        "id": p.get("id"),
                        "processo_numero": p.get("processo_numero", ""),
                        "relator": p.get("relator", "") or "",
                        "editor": p.get("editor", "") or "",
                        "editado": bool(p.get("editado", False)),
                        "revisor": p.get("revisor", "") or "",
                        "revisado": bool(p.get("revisado", False)),
                        "comentario": p.get("comentario", "") or "",
                    })

                df = pd.DataFrame(df_dados)

                edited_df = st.data_editor(
                    df,
                    column_config={
                        "id": None,
                        "processo_numero": st.column_config.TextColumn("Processo", disabled=True),
                        "relator": st.column_config.TextColumn("Relator", disabled=True),
                        "editor": st.column_config.SelectboxColumn("Editor", options=disponiveis, required=True),
                        "editado": st.column_config.CheckboxColumn("Editado", default=False),
                        "revisor": st.column_config.SelectboxColumn("Revisor", options=disponiveis, required=True),
                        "revisado": st.column_config.CheckboxColumn("Revisado", default=False),
                        "comentario": st.column_config.TextColumn("Comentario", width="medium"),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="dist_data_editor_v2",
                )

                if st.button("Salvar Alteracoes", key="dist_btn_salvar"):
                    salvos = 0

                    for _, row in edited_df.iterrows():
                        editor_atual = row["editor"]
                        revisor_atual = row["revisor"]

                        original = next((p for p in processos_distribuidos if p.get("id") == row["id"]), None)
                        if not original:
                            continue

                        mudancas = {}

                        if (original.get("editor") or "") != editor_atual:
                            mudancas["editor"] = editor_atual if editor_atual else None

                        if (original.get("revisor") or "") != revisor_atual:
                            mudancas["revisor"] = revisor_atual if revisor_atual else None

                        editado_original = bool(original.get("editado", False))
                        editado_novo = bool(row["editado"])
                        if editado_original != editado_novo:
                            mudancas["editado"] = editado_novo

                        revisado_original = bool(original.get("revisado", False))
                        revisado_novo = bool(row["revisado"])
                        if revisado_original != revisado_novo:
                            mudancas["revisado"] = revisado_novo

                        comentario_original = original.get("comentario", "") or ""
                        comentario_novo = row["comentario"] or ""
                        if comentario_original != comentario_novo:
                            mudancas["comentario"] = comentario_novo.strip()

                        # Recalcular status automaticamente
                        if "editado" in mudancas or "revisado" in mudancas:
                            editado_val = mudancas.get("editado", editado_original)
                            revisado_val = mudancas.get("revisado", revisado_original)

                            if revisado_val and editado_val:
                                mudancas["status"] = "encaminhado"
                            elif editado_val and not revisado_val:
                                mudancas["status"] = "em_revisao"
                            elif not editado_val and not revisado_val:
                                mudancas["status"] = "em_edicao"
                            elif revisado_val and not editado_val:
                                mudancas["status"] = "encaminhado"

                        if mudancas:
                            resultado = db_manager.atualizar("pauta_seat", row["id"], mudancas)
                            if resultado:
                                salvos += 1

                    if salvos > 0:
                        st.success(f"{salvos} alteracao(oes) salva(s) com sucesso!")
                        st.rerun()
                    else:
                        st.info("Nenhuma alteracao detectada.")

            elif PANDAS_OK:
                # Modo visualizacao
                df_dados = []
                for p in processos_distribuidos:
                    df_dados.append({
                        "Processo": p.get("processo_numero", ""),
                        "Relator": p.get("relator", "") or "-",
                        "Editor": p.get("editor", "") or "-",
                        "Editado": "Sim" if p.get("editado", False) else "Nao",
                        "Revisor": p.get("revisor", "") or "-",
                        "Revisado": "Sim" if p.get("revisado", False) else "Nao",
                        "Comentario": p.get("comentario", "") or "-",
                    })
                df = pd.DataFrame(df_dados)
                st.dataframe(df, hide_index=True, use_container_width=True)

            else:
                for p in processos_distribuidos:
                    st.write(
                        f"- {p.get('processo_numero', '')} | "
                        f"Relator: {p.get('relator', '-') or '-'} | "
                        f"Editor: {p.get('editor', '-') or '-'} | "
                        f"Editado: {'Sim' if p.get('editado') else 'Nao'} | "
                        f"Revisor: {p.get('revisor', '-') or '-'} | "
                        f"Revisado: {'Sim' if p.get('revisado') else 'Nao'} | "
                        f"Comentario: {p.get('comentario', '') or '-'}"
                    )

# ============================================================
# DESPACHOS SINGULARES - FUNCOES
# ============================================================

def _verificar_ds_pendente(processo_numero):
    """
    Verifica se o processo tem um DS pendente.
    Retorna o tipo ('Despacho Singular' ou 'Sustentacao Oral') ou None.
    """
    if not processo_numero:
        return None

    proc_higienizado = _higienizar_numero_processo(processo_numero)

    resultados = db_manager.buscar_todos(
        "despachos_ds",
        filtros={"processo_numero": proc_higienizado, "status": "pendente"}
    )

    if resultados:
        return resultados[0].get("tipo", "Despacho Singular")

    return None

def _marcar_ds_distribuido(processo_numero):
    """Marca o DS como distribuido apos o processo entrar na pauta."""
    if not processo_numero:
        return

    proc_higienizado = _higienizar_numero_processo(processo_numero)

    resultados = db_manager.buscar_todos(
        "despachos_ds",
        filtros={"processo_numero": proc_higienizado, "status": "pendente"}
    )

    for ds in resultados:
        db_manager.atualizar("despachos_ds", ds["id"], {"status": "distribuido"})

def _identificar_ds_apos_inclusao(processo_numero, pauta_id):
    """
    Funcao gatilho: apos incluir um processo na pauta_seat, verifica se
    existe um DS pendente para ele. Se sim, preenche o comentario e marca
    o DS como distribuido.
    """
    if not processo_numero or not pauta_id:
        return

    ds_tipo = _verificar_ds_pendente(processo_numero)

    if ds_tipo:
        comentario_ds = ds_tipo.upper()
        db_manager.atualizar("pauta_seat", pauta_id, {"comentario": comentario_ds})
        _marcar_ds_distribuido(processo_numero)

def _cadastrar_despacho(usuario):
    """Formulario para cadastrar novo Despacho Singular."""
    st.markdown("#### Cadastrar Novo Despacho")

    nome_usuario = usuario.get("nome", "Sistema")

    if "ds_oficios_temp" not in st.session_state:
        st.session_state["ds_oficios_temp"] = []

    col1, col2 = st.columns(2)

    with col1:
        processo_numero = st.text_input(
            "Numero do Processo *",
            placeholder="Ex: 00600-0007999/2022-63-e",
            key="ds_processo_numero"
        )
        tipo = st.selectbox(
            "Tipo *",
            options=["Despacho Singular", "Sustentacao Oral"],
            key="ds_tipo"
        )

    with col2:
        relator = st.text_input(
            "Relator (opcional)",
            placeholder="Ex: AM ou GAVF / Subst.",
            key="ds_relator"
        )
        forma_envio = st.selectbox(
            "Forma de Envio *",
            options=["E-mail", "Mensageria", "Protocolo"],
            key="ds_forma_envio"
        )

    observacoes = st.text_area(
        "Observacoes (opcional)",
        placeholder="Informacoes adicionais...",
        height=60,
        key="ds_observacoes"
    )

    st.markdown("---")
    st.markdown("##### Documentos Vinculados (Oficios / Memorandos)")
    st.caption("E obrigatorio cadastrar pelo menos 1 documento.")

    # Mostrar documentos ja adicionados
    if st.session_state["ds_oficios_temp"]:
        for i, of in enumerate(st.session_state["ds_oficios_temp"]):
            col_a, col_b, col_c, col_d, col_e = st.columns([2, 2, 2, 2, 1])
            with col_a:
                st.write(f"**{of['tipo_documento']}**")
            with col_b:
                st.write(f"N: {of['numero_oficio']}")
            with col_c:
                st.write(f"Para: {of['destinatario']}")
            with col_d:
                st.write(f"Envio: {of['tipo_envio']}")
            with col_e:
                if st.button("X", key=f"rm_of_{i}", help="Remover"):
                    st.session_state["ds_oficios_temp"].pop(i)
                    st.rerun()
    else:
        st.info("Nenhum documento adicionado ainda.")

    # Form para adicionar documento
    with st.form("form_add_oficio_ds"):
        st.markdown("**Adicionar Documento**")
        col_of1, col_of2 = st.columns(2)
        with col_of1:
            tipo_doc = st.selectbox(
                "Tipo de Documento",
                options=["Oficio", "Memorando"],
                key="ds_oficio_tipo"
            )
            numero_oficio = st.text_input(
                "Numero do Documento *",
                placeholder="Ex: 123/2026",
                key="ds_oficio_numero"
            )
        with col_of2:
            destinatario = st.text_input(
                "Destinatario *",
                placeholder="Ex: Secretaria de Fazenda",
                key="ds_oficio_dest"
            )
            tipo_envio_of = st.selectbox(
                "Tipo de Envio",
                options=["E-mail", "Mensageria", "Protocolo"],
                key="ds_oficio_envio"
            )

        adicionar = st.form_submit_button("Adicionar Documento")

        if adicionar:
            if not numero_oficio or not destinatario:
                st.error("Preencha o numero e o destinatario do documento.")
            else:
                st.session_state["ds_oficios_temp"].append({
                    "tipo_documento": tipo_doc,
                    "numero_oficio": numero_oficio,
                    "destinatario": destinatario,
                    "tipo_envio": tipo_envio_of,
                    "status": "aguardando",
                })
                st.rerun()

    st.markdown("---")

    # Botao para salvar o DS completo
    if st.button("Salvar Despacho", type="primary", use_container_width=True, key="btn_salvar_ds"):
        if not processo_numero:
            st.error("Numero do processo e obrigatorio.")
        elif not st.session_state["ds_oficios_temp"]:
            st.error("E obrigatorio cadastrar pelo menos 1 oficio/memorando.")
        else:
            proc_higienizado = _higienizar_numero_processo(processo_numero)
            relator_higienizado = _higienizar_relator(relator) if relator else None

            # Verificar se ja existe DS pendente
            ds_existente = _verificar_ds_pendente(proc_higienizado)
            if ds_existente:
                st.error(f"Ja existe um DS pendente para o processo {proc_higienizado}.")
                return

            dados_ds = {
                "processo_numero": proc_higienizado,
                "relator": relator_higienizado,
                "tipo": tipo,
                "forma_envio": forma_envio,
                "recebido_confirmado": False,
                "cadastrado_por": nome_usuario,
                "observacoes": observacoes.strip(),
                "status": "pendente",
            }

            resultado = db_manager.inserir("despachos_ds", dados_ds)

            if resultado:
                ds_id = resultado.get("id")

                if ds_id:
                    salvos = 0
                    for of in st.session_state["ds_oficios_temp"]:
                        dados_of = {
                            "despacho_id": ds_id,
                            "tipo_documento": of["tipo_documento"],
                            "numero_oficio": of["numero_oficio"],
                            "destinatario": of["destinatario"],
                            "tipo_envio": of["tipo_envio"],
                            "status": of["status"],
                        }
                        res_of = db_manager.inserir("oficios_ds", dados_of)
                        if res_of:
                            salvos += 1

                    st.session_state["ds_oficios_temp"] = []
                    st.success(f"Despacho cadastrado com sucesso! {salvos} documento(s) vinculado(s).")
                    st.rerun()
                else:
                    st.success("Despacho cadastrado, mas houve erro ao vincular documentos. Adicione manualmente na lista.")
                    st.rerun()
            else:
                st.error("Erro ao cadastrar despacho. Tente novamente.")

def _listar_despachos(usuario, modo_edicao):
    """Lista todos os DS cadastrados com seus documentos vinculados."""
    st.markdown("#### Despachos Cadastrados")

    nome_usuario = usuario.get("nome", "")

    todos_ds = db_manager.buscar_todos(
        "despachos_ds",
        ordem_coluna="created_at",
        ordem_desc=True,
    )

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filtro_status = st.selectbox(
            "Filtrar por status",
            options=["todos", "pendente", "distribuido"],
            key="ds_filtro_status"
        )
    with col_f2:
        busca = st.text_input(
            "Buscar por processo",
            placeholder="Digite o numero...",
            key="ds_busca"
        )

    if filtro_status != "todos":
        todos_ds = [d for d in todos_ds if d.get("status") == filtro_status]

    if busca.strip():
        busca_lower = busca.strip().lower()
        todos_ds = [d for d in todos_ds if busca_lower in (d.get("processo_numero", "") or "").lower()]

    if not todos_ds:
        st.info("Nenhum despacho cadastrado.")
        return

    st.write(f"**{len(todos_ds)} despacho(s) encontrado(s).**")

    for ds in todos_ds:
        status_icone = "🟡" if ds.get("status") == "pendente" else "🟢"
        # Exibir alterado_por se existir, senao cadastrado_por
        exibido_por = ds.get("alterado_por") or ds.get("cadastrado_por", "")
        rotulo_por = "Alterado por" if ds.get("alterado_por") else "Cadastrado por"

        with st.expander(
            f"{status_icone} {ds.get('processo_numero', '')} | "
            f"{ds.get('tipo', '')} | "
            f"{ds.get('status', '').upper()} | "
            f"{rotulo_por}: {exibido_por}"
        ):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Processo:** {ds.get('processo_numero', '')}")
                st.write(f"**Relator:** {ds.get('relator', '-') or '-'}")
            with col2:
                st.write(f"**Tipo:** {ds.get('tipo', '')}")
                st.write(f"**Envio:** {ds.get('forma_envio', '-') or '-'}")
            with col3:
                st.write(f"**{rotulo_por}:** {exibido_por}")
                st.write(f"**Recebido:** {'Sim' if ds.get('recebido_confirmado') else 'Nao'}")

            if ds.get("observacoes"):
                st.write(f"**Observacoes:** {ds.get('observacoes')}")

            oficios = db_manager.buscar_todos(
                "oficios_ds",
                filtros={"despacho_id": ds["id"]},
                ordem_coluna="created_at",
                ordem_desc=False,
            )

            st.markdown("**Documentos Vinculados:**")
            if oficios:
                for of in oficios:
                    col_a, col_b, col_c, col_d, col_e = st.columns([2, 2, 2, 2, 1])
                    with col_a:
                        st.write(f"{of.get('tipo_documento', '')} {of.get('numero_oficio', '')}")
                    with col_b:
                        st.write(f"Para: {of.get('destinatario', '')}")
                    with col_c:
                        st.write(f"Envio: {of.get('tipo_envio', '')}")
                    with col_d:
                        st.write(f"Status: {of.get('status', '')}")
                    with col_e:
                        if modo_edicao and of.get("status") == "aguardando":
                            if st.button("OK", key=f"of_recv_{of['id']}", help="Marcar como recebido"):
                                db_manager.atualizar("oficios_ds", of["id"], {"status": "recebido"})
                                db_manager.atualizar("despachos_ds", ds["id"], {"alterado_por": nome_usuario})
                                st.rerun()
            else:
                st.caption("Nenhum documento vinculado.")

            if modo_edicao:
                # Form para editar dados do DS
                with st.form(f"form_edit_ds_{ds['id']}"):
                    st.markdown("**Editar Despacho**")
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        edit_processo = st.text_input(
                            "Processo",
                            value=ds.get("processo_numero", ""),
                            key=f"edit_proc_{ds['id']}"
                        )
                        edit_relator = st.text_input(
                            "Relator",
                            value=ds.get("relator", "") or "",
                            key=f"edit_rel_{ds['id']}"
                        )
                        edit_forma = st.selectbox(
                            "Forma de Envio",
                            options=["E-mail", "Mensageria", "Protocolo"],
                            index=["E-mail", "Mensageria", "Protocolo"].index(ds.get("forma_envio", "E-mail")) if ds.get("forma_envio") in ["E-mail", "Mensageria", "Protocolo"] else 0,
                            key=f"edit_forma_{ds['id']}"
                        )
                    with col_e2:
                        edit_tipo = st.selectbox(
                            "Tipo",
                            options=["Despacho Singular", "Sustentacao Oral"],
                            index=["Despacho Singular", "Sustentacao Oral"].index(ds.get("tipo", "Despacho Singular")) if ds.get("tipo") in ["Despacho Singular", "Sustentacao Oral"] else 0,
                            key=f"edit_tipo_{ds['id']}"
                        )
                        edit_obs = st.text_area(
                            "Observacoes",
                            value=ds.get("observacoes", "") or "",
                            height=60,
                            key=f"edit_obs_{ds['id']}"
                        )

                    if st.form_submit_button("Salvar Alteracoes"):
                        proc_higienizado = _higienizar_numero_processo(edit_processo) if edit_processo else ds.get("processo_numero", "")
                        relator_higienizado = _higienizar_relator(edit_relator) if edit_relator else None
                        db_manager.atualizar("despachos_ds", ds["id"], {
                            "processo_numero": proc_higienizado,
                            "relator": relator_higienizado,
                            "tipo": edit_tipo,
                            "forma_envio": edit_forma,
                            "observacoes": edit_obs.strip(),
                            "alterado_por": nome_usuario,
                        })
                        st.success("Alteracoes salvas!")
                        st.rerun()

                # Form para adicionar documento extra
                with st.form(f"form_add_oficio_extra_{ds['id']}"):
                    st.markdown("**Adicionar Documento**")
                    col_a1, col_a2 = st.columns(2)
                    with col_a1:
                        novo_tipo_doc = st.selectbox(
                            "Tipo",
                            options=["Oficio", "Memorando"],
                            key=f"extra_tipo_{ds['id']}"
                        )
                        novo_numero = st.text_input(
                            "Numero *",
                            key=f"extra_numero_{ds['id']}"
                        )
                    with col_a2:
                        novo_dest = st.text_input(
                            "Destinatario *",
                            key=f"extra_dest_{ds['id']}"
                        )
                        novo_envio = st.selectbox(
                            "Tipo de Envio",
                            options=["E-mail", "Mensageria", "Protocolo"],
                            key=f"extra_envio_{ds['id']}"
                        )

                    if st.form_submit_button("Adicionar"):
                        if novo_numero and novo_dest:
                            db_manager.inserir("oficios_ds", {
                                "despacho_id": ds["id"],
                                "tipo_documento": novo_tipo_doc,
                                "numero_oficio": novo_numero,
                                "destinatario": novo_dest,
                                "tipo_envio": novo_envio,
                                "status": "aguardando",
                            })
                            db_manager.atualizar("despachos_ds", ds["id"], {"alterado_por": nome_usuario})
                            st.success("Documento adicionado!")
                            st.rerun()
                        else:
                            st.error("Preencha numero e destinatario.")

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if not ds.get("recebido_confirmado"):
                        if st.button("Marcar Recebido", key=f"ds_recv_{ds['id']}"):
                            db_manager.atualizar("despachos_ds", ds["id"], {
                                "recebido_confirmado": True,
                                "alterado_por": nome_usuario,
                            })
                            st.rerun()
                with col_btn2:
                    if ds.get("status") == "pendente":
                        if st.button("Marcar como Distribuido", key=f"ds_dist_{ds['id']}"):
                            db_manager.atualizar("despachos_ds", ds["id"], {
                                "status": "distribuido",
                                "alterado_por": nome_usuario,
                            })
                            st.rerun()

def _renderizar_despachos_singulares(modo_edicao, usuario):
    """Funcao principal da aba de Despachos Singulares."""
    st.markdown("### Controle de Despachos Singulares e Sustentacoes Orais")
    st.caption(
        "Cadastre despachos singulares e sustentacoes orais. "
        "O sistema identificara automaticamente o processo quando ele for "
        "incluido na distribuicao da pauta."
    )

    tab_cad, tab_lista = st.tabs(["Cadastrar", "Lista"])

    with tab_cad:
        if modo_edicao:
            _cadastrar_despacho(usuario)
        else:
            st.info("Modo visualizacao. Apenas colaboradores do SEAT, gerentes e criador podem cadastrar.")

    with tab_lista:
        _listar_despachos(usuario, modo_edicao)
      
# ==================== MOTOR NIP ====================

def _extrair_texto_pdf(arquivo):
    """Extrai texto de um arquivo PDF usando pdfplumber."""
    try:
        import pdfplumber
        texto = ""
        with pdfplumber.open(arquivo) as pdf:
            for pagina in pdf.pages:
                pagina_texto = pagina.extract_text()
                if pagina_texto:
                    texto += pagina_texto + "\n"
        return texto
    except ImportError:
        st.error("Biblioteca 'pdfplumber' não instalada. Execute: pip install pdfplumber")
        return None
    except Exception as e:
        st.error(f"Erro ao extrair texto do PDF: {str(e)}")
        return None

def _identificar_relator(texto):
    """Identifica o relator pelo cabeçalho do PDF."""
    texto_upper = texto.upper()
    if "ANILCÉIA MACHADO" in texto_upper or "GABINETE DA CONSELHEIRA ANILCÉIA" in texto_upper:
        return "GCAM"
    elif "VINÍCIUS FRAGOSO" in texto_upper:
        return "VINICIUS_FRAGOSO"
    else:
        return "OUTRO"

def _extrair_voto(texto):
    """Extrai somente a parte do voto do texto completo do PDF."""
    import re

    padroes_inicio = [
        r'(?:Pelo exposto|Ante o exposto)[,\s]*(?:em harmonia com o órgão instrutivo,?\s*)?VOTO',
        r'VOTO\s+(?:no sentido|por|que)',
    ]

    for padrao in padroes_inicio:
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            inicio = match.start()
            voto = texto[inicio:]

            # Remover assinatura no final
            # Padrão: "Sala das Sessões, [data]. [NOME EM MAIÚSCULAS]"
            assinatura_padroes = [
                r'\n\s*Sala das Sessões.*',
                r'\n\s*(?:Conselheir[oa]|Auditor|Conselheiro-Substituto)\s+',
                r'\n\s*[A-ZÀ-Ú]{4,}\s*\n\s*[A-ZÀ-Ú]',
            ]
            for ass_padrao in assinatura_padroes:
                ass_match = re.search(ass_padrao, voto, re.DOTALL)
                if ass_match:
                    voto = voto[:ass_match.start()]

            return voto.strip()

    return None

def _aplicar_substituicoes(texto, regras):
    """Aplica substituições de frases e termos cadastradas no banco."""
    for regra in regras:
        if regra.get("tipo") in ("frase", "termo") and regra.get("ativo", True):
            procurar = regra["procurar"]
            substituir = regra["substituir_por"]
            texto = texto.replace(procurar, substituir)
    return texto

def _transformar_verbos(texto, regras):
    """Transforma verbos do imperativo para infinitivo."""
    import re

    for regra in regras:
        if regra.get("tipo") == "verbo" and regra.get("ativo", True):
            imperativo = regra["procurar"]
            infinitivo = regra["substituir_por"]
            texto = re.sub(
                re.escape(imperativo),
                infinitivo,
                texto,
                flags=re.IGNORECASE
            )
    return texto

def _ofuscar_cpf(texto):
    """Ofusca CPFs no texto (3 primeiros e 2 últimos dígitos)."""
    import re

    def ofuscar(match):
        cpf = match.group(0)
        return f"***.{cpf[4:11]}-**"

    return re.sub(r'\d{3}\.\d{3}\.\d{3}-\d{2}', ofuscar, texto)

def _formatar_numerais(texto):
    """Padroniza formatação de numerais romanos, letras de itens e abreviações."""
    import re

    # Roman numerals: I. → I –, I - → I –, I) → I –
    texto = re.sub(r'\b([IVXLCDM]+)[\.\)]\s*', r'\1 – ', texto)
    texto = re.sub(r'\b([IVXLCDM]+)\s*-\s*', r'\1 – ', texto)

    # Letter items: a. → a), a) stays a)
    texto = re.sub(r'\b([a-z])\.\s*', r'\1) ', texto)

    # Standardize n.º, n° → nº
    texto = texto.replace("n.º", "nº")
    texto = texto.replace("n°", "nº")

    # Add space after nº if missing: nº1.561 → nº 1.561
    texto = re.sub(r'nº(\d)', r'nº \1', texto)

    # LTDA – ME → LTDA. – ME (add period if missing)
    texto = re.sub(r'LTDA(?!\.)\s*[-–]\s*ME', 'LTDA. – ME', texto)

    return texto

def _remover_e_antes_itens(texto):
    """Remove 'e' antes de itens (I, II, a), b))."""
    import re

    # ; e V. → ; V.
    texto = re.sub(r';\s+e\s+([IVXLCDM]+)', r'; \1', texto)
    # ; e c. → ; c)
    texto = re.sub(r';\s+e\s+([a-z])\)', r'; \1)', texto)

    return texto

def _adicionar_preambulo(texto, relator):
    """Adiciona o preâmbulo correto baseado no relator e remove o texto original do voto."""
    import re

    if relator == "GCAM":
        preambulo = "O Tribunal, por unanimidade, de acordo com o voto da Relatora, decidiu:"
    elif relator == "VINICIUS_FRAGOSO":
        preambulo = "O Tribunal, por unanimidade, de acordo com o voto do Relator, Conselheiro-Substituto VINÍCIUS FRAGOSO, atuando em substituição ao Conselheiro TAL, nos termos do art. 44, § 3º, do RI/TCDF, decidiu:"
    else:
        preambulo = "O Tribunal, por unanimidade, de acordo com o voto do Relator, decidiu:"

    # Remove o texto original do voto
    padroes_remocao = [
        r'(?:Pelo exposto|Ante o exposto)[,\s]*(?:em harmonia com o órgão instrutivo,?\s*)?VOTO\s*(?:no sentido de que\s*)?(?:por\s+o\s*)?(?:o\s+)?egrégio Plenário:\s*',
        r'VOTO\s*(?:no sentido de que\s*)?(?:por\s+o\s*)?(?:o\s+)?egrégio Plenário:\s*',
        r'VOTO\s*(?:no sentido de que\s*)?',
    ]

    for padrao in padroes_remocao:
        texto = re.sub(padrao, '', texto, flags=re.IGNORECASE)

    return f"{preambulo} {texto.strip()}"

def _corrigir_hifenizacao(texto):
    """Remove hifens que quebram palavras no final de linhas (comum em extração de PDF)."""
    import re
    # Padrão: palavra + hífen + espaços + quebra de linha + palavra
    # Ex: "inscri-\nção" → "inscrição"
    # Ex: "in-\ngresso" → "ingresso"
    # Ex: "com-\nprovação" → "comprovação"
    # NÃO afeta: "e-DOC", "CBMDF-DF" (sem quebra de linha após o hífen)
    texto = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', texto)
    return texto
  
def _formatar_teleprompt(texto):
    """Formata o texto como teleprompt (texto corrido sem quebras)."""
    import re

    texto = re.sub(r'\n+', ' ', texto)
    texto = re.sub(r'\t+', ' ', texto)
    texto = re.sub(r'\r+', ' ', texto)
    texto = re.sub(r' +', ' ', texto)

    return texto.strip()

def _aplicar_negrito(texto):
    """Aplica negrito em numerais romanos, letras de itens, prazos e palavras-chave."""
    import re

    # Negito em numerais romanos seguidos de travessão
    texto = re.sub(r'\b([IVXLCDM]+)\s*–', r'**\1** –', texto)

    # Negrito em letras de itens: a), b), c)
    texto = re.sub(r'\b([a-z])\)', r'**\1)**', texto)

    # Negrito em prazos de 0 a 20 dias (incluindo "X (extenso) dias")
    for i in range(21):
        texto = re.sub(
            rf'\b{i}\s*(?:\([^)]+\)\s*)?dias?\b',
            lambda m: f'**{m.group(0)}**',
            texto,
            flags=re.IGNORECASE
        )

    # Negrito em palavras-chave
    palavras_chave = [
        "acórdãos", "Acórdão", "Urgente", "urgência",
        "prioridade", "Governador", "Suspender licitação",
        "suspender licitação"
    ]
    for palavra in palavras_chave:
        texto = re.sub(rf'\b{re.escape(palavra)}\b', f'**{palavra}**', texto)

    return texto

def _processar_voto(voto_texto, relator, regras):
    """Pipeline completo de processamento do voto."""
    # 0. Corrigir hifenização de palavras quebradas (NOVO)
    texto = _corrigir_hifenizacao(voto_texto)

    # 1. Substituições de frases e termos
    texto = _aplicar_substituicoes(texto, regras)

    # 2. Transformação de verbos (imperativo → infinitivo)
    texto = _transformar_verbos(texto, regras)

    # 3. Ofuscar CPF
    texto = _ofuscar_cpf(texto)

    # 4. Formatar numerais
    texto = _formatar_numerais(texto)

    # 5. Remover "e" antes de itens
    texto = _remover_e_antes_itens(texto)

    # 6. Adicionar preâmbulo
    texto = _adicionar_preambulo(texto, relator)

    # 7. Formatar como teleprompt
    texto = _formatar_teleprompt(texto)

    # 8. Aplicar negrito
    texto = _aplicar_negrito(texto)

    return texto

def _gerar_docx(texto_markdown):
    """Gera um arquivo .docx a partir do texto com marcações markdown de negrito."""
    try:
        from docx import Document
        from io import BytesIO
        import re

        doc = Document()
        paragrafo = doc.add_paragraph()

        partes = re.split(r'(\*\*.*?\*\*)', texto_markdown)
        for parte in partes:
            if parte.startswith('**') and parte.endswith('**'):
                run = paragrafo.add_run(parte[2:-2])
                run.bold = True
            else:
                paragrafo.add_run(parte)

        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue()
    except ImportError:
        return None
    except Exception:
        return None

def _obter_regras_padrao():
    """Retorna regras padrão caso não existam no banco."""
    return [
        {"procurar": "Ministério Público junto ao Tribunal de Contas do Distrito Federal", "substituir_por": "Ministério Público junto ao Tribunal", "tipo": "frase", "ativo": True},
        {"procurar": "os acórdãos que submeto à apreciação plenária", "substituir_por": "os acórdãos apresentados pelo Relator", "tipo": "frase", "ativo": True},
        {"procurar": "o Acórdão ora submetido pelo Relator", "substituir_por": "os acórdãos apresentados pelo Relator", "tipo": "frase", "ativo": True},
        {"procurar": "da decisão que vier a ser proferida", "substituir_por": "desta decisão", "tipo": "frase", "ativo": True},
        {"procurar": "da decisão que vier a ser prolatada", "substituir_por": "desta decisão", "tipo": "frase", "ativo": True},
        {"procurar": "presente feito", "substituir_por": "feito em apreço", "tipo": "frase", "ativo": True},
        {"procurar": "presentes autos", "substituir_por": "autos em exame", "tipo": "frase", "ativo": True},
        {"procurar": "em comento", "substituir_por": "em análise", "tipo": "frase", "ativo": True},
        {"procurar": "Ministério Público de Contas", "substituir_por": "Ministério Público junto ao Tribunal - MPjTCDF", "tipo": "frase", "ativo": True},
        {"procurar": "n.º", "substituir_por": "nº", "tipo": "termo", "ativo": True},
        {"procurar": "n°", "substituir_por": "nº", "tipo": "termo", "ativo": True},
        {"procurar": "tome", "substituir_por": "tomar", "tipo": "verbo", "ativo": True},
        {"procurar": "conheça", "substituir_por": "conhecer", "tipo": "verbo", "ativo": True},
        {"procurar": "dê", "substituir_por": "dar", "tipo": "verbo", "ativo": True},
        {"procurar": "declare", "substituir_por": "declarar", "tipo": "verbo", "ativo": True},
        {"procurar": "aprove", "substituir_por": "aprovar", "tipo": "verbo", "ativo": True},
        {"procurar": "expeça", "substituir_por": "expedir", "tipo": "verbo", "ativo": True},
        {"procurar": "autorize", "substituir_por": "autorizar", "tipo": "verbo", "ativo": True},
        {"procurar": "faculte", "substituir_por": "facultar", "tipo": "verbo", "ativo": True},
        {"procurar": "determine", "substituir_por": "determinar", "tipo": "verbo", "ativo": True},
        {"procurar": "considere", "substituir_por": "considerar", "tipo": "verbo", "ativo": True},
        {"procurar": "oficie", "substituir_por": "oficiar", "tipo": "verbo", "ativo": True},
        {"procurar": "postergue", "substituir_por": "postergar", "tipo": "verbo", "ativo": True},
        {"procurar": "notifique", "substituir_por": "notificar", "tipo": "verbo", "ativo": True},
        {"procurar": "julgue", "substituir_por": "julgar", "tipo": "verbo", "ativo": True},
        {"procurar": "responda", "substituir_por": "responder", "tipo": "verbo", "ativo": True},
        {"procurar": "ciência da decisão que vier a ser proferida", "substituir_por": "ciência desta decisão", "tipo": "frase", "ativo": True},
        {"procurar": "ciência da decisão que vier a ser prolatada", "substituir_por": "ciência desta decisão", "tipo": "frase", "ativo": True},
    ]

def _renderizar_motor_nip(modo_edicao, usuario):
    """Função principal do Motor NIP - Edição Automática de Votos."""
    st.markdown("### Motor NIP - Edição Automática de Votos")
    st.caption(
        "Faça upload do PDF do relatório/voto. O sistema extrai o voto, "
        "aplica as regras de edição e entrega o texto pronto no formato teleprompt."
    )

    st.markdown("---")

    # Upload do PDF
    uploaded_file = st.file_uploader(
        "📄 Upload do PDF do Relatório/Voto",
        type=['pdf'],
        key="motor_nip_upload"
    )

    if uploaded_file is not None:
        with st.spinner("Processando PDF..."):
            # 1. Extrair texto do PDF
            texto_completo = _extrair_texto_pdf(uploaded_file)

            if not texto_completo:
                st.error("Não foi possível extrair texto do PDF.")
                return

            # 2. Identificar relator
            relator = _identificar_relator(texto_completo)
            relator_nome = {
                "GCAM": "Anilcéia Machado (Relatora)",
                "VINICIUS_FRAGOSO": "Vinícius Fragoso (Substituto)",
                "OUTRO": "Relator identificado no PDF"
            }
            st.info(f"**Relator identificado:** {relator_nome.get(relator, relator)}")

            # 3. Extrair voto
            voto_extraido = _extrair_voto(texto_completo)

            if not voto_extraido:
                st.error("Não foi possível identificar o voto no PDF. Verifique se o arquivo contém a seção de voto.")
                return

            # 4. Buscar regras do banco
            try:
                regras = db_manager.buscar_todos(
                    "regras_substituicao_nip",
                    filtros={"ativo": True},
                    ordem_coluna="ordem",
                    ordem_desc=False,
                )
            except Exception:
                regras = []

            # Se não houver regras no banco, usar regras padrão
            if not regras:
                regras = _obter_regras_padrao()

            # 5. Processar o voto
            texto_editado = _processar_voto(voto_extraido, relator, regras)

            # 6. Exibir resultado
            st.markdown("---")
            st.markdown("#### ✅ Voto Editado")

            # Preview com formatação (bold visível)
            st.markdown(f"> {texto_editado}")

            st.markdown("---")

            # Caixa de texto para copiar (texto plano sem markdown)
            texto_plain = texto_editado.replace("**", "")
            st.text_area(
                "📋 Texto para copiar (clique na caixa, Ctrl+A, Ctrl+C):",
                value=texto_plain,
                height=300,
                key="motor_nip_resultado"
            )

            # Download como .docx (com negrito preservado)
            docx_data = _gerar_docx(texto_editado)
            if docx_data:
                st.download_button(
                    label="📥 Baixar como Word (.docx) — com negrito",
                    data=docx_data,
                    file_name="voto_editado.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

            # Mostrar voto original (colapsável)
            with st.expander("Ver voto original extraído do PDF"):
                st.text(voto_extraido)

# ============================================================
# FUNCAO PRINCIPAL
# ============================================================

def renderizar(usuario: dict, modo_edicao: bool = False):
    """
    Funcao principal do modulo SEAT.
    """
    nome = usuario.get("nome", "Usuario")
    cargo = usuario.get("cargo", "operacional")
    setor = usuario.get("setor", "SEAT")

    st.markdown(f"**Colaborador:** {nome} | **Cargo:** {cargo} | **Setor:** {setor}")

    if not modo_edicao:
        st.info("Voce esta em modo de visualizacao. Operacoes de edicao estao bloqueadas.")

    st.markdown("---")

    # renderizar_sidebar ja e chamada pelo app.py via sidebar_placeholder
    # Apenas _renderizar_sidebar_ds precisa ser chamada aqui
    _renderizar_sidebar_ds(usuario)

    tab_pauta, tab_distribuicao, tab_ds, tab_motor, tab_DOETCDF = st.tabs([
        "Pauta Ativa",
        "Distribuicao",
        "Despachos Singulares",
        "Motor NIP",
        "Escala DOETCDF (em breve)",
    ])

    with tab_pauta:
        _renderizar_pauta_ativa(modo_edicao, usuario)

    with tab_distribuicao:
        _renderizar_distribuicao(modo_edicao, usuario)

    with tab_ds:
        _renderizar_despachos_singulares(modo_edicao, usuario)

    with tab_motor:
        _renderizar_motor_nip(modo_edicao, usuario)
      
    with tab_DOETCDF:
        st.info("A Escala de Publicacao DOETCDF sera implementada na sub-etapa 1I.")
