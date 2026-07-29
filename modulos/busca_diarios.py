"""
Busca nos Diários Oficiais — DODF e DOE-TCDF
Módulo de busca em tempo real, sem armazenamento em banco.
"""

import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import streamlit as st

# ============================================================
# CONFIGURAÇÃO
# ============================================================
DODF_BASE = "https://dodf.df.gov.br"
DOE_BASE = "https://doe.tc.df.gov.br"

# ============================================================
# FUNÇÃO PRINCIPAL — RENDERIZA A ABA DE BUSCA NO GAB
# ============================================================
def _renderizar_busca_diarios(usuario):
    """Renderiza a aba de busca nos diários oficiais.
    Busca em tempo real — não armazena nada no banco."""

    st.markdown("### 🔍 Busca nos Diários Oficiais")
    st.caption("Pesquise termos específicos no DODF e DOE-TCDF. Resultados em tempo real, sem armazenar no banco.")

    # Formulário de busca
    col1, col2 = st.columns([3, 1])
    with col1:
        termo = st.text_input(
            "Termo de busca",
            placeholder="Ex: Resolução 416, nome do servidor, portaria...",
            key="busca_diarios_termo"
        )
    with col2:
        fonte = st.selectbox("Fonte", ["Ambos", "DODF", "DOE-TCDF"], key="busca_diarios_fonte")

    col3, col4, col5 = st.columns(3)
    with col3:
        data_inicio = st.date_input("Data inicial", datetime.now() - timedelta(days=7), key="busca_diarios_inicio")
    with col4:
        data_fim = st.date_input("Data final", datetime.now(), key="busca_diarios_fim")
    with col5:
        st.write("")
        st.write("")
        buscar = st.button("🔍 Buscar", type="primary", use_container_width=True, key="busca_diarios_btn")

    if buscar:
        if not termo or len(termo.strip()) < 3:
            st.warning("Digite pelo menos 3 caracteres para buscar.")
            return

        resultados = []

        with st.spinner("Buscando nos diários oficiais..."):

            # Buscar no DOE-TCDF
            if fonte in ["Ambos", "DOE-TCDF"]:
                try:
                    resultados_doe = _buscar_doe_tcdf(termo.strip())
                    resultados.extend(resultados_doe)
                except Exception:
                    pass

            # Buscar no DODF
            if fonte in ["Ambos", "DODF"]:
                try:
                    resultados_dodf = _buscar_dodf(termo.strip(), data_inicio, data_fim)
                    resultados.extend(resultados_dodf)
                except Exception:
                    pass

        # Exibir resultados
        if resultados:
            st.success(f"✅ {len(resultados)} resultado(s) encontrado(s) para '{termo}'")

            for i, r in enumerate(resultados, 1):
                icone = "📄" if r['fonte'] == 'DOE-TCDF' else "📰"
                with st.expander(
                    f"{icone} {r['fonte']} — {r.get('data', '—')} — {r.get('titulo', '')[:70]}...",
                    expanded=(i == 1)
                ):
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.write(f"**Fonte:** {r['fonte']}")
                        st.write(f"**Data:** {r.get('data', '—')}")
                    with col_b:
                        st.write(f"**Seção:** {r.get('secao', '—')}")
                        st.write(f"**Edição:** {r.get('edicao', '—')}")
                    with col_c:
                        st.write(f"**Página:** {r.get('pagina', '—')}")
                        if r.get('url'):
                            st.markdown(f"[🔗 Abrir original]({r['url']})")

                    st.markdown("**Trecho encontrado:**")
                    st.text_area(
                        "",
                        r.get('trecho', ''),
                        height=200,
                        key=f"trecho_resultado_{i}",
                        disabled=True
                    )

                    if r.get('url'):
                        st.caption("💡 Para tirar um print, clique no link acima para abrir a publicação original.")
        else:
            st.warning(f"Nenhum resultado encontrado para '{termo}' no período selecionado.")

# ============================================================
# BUSCA NO DOE-TCDF
# ============================================================
def _buscar_doe_tcdf(termo):
    """Busca um termo na edição atual do DOE-TCDF."""
    resultados = []

    try:
        resp = requests.get(DOE_BASE, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code != 200:
            return resultados

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Extrair número da edição e data
        edicao = ""
        data_pub = ""
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "strong", "b"]):
            texto = tag.get_text(strip=True)
            if "Edição" in texto and "de" in texto:
                match_num = re.search(r'n[ºo°]\s*(\d+)', texto)
                if match_num:
                    edicao = match_num.group(1)
                data_pub = texto
                break

        # Extrair texto completo
        texto_completo = soup.get_text(separator="\n", strip=True)
        texto_completo = re.sub(r'\n{3,}', '\n\n', texto_completo)

        # Dividir em publicações (separadas por "Extrato")
        partes = re.split(r'\n\s*Extrato\s*\n', texto_completo)

        termo_upper = termo.upper()

        for parte in partes:
            parte = parte.strip()
            if len(parte) < 50:
                continue

            if termo_upper in parte.upper():
                secao = _identificar_secao_doe(parte)
                trecho = _extrair_trecho_busca(parte, termo, contexto=300)
                titulo = parte.split('\n')[0][:100] if parte else "Publicação"

                resultados.append({
                    'fonte': 'DOE-TCDF',
                    'data': data_pub or datetime.now().strftime('%d/%m/%Y'),
                    'secao': secao,
                    'edicao': f"nº {edicao}" if edicao else "—",
                    'pagina': "—",
                    'titulo': titulo,
                    'trecho': trecho,
                    'url': DOE_BASE
                })

    except Exception:
        pass

    return resultados

