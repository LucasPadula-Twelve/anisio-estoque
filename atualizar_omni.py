#!/usr/bin/env python3
"""
Atualizar Base de Conhecimento do Omni - Selenium
Faz login no painel Omni (com cookies persistentes), limpa a tabela
'Estoque de Veículos' e insere os dados atualizados do scraper.

Na primeira execução: pede código OTP e salva cookies.
Nas próximas execuções: usa cookies salvos (sem OTP).

Uso: python3 atualizar_omni.py
"""

import json
import os
import pickle
import re
import time
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ============================================================
# CONFIGURAÇÕES
# ============================================================
OMNI_URL = "https://omni.flw.chat"
TABLE_URL = f"{OMNI_URL}/ai/knowledge/new/table/20856b13-db5c-4953-93b9-3d7f4c6dd78d"
PHONE_NUMBER = "19999041499"

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(OUTPUT_DIR, "omni_cookies.pkl")
STORAGE_FILE = os.path.join(OUTPUT_DIR, "omni_storage.json")
ESTOQUE_JSON = os.path.join(OUTPUT_DIR, "estoque_atual.json")
LOG_FILE = os.path.join(OUTPUT_DIR, "omni_update_log.txt")

# Colunas da tabela no Omni (na ordem exata)
COLUNAS_OMNI = [
    "Marca", "Modelo", "Ano", "Preco", "Cor", "KM",
    "Tipo", "Cambio", "Combustivel", "Descricao", "Opcionais", "Link"
]


def log(msg):
    """Registra mensagem no log com timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def criar_driver(headless=True):
    """Cria e retorna uma instância do Chrome WebDriver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
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
    service = Service(executable_path="/home/ubuntu/.cache/selenium/chromedriver/linux64/128.0.6613.137/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver


def salvar_cookies(driver):
    """Salva cookies e storage do navegador."""
    cookies = driver.get_cookies()
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(cookies, f)

    local_storage = driver.execute_script(
        "var items = {}; for (var i = 0; i < localStorage.length; i++) {"
        "var key = localStorage.key(i); items[key] = localStorage.getItem(key);} return items;"
    )
    session_storage = driver.execute_script(
        "var items = {}; for (var i = 0; i < sessionStorage.length; i++) {"
        "var key = sessionStorage.key(i); items[key] = sessionStorage.getItem(key);} return items;"
    )

    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "localStorage": local_storage,
            "sessionStorage": session_storage
        }, f, ensure_ascii=False)

    log("Cookies e storage salvos com sucesso.")


def carregar_cookies(driver):
    """Carrega cookies salvos no navegador."""
    if not os.path.exists(COOKIES_FILE):
        return False

    try:
        driver.get(OMNI_URL)
        time.sleep(2)

        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)

        for cookie in cookies:
            try:
                for key in ["sameSite", "expiry"]:
                    cookie.pop(key, None)
                driver.add_cookie(cookie)
            except Exception:
                pass

        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                storage = json.load(f)

            for key, value in storage.get("localStorage", {}).items():
                try:
                    escaped_value = json.dumps(value)[1:-1]
                    driver.execute_script(
                        f"localStorage.setItem('{key}', '{escaped_value}');"
                    )
                except Exception:
                    pass

        log("Cookies e storage carregados com sucesso.")
        return True
    except Exception as e:
        log(f"Erro ao carregar cookies: {e}")
        return False


