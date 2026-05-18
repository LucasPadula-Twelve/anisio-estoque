#!/usr/bin/env python3
"""
Scraper Anísio Automóveis - Selenium
Extrai todos os veículos do estoque, gera base de conhecimento para o Omni
e mantém histórico de veículos vendidos.

Uso diário: python3 scraper_anisio.py
"""

import json
import csv
import os
import re
import time
import subprocess
import shutil
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ============================================================
# CONFIGURAÇÕES
# ============================================================
BASE_URL = "https://www.anisioautomoveis.com.br"
ESTOQUE_URL = f"{BASE_URL}/estoque/"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
ESTOQUE_JSON = os.path.join(OUTPUT_DIR, "estoque_atual.json")
HISTORICO_JSON = os.path.join(OUTPUT_DIR, "historico_vendidos.json")
BASE_CONHECIMENTO_TXT = os.path.join(OUTPUT_DIR, "base_conhecimento_omni.txt")
ESTOQUE_CSV = os.path.join(OUTPUT_DIR, "estoque_atual.csv")
LOG_FILE = os.path.join(OUTPUT_DIR, "scraper_log.txt")

# GitHub - Repositório para publicação da base de conhecimento
GITHUB_REPO = "LucasPadula-Twelve/anisio-estoque"
GITHUB_BRANCH = "main"
# URL pública raw do GitHub (após push)
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/base_conhecimento_omni.txt"


def log(msg):
    """Registra mensagem no log com timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def criar_driver():
    """Cria e retorna uma instância do Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=pt-BR")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    options.binary_location = "/usr/bin/chromium-browser"
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def coletar_urls_veiculos(driver):
    """Acessa a página de estoque e coleta todas as URLs dos veículos."""
    log("Acessando página de estoque...")
    driver.get(ESTOQUE_URL)
    time.sleep(3)

    urls = set()

    # Clicar em "Mais veículos" até não haver mais
    while True:
        # Coletar URLs visíveis
        links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/veiculo/"]')
        for link in links:
            href = link.get_attribute("href")
            if href and "/veiculo/" in href and href != f"{BASE_URL}/veiculo/":
                # Filtrar apenas links de veículos individuais (com ID numérico)
                parts = href.replace(f"{BASE_URL}/veiculo/", "").strip("/")
                if parts and parts[0].isdigit():
                    urls.add(href)

        # Tentar clicar em "Mais veículos"
        try:
            load_more = driver.find_element(By.CSS_SELECTOR, "button.facetwp-load-more")
            if load_more.is_displayed() and load_more.is_enabled():
                driver.execute_script("arguments[0].click();", load_more)
                log(f"  Clicou 'Mais veículos'... ({len(urls)} URLs coletadas até agora)")
                time.sleep(3)
            else:
                break
        except Exception:
            break

    # Coletar URLs após último clique
    links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/veiculo/"]')
    for link in links:
        href = link.get_attribute("href")
        if href and "/veiculo/" in href and href != f"{BASE_URL}/veiculo/":
            parts = href.replace(f"{BASE_URL}/veiculo/", "").strip("/")
            if parts and parts[0].isdigit():
                urls.add(href)

    log(f"Total de {len(urls)} veículos encontrados no estoque.")
    return sorted(urls)


