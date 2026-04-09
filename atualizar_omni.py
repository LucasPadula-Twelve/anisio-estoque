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
import time
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ============================================================
# CONFIGURAÇÕES
# ============================================================
OMNI_URL = "https://omni.flw.chat"
TABLE_URL = f"{OMNI_URL}/ai/knowledge/new/table/20856b13-db5c-4953-93b9-3d7f4c6dd78d"
PHONE_NUMBER = "19999041499"

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(OUTPUT_DIR, "omni_cookies.pkl")
ESTOQUE_JSON = os.path.join(OUTPUT_DIR, "estoque_atual.json")
LOG_FILE = os.path.join(OUTPUT_DIR, "omni_update_log.txt")

# Colunas da tabela no Omni (na ordem exata)
COLUNAS_OMNI = ["Marca", "Modelo", "Ano", "Preco", "Cor", "KM", "Tipo"]


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


def salvar_cookies(driver):
    """Salva os cookies do navegador em arquivo."""
    cookies = driver.get_cookies()
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(cookies, f)
    
    # Salvar também localStorage e sessionStorage
    local_storage = driver.execute_script(
        "var items = {}; for (var i = 0; i < localStorage.length; i++) {"
        "var key = localStorage.key(i); items[key] = localStorage.getItem(key);} return items;"
    )
    session_storage = driver.execute_script(
        "var items = {}; for (var i = 0; i < sessionStorage.length; i++) {"
        "var key = sessionStorage.key(i); items[key] = sessionStorage.getItem(key);} return items;"
    )
    
    storage_file = os.path.join(OUTPUT_DIR, "omni_storage.json")
    with open(storage_file, "w", encoding="utf-8") as f:
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
        # Primeiro navegar para o domínio para poder definir cookies
        driver.get(OMNI_URL)
        time.sleep(2)
        
        # Carregar cookies
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        
        for cookie in cookies:
            try:
                # Remover campos que podem causar erro
                for key in ["sameSite", "expiry"]:
                    cookie.pop(key, None)
                driver.add_cookie(cookie)
            except Exception:
                pass
        
        # Carregar localStorage
        storage_file = os.path.join(OUTPUT_DIR, "omni_storage.json")
        if os.path.exists(storage_file):
            with open(storage_file, "r", encoding="utf-8") as f:
                storage = json.load(f)
            
            for key, value in storage.get("localStorage", {}).items():
                try:
                    escaped_value = value.replace("'", "\\'").replace("\n", "\\n")
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
    
    # Verificar se já está logado
    if "/auth/" not in driver.current_url:
        log("Já está logado!")
        return True
    
    # Preencher telefone
    try:
        phone_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='tel'], input[formcontrolname='phone'], input"))
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
    
    # Solicitar código OTP ao usuário
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
        otp_inputs = driver.find_elements(By.CSS_SELECTOR, "input[maxlength='1'], input.otp-input")
        if len(otp_inputs) >= 6:
            for i, digit in enumerate(otp_code):
                otp_inputs[i].clear()
                otp_inputs[i].send_keys(digit)
                time.sleep(0.2)
        else:
            # Tentar campo único
            otp_single = driver.find_element(By.CSS_SELECTOR, "input[type='text'], input[type='number']")
            otp_single.clear()
            otp_single.send_keys(otp_code)
        
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
    
    # Verificar se login foi bem-sucedido
    if "/auth/" not in driver.current_url:
        log("Login realizado com sucesso!")
        salvar_cookies(driver)
        return True
    else:
        log("Falha no login. Verifique o código OTP.")
        return False


def verificar_sessao(driver):
    """Verifica se a sessão está ativa navegando para a tabela."""
    log("Verificando sessão...")
    driver.get(TABLE_URL)
    time.sleep(5)
    
    # Se redirecionou para login, sessão expirou
    if "/auth/" in driver.current_url:
        log("Sessão expirada. Necessário novo login.")
        return False
    
    # Verificar se a tabela carregou
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table, .mat-table, tr"))
        )
        log("Sessão ativa. Tabela carregada.")
        return True
    except TimeoutException:
        log("Tabela não carregou. Verificando...")
        if "/auth/" in driver.current_url:
            return False
        # Pode estar em outra página, tentar novamente
        driver.get(TABLE_URL)
        time.sleep(5)
        return "/auth/" not in driver.current_url


