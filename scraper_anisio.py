#!/usr/bin/env python3
"""
Scraper da Anísio Automóveis - Feed XML Integra Carros
======================================================
Consome o feed XML do Integra Carros para obter o estoque atualizado.
Substitui o scraping via Playwright/Selenium que era bloqueado por anti-bot.

URL do Feed: https://cliente.integracarros.com.br/site/24cde81a05336ba
Formato: XML com estrutura <estoque><veiculo>...</veiculo></estoque>

Uso: python3 scraper_anisio.py
Agendamento: Executar diariamente às 7h da manhã
"""

import json
import os
import re
import csv
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

# ============================================================
# CONFIGURAÇÕES
# ============================================================
FEED_URL = "https://cliente.integracarros.com.br/site/24cde81a05336ba"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
ESTOQUE_JSON = os.path.join(OUTPUT_DIR, "estoque_atual.json")
HISTORICO_JSON = os.path.join(OUTPUT_DIR, "historico_vendidos.json")
BASE_CONHECIMENTO_TXT = os.path.join(OUTPUT_DIR, "base_conhecimento_omni.txt")
ESTOQUE_CSV = os.path.join(OUTPUT_DIR, "estoque_atual.csv")
LOG_FILE = os.path.join(OUTPUT_DIR, "scraper_log.txt")

# GitHub - Repositório para publicação da base de conhecimento
GITHUB_REPO = "LucasPadula-Twelve/anisio-estoque"
GITHUB_BRANCH = "main"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/base_conhecimento_omni.txt"

# URL base do site para links dos veículos
SITE_BASE_URL = "https://www.anisioautomoveis.com.br/veiculo/"


