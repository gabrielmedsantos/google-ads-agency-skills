"""Gera GOOGLE_ADS_REFRESH_TOKEN via OAuth2 (Desktop client) e grava no .env.

Uso:
    cd "google ads"
    python mcp/get_refresh_token.py

Vai abrir o navegador, pedir login na conta Google que tem acesso ao MCC,
aceitar o escopo do Google Ads, e voltar pra callback localhost. Refresh token
é printado e atualizado em .env (substituindo a linha PENDENTE).
"""

import os
import re
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Console do Windows costuma vir em cp1252, que não sabe imprimir emoji — sem isso,
# o script quebra com UnicodeEncodeError bem depois de já ter salvo o token no .env.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCOPES = ["https://www.googleapis.com/auth/adwords"]
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
REDIRECT_PORT = 8765  # cadastra http://localhost:8765/ no OAuth client (tipo Web)


def read_env() -> dict:
    if not ENV_PATH.exists():
        sys.exit(f"❌ {ENV_PATH} não existe. Cria com client_id/secret antes.")
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def write_refresh_token(token: str) -> None:
    content = ENV_PATH.read_text(encoding="utf-8")
    new = re.sub(
        r"^GOOGLE_ADS_REFRESH_TOKEN=.*$",
        f"GOOGLE_ADS_REFRESH_TOKEN={token}",
        content,
        flags=re.MULTILINE,
    )
    ENV_PATH.write_text(new, encoding="utf-8")


def main() -> None:
    env = read_env()
    client_id = env.get("GOOGLE_ADS_CLIENT_ID", "")
    client_secret = env.get("GOOGLE_ADS_CLIENT_SECRET", "")
    if not client_id or "PENDENTE" in client_id or not client_secret or "PENDENTE" in client_secret:
        sys.exit("❌ CLIENT_ID/CLIENT_SECRET ausentes ou PENDENTE no .env")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [f"http://localhost:{REDIRECT_PORT}/"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(
        port=REDIRECT_PORT,
        access_type="offline",
        prompt="consent",
        open_browser=True,
    )

    if not creds.refresh_token:
        sys.exit("❌ Sem refresh_token no retorno. Reseta o consent na conta e roda de novo.")

    write_refresh_token(creds.refresh_token)
    print("\n✅ Refresh token salvo em .env")
    print(f"   Conta autorizada: {creds.id_token.get('email') if creds.id_token else '(sem id_token)'}")
    print("\nPróximos passos:")
    print("  1) preencher GOOGLE_ADS_DEVELOPER_TOKEN no .env")
    print("  2) preencher GOOGLE_ADS_LOGIN_CUSTOMER_ID (MCC, só 10 dígitos)")
    print("  3) testar com mcp/test_connection.py (próxima entrega)")


if __name__ == "__main__":
    main()