def fazer_login(driver):
    """Faz login no Omni com telefone + OTP."""
    log("Iniciando login no Omni...")
    driver.get(f"{OMNI_URL}/auth/sign-in")
    time.sleep(3)

    if "/auth/" not in driver.current_url:
        log("Já está logado!")
        return True

    # Preencher telefone
    try:
        phone_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input"))
        )
        phone_input.clear()
        phone_input.send_keys(PHONE_NUMBER)
        log(f"Telefone inserido: {PHONE_NUMBER}")
        time.sleep(1)
    except Exception as e:
        log(f"Erro ao inserir telefone: {e}")
        return False

    # Clicar em Entrar
    try:
        entrar_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Entrar')]")
        entrar_btn.click()
        log("Botão 'Entrar' clicado. Aguardando código OTP...")
        time.sleep(3)
    except Exception as e:
        log(f"Erro ao clicar em Entrar: {e}")
        return False

    # Solicitar código OTP
    print("\n" + "=" * 50)
    print("CÓDIGO OTP NECESSÁRIO")
    print("Um código foi enviado para o seu WhatsApp/SMS.")
    print("=" * 50)
    otp_code = input("Digite o código de 6 dígitos: ").strip()

    if len(otp_code) != 6 or not otp_code.isdigit():
        log("Código OTP inválido!")
        return False

    # Preencher os 6 campos do OTP
    try:
        otp_inputs = driver.find_elements(By.CSS_SELECTOR, "input[maxlength='1']")
        if len(otp_inputs) >= 6:
            for i, digit in enumerate(otp_code):
                otp_inputs[i].clear()
                otp_inputs[i].send_keys(digit)
                time.sleep(0.2)
        log("Código OTP inserido.")
        time.sleep(1)
    except Exception as e:
        log(f"Erro ao inserir OTP: {e}")
        return False

    # Clicar em Entrar novamente
    try:
        entrar_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Entrar')]")
        entrar_btn.click()
        time.sleep(5)
    except Exception:
        pass

    if "/auth/" not in driver.current_url:
        log("Login realizado com sucesso!")
        salvar_cookies(driver)
        return True
    else:
        log("Falha no login. Verifique o código OTP.")
        return False


def verificar_sessao(driver):
    """Verifica se a sessão está ativa."""
    log("Verificando sessão...")
    driver.get(TABLE_URL)
    time.sleep(5)

    if "/auth/" in driver.current_url:
        log("Sessão expirada. Necessário novo login.")
        return False

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table, tbody, tr"))
        )
        log("Sessão ativa. Tabela carregada.")
        return True
    except TimeoutException:
        if "/auth/" in driver.current_url:
            return False
        driver.get(TABLE_URL)
        time.sleep(5)
        return "/auth/" not in driver.current_url


def limpar_tabela(driver):
    """Seleciona todas as linhas e exclui via interface."""
    log("Limpando tabela existente...")
    time.sleep(3)

    # Contar linhas
    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
    total = len(rows)
    log(f"  {total} linhas encontradas.")

    if total == 0:
        log("  Tabela já está vazia.")
        return True

    # Selecionar todas via checkbox do header
    try:
        header_cb = driver.find_element(By.CSS_SELECTOR, "thead mat-checkbox, th mat-checkbox")
        header_cb.click()
        time.sleep(1)
        log("  Todas as linhas selecionadas.")
    except Exception as e:
        log(f"  Erro ao selecionar: {e}")
        return False

    # Clicar em Excluir
    try:
        excluir_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Excluir')]"))
        )
        excluir_btn.click()
        time.sleep(1)
        log("  Botão Excluir clicado.")
    except Exception as e:
        log(f"  Botão Excluir não encontrado: {e}")
        return False

    # Confirmar exclusão no modal
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[contains(text(), 'Excluir') and ancestor::mat-dialog-container]"
                " | //mat-dialog-container//button[contains(text(), 'Excluir')]"
                " | //div[contains(@class,'dialog')]//button[contains(text(), 'Excluir')]"
            ))
        )
        confirm_btn.click()
        time.sleep(2)
        log("  Exclusão confirmada.")
    except Exception:
        # Tentar clicar no segundo botão Excluir visível
        try:
            btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Excluir')]")
            if len(btns) > 1:
                btns[-1].click()
                time.sleep(2)
                log("  Exclusão confirmada (fallback).")
        except Exception:
            pass

    # Verificar se limpou
    time.sleep(2)
    rows_after = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
    log(f"  Linhas restantes: {len(rows_after)}")
    return True


def adicionar_linhas(driver, quantidade):
    """Adiciona N linhas vazias na tabela."""
    log(f"Adicionando {quantidade} linhas vazias...")

    for i in range(quantidade):
        try:
            add_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Adicionar linha')]")
            driver.execute_script("arguments[0].click();", add_btn)
            time.sleep(0.3)
        except Exception as e:
            log(f"  Erro ao adicionar linha {i+1}: {e}")
            return False

        if (i + 1) % 10 == 0:
            log(f"  {i+1}/{quantidade} linhas adicionadas...")

    log(f"  {quantidade} linhas adicionadas com sucesso.")
    return True


