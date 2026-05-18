#!/usr/bin/env python3
"""
Scraper da Anísio Automóveis usando Playwright + Stealth Mode
Contorna a proteção anti-bot do site (BotShield/Cloudflare)
Substitui o scraper_anisio.py que usava Selenium

Uso: python3 scraper_playwright.py
"""
import asyncio
import json
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configurações
URL_ESTOQUE = "https://www.anisioautomoveis.com.br/veiculo/"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "estoque_atual.json")
BACKUP_FILE = os.path.join(OUTPUT_DIR, "estoque_anterior.json")
BASE_CONHECIMENTO_FILE = os.path.join(OUTPUT_DIR, "base_conhecimento_omni.txt")
HISTORICO_FILE = os.path.join(OUTPUT_DIR, "historico_vendidos.json")

# Tempo de espera para bypass anti-bot (segundos)
ANTIBOT_WAIT = 12


async def wait_for_antibot(page):
    """Aguarda a proteção anti-bot resolver"""
    try:
        title = await page.title()
    except Exception:
        # Página pode estar navegando, esperar
        await page.wait_for_timeout(3000)
        try:
            title = await page.title()
        except Exception:
            await page.wait_for_load_state('domcontentloaded')
            title = await page.title()
    
    if 'momento' in title.lower() or 'checking' in title.lower():
        print(f"  [Anti-bot] Detectado: '{title}'. Aguardando resolução...")
        # Esperar até o título mudar (máximo 30s)
        for i in range(30):
            await page.wait_for_timeout(1000)
            try:
                title = await page.title()
            except Exception:
                # Navegação em andamento, esperar mais
                await page.wait_for_timeout(2000)
                try:
                    await page.wait_for_load_state('domcontentloaded')
                    title = await page.title()
                except Exception:
                    continue
            if 'momento' not in title.lower() and 'checking' not in title.lower():
                print(f"  [Anti-bot] Resolvido em {i+1}s. Título: '{title}'")
                return True
        print("  [Anti-bot] TIMEOUT - não conseguiu resolver em 30s")
        return False
    return True


async def load_all_vehicles(page):
    """Clica em 'Mais veículos' até carregar todos"""
    max_clicks = 10
    prev_count = 0
    
    for i in range(max_clicks):
        try:
            # Contar veículos atuais antes do clique
            current_cards = await page.query_selector_all('a[href*="/veiculo/"][href*="-"]')
            current_count = len(current_cards)
            
            if current_count == prev_count and i > 0:
                print(f"  [Load] Sem novos veículos após clique - total: {current_count}")
                break
            prev_count = current_count
            
            # Buscar botão de várias formas
            btn = None
            
            # Método 1: Seletor específico
            btn = await page.query_selector('a.btn-load-more, button.btn-load-more')
            
            # Método 2: Por texto
            if not btn:
                elements = await page.query_selector_all('a, button')
                for el in elements:
                    try:
                        text = await el.inner_text()
                        if 'mais veículo' in text.lower():
                            btn = el
                            break
                    except:
                        continue
            
            if btn:
                is_visible = await btn.is_visible()
                if is_visible:
                    await btn.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)
                    await btn.click()
                    print(f"  [Load] Clicou em 'Mais veículos' ({i+1}) - cards até agora: {current_count}")
                    # Esperar mais tempo para o conteúdo carregar
                    await page.wait_for_timeout(3000)
                else:
                    print(f"  [Load] Botão não visível - todos carregados ({current_count} cards)")
                    break
            else:
                print(f"  [Load] Botão não encontrado - todos carregados ({current_count} cards)")
                break
        except Exception as e:
            print(f"  [Load] Erro ao clicar: {e}")
            break
    
    # Contagem final
    final_cards = await page.query_selector_all('a[href*="/veiculo/"][href*="-"]')
    print(f"  [Load] Total de cards na página: {len(final_cards)}")