def extrair_dados_veiculo(driver, url):
    """Acessa a página de um veículo e extrai todos os dados disponíveis."""
    driver.get(url)
    time.sleep(2)

    veiculo = {
        "url": url,
        "id": url.split("/veiculo/")[1].split("-")[0] if "/veiculo/" in url else "",
        "data_coleta": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Nome do veículo
    try:
        titulo = driver.find_element(By.CSS_SELECTOR, "h1, .fl-heading-text")
        veiculo["nome"] = titulo.text.strip()
    except Exception:
        veiculo["nome"] = ""

    # Preço
    try:
        preco_el = driver.find_element(By.XPATH, "//*[contains(text(), 'R$')]")
        preco_text = preco_el.text.strip()
        # Pegar apenas a primeira linha com R$
        for line in preco_text.split("\n"):
            if "R$" in line:
                veiculo["preco"] = line.strip()
                break
    except Exception:
        veiculo["preco"] = ""

    # Ficha técnica (tabela de dados)
    ficha = {}
    try:
        # Procurar pares label/valor na ficha técnica
        labels = driver.find_elements(By.CSS_SELECTOR, ".fl-post-info-term")
        values = driver.find_elements(By.CSS_SELECTOR, ".fl-post-info-value")
        for label, value in zip(labels, values):
            key = label.text.strip().lower().replace("/", "_").replace(" ", "_")
            val = value.text.strip()
            if key and val:
                ficha[key] = val
    except Exception:
        pass

    # Fallback: tentar extrair dados da ficha de outra forma
    if not ficha:
        try:
            info_items = driver.find_elements(By.CSS_SELECTOR, ".q11-post-info-item, .fl-post-info-item")
            for item in info_items:
                text = item.text.strip()
                if ":" in text:
                    parts = text.split(":", 1)
                    key = parts[0].strip().lower().replace("/", "_").replace(" ", "_")
                    val = parts[1].strip()
                    if key and val:
                        ficha[key] = val
        except Exception:
            pass

    # Fallback 2: extrair da meta/title da página
    # Formato: "Honda HR-V 1.5 ... 2019/20 Gasolina Vinho 4P 81.000 km em Piracicaba"
    try:
        title = driver.title
        veiculo["titulo_pagina"] = title
        # Extrair campos faltantes do título

        # Ano/Modelo: padrão XXXX/XX ou XXXX/XXXX
        if "ano_modelo" not in ficha or not ficha.get("ano_modelo"):
            ano_match = re.search(r'(\d{4}/\d{2,4})', title)
            if ano_match:
                ficha["ano_modelo"] = ano_match.group(1)
        # Combustível
        combustiveis = ["Gasolina", "Flex", "Diesel", "Elétrico", "Híbrido", "GNV"]
        if "combustivel" not in ficha or not ficha.get("combustivel"):
            for comb in combustiveis:
                if comb.lower() in title.lower():
                    ficha["combustivel"] = comb
                    break
        # Cor
        cores = ["Branco", "Preto", "Prata", "Cinza", "Vermelho", "Azul", "Vinho",
                 "Verde", "Amarelo", "Marrom", "Bege", "Dourado", "Laranja", "Grafite"]
        if "cor" not in ficha or not ficha.get("cor"):
            for cor in cores:
                if cor.lower() in title.lower():
                    ficha["cor"] = cor
                    break
        # KM
        if "km" not in ficha or not ficha.get("km"):
            km_match = re.search(r'([\d\.]+)\s*km', title.lower())
            if km_match:
                ficha["km"] = km_match.group(1)
        # Portas
        if "portas" not in ficha or not ficha.get("portas"):
            portas_match = re.search(r'(\d)P', title)
            if portas_match:
                ficha["portas"] = portas_match.group(1)
    except Exception:
        pass

    # Tentar extrair campos específicos via XPath
    campos_xpath = {
        "ano_modelo": "ANO/MODELO",
        "cambio": "CÂMBIO",
        "combustivel": "COMBUSTÍVEL",
        "cor": "COR",
        "portas": "PORTAS",
        "km": "KM",
    }
    for campo, label_text in campos_xpath.items():
        if campo not in ficha or not ficha.get(campo):
            try:
                label_el = driver.find_element(
                    By.XPATH,
                    f"//*[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{label_text}')]"
                )
                parent = label_el.find_element(By.XPATH, "..")
                all_text = parent.text.strip()
                if label_text in all_text.upper():
                    val = all_text.upper().replace(label_text, "").strip().strip(":")
                    if val:
                        ficha[campo] = val
            except Exception:
                pass

    # Câmbio: inferir dos opcionais se não encontrado
    if "cambio" not in ficha or not ficha.get("cambio"):
        nome_lower = veiculo.get("nome", "").lower()
        if "automático" in nome_lower or "automatico" in nome_lower or "cvt" in nome_lower:
            ficha["cambio"] = "Automático"
        else:
            ficha["cambio"] = "Manual"

    veiculo["ficha_tecnica"] = ficha

    # Marca (extrair do título da página ou do card)
    try:
        # Tentar pegar a marca do breadcrumb ou de um elemento específico
        marca_el = driver.find_elements(By.CSS_SELECTOR, ".fl-post-info-value")
        # A marca geralmente aparece no título da página
        title = driver.title
        marcas_conhecidas = [
            "Honda", "Volkswagen", "Fiat", "Chevrolet", "Jeep", "Hyundai",
            "Toyota", "Nissan", "Renault", "Ford", "Chery", "Peugeot",
            "Citroën", "Mitsubishi", "Kia", "BMW", "Mercedes", "Audi"
        ]
        veiculo["marca"] = ""
        for marca in marcas_conhecidas:
            if marca.lower() in title.lower():
                veiculo["marca"] = marca
                break
    except Exception:
        veiculo["marca"] = ""

    # Descrição
    try:
        desc_elements = driver.find_elements(By.CSS_SELECTOR, ".fl-module-content .fl-rich-text p, .fl-module-content .fl-rich-text")
        descricao_parts = []
        for el in desc_elements:
            text = el.text.strip()
            if text and len(text) > 20 and "R$" not in text and "CARACTERÍSTICAS" not in text.upper():
                descricao_parts.append(text)
        veiculo["descricao"] = " ".join(descricao_parts).strip()
    except Exception:
        veiculo["descricao"] = ""

    # Fallback para descrição
    if not veiculo["descricao"]:
        try:
            all_text = driver.find_element(By.TAG_NAME, "body").text
            # Procurar bloco de texto descritivo (geralmente contém "IPVA", "LAUDO", etc.)
            for line in all_text.split("\n"):
                line = line.strip()
                if any(kw in line.upper() for kw in ["IPVA", "LAUDO", "IMPECÁVEL", "CONSERVADO", "REVISÕES", "MANUAL"]):
                    veiculo["descricao"] = line
                    break
        except Exception:
            pass

    # Características / Opcionais
    try:
        caracteristicas = []
        # Procurar a seção de características
        body_text = driver.find_element(By.TAG_NAME, "body").text
        in_caract = False
        for line in body_text.split("\n"):
            line = line.strip()
            if "CARACTERÍSTICAS" in line.upper() or "CARACTERISTICAS" in line.upper():
                in_caract = True
                continue
            if in_caract:
                if line and line.isupper() and len(line) > 2 and "VER TODO" not in line.upper():
                    caracteristicas.append(line)
                elif line and not line.isupper() and len(caracteristicas) > 0:
                    # Fim da seção de características
                    break
        veiculo["caracteristicas"] = caracteristicas
    except Exception:
        veiculo["caracteristicas"] = []

    # Fotos
    try:
        fotos = []
        imgs = driver.find_elements(By.CSS_SELECTOR, "img[src*='wp-content/uploads']")
        for img in imgs:
            src = img.get_attribute("src") or img.get_attribute("data-src")
            if src and "uploads" in src:
                # Remover parâmetros de resize
                clean_src = src.split("?")[0] if "?" in src else src
                if clean_src not in fotos:
                    fotos.append(clean_src)
        veiculo["fotos"] = fotos
    except Exception:
        veiculo["fotos"] = []

    return veiculo


def atualizar_historico(estoque_atual):
    """Compara o estoque atual com o anterior e registra veículos vendidos."""
    # Carregar estoque anterior
    estoque_anterior = []
    if os.path.exists(ESTOQUE_JSON):
        try:
            with open(ESTOQUE_JSON, "r", encoding="utf-8") as f:
                estoque_anterior = json.load(f)
        except Exception:
            estoque_anterior = []

    # Carregar histórico de vendidos
    historico = []
    if os.path.exists(HISTORICO_JSON):
        try:
            with open(HISTORICO_JSON, "r", encoding="utf-8") as f:
                historico = json.load(f)
        except Exception:
            historico = []

    # IDs atuais
    ids_atuais = {v["id"] for v in estoque_atual}
    ids_anteriores = {v["id"] for v in estoque_anterior}

    # Veículos que saíram do estoque = provavelmente vendidos
    ids_vendidos = ids_anteriores - ids_atuais
    novos_vendidos = 0

    # IDs já registrados no histórico
    ids_historico = {v["id"] for v in historico}

    for veiculo_anterior in estoque_anterior:
        if veiculo_anterior["id"] in ids_vendidos and veiculo_anterior["id"] not in ids_historico:
            veiculo_anterior["status"] = "VENDIDO"
            veiculo_anterior["data_saida"] = datetime.now().strftime("%Y-%m-%d")
            historico.append(veiculo_anterior)
            novos_vendidos += 1

    # Veículos novos no estoque
    ids_novos = ids_atuais - ids_anteriores
    if ids_novos:
        log(f"  {len(ids_novos)} veículo(s) NOVO(S) no estoque.")

    if novos_vendidos > 0:
        log(f"  {novos_vendidos} veículo(s) marcado(s) como VENDIDO(S).")

    # Salvar histórico atualizado
    with open(HISTORICO_JSON, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)

    return historico, ids_novos, ids_vendidos


def gerar_base_conhecimento(estoque):
    """Gera o arquivo de base de conhecimento formatado para o Omni."""
    lines = []
    lines.append("=" * 60)
    lines.append("BASE DE CONHECIMENTO - ESTOQUE ANÍSIO AUTOMÓVEIS")
    lines.append(f"Atualizado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}")
    lines.append(f"Total de veículos disponíveis: {len(estoque)}")
    lines.append("=" * 60)
    lines.append("")

    for i, v in enumerate(estoque, 1):
        ficha = v.get("ficha_tecnica", {})
        lines.append(f"--- VEÍCULO {i} ---")
        lines.append(f"Nome: {v.get('nome', 'N/A')}")
        lines.append(f"Marca: {v.get('marca', 'N/A')}")
        lines.append(f"Preço: {v.get('preco', 'N/A')}")
        lines.append(f"Ano/Modelo: {ficha.get('ano_modelo', ficha.get('ano/modelo', 'N/A'))}")
        lines.append(f"Câmbio: {ficha.get('cambio', ficha.get('câmbio', 'N/A'))}")
        lines.append(f"Combustível: {ficha.get('combustivel', ficha.get('combustível', 'N/A'))}")
        lines.append(f"Cor: {ficha.get('cor', 'N/A')}")
        lines.append(f"Portas: {ficha.get('portas', 'N/A')}")
        lines.append(f"Quilometragem: {ficha.get('km', 'N/A')}")
        lines.append(f"Link: {v.get('url', 'N/A')}")

        if v.get("descricao"):
            lines.append(f"Descrição: {v['descricao']}")

        if v.get("caracteristicas"):
            lines.append(f"Opcionais: {', '.join(v['caracteristicas'])}")

        lines.append("")

    # Salvar
    with open(BASE_CONHECIMENTO_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log(f"Base de conhecimento gerada: {BASE_CONHECIMENTO_TXT}")


def gerar_csv(estoque):
    """Gera um CSV com o estoque atual."""
    if not estoque:
        return

    fieldnames = [
        "id", "nome", "marca", "preco", "ano_modelo", "cambio",
        "combustivel", "cor", "portas", "km", "descricao",
        "opcionais", "url", "data_coleta"
    ]

    with open(ESTOQUE_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for v in estoque:
            ficha = v.get("ficha_tecnica", {})
            row = {
                "id": v.get("id", ""),
                "nome": v.get("nome", ""),
                "marca": v.get("marca", ""),
                "preco": v.get("preco", ""),
                "ano_modelo": ficha.get("ano_modelo", ficha.get("ano/modelo", "")),
                "cambio": ficha.get("cambio", ficha.get("câmbio", "")),
                "combustivel": ficha.get("combustivel", ficha.get("combustível", "")),
                "cor": ficha.get("cor", ""),
                "portas": ficha.get("portas", ""),
                "km": ficha.get("km", ""),
                "descricao": v.get("descricao", ""),
                "opcionais": ", ".join(v.get("caracteristicas", [])),
                "url": v.get("url", ""),
                "data_coleta": v.get("data_coleta", ""),
            }
            writer.writerow(row)

    log(f"CSV gerado: {ESTOQUE_CSV}")


def publicar_no_github():
    """Faz commit e push dos arquivos atualizados para o GitHub."""
    try:
        log("Publicando no GitHub...")
        
        # Verificar se estamos dentro de um repositório git
        git_dir = os.path.join(OUTPUT_DIR, ".git")
        if not os.path.exists(git_dir):
            log("  Repositório git não encontrado. Clonando...")
            # Clonar em diretório temporário e mover .git
            tmp_dir = os.path.join(OUTPUT_DIR, "_tmp_clone")
            subprocess.run(
                ["gh", "repo", "clone", GITHUB_REPO, tmp_dir],
                capture_output=True, text=True, cwd=OUTPUT_DIR
            )
            # Mover .git para o diretório de trabalho
            shutil.move(os.path.join(tmp_dir, ".git"), git_dir)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            # Configurar git
            subprocess.run(["git", "config", "user.email", "scraper@anisio.com.br"], cwd=OUTPUT_DIR)
            subprocess.run(["git", "config", "user.name", "Scraper Anisio"], cwd=OUTPUT_DIR)
        
        # Adicionar arquivos relevantes
        arquivos = [
            "base_conhecimento_omni.txt",
            "estoque_atual.json",
            "estoque_atual.csv",
            "historico_vendidos.json",
        ]
        for arq in arquivos:
            caminho = os.path.join(OUTPUT_DIR, arq)
            if os.path.exists(caminho):
                subprocess.run(["git", "add", arq], cwd=OUTPUT_DIR)
        
        # Commit com data/hora
        data_hora = datetime.now().strftime("%d/%m/%Y %H:%M")
        msg = f"Atualização automática do estoque - {data_hora}"
        result = subprocess.run(
            ["git", "commit", "-m", msg],
            capture_output=True, text=True, cwd=OUTPUT_DIR
        )
        
        if "nothing to commit" in result.stdout:
            log("  Nenhuma alteração no estoque. Nada para publicar.")
            return True
        
        # Push
        result = subprocess.run(
            ["git", "push", "origin", GITHUB_BRANCH],
            capture_output=True, text=True, cwd=OUTPUT_DIR
        )
        
        if result.returncode == 0:
            log(f"  Push realizado com sucesso!")
            log(f"  URL pública da base: {GITHUB_RAW_URL}")
            return True
        else:
            log(f"  ERRO no push: {result.stderr}")
            return False
            
    except Exception as e:
        log(f"  ERRO ao publicar no GitHub: {e}")
        return False


def main():
    log("=" * 50)
    log("INICIANDO SCRAPER ANÍSIO AUTOMÓVEIS")
    log("=" * 50)

    driver = criar_driver()

    try:
        # 1. Coletar URLs de todos os veículos
        urls = coletar_urls_veiculos(driver)

        # 2. Extrair dados de cada veículo
        estoque = []
        for i, url in enumerate(urls, 1):
            log(f"  Extraindo veículo {i}/{len(urls)}: {url.split('/')[-2]}")
            try:
                dados = extrair_dados_veiculo(driver, url)
                estoque.append(dados)
            except Exception as e:
                log(f"  ERRO ao extrair {url}: {e}")

        # 3. Atualizar histórico de vendidos
        historico, novos, vendidos = atualizar_historico(estoque)

        # 4. Salvar estoque atual
        with open(ESTOQUE_JSON, "w", encoding="utf-8") as f:
            json.dump(estoque, f, ensure_ascii=False, indent=2)
        log(f"Estoque salvo: {ESTOQUE_JSON}")

        # 5. Gerar base de conhecimento para o Omni
        gerar_base_conhecimento(estoque)

        # 6. Gerar CSV
        gerar_csv(estoque)

        # 7. Publicar no GitHub
        publicar_no_github()

        # 8. Atualizar tabela no Omni (Opção A)
        try:
            from atualizar_omni import main as atualizar_omni_main
            log("Iniciando atualização da tabela no Omni...")
            atualizar_omni_main()
        except ImportError:
            log("Módulo atualizar_omni não encontrado. Pulando atualização do Omni.")
        except Exception as e:
            log(f"Erro ao atualizar Omni (não crítico): {e}")
            log("A base de conhecimento no GitHub foi atualizada normalmente.")

        # 9. Resumo
        log("-" * 50)
        log("RESUMO DA EXECUÇÃO:")
        log(f"  Veículos no estoque: {len(estoque)}")
        log(f"  Veículos novos: {len(novos)}")
        log(f"  Veículos vendidos (saíram): {len(vendidos)}")
        log(f"  Total no histórico de vendidos: {len(historico)}")
        log(f"  URL pública: {GITHUB_RAW_URL}")
        log("-" * 50)

    except Exception as e:
        log(f"ERRO CRÍTICO: {e}")
        raise
    finally:
        driver.quit()
        log("Driver encerrado. Scraper finalizado.")


if __name__ == "__main__":
    main()
