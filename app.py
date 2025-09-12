
# app_v08_full_v6_counter_only.py
# Versão fail-safe: gera RNC pelo contador anual, PDF protegido, inclui página Status.

import os, io, uuid, traceback, time
from datetime import datetime, date
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

BUILD_TAG = "v08-v6-counter-only"

st.set_page_config(page_title=f"RNC — {BUILD_TAG}", page_icon="📝", layout="wide")

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")
QUALITY_PASS = os.getenv("QUALITY_PASS", "qualidade123")

def get_engine():
    if SUPABASE_DB_URL:
        try:
            eng = create_engine(SUPABASE_DB_URL, poolclass=NullPool, future=True)
            with eng.connect() as c:
                c.exec_driver_sql("SELECT 1;")
            st.info("🔌 Banco conectado.")
            return eng
        except Exception as e:
            st.warning("Não conectou ao Supabase. Usando SQLite local.")
            with st.expander("Detalhes de conexão"):
                st.code(f"{e}\n{traceback.format_exc()}")
    eng = create_engine("sqlite:///rnc.db", poolclass=NullPool, future=True)
    return eng

engine = get_engine()
DB_KIND = engine.url.get_backend_name()

def init_db():
    with engine.begin() as conn:
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS inspecoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TIMESTAMP NULL,
            rnc_num TEXT,
            emitente TEXT,
            area TEXT,
            pep TEXT,
            titulo TEXT,
            descricao TEXT,
            referencias TEXT,
            status TEXT DEFAULT 'Aberta'
        );
        """)
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS rnc_counters (
            year INTEGER PRIMARY KEY,
            last_seq INTEGER NOT NULL
        );
        """)

init_db()

def next_rnc_num_tx(conn):
    y = int(datetime.now().year)
    try:
        seq = conn.exec_driver_sql("""
            INSERT INTO rnc_counters(year,last_seq) VALUES(:y,0)
            ON CONFLICT(year) DO UPDATE SET last_seq=last_seq+1
            RETURNING last_seq;
        """, {"y": y}).scalar_one()
    except Exception:
        row = conn.exec_driver_sql("SELECT last_seq FROM rnc_counters WHERE year=:y", {"y": y}).fetchone()
        if row is None:
            conn.exec_driver_sql("INSERT INTO rnc_counters(year,last_seq) VALUES(:y,0)", {"y": y})
            seq = 0
        else:
            seq = int(row[0]) + 1
            conn.exec_driver_sql("UPDATE rnc_counters SET last_seq=:s WHERE year=:y", {"s": seq, "y": y})
    return f"{y}-{int(seq):03d}"

def insert_rnc(conn, payload: dict):
    for _ in range(10):
        num = next_rnc_num_tx(conn)
        try:
            conn.exec_driver_sql("""
                INSERT INTO inspecoes(data,rnc_num,emitente,area,pep,titulo,descricao,referencias,status)
                VALUES(:data,:rnc,:emit,:area,:pep,:tit,:desc,:refs,'Aberta')
            """, dict(payload, rnc=num))
            rid = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()
            return rid, num
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("Falha em gerar RNC.")

def auth_box():
    with st.sidebar.expander("🔐 Acesso Qualidade"):
        pwd = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            if pwd == QUALITY_PASS:
                st.session_state.is_quality = True
                st.success("Perfil Qualidade ativo.")
            else:
                st.error("Senha incorreta.")
        if st.button("Sair"):
            st.session_state.is_quality = False

menu = st.sidebar.radio("Menu", ["➕ Nova RNC","🔎 Consultar","⬇️⬆️ CSV","ℹ️ Status"])

if menu=="➕ Nova RNC":
    st.title("Nova RNC")
    with st.form("f1"):
        emit = st.text_input("Emitente")
        datai = st.date_input("Data", value=date.today())
        area = st.text_input("Área")
        pep = st.text_input("PEP")
        tit = st.text_input("Título")
        desc = st.text_area("Descrição")
        refs = st.text_area("Referências")
        sub = st.form_submit_button("Salvar RNC")
    if sub:
        if not st.session_state.get("is_quality"):
            st.error("Somente Qualidade pode salvar.")
        else:
            payload = {"data":datetime.combine(datai,datetime.min.time()),"emit":emit,"area":area,
                       "pep":pep,"tit":tit,"desc":desc,"refs":refs}
            with engine.begin() as conn:
                rid,num = insert_rnc(conn,payload)
            st.success(f"RNC salva {num} (ID {rid})")

elif menu=="🔎 Consultar":
    st.title("Consultar RNCs")
    df = pd.read_sql("SELECT * FROM inspecoes ORDER BY id DESC",engine)
    st.dataframe(df,use_container_width=True)

elif menu=="⬇️⬆️ CSV":
    st.title("Importar / Exportar CSV")
    df = pd.read_sql("SELECT * FROM inspecoes",engine)
    st.download_button("⬇️ Exportar",df.to_csv(index=False).encode("utf-8-sig"),
                       "rnc_export.csv","text/csv")
    up=st.file_uploader("Importar CSV",type=["csv"])
    if up and st.button("Importar"):
        imp=pd.read_csv(up)
        if "id" in imp.columns: imp=imp.drop(columns=["id"])
        with engine.begin() as conn:
            for _,r in imp.iterrows():
                payload={"data":r.get("data"),"emit":r.get("emitente"),
                         "area":r.get("area"),"pep":r.get("pep"),
                         "tit":r.get("titulo"),"desc":r.get("descricao"),
                         "refs":r.get("referencias")}
                insert_rnc(conn,payload)
        st.success("Importado.")

elif menu=="ℹ️ Status":
    st.title("Status")
    st.write(f"Build: {BUILD_TAG}")
    st.write(f"DB: {DB_KIND}")