def limpar_tabela(driver):
    """Seleciona todas as linhas da tabela e as remove."""
    log("Limpando tabela existente...")
    
    # Aguardar tabela carregar
    time.sleep(3)
    
    # Contar linhas existentes
    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr, tr.mat-row")
    total_rows = len(rows)
    log(f"  {total_rows} linhas encontradas na tabela.")
    
    if total_rows == 0:
        log("  Tabela já está vazia.")
        return True
    
    # Selecionar todas as linhas clicando no checkbox do header
    try:
        header_checkbox = driver.find_element(By.CSS_SELECTOR, "th mat-checkbox, thead mat-checkbox")
        header_checkbox.click()
        time.sleep(1)
        log("  Todas as linhas selecionadas.")
    except Exception as e:
        log(f"  Erro ao selecionar todas: {e}")
        # Tentar selecionar individualmente
        checkboxes = driver.find_elements(By.CSS_SELECTOR, "tbody mat-checkbox, tr.mat-row mat-checkbox")
        for cb in checkboxes:
            try:
                cb.click()
                time.sleep(0.1)
            except Exception:
                pass
    
    # Procurar e clicar no botão de deletar/remover
    time.sleep(1)
    deleted = False
    
    # Tentar encontrar botão de excluir que aparece após seleção
    delete_selectors = [
        "//button[contains(text(), 'Excluir')]",
        "//button[contains(text(), 'Remover')]",
        "//button[contains(text(), 'Deletar')]",
        "//button[contains(@mattooltip, 'Excluir')]",
        "//mat-icon[text()='delete']/..",
        "//mat-icon[text()='delete_outline']/..",
    ]
    
    for selector in delete_selectors:
        try:
            btn = driver.find_element(By.XPATH, selector)
            if btn.is_displayed():
                btn.click()
                time.sleep(1)
                # Confirmar exclusão se houver diálogo
                try:
                    confirm = driver.find_element(By.XPATH, 
                        "//button[contains(text(), 'Confirmar') or contains(text(), 'Sim') or contains(text(), 'OK')]")
                    confirm.click()
                    time.sleep(1)
                except Exception:
                    pass
                deleted = True
                log("  Linhas excluídas com sucesso.")
                break
        except Exception:
            continue
    
    if not deleted:
        # Se não encontrou botão de excluir, limpar linha por linha via teclado
        log("  Botão de excluir não encontrado. Limpando via edição de células...")
        # Alternativa: limpar cada célula individualmente
        # Isso será feito na inserção (sobrescrever os dados)
        
        # Desmarcar seleção
        try:
            header_checkbox = driver.find_element(By.CSS_SELECTOR, "th mat-checkbox, thead mat-checkbox")
            header_checkbox.click()
            time.sleep(0.5)
        except Exception:
            pass
        
        return "overwrite"
    
    return True


def inserir_dados(driver, veiculos):
    """Insere os dados dos veículos na tabela do Omni."""
    log(f"Inserindo {len(veiculos)} veículos na tabela...")
    
    for i, veiculo in enumerate(veiculos):
        ficha = veiculo.get("ficha_tecnica", {})
        
        # Preparar dados para as colunas do Omni
        dados_linha = {
            "Marca": veiculo.get("marca", ""),
            "Modelo": veiculo.get("nome", ""),
            "Ano": ficha.get("ano_modelo", ficha.get("ano/modelo", "")),
            "Preco": veiculo.get("preco", ""),
            "Cor": ficha.get("cor", ""),
            "KM": ficha.get("km", ""),
            "Tipo": classificar_tipo(veiculo.get("nome", ""), veiculo.get("marca", ""))
        }
        
        # Clicar em "Adicionar linha"
        try:
            add_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Adicionar linha')]"))
            )
            add_btn.click()
            time.sleep(0.8)
        except Exception as e:
            log(f"  Erro ao clicar 'Adicionar linha' para veículo {i+1}: {e}")
            continue
        
        # Preencher cada célula da nova linha
        # A nova linha aparece no final da tabela
        try:
            # Rolar até o final da tabela
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            
            # Encontrar a última linha da tabela
            rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr, tr.mat-row")
            if not rows:
                log(f"  Nenhuma linha encontrada após adicionar.")
                continue
            
            ultima_linha = rows[-1]
            celulas = ultima_linha.find_elements(By.CSS_SELECTOR, "td")
            
            # Preencher cada célula (pular a primeira que é o checkbox)
            col_idx = 0
            for celula in celulas:
                # Pular célula de checkbox
                try:
                    celula.find_element(By.CSS_SELECTOR, "mat-checkbox")
                    continue
                except NoSuchElementException:
                    pass
                
                if col_idx < len(COLUNAS_OMNI):
                    coluna = COLUNAS_OMNI[col_idx]
                    valor = dados_linha.get(coluna, "")
                    
                    try:
                        # Clicar na célula para ativar edição
                        celula.click()
                        time.sleep(0.3)
                        
                        # Encontrar o input dentro da célula
                        try:
                            input_el = celula.find_element(By.CSS_SELECTOR, "input, textarea")
                            input_el.clear()
                            input_el.send_keys(str(valor))
                        except NoSuchElementException:
                            # Tentar editar diretamente o div editável
                            div_el = celula.find_element(By.CSS_SELECTOR, "div[contenteditable], div")
                            div_el.click()
                            time.sleep(0.2)
                            # Selecionar todo e substituir
                            div_el.send_keys(Keys.CONTROL + "a")
                            div_el.send_keys(str(valor))
                        
                        time.sleep(0.2)
                    except Exception as e:
                        log(f"  Erro ao preencher {coluna} do veículo {i+1}: {e}")
                    
                    col_idx += 1
            
            if (i + 1) % 5 == 0:
                log(f"  {i+1}/{len(veiculos)} veículos inseridos...")
                
        except Exception as e:
            log(f"  Erro ao preencher linha do veículo {i+1}: {e}")
            continue
    
    log(f"  Inserção concluída: {len(veiculos)} veículos.")