def preencher_dados_js(driver, dados_rows):
    """Preenche os dados usando JavaScript com contentEditable (técnica que funcionou)."""
    log(f"Preenchendo {len(dados_rows)} veículos via JavaScript...")

    # Dividir em lotes de 5 para evitar timeout
    lote_size = 5
    total_preenchidos = 0

    for lote_idx in range(0, len(dados_rows), lote_size):
        lote = dados_rows[lote_idx:lote_idx + lote_size]
        start_row = lote_idx

        # Gerar JavaScript para este lote
        js_data = json.dumps(lote, ensure_ascii=False)
        cols_json = json.dumps(COLUNAS_OMNI)

        js_code = f"""
        async function preencherLote() {{
            const data = {js_data};
            const cols = {cols_json};
            const startIdx = {start_row};
            function sleep(ms) {{ return new Promise(r => setTimeout(r, ms)); }}
            async function fillCell(td, value) {{
                const cellDiv = td.querySelector('.h-table-editable-cell');
                if (!cellDiv) return false;
                cellDiv.click();
                await sleep(200);
                const editable = td.querySelector('[contenteditable="true"]');
                if (editable) {{
                    editable.focus();
                    editable.textContent = value;
                    editable.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    editable.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}
            const allRows = document.querySelectorAll('tbody tr');
            let filled = 0;
            for (let i = 0; i < data.length; i++) {{
                const rowIdx = startIdx + i;
                if (rowIdx >= allRows.length) break;
                const row = allRows[rowIdx];
                const tds = row.querySelectorAll('td');
                for (let j = 0; j < cols.length; j++) {{
                    await fillCell(tds[j + 1], data[i][cols[j]] || '');
                    await sleep(50);
                }}
                filled++;
            }}
            return 'OK: ' + filled;
        }}
        return preencherLote();
        """

        try:
            result = driver.execute_script(js_code)
            total_preenchidos += len(lote)
            log(f"  Lote {lote_idx // lote_size + 1}: {result} ({total_preenchidos}/{len(dados_rows)})")
        except Exception as e:
            log(f"  Erro no lote {lote_idx // lote_size + 1}: {e}")

        time.sleep(1)

    log(f"  Preenchimento concluído: {total_preenchidos} veículos.")
    return total_preenchidos


def salvar_tabela(driver):
    """Clica no botão Salvar."""
    log("Salvando tabela...")
    try:
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        save_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Salvar')]"))
        )
        save_btn.click()
        time.sleep(5)
        log("Tabela salva com sucesso!")
        return True
    except Exception as e:
        log(f"Erro ao salvar tabela: {e}")
        return False


def limpar_descricao(descricao):
    """Remove telefones, nomes de vendedores e informacoes de contato da descricao."""
    if not descricao:
        return ''
    # Remover padroes como: ZAP (19) 99933-2423 FERNANDO
    descricao = re.sub(r'ZAP\s*\(?\d{2}\)?\s*[\d\-\.]+\s*[A-Z]+', '', descricao, flags=re.IGNORECASE)
    # Remover telefones soltos: (19) 99933-2423 ou 19 99933-2423
    descricao = re.sub(r'\(?\d{2}\)?\s*\d{4,5}[\-\.]?\d{4}', '', descricao)
    # Remover "ZAP" ou "WHATSAPP" solto
    descricao = re.sub(r'\b(ZAP|WHATSAPP|WHATS|FONE|TELEFONE|LIGUE)\b', '', descricao, flags=re.IGNORECASE)
    # Limpar espacos extras e pontuacao solta
    descricao = re.sub(r'\s{2,}', ' ', descricao).strip()
    descricao = re.sub(r'\s*\.\s*$', '.', descricao)
    return descricao


