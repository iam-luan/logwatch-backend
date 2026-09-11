"""Coletor modular de arquivos .log/.txt com failover e heartbeat."""

import argparse
import glob
import os
import socket
import time
import requests


def follow_file(filepath, last_position):
    new_lines = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(last_position)
        for line in f:
            if line.strip():
                new_lines.append(line.rstrip("\n"))
        new_position = f.tell()
    return new_lines, new_position


def send_to_api(api_urls, raw_line, origem):
    for idx, api_url in enumerate(api_urls):
        try:
            resp = requests.post(
                f"{api_url.rstrip('/')}/api/ingest",
                json={"raw_line": raw_line, "origem": origem}, timeout=3,
            )
            if resp.status_code == 201:
                data = resp.json()
                marca = " 🚨 ALERTA CRÍTICO" if data.get("alerta_gerado") else ""
                failover = f" [FAILOVER -> {api_url}]" if idx > 0 else ""
                print(f"[coletor] -> id={data['log_id']} nivel={data['nivel']} instancia={data.get('atendido_por')}{marca}{failover}")
                return True
            print(f"[coletor] {api_url} respondeu {resp.status_code}, tentando próxima...")
        except requests.exceptions.RequestException as exc:
            print(f"[coletor] {api_url} indisponível ({exc.__class__.__name__}), tentando próxima...")
    print("[coletor] ⚠️ nenhuma API disponível; linha não enviada")
    return False


def heartbeat(api_urls, nome, arquivos):
    payload = {"nome": nome, "hostname": socket.gethostname(), "arquivos": ",".join(arquivos)}
    for api_url in api_urls:
        try:
            r = requests.post(f"{api_url.rstrip('/')}/api/collectors/heartbeat", json=payload, timeout=2)
            if r.ok:
                return True
        except requests.exceptions.RequestException:
            continue
    return False


def main():
    parser = argparse.ArgumentParser(description="Coletor de logs distribuído - LogWatch")
    parser.add_argument("--path", default="../sample_logs")
    parser.add_argument("--api", default="http://localhost:5000")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--name", default="collector-01")
    args = parser.parse_args()
    api_urls = [u.strip() for u in args.api.split(",") if u.strip()]
    positions = {}
    last_heartbeat = 0
    print(f"[coletor] monitorando '{os.path.abspath(args.path)}'")
    print(f"[coletor] APIs: {api_urls}")

    while True:
        files = sorted(glob.glob(os.path.join(args.path, "*.log")) + glob.glob(os.path.join(args.path, "*.txt")))
        if time.time() - last_heartbeat >= 10:
            heartbeat(api_urls, args.name, files)
            last_heartbeat = time.time()

        for filepath in files:
            last_pos = positions.get(filepath, 0)
            try:
                new_lines, new_pos = follow_file(filepath, last_pos)
            except FileNotFoundError:
                continue
            positions[filepath] = new_pos
            origem = os.path.basename(filepath)
            for line in new_lines:
                send_to_api(api_urls, line, origem)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
