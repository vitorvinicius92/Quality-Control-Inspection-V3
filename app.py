
import os, socket, traceback, re
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

st.set_page_config(page_title="Teste Supabase Conexão v2", page_icon="🔌")

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")
FORCE_IPV4 = os.getenv("FORCE_IPV4", "1") == "1"

def _parse_host(url: str):
    m = re.search(r'@([^:/?#]+):(\d+)', url)
    return (m.group(1).strip(), int(m.group(2))) if m else (None, None)

def get_db_engine():
    if not SUPABASE_DB_URL:
        st.warning("⚠️ Nenhuma SUPABASE_DB_URL definida. Usando SQLite.")
        return create_engine("sqlite:///rnc.db", poolclass=NullPool, future=True)

    st.write("🔎 URL recebida:", SUPABASE_DB_URL)
    host, port = _parse_host(SUPABASE_DB_URL)
    st.write("🔎 Host/Porta parseados:", repr(host), port)

    try:
        if "supabase.co" in SUPABASE_DB_URL and "psycopg2" in SUPABASE_DB_URL and FORCE_IPV4 and host:
            # tenta resolver IPv4 explicitamente
            ipv4 = socket.getaddrinfo(host, None, family=socket.AF_INET)[0][4][0]
            st.write("🌐 IPv4 resolvido:", ipv4)
            eng = create_engine(
                SUPABASE_DB_URL,
                connect_args={"hostaddr": ipv4, "sslmode": "require"},
                poolclass=NullPool,
                future=True,
            )
            with eng.connect() as conn:
                val = conn.exec_driver_sql("SELECT 42;").scalar()
            st.success(f"✅ Conectado ao Supabase (IPv4: {ipv4}) — SELECT 42 -> {val}")
            return eng

    except Exception as e:
        st.error("❌ Falha ao resolver IPv4 (hostaddr). Vou tentar conexão padrão SEM forçar IPv4.")
        st.code(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")

    # Tentativa padrão (sem forçar IPv4)
    try:
        eng = create_engine(SUPABASE_DB_URL, poolclass=NullPool, future=True)
        with eng.connect() as conn:
            val = conn.exec_driver_sql("SELECT 42;").scalar()
        st.success(f"✅ Conectado ao Supabase (modo padrão) — SELECT 42 -> {val}")
        return eng
    except Exception as e2:
        st.error("❌ Falha também no modo padrão. Cai para SQLite.")
        st.code(f"{type(e2).__name__}: {e2}\n\n{traceback.format_exc()}")
        return create_engine("sqlite:///rnc.db", poolclass=NullPool, future=True)

# ===== Execução =====
st.title("🔌 Teste de Conexão com Supabase — v2")
st.caption("Dicas: se host vier estranho (com aspas, espaços, ou caracteres invisíveis), ajuste no secrets.toml. Se precisar, desative IPv4 forçado com FORCE_IPV4='0'.")
engine = get_db_engine()