def log(msg):
    """Registra mensagem no log com timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_xml_feed():
    """Baixa o feed XML do Integra Carros."""
    log(f"Baixando feed XML: {FEED_URL}")
    try:
        response = requests.get(FEED_URL, timeout=30)
        response.raise_for_status()
        log(f"Feed baixado com sucesso: {len(response.content)} bytes")
        return response.content
    except requests.RequestException as e:
        log(f"ERRO ao baixar feed: {e}")
        return None


def parse_xml_feed(xml_content):
    """Parseia o XML e extrai os veículos no formato compatível com o pipeline."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        log(f"ERRO ao parsear XML: {e}")
        return []

    vehicles = []

    for veiculo in root.findall('veiculo'):
        # Extrair campos do XML
        hash_id = veiculo.findtext('hash', '')
        placa = veiculo.findtext('placa', '')
        marca = veiculo.findtext('marca', '')
        modelo = veiculo.findtext('modelo', '')
        submodelo = veiculo.findtext('submodelo', '')
        ano = veiculo.findtext('ano', '')
        ano_fab = veiculo.findtext('ano_fab', '')
        cor = veiculo.findtext('cor', '')
        combustivel = veiculo.findtext('combustivel', '')
        km = veiculo.findtext('km', '')
        portas = veiculo.findtext('portas', '')
        valor = veiculo.findtext('valor', '')
        observacao = veiculo.findtext('observacao', '')
        cambio = veiculo.findtext('cambio', '')
        tipo = veiculo.findtext('tipo', '')
        data_cadastro = veiculo.findtext('data_cadastro', '')
        data_modificacao = veiculo.findtext('data_modificacao', '')

        # Imagens
        fotos = []
        imagens_el = veiculo.find('imagens')
        if imagens_el is not None:
            for img in imagens_el.findall('imagem'):
                if img.text:
                    fotos.append(img.text.strip())

        # Opcionais
        caracteristicas = []
        opcionais_el = veiculo.find('opcionais')
        if opcionais_el is not None:
            for opc in opcionais_el.findall('opcional'):
                if opc.text:
                    caracteristicas.append(opc.text.strip())

        # Formatar preço
        preco_formatado = ''
        if valor:
            try:
                preco_float = float(valor)
                preco_formatado = f"R$ {preco_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            except ValueError:
                preco_formatado = valor

        # Formatar ano
        ano_modelo = ''
        if ano_fab and ano:
            ano_modelo = f"{ano_fab}/{ano}"
        elif ano:
            ano_modelo = ano

        # Nome completo do veículo
        nome_completo = f"{marca.title()} {modelo}"

        # Gerar URL do veículo no site
        slug = f"{hash_id}-{marca}-{modelo}".lower().replace(' ', '-')
        slug = re.sub(r'[^a-z0-9\-]', '', slug)
        url_veiculo = f"{SITE_BASE_URL}{slug}"

        # Limpar descrição (remover telefones, WhatsApp, etc.)
        descricao_limpa = observacao if observacao else ''
        if descricao_limpa:
            descricao_limpa = re.sub(r'\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4}', '', descricao_limpa)
            descricao_limpa = re.sub(r'[Ww]hats?[Aa]pp?', '', descricao_limpa)
            descricao_limpa = re.sub(r'[Zz][Aa][Pp]', '', descricao_limpa)
            descricao_limpa = re.sub(r'\s+', ' ', descricao_limpa).strip()

        # Montar veículo no formato compatível com o pipeline existente
        # (mesmas chaves que o scraper Selenium gerava)
        vehicle = {
            'id': hash_id,
            'url': url_veiculo,
            'data_coleta': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'titulo_pagina': f"{nome_completo} {submodelo} {ano_modelo} {combustivel} {cor} {portas}P {km} km",
            'nome': nome_completo,
            'preco': preco_formatado,
            'ficha_tecnica': {
                'ano_modelo': ano_modelo,
                'combustivel': combustivel,
                'cor': cor,
                'km': km,
                'portas': portas,
                'cambio': cambio,
            },
            'marca': marca.title() if marca else '',
            'descricao': descricao_limpa,
            'caracteristicas': caracteristicas,
            'fotos': fotos,
            # Campos extras do feed Integra (bônus)
            'submodelo': submodelo,
            'valor_numerico': valor,
            'tipo': tipo,
            'data_cadastro': data_cadastro,
            'data_modificacao': data_modificacao,
        }

        vehicles.append(vehicle)

    return vehicles


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

    # IDs atuais vs anteriores
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
    lines.append("Endereço: Rua Armando Sales de Oliveira, 1000 - Piracicaba/SP")
    lines.append("Horário: Seg-Sex 8h-18h | Sáb 8h-12h")
    lines.append("=" * 60)
    lines.append("")

    for i, v in enumerate(estoque, 1):
        ficha = v.get("ficha_tecnica", {})
        lines.append(f"--- VEÍCULO {i} ---")
        lines.append(f"Nome: {v.get('nome', 'N/A')}")
        lines.append(f"Marca: {v.get('marca', 'N/A')}")
        if v.get('submodelo'):
            lines.append(f"Versão: {v['submodelo']}")
        lines.append(f"Preço: {v.get('preco', 'N/A')}")
        lines.append(f"Ano/Modelo: {ficha.get('ano_modelo', 'N/A')}")
        lines.append(f"Câmbio: {ficha.get('cambio', 'N/A')}")
        lines.append(f"Combustível: {ficha.get('combustivel', 'N/A')}")
        lines.append(f"Cor: {ficha.get('cor', 'N/A')}")
        lines.append(f"Portas: {ficha.get('portas', 'N/A')}")
        lines.append(f"Quilometragem: {ficha.get('km', 'N/A')}")
        if v.get('fotos'):
            lines.append(f"Foto: {v['fotos'][0]}")

        if v.get("descricao"):
            lines.append(f"Descrição: {v['descricao'][:300]}")

        if v.get("caracteristicas"):
            lines.append(f"Opcionais: {', '.join(v['caracteristicas'][:20])}")

        lines.append("")

    # Salvar
    with open(BASE_CONHECIMENTO_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log(f"Base de conhecimento gerada: {BASE_CONHECIMENTO_TXT} ({len(estoque)} veículos)")


def gerar_csv(estoque):
    """Gera um CSV com o estoque atual."""
    if not estoque:
        return

    fieldnames = [
        "id", "nome", "marca", "preco", "ano_modelo", "cambio",
        "combustivel", "cor", "portas", "km", "descricao", "opcionais",
        "url", "data_coleta", "foto"
    ]

    with open(ESTOQUE_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for v in estoque:
            ft = v.get("ficha_tecnica", {})
            row = {
                "id": v.get("id", ""),
                "nome": v.get("nome", ""),
                "marca": v.get("marca", ""),
                "preco": v.get("preco", ""),
                "ano_modelo": ft.get("ano_modelo", ""),
                "cambio": ft.get("cambio", ""),
                "combustivel": ft.get("combustivel", ""),
                "cor": ft.get("cor", ""),
                "portas": ft.get("portas", ""),
                "km": ft.get("km", ""),
                "descricao": v.get("descricao", "")[:200],
                "opcionais": ", ".join(v.get("caracteristicas", [])[:10]),
                "url": v.get("url", ""),
                "data_coleta": v.get("data_coleta", ""),
                "foto": v.get("fotos", [""])[0] if v.get("fotos") else "",
            }
            writer.writerow(row)

    log(f"CSV gerado: {ESTOQUE_CSV}")


def publicar_github():
    """Publica as alterações no GitHub."""
    try:
        # Verificar se é um repositório git
        result = subprocess.run(
            ['git', 'status'], capture_output=True, text=True, cwd=OUTPUT_DIR
        )
        if result.returncode != 0:
            log("Diretório não é um repositório git - pulando publicação")
            return False

        # Add, commit e push
        subprocess.run(['git', 'add', '.'], cwd=OUTPUT_DIR, capture_output=True)

        commit_msg = f"Atualização estoque {datetime.now().strftime('%d/%m/%Y %H:%M')} - Feed Integra Carros"
        result = subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            cwd=OUTPUT_DIR, capture_output=True, text=True
        )

        if 'nothing to commit' in (result.stdout + result.stderr):
            log("Sem alterações para commitar")
            return True

        result = subprocess.run(
            ['git', 'push'],
            cwd=OUTPUT_DIR, capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            log(f"Publicado no GitHub com sucesso")
            log(f"URL pública: {GITHUB_RAW_URL}")
            return True
        else:
            log(f"AVISO: Push falhou: {result.stderr}")
            return False

    except Exception as e:
        log(f"ERRO ao publicar no GitHub: {e}")
        return False


def main():
    """Executa o pipeline completo de atualização do estoque."""
    log("=" * 60)
    log("SCRAPER ANÍSIO AUTOMÓVEIS - Feed XML Integra Carros")
    log(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Fonte: {FEED_URL}")
    log("=" * 60)

    # 1. Baixar feed XML
    xml_content = fetch_xml_feed()
    if not xml_content:
        log("FALHA: Não foi possível baixar o feed XML")
        exit(1)

    # 2. Parsear XML
    log("Parseando feed XML...")
    estoque_novo = parse_xml_feed(xml_content)

    if not estoque_novo:
        log("FALHA: Nenhum veículo encontrado no feed")
        exit(1)

    log(f"Total de veículos no feed: {len(estoque_novo)}")

    # 3. Comparar com estoque anterior (detectar vendidos/novos)
    log("Comparando com estoque anterior...")
    historico, ids_novos, ids_vendidos = atualizar_historico(estoque_novo)

    # 4. Salvar estoque atual (sobrescreve o anterior)
    # Backup antes
    if os.path.exists(ESTOQUE_JSON):
        shutil.copy2(ESTOQUE_JSON, ESTOQUE_JSON.replace('.json', '_backup.json'))

    with open(ESTOQUE_JSON, 'w', encoding='utf-8') as f:
        json.dump(estoque_novo, f, ensure_ascii=False, indent=2)
    log(f"Estoque salvo: {ESTOQUE_JSON}")

    # 5. Gerar base de conhecimento para o Omni
    gerar_base_conhecimento(estoque_novo)

    # 6. Gerar CSV
    gerar_csv(estoque_novo)

    # 7. Publicar no GitHub
    publicar_github()

    # 8. Resumo final
    log("")
    log("=" * 60)
    log("RESUMO DA EXECUÇÃO")
    log(f"  Fonte: Feed XML Integra Carros")
    log(f"  Veículos no estoque: {len(estoque_novo)}")
    log(f"  Novos: {len(ids_novos)}")
    log(f"  Vendidos: {len(ids_vendidos)}")
    log(f"  Base de conhecimento: {BASE_CONHECIMENTO_TXT}")
    log(f"  CSV: {ESTOQUE_CSV}")
    log("=" * 60)

    return estoque_novo


if __name__ == '__main__':
    estoque = main()
    if estoque:
        log(f"\n[OK] Scraper concluído com sucesso: {len(estoque)} veículos")
    else:
        log(f"\n[FALHA] Scraper não coletou veículos")
        exit(1)