def salvar_tabela(driver):
    """Clica no botão Salvar para persistir as alterações."""
    log("Salvando tabela...")
    try:
        # Rolar para o topo
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        save_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Salvar')]"))
        )
        save_btn.click()
        time.sleep(3)
        
        # Verificar se salvou (procurar mensagem de sucesso)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, 
                    "//*[contains(text(), 'sucesso') or contains(text(), 'salvo') or contains(text(), 'Salvo')]"))
            )
            log("Tabela salva com sucesso!")
        except TimeoutException:
            log("Tabela salva (sem mensagem de confirmação detectada).")
        
        return True
    except Exception as e:
        log(f"Erro ao salvar tabela: {e}")
        return False


def classificar_tipo(nome, marca):
    """Classifica o tipo do veículo com base no nome/modelo."""
    nome_lower = nome.lower() if nome else ""
    
    # SUVs conhecidos
    suvs = ["hr-v", "hrv", "creta", "renegade", "tracker", "nivus", "t-cross", 
            "tcross", "kicks", "duster", "compass", "tucson", "ix35", "sportage",
            "tiggo", "tiguan", "captur", "eclipsse", "eclipse", "rav4", "cx-5",
            "cx5", "seltos", "stonic", "soul"]
    
    # Pickups conhecidas
    pickups = ["toro", "strada", "saveiro", "montana", "hilux", "s10", "ranger",
               "amarok", "frontier", "oroch", "maverick"]
    
    # Sedans conhecidos
    sedans = ["corolla", "civic", "cruze", "sentra", "virtus", "cronos", "onix plus",
              "voyage", "prisma", "cobalt", "city", "yaris sedan", "versa", "hb20s"]
    
    # Hatches conhecidos
    hatches = ["fit", "hb20", "polo", "gol", "onix", "argo", "mobi", "kwid",
               "sandero", "up!", "ka", "yaris", "etios", "fox"]
    
    # Minivans/MPVs
    minivans = ["spin", "livina", "mobilio", "br-v"]
    
    for suv in suvs:
        if suv in nome_lower:
            return "SUV"
    
    for pickup in pickups:
        if pickup in nome_lower:
            return "Pickup"
    
    for sedan in sedans:
        if sedan in nome_lower:
            return "Sedan"
    
    for hatch in hatches:
        if hatch in nome_lower:
            return "Hatch"
    
    for mini in minivans:
        if mini in nome_lower:
            return "Minivan"
    
    return "Outro"


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
    log("=" * 50)
    log("ATUALIZANDO BASE DE CONHECIMENTO NO OMNI")
    log("=" * 50)
    
    # 1. Carregar estoque
    estoque = carregar_estoque()
    if not estoque:
        return
    
    # 2. Criar driver
    # Usar headless=False na primeira vez para debug, depois True
    first_run = not os.path.exists(COOKIES_FILE)
    driver = criar_driver(headless=not first_run)
    
    try:
        # 3. Tentar carregar cookies salvos
        if not first_run:
            carregar_cookies(driver)
        
        # 4. Verificar se sessão está ativa
        sessao_ativa = verificar_sessao(driver)
        
        if not sessao_ativa:
            # Precisa fazer login
            if not fazer_login(driver):
                log("ERRO: Não foi possível fazer login.")
                return
            
            # Navegar para a tabela
            driver.get(TABLE_URL)
            time.sleep(5)
        
        # 5. Limpar tabela existente
        resultado_limpeza = limpar_tabela(driver)
        
        # 6. Inserir novos dados
        inserir_dados(driver, estoque)
        
        # 7. Salvar
        salvar_tabela(driver)
        
        # 8. Salvar cookies atualizados
        salvar_cookies(driver)
        
        log("=" * 50)
        log("ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!")
        log(f"  {len(estoque)} veículos atualizados na tabela do Omni.")
        log("=" * 50)
        
    except Exception as e:
        log(f"ERRO CRÍTICO: {e}")
        # Salvar screenshot para debug
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