async def extract_vehicle_list(page):
    """Extrai a lista de veículos da página de estoque"""
    vehicles = []
    
    # Buscar todos os cards de veículos
    cards = await page.query_selector_all('a[href*="/veiculo/"][href*="-"]')
    
    print(f"  [Extract] Encontrados {len(cards)} links de veículos")
    
    seen_urls = set()
    vehicle_urls = []
    
    for card in cards:
        href = await card.get_attribute('href')
        if href and '/veiculo/' in href and href.count('/') > 3 and href not in seen_urls:
            # Filtrar apenas links de veículos individuais (não a página de listagem)
            if re.search(r'/veiculo/\d+', href):
                seen_urls.add(href)
                if not href.startswith('http'):
                    href = f"https://www.anisioautomoveis.com.br{href}"
                vehicle_urls.append(href)
    
    print(f"  [Extract] URLs únicas de veículos: {len(vehicle_urls)}")
    return vehicle_urls


async def extract_vehicle_details(page, url):
    """Extrai os detalhes de um veículo individual"""
    try:
        response = await page.goto(url, wait_until='domcontentloaded', timeout=20000)
        
        # Verificar anti-bot novamente
        await wait_for_antibot(page)
        await page.wait_for_timeout(1500)
        
        vehicle = {
            'url': url,
            'id': re.search(r'/(\d+)-', url).group(1) if re.search(r'/(\d+)-', url) else '',
            'data_coleta': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        # Título da página (contém muitas informações)
        title = await page.title()
        vehicle['titulo_pagina'] = title
        
        # Nome do veículo
        nome_el = await page.query_selector('h1, .vehicle-title, .titulo-veiculo')
        if nome_el:
            vehicle['nome'] = (await nome_el.inner_text()).strip()
        else:
            vehicle['nome'] = ''
        
        # Preço
        preco_el = await page.query_selector('.vehicle-price, .preco, [class*="price"], [class*="preco"]')
        if preco_el:
            vehicle['preco'] = (await preco_el.inner_text()).strip()
        else:
            # Tentar extrair do texto da página
            body = await page.inner_text('body')
            preco_match = re.search(r'R\$\s*[\d.,]+', body)
            if preco_match:
                vehicle['preco'] = preco_match.group(0)
            else:
                vehicle['preco'] = ''
        
        # Ficha técnica
        ficha = {}
        # Tentar extrair da tabela de ficha técnica
        rows = await page.query_selector_all('table tr, .ficha-tecnica li, .specs li, [class*="spec"] li, [class*="ficha"] li')
        for row in rows:
            text = (await row.inner_text()).strip()
            if ':' in text:
                parts = text.split(':', 1)
                key = parts[0].strip().lower()
                val = parts[1].strip()
                if 'ano' in key:
                    ficha['ano_modelo'] = val
                elif 'combust' in key:
                    ficha['combustivel'] = val
                elif 'cor' in key:
                    ficha['cor'] = val
                elif 'km' in key or 'quilom' in key:
                    ficha['km'] = val.replace(' km', '').replace('.', '').strip()
                elif 'porta' in key:
                    ficha['portas'] = val
                elif 'câmbio' in key or 'cambio' in key:
                    ficha['cambio'] = val
        
        # Se ficha vazia, tentar extrair do título da página
        if not ficha and title:
            # Formato típico: "Marca Modelo Ano Combustível Cor Portas KM km em Cidade"
            ano_match = re.search(r'(\d{4}/\d{2,4})', title)
            if ano_match:
                ficha['ano_modelo'] = ano_match.group(1)
            
            if 'Flex' in title:
                ficha['combustivel'] = 'Flex'
            elif 'Diesel' in title:
                ficha['combustivel'] = 'Diesel'
            elif 'Híbrido' in title or 'Hybrid' in title:
                ficha['combustivel'] = 'Híbrido e Flex'
            
            km_match = re.search(r'([\d.]+)\s*km', title)
            if km_match:
                ficha['km'] = km_match.group(1).replace('.', '')
            
            cores = ['Preto', 'Branco', 'Prata', 'Cinza', 'Vermelho', 'Azul', 'Verde', 'Marrom', 'Bege']
            for cor in cores:
                if cor in title:
                    ficha['cor'] = cor
                    break
            
            portas_match = re.search(r'(\d)P', title)
            if portas_match:
                ficha['portas'] = portas_match.group(1)
        
        vehicle['ficha_tecnica'] = ficha
        
        # Marca (extrair do título ou breadcrumb)
        marca = ''
        marcas_conhecidas = ['Volkswagen', 'Fiat', 'Chevrolet', 'Toyota', 'Honda', 'Hyundai', 
                           'Jeep', 'Nissan', 'Audi', 'BMW', 'Mercedes', 'Chery', 'Ford',
                           'Renault', 'Peugeot', 'Citroën', 'Mitsubishi', 'Kia', 'Suzuki']
        for m in marcas_conhecidas:
            if m.lower() in title.lower():
                marca = m
                break
        vehicle['marca'] = marca
        
        # Descrição
        desc_el = await page.query_selector('.vehicle-description, .descricao, [class*="description"], [class*="descricao"], .obs')
        if desc_el:
            vehicle['descricao'] = (await desc_el.inner_text()).strip()
        else:
            vehicle['descricao'] = ''
        
        # Características/Opcionais
        caracteristicas = []
        items = await page.query_selector_all('.vehicle-features li, .opcionais li, [class*="feature"] li, [class*="opcional"] li, [class*="caracteristic"] li')
        for item in items:
            text = (await item.inner_text()).strip()
            if text:
                caracteristicas.append(text)
        vehicle['caracteristicas'] = caracteristicas
        
        # Fotos
        fotos = []
        imgs = await page.query_selector_all('.vehicle-gallery img, .galeria img, [class*="gallery"] img, [class*="slider"] img, [class*="carousel"] img')
        for img in imgs:
            src = await img.get_attribute('src') or await img.get_attribute('data-src')
            if src and 'placeholder' not in src:
                fotos.append(src)
        vehicle['fotos'] = fotos
        
        return vehicle
        
    except Exception as e:
        print(f"  [ERRO] Falha ao extrair {url}: {e}")
        return None


async def run_scraper():
    """Executa o scraper completo"""
    print(f"{'='*60}")
    print(f"SCRAPER ANÍSIO AUTOMÓVEIS - Playwright + Stealth")
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # Backup do estoque anterior
    if os.path.exists(OUTPUT_FILE):
        import shutil
        shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
        print(f"\n[Backup] estoque_atual.json → estoque_anterior.json")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            locale='pt-BR',
            timezone_id='America/Sao_Paulo'
        )
        
        page = await context.new_page()
        
        # Aplicar stealth
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        # 1. Acessar página de estoque
        print(f"\n[1] Acessando página de estoque...")
        await page.goto(URL_ESTOQUE, wait_until='domcontentloaded', timeout=30000)
        
        # 2. Aguardar anti-bot (esperar navegação completar)
        print("  Aguardando anti-bot...")
        await page.wait_for_timeout(5000)
        
        # Tentar esperar a página real carregar
        try:
            await page.wait_for_load_state('networkidle', timeout=25000)
        except Exception:
            pass
        
        if not await wait_for_antibot(page):
            print("[FALHA] Não conseguiu passar pela proteção anti-bot")
            await browser.close()
            return []
        
        await page.wait_for_timeout(3000)
        
        # 3. Carregar todos os veículos
        print(f"\n[2] Carregando todos os veículos...")
        await load_all_vehicles(page)
        
        # 4. Extrair URLs dos veículos
        print(f"\n[3] Extraindo URLs dos veículos...")
        vehicle_urls = await extract_vehicle_list(page)
        
        if not vehicle_urls:
            print("[FALHA] Nenhum veículo encontrado na página")
            await browser.close()
            return []
        
        # 5. Visitar cada veículo e extrair detalhes
        print(f"\n[4] Extraindo detalhes de {len(vehicle_urls)} veículos...")
        vehicles = []
        for i, url in enumerate(vehicle_urls):
            print(f"  [{i+1}/{len(vehicle_urls)}] {url.split('/')[-2][:50]}...")
            vehicle = await extract_vehicle_details(page, url)
            if vehicle:
                vehicles.append(vehicle)
            # Pequeno delay entre requisições
            await page.wait_for_timeout(1000)
        
        await browser.close()
    
    print(f"\n[5] Total de veículos coletados: {len(vehicles)}")
    
    # Salvar resultado
    if vehicles:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(vehicles, f, ensure_ascii=False, indent=2)
        print(f"[6] Salvo em: {OUTPUT_FILE}")
        
        # Gerar base de conhecimento
        generate_knowledge_base(vehicles)
        
        # Comparar com anterior
        compare_with_previous(vehicles)
    
    return vehicles