def classificar_tipo(nome):
    """Classifica o tipo do veículo com base no nome/modelo."""
    nome_lower = nome.lower() if nome else ""

    suvs = ['creta', 'tracker', 'hr-v', 'hrv', 't-cross', 'tcross', 'tiggo',
            'renegade', 'compass', 'kicks', 'duster', 'captur', 'tucson',
            'sportage', 'rav4', 'cx-5', 'ecosport', 'pulse', 'nivus']
    sedans = ['corolla', 'civic', 'cruze', 'sentra', 'virtus', 'cronos',
              'onix plus', 'hb20s', 'yaris sedan', 'city', 'versa',
              'hb 20 sedan', 'onix sedan']
    hatches = ['polo', 'gol', 'onix hatch', 'hb20 hatch', 'hb 20 hatch',
               'hb 20 1.0', 'argo', 'mobi', 'kwid', 'sandero', 'ka',
               'up!', 'fox', 'fit']
    pickups = ['hilux', 'ranger', 'amarok', 's10', 'frontier', 'toro',
               'saveiro', 'strada', 'montana', 'oroch']

    for s in suvs:
        if s in nome_lower:
            return 'SUV'
    for s in sedans:
        if s in nome_lower:
            return 'Sedan'
    for s in hatches:
        if s in nome_lower:
            return 'Hatch'
    for s in pickups:
        if s in nome_lower:
            return 'Pickup'
    return 'Outro'


def preparar_dados(estoque):
    """Converte os dados do JSON do scraper para o formato da tabela Omni."""
    rows = []
    for v in estoque:
        ft = v.get('ficha_tecnica', {})
        carac = v.get('caracteristicas', [])

        row = {
            'Marca': v.get('marca', ''),
            'Modelo': v.get('nome', ''),
            'Ano': ft.get('ano_modelo', ''),
            'Preco': v.get('preco', ''),
            'Cor': ft.get('cor', ''),
            'KM': ft.get('km', ''),
            'Tipo': classificar_tipo(v.get('nome', '')),
            'Cambio': ft.get('cambio', ''),
            'Combustivel': ft.get('combustivel', ''),
            'Descricao': limpar_descricao(v.get('descricao', '') or ''),
            'Opcionais': ', '.join(carac) if carac else '',
            'Link': v.get('url', '')
        }
        rows.append(row)

    return rows


def carregar_estoque():
    """Carrega os dados do estoque do JSON gerado pelo scraper."""
    if not os.path.exists(ESTOQUE_JSON):
        log(f"ERRO: Arquivo de estoque não encontrado: {ESTOQUE_JSON}")
        log("Execute primeiro o scraper: python3 scraper_anisio.py")
        return None

    with open(ESTOQUE_JSON, "r", encoding="utf-8") as f:
        estoque = json.load(f)

    log(f"Estoque carregado: {len(estoque)} veículos.")
    return estoque


def main():
    log("=" * 60)
    log("ATUALIZANDO BASE DE CONHECIMENTO NO OMNI")
    log("=" * 60)

    # 1. Carregar estoque
    estoque = carregar_estoque()
    if not estoque:
        return

    # 2. Preparar dados para a tabela
    dados_rows = preparar_dados(estoque)
    log(f"Dados preparados: {len(dados_rows)} veículos com {len(COLUNAS_OMNI)} colunas.")

    # 3. Criar driver (headless=False na primeira vez para OTP)
    first_run = not os.path.exists(COOKIES_FILE)
    driver = criar_driver(headless=not first_run)

    try:
        # 4. Tentar carregar cookies salvos
        if not first_run:
            carregar_cookies(driver)

        # 5. Verificar sessão
        sessao_ativa = verificar_sessao(driver)

        if not sessao_ativa:
            if not fazer_login(driver):
                log("ERRO: Não foi possível fazer login.")
                return
            driver.get(TABLE_URL)
            time.sleep(5)

        # 6. Limpar tabela existente
        limpar_tabela(driver)

        # 7. Recarregar página para garantir estado limpo
        driver.get(TABLE_URL)
        time.sleep(5)

        # 8. Adicionar linhas vazias
        adicionar_linhas(driver, len(dados_rows))

        # 9. Preencher dados via JavaScript (contentEditable)
        preencher_dados_js(driver, dados_rows)

        # 10. Salvar tabela
        salvar_tabela(driver)

        # 11. Salvar cookies atualizados
        salvar_cookies(driver)

        log("=" * 60)
        log("ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!")
        log(f"  {len(dados_rows)} veículos atualizados na tabela do Omni.")
        log("=" * 60)

    except Exception as e:
        log(f"ERRO CRÍTICO: {e}")
        try:
            screenshot_path = os.path.join(OUTPUT_DIR, "erro_screenshot.png")
            driver.save_screenshot(screenshot_path)
            log(f"Screenshot de erro salvo: {screenshot_path}")
        except Exception:
            pass
        raise
    finally:
        driver.quit()
        log("Driver encerrado.")


if __name__ == "__main__":
    main()