# ============================================================
# BUSCA NO DODF
# ============================================================
def _buscar_dodf(termo, data_inicio, data_fim):
    """Busca um termo no DODF dentro de um período."""
    resultados = []

    # Tentar API de busca do DODF
    try:
        data_ini_str = data_inicio.strftime("%d/%m/%Y")
        data_fim_str = data_fim.strftime("%d/%m/%Y")

        # Tentar POST (API de busca)
        url_busca = f"{DODF_BASE}/dodf/buscar"
        payload = {
            "termo": termo,
            "data_inicio": data_ini_str,
            "data_fim": data_fim_str,
            "pagina": 1
        }

        resp = requests.post(url_busca, json=payload, timeout=60, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

        if resp.status_code == 200:
            data = resp.json()
            resultados = _processar_resultados_dodf_api(data, termo)
            if resultados:
                return resultados

        # Fallback: tentar GET
        params = {
            "termo": termo,
            "data_inicio": data_ini_str,
            "data_fim": data_fim_str
        }
        resp = requests.get(url_busca, params=params, timeout=60, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        })

        if resp.status_code == 200:
            data = resp.json()
            resultados = _processar_resultados_dodf_api(data, termo)
            if resultados:
                return resultados

    except Exception:
        pass

    # Fallback 2: Buscar dia a dia por scraping
    try:
        resultados = _buscar_dodf_scraping(termo, data_inicio, data_fim)
    except Exception:
        pass

    return resultados

# ============================================================
# PROCESSAR RESULTADOS DA API DO DODF
# ============================================================
def _processar_resultados_dodf_api(data, termo):
    """Processa os resultados retornados pela API de busca do DODF."""
    resultados = []

    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "resultados" in data:
            items = data["resultados"]
        elif "data" in data:
            items = data["data"]
        elif "items" in data:
            items = data["items"]

    for item in items:
        if not isinstance(item, dict):
            continue

        texto = item.get("texto", item.get("conteudo", item.get("content", "")))
        titulo = item.get("titulo", item.get("title", ""))
        url = item.get("url", item.get("link", ""))
        data_pub = item.get("data", item.get("data_publicacao", ""))
        pagina = item.get("pagina", item.get("page", "—"))
        secao = item.get("secao", item.get("section", "—"))
        edicao = item.get("edicao", item.get("edition", "—"))

        if texto and termo.upper() in texto.upper():
            trecho = _extrair_trecho_busca(texto, termo, contexto=300)
            resultados.append({
                'fonte': 'DODF',
                'data': data_pub or "—",
                'secao': secao,
                'edicao': edicao,
                'pagina': str(pagina) if pagina else "—",
                'titulo': titulo or "Publicação DODF",
                'trecho': trecho,
                'url': url or DODF_BASE
            })

    return resultados

# ============================================================
# FALLBACK: BUSCAR NO DODF POR SCRAPING DIA A DIA
# ============================================================
def _buscar_dodf_scraping(termo, data_inicio, data_fim):
    """Busca no DODF por scraping, dia a dia."""
    resultados = []
    termo_upper = termo.upper()

    # Limitar a 7 dias para evitar timeout
    delta = data_fim - data_inicio
    if delta.days > 7:
        data_inicio = data_fim - timedelta(days=7)

    data_atual = data_inicio
    while data_atual <= data_fim:
        if data_atual.weekday() >= 5:
            data_atual += timedelta(days=1)
            continue

        data_str = data_atual.strftime("%Y-%m-%d")

        try:
            url_lista = f"{DODF_BASE}/dodf/materia/listar?data={data_str}"
            resp = requests.get(url_lista, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            if resp.status_code == 200:
                try:
                    materias = resp.json()
                    if isinstance(materias, list):
                        for mat in materias:
                            texto = mat.get("texto", mat.get("conteudo", ""))
                            if texto and termo_upper in texto.upper():
                                trecho = _extrair_trecho_busca(texto, termo, contexto=300)
                                resultados.append({
                                    'fonte': 'DODF',
                                    'data': data_atual.strftime("%d/%m/%Y"),
                                    'secao': mat.get("secao", mat.get("tipo", "—")),
                                    'edicao': mat.get("edicao", "—"),
                                    'pagina': str(mat.get("pagina", "—")),
                                    'titulo': mat.get("titulo", "Matéria DODF"),
                                    'trecho': trecho,
                                    'url': mat.get("url", f"{DODF_BASE}/dodf/materia/visualizar?data={data_str}")
                                })
                except Exception:
                    pass
        except Exception:
            pass

        data_atual += timedelta(days=1)

    return resultados

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def _identificar_secao_doe(texto):
    """Identifica a seção do DOE-TCDF."""
    texto_upper = texto.upper()
    if "PRESIDÊNCIA" in texto_upper or "PORTARIA" in texto_upper:
        return "Atos da Presidência"
    elif "SEGEDAM" in texto_upper:
        return "Atos da Segedam"
    elif "SEGEP" in texto_upper:
        return "Atos da Segep"
    elif "SESBE" in texto_upper:
        return "Atos da Sesbe"
    return "Geral"

def _extrair_trecho_busca(texto, termo, contexto=300):
    """Extrai um trecho do texto ao redor do termo encontrado."""
    idx = texto.upper().find(termo.upper())
    if idx == -1:
        return texto[:500]

    inicio = max(0, idx - contexto)
    fim = min(len(texto), idx + len(termo) + contexto)
    trecho = texto[inicio:fim]

    if inicio > 0:
        trecho = "..." + trecho
    if fim < len(texto):
        trecho = trecho + "..."

    trecho = re.sub(r'\n{3,}', '\n\n', trecho)
    return trecho.strip()