def generate_knowledge_base(vehicles):
    """Gera o arquivo de base de conhecimento para o Omni"""
    lines = []
    lines.append("ESTOQUE DE VEÍCULOS - ANÍSIO AUTOMÓVEIS")
    lines.append(f"Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines.append(f"Total: {len(vehicles)} veículos disponíveis")
    lines.append("=" * 60)
    
    for i, v in enumerate(vehicles, 1):
        ft = v.get('ficha_tecnica', {})
        lines.append(f"\n--- VEÍCULO {i} ---")
        lines.append(f"Marca: {v.get('marca', 'N/A')}")
        lines.append(f"Modelo: {v.get('nome', 'N/A')}")
        lines.append(f"Ano: {ft.get('ano_modelo', 'N/A')}")
        lines.append(f"Preço: {v.get('preco', 'N/A')}")
        lines.append(f"Cor: {ft.get('cor', 'N/A')}")
        lines.append(f"KM: {ft.get('km', 'N/A')}")
        lines.append(f"Combustível: {ft.get('combustivel', 'N/A')}")
        lines.append(f"Câmbio: {ft.get('cambio', 'N/A')}")
        lines.append(f"Portas: {ft.get('portas', 'N/A')}")
        if v.get('descricao'):
            lines.append(f"Descrição: {v['descricao'][:200]}")
        if v.get('caracteristicas'):
            lines.append(f"Opcionais: {', '.join(v['caracteristicas'][:15])}")
        lines.append(f"Link: {v.get('url', 'N/A')}")
    
    with open(BASE_CONHECIMENTO_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"[7] Base de conhecimento salva: {BASE_CONHECIMENTO_FILE}")


def compare_with_previous(vehicles):
    """Compara com o estoque anterior e reporta mudanças"""
    if not os.path.exists(BACKUP_FILE):
        print("[Compare] Sem estoque anterior para comparar")
        return
    
    with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
        anterior = json.load(f)
    
    def normalize(marca, nome):
        return f"{marca.lower().strip()}|{nome.lower().strip()}"
    
    site_map = {normalize(v.get('marca', ''), v.get('nome', '')): v for v in vehicles}
    ant_map = {normalize(v.get('marca', ''), v.get('nome', '')): v for v in anterior}
    
    novos = [site_map[k] for k in site_map if k not in ant_map]
    vendidos = [ant_map[k] for k in ant_map if k not in site_map]
    
    print(f"\n{'='*60}")
    print(f"COMPARAÇÃO COM ESTOQUE ANTERIOR")
    print(f"{'='*60}")
    print(f"Anterior: {len(anterior)} veículos")
    print(f"Atual: {len(vehicles)} veículos")
    print(f"Novos: {len(novos)}")
    print(f"Vendidos: {len(vendidos)}")
    
    if novos:
        print("\nVEÍCULOS NOVOS:")
        for v in novos:
            print(f"  + {v.get('marca')} {v.get('nome')} - {v.get('preco')}")
    
    if vendidos:
        print("\nVEÍCULOS VENDIDOS:")
        # Salvar no histórico
        historico = []
        if os.path.exists(HISTORICO_FILE):
            with open(HISTORICO_FILE, 'r', encoding='utf-8') as f:
                historico = json.load(f)
        
        for v in vendidos:
            print(f"  - {v.get('marca')} {v.get('nome')} - {v.get('preco')}")
            v['data_venda'] = datetime.now().strftime('%Y-%m-%d')
            historico.append(v)
        
        with open(HISTORICO_FILE, 'w', encoding='utf-8') as f:
            json.dump(historico, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    vehicles = asyncio.run(run_scraper())
    if vehicles:
        print(f"\n[OK] Scraper concluído com sucesso: {len(vehicles)} veículos")
    else:
        print(f"\n[FALHA] Scraper não coletou veículos")
        exit(1)
