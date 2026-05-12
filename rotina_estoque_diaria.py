#!/usr/bin/env python3
"""
Rotina Diária de Atualização do Estoque - Anísio Automóveis
============================================================
1. Executa o scraper (coleta veículos do site)
2. Publica no GitHub (base de conhecimento)
3. Gera arquivo de instruções para atualizar a tabela do Omni

Uso: python3 rotina_estoque_diaria.py
Agendamento: Executar diariamente às 7h da manhã
"""

import json
import os
import subprocess
import sys
from datetime import datetime

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(OUTPUT_DIR, "rotina_diaria_log.txt")
ESTOQUE_JSON = os.path.join(OUTPUT_DIR, "estoque_atual.json")
ESTOQUE_CSV = os.path.join(OUTPUT_DIR, "estoque_atual.csv")


def log(msg):
    """Registra mensagem no log com timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def executar_scraper():
    """Executa o scraper principal."""
    log("Executando scraper...")
    scraper_path = os.path.join(OUTPUT_DIR, "scraper_anisio.py")
    
    result = subprocess.run(
        [sys.executable, scraper_path],
        capture_output=True,
        text=True,
        cwd=OUTPUT_DIR,
        timeout=300  # 5 minutos de timeout
    )
    
    if result.returncode != 0:
        log(f"ERRO no scraper: {result.stderr}")
        return False
    
    # Verificar se o estoque foi gerado
    if not os.path.exists(ESTOQUE_JSON):
        log("ERRO: estoque_atual.json não foi gerado")
        return False
    
    with open(ESTOQUE_JSON, "r", encoding="utf-8") as f:
        estoque = json.load(f)
    
    log(f"Scraper concluído: {len(estoque)} veículos coletados")
    return True


def gerar_resumo():
    """Gera um resumo da execução para o log."""
    with open(ESTOQUE_JSON, "r", encoding="utf-8") as f:
        estoque = json.load(f)
    
    log("=" * 50)
    log("RESUMO DA ROTINA DIÁRIA")
    log(f"  Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    log(f"  Veículos no estoque: {len(estoque)}")
    log(f"  Arquivo JSON: {ESTOQUE_JSON}")
    log(f"  Arquivo CSV: {ESTOQUE_CSV}")
    log("=" * 50)
    
    return len(estoque)


def main():
    log("=" * 60)
    log("ROTINA DIÁRIA DE ATUALIZAÇÃO DO ESTOQUE")
    log("=" * 60)
    
    # 1. Executar scraper (coleta + GitHub)
    if not executar_scraper():
        log("FALHA: Scraper não concluiu com sucesso")
        return False
    
    # 2. Gerar resumo
    total = gerar_resumo()
    
    log(f"Rotina concluída com sucesso! {total} veículos atualizados.")
    log("A tabela do Omni será atualizada pelo Manus via navegador.")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
