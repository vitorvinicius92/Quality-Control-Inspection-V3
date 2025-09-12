
import os, socket, traceback
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

st.set_page_config(page_title="Teste Supabase Conexão", page_icon="🔌")

# Pega a URL dos secrets
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")
FORCE_IPV4 = os.getenv("FORCE_IPV4", "1") == "1"

def get_db_engine():
    # Tenta conectar no Supabase. Se falhar, cai para SQLite local.
    if not SUPABASE_DB_URL:
        st.warning("⚠️ Nenhuma SUPABASE_DB_URL definida. Usando SQLite.")
        return create_engine("sqlite:///rnc.db", poolclass=NullPool, future=True)

    try:
        if "supabase.co" in SUPABASE_DB_URL and "psycopg2" in SUPABASE_DB_URL and FORCE_IPV4:
            import re
            m = re.search(r'@([^:/?#]+):(\d+)', SUPABASE_DB_URL)
            if m:
                host = m.group(1)
                ipv4 = socket.gethostbyname(host)  # força IPv4
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

        # Tentativa padrão (sem forçar IPv4)
        eng = create_engine(SUPABASE_DB_URL, poolclass=NullPool, future=True)
        with eng.connect() as conn:
            val = conn.exec_driver_sql("SELECT 42;").scalar()
        st.success(f"✅ Conectado ao Supabase (modo padrão) — SELECT 42 -> {val}")
        return eng

    except Exception as e:
        st.error("❌ Falha ao conectar ao Supabase. Cai para SQLite.")
        st.code(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        return create_engine("sqlite:///rnc.db", poolclass=NullPool, future=True)

# ===== Execução =====
st.title("🔌 Teste de Conexão com Supabase")
engine = get_db_engine()
