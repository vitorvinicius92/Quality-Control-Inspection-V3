
import os, io, uuid, traceback, csv
from datetime import datetime, date
from typing import List, Optional

import streamlit as st
import pandas as pd

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

# Supabase
try:
    from supabase import create_client
except Exception:
    create_client = None

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Email (opcional)
import smtplib
from email.message import EmailMessage

st.set_page_config(page_title="RNC v08 — Completo (PG fix v3)", page_icon="📝", layout="wide")

# ----------------- Secrets / Env -----------------
SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "RNC-FOTOS")
QUALITY_PASS = os.getenv("QUALITY_PASS", "qualidade123")

# Email (opcional)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO = [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]

# ----------------- Conexões -----------------
def get_engine():
    if SUPABASE_DB_URL:
        try:
            eng = create_engine(SUPABASE_DB_URL, poolclass=NullPool, future=True)
            with eng.connect() as c:
                c.exec_driver_sql("SELECT 1;")
            st.info("🔌 Banco conectado (Supabase).")
            return eng
        except Exception as e:
            st.warning("Não conectou ao Supabase. Usando SQLite local (rnc.db).")
            with st.expander("Detalhes de conexão"):
                st.code(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
    eng = create_engine("sqlite:///rnc.db", poolclass=NullPool, future=True)
    with eng.connect() as c:
        c.exec_driver_sql("SELECT 1;")
    st.warning("⚠️ Banco local (SQLite) em uso.")
    return eng

def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY and create_client):
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None

engine = get_engine()
DB_KIND = engine.url.get_backend_name()
supabase = get_supabase()

# ----------------- Migrações -----------------
def init_db():
    with engine.begin() as conn:
        if DB_KIND == "postgresql":
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS inspecoes (
                id BIGSERIAL PRIMARY KEY,
                data TIMESTAMP NULL,
                rnc_num TEXT,
                emitente TEXT,
                area TEXT,
                pep TEXT,
                titulo TEXT,
                responsavel TEXT,
                descricao TEXT,
                referencias TEXT,
                causador TEXT,
                processo_envolvido TEXT,
                origem TEXT,
                severidade TEXT,
                categoria TEXT,
                acoes TEXT,
                status TEXT DEFAULT 'Aberta',
                encerrada_em TIMESTAMP NULL,
                encerrada_por TEXT,
                encerramento_obs TEXT,
                encerramento_desc TEXT,
                eficacia TEXT,
                responsavel_acao TEXT,
                reaberta_em TIMESTAMP NULL,
                reaberta_por TEXT,
                reabertura_motivo TEXT,
                reabertura_desc TEXT,
                cancelada_em TIMESTAMP NULL,
                cancelada_por TEXT,
                cancelamento_motivo TEXT
            );
            """)
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS fotos (
                id BIGSERIAL PRIMARY KEY,
                inspecao_id BIGINT NOT NULL,
                tipo TEXT,
                url TEXT,
                path TEXT,
                filename TEXT,
                mimetype TEXT
            );
            """)
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS peps (
                id BIGSERIAL PRIMARY KEY,
                code TEXT UNIQUE
            );
            """)
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                blob BYTEA,
                text TEXT
            );
            """)
            # índice único opcional em rnc_num
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uidx_inspecoes_rnc ON inspecoes (rnc_num);")
        else:
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS inspecoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TIMESTAMP NULL,
                rnc_num TEXT,
                emitente TEXT,
                area TEXT,
                pep TEXT,
                titulo TEXT,
                responsavel TEXT,
                descricao TEXT,
                referencias TEXT,
                causador TEXT,
                processo_envolvido TEXT,
                origem TEXT,
                severidade TEXT,
                categoria TEXT,
                acoes TEXT,
                status TEXT DEFAULT 'Aberta',
                encerrada_em TIMESTAMP NULL,
                encerrada_por TEXT,
                encerramento_obs TEXT,
                encerramento_desc TEXT,
                eficacia TEXT,
                responsavel_acao TEXT,
                reaberta_em TIMESTAMP NULL,
                reaberta_por TEXT,
                reabertura_motivo TEXT,
                reabertura_desc TEXT,
                cancelada_em TIMESTAMP NULL,
                cancelada_por TEXT,
                cancelamento_motivo TEXT
            );
            """)
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS fotos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspecao_id INTEGER NOT NULL,
                tipo TEXT,
                url TEXT,
                path TEXT,
                filename TEXT,
                mimetype TEXT
            );
            """)
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS peps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE
            );
            """)
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                blob BLOB,
                text TEXT
            );
            """)
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uidx_inspecoes_rnc ON inspecoes (rnc_num);")

init_db()

# ----------------- Helpers -----------------
def is_quality() -> bool:
    return st.session_state.get("is_quality", False)

def require_quality():
    with st.sidebar.expander("🔐 Entrar (Qualidade)"):
        pwd = st.text_input("Senha", type="password", key="pwd_q")
        c1, c2 = st.columns(2)
        if c1.button("Entrar"):
            if pwd == QUALITY_PASS:
                st.session_state.is_quality = True
                st.success("Perfil Qualidade ativo.")
            else:
                st.error("Senha incorreta.")
        if c2.button("Sair"):
            st.session_state.is_quality = False
            st.info("Saiu do perfil Qualidade.")

def next_rnc_num_sql(conn) -> str:
    y = datetime.now().year
    if DB_KIND == "postgresql":
        # usa split_part para pegar o sufixo numérico
        q = text("""
            SELECT COALESCE(MAX(CAST(SPLIT_PART(rnc_num, '-', 2) AS INTEGER)), 0)
            FROM inspecoes
            WHERE rnc_num LIKE :p
        """)
        mx = conn.execute(q, {"p": f"{y}-%"}).scalar() or 0
    else:
        # sqlite: substr após '-'
        q = text("""
            SELECT COALESCE(MAX(CAST(substr(rnc_num, instr(rnc_num, '-')+1) AS INTEGER)), 0)
            FROM inspecoes
            WHERE rnc_num LIKE :p
        """)
        mx = conn.execute(q, {"p": f"{y}-%"}).scalar() or 0
    return f"{y}-{int(mx)+1:03d}"

def list_peps() -> List[str]:
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("SELECT code FROM peps ORDER BY code").fetchall()
    return [r[0] for r in rows]

def add_peps_bulk(codes: List[str]) -> int:
    ok = 0
    with engine.begin() as conn:
        for c in codes:
            c = c.strip()
            if not c: continue
            try:
                if DB_KIND == "postgresql":
                    conn.exec_driver_sql("INSERT INTO peps(code) VALUES(:c) ON CONFLICT (code) DO NOTHING", {"c": c})
                else:
                    conn.exec_driver_sql("INSERT OR IGNORE INTO peps(code) VALUES(:c)", {"c": c})
                ok += 1
            except Exception:
                pass
    return ok

def set_logo(image_bytes: bytes):
    with engine.begin() as conn:
        if DB_KIND == "postgresql":
            conn.exec_driver_sql("INSERT INTO settings(key, blob) VALUES('logo', :b) ON CONFLICT (key) DO UPDATE SET blob=EXCLUDED.blob", {"b": image_bytes})
        else:
            conn.exec_driver_sql("INSERT OR REPLACE INTO settings(key, blob) VALUES('logo', :b)", {"b": image_bytes})

def get_logo() -> Optional[bytes]:
    with engine.begin() as conn:
        r = conn.exec_driver_sql("SELECT blob FROM settings WHERE key='logo'").fetchone()
    return bytes(r[0]) if (r and r[0] is not None) else None

def clear_logo():
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM settings WHERE key='logo'")

def upload_photos(files, rnc_num: str, tipo: str) -> List[dict]:
    out = []
    if not files:
        return out
    if not supabase:
        st.warning("Supabase Storage não configurado — as fotos não serão enviadas para a nuvem.")
        return out
    try:
        supabase.storage.create_bucket(SUPABASE_BUCKET, public=True)
    except Exception:
        pass
    for f in files:
        try:
            ext = os.path.splitext(f.name)[1].lower() or ".jpg"
            key = f"{rnc_num}/{tipo}/{uuid.uuid4().hex}{ext}"
            data = f.read(); f.seek(0)
            supabase.storage.from_(SUPABASE_BUCKET).upload(key, data, {"content-type": f.type})
            url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(key)
            out.append({"url": url, "path": key, "filename": f.name, "mimetype": f.type or "image/jpeg", "tipo": tipo})
        except Exception as e:
            st.error(f"Falha ao subir {f.name}: {e}")
    return out

def send_email(subject: str, body: str, attachments: List[tuple] = None):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM and EMAIL_TO):
        st.info("✉️ E-mail não enviado: SMTP incompleto nos Secrets.")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(EMAIL_TO)
        msg.set_content(body)
        for att in attachments or []:
            fname, data, mime = att
            maintype, subtype = (mime.split("/", 1) + ["octet-stream"])[:2]
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        st.success("✉️ E-mail enviado.")
    except Exception as e:
        st.warning(f"E-mail não enviado: {e}")

# ----------------- PDF -----------------
def generate_pdf(irow: dict, fotos_ab: List[dict], fotos_enc: List[dict], fotos_rea: List[dict]) -> bytes:
    import io as _io, requests
    buf = _io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    y = H - 30
    logo = get_logo()
    if logo:
        try:
            c.drawImage(ImageReader(_io.BytesIO(logo)), 30, y-25, width=120, height=25, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 14)
    c.drawString(170, y-10, "RNC - RELATÓRIO DE NÃO CONFORMIDADE")
    y -= 40

    def line(label, val):
        nonlocal y
        c.setFont("Helvetica-Bold", 10); c.drawString(30, y, f"{label}: ")
        c.setFont("Helvetica", 10); c.drawString(160, y, str(val or "")); y -= 14

    line("RNC Nº", irow.get("rnc_num"))
    line("Data", str(irow.get("data") or "")[:10])
    line("Emitente", irow.get("emitente"))
    line("Área/Local", irow.get("area"))
    line("PEP", irow.get("pep"))
    line("Categoria", irow.get("categoria"))
    line("Severidade", irow.get("severidade"))
    line("Causador / Processo / Origem",
         f"{irow.get('causador','')} / {irow.get('processo_envolvido','')} / {irow.get('origem','')}")
    line("Responsável", irow.get("responsavel"))

    def block(title, textv):
        nonlocal y
        c.setFont("Helvetica-Bold", 11); c.drawString(30, y, title); y -= 12
        c.setFont("Helvetica", 10)
        for ln in str(textv or "").splitlines():
            c.drawString(30, y, ln[:110]); y -= 12
            if y < 80: c.showPage(); y = H - 30
        y -= 6

    y -= 6
    block("Título", irow.get("titulo"))
    block("Descrição da não conformidade", irow.get("descricao"))
    block("Referências", irow.get("referencias"))

    if irow.get("encerrada_em") or irow.get("encerramento_desc") or irow.get("eficacia"):
        block("Encerramento (observações / descrição / eficácia)",
              f"{irow.get('encerramento_obs','')}\n{irow.get('encerramento_desc','')}\nEficácia: {irow.get('eficacia','')}")
        line("Encerrado por / Em", f"{irow.get('encerrada_por','')} / {irow.get('encerrada_em','')}")

    if irow.get("reaberta_em") or irow.get("reabertura_desc") or irow.get("reabertura_motivo"):
        block("Reabertura (motivo / descrição)",
              f"{irow.get('reabertura_motivo','')}\n{irow.get('reabertura_desc','')}")
        line("Reaberta por / Em", f"{irow.get('reaberta_por','')} / {irow.get('reaberta_em','')}")

    if irow.get("status") == "Cancelada":
        block("Cancelamento", f"Motivo: {irow.get('cancelamento_motivo','')}")
        line("Cancelada por / Em", f"{irow.get('cancelada_por','')} / {irow.get('cancelada_em','')}")

    def draw_fotos(title, lst):
        nonlocal y
        if not lst: return
        c.setFont("Helvetica-Bold", 11); c.drawString(30, y, title); y -= 10
        x = 30; size = 140; pad = 8; col = 0
        for fo in lst:
            try:
                if fo.get("url"):
                    import requests
                    r = requests.get(fo["url"], timeout=8)
                    img = ImageReader(_io.BytesIO(r.content))
                else:
                    img = ImageReader(fo.get("path"))
                if y - size < 60:
                    c.showPage(); y = H - 30
                c.drawImage(img, x, y-size, width=size, height=size, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
            x += size + pad; col += 1
            if col == 3:
                col = 0; x = 30; y -= size + pad
        y -= size + 10

    draw_fotos("Fotos da abertura", fotos_ab)
    draw_fotos("Evidências de encerramento", fotos_enc)
    draw_fotos("Fotos da reabertura", fotos_rea)

    c.showPage(); c.save()
    buf.seek(0); return buf.read()

# ----------------- UI / Sidebar -----------------
def auth_box():
    with st.sidebar.expander("🔐 Acesso Qualidade"):
        pwd = st.text_input("Senha", type="password", key="pwd_q")
        c1, c2 = st.columns(2)
        if c1.button("Entrar"):
            if pwd == QUALITY_PASS:
                st.session_state.is_quality = True
                st.success("Perfil Qualidade ativo.")
            else:
                st.error("Senha incorreta.")
        if c2.button("Sair"):
            st.session_state.is_quality = False
            st.info("Saiu do perfil Qualidade.")

    with st.sidebar.expander("🖼️ Logo da empresa (PDF)"):
        up = st.file_uploader("Enviar logo (PNG/JPG)", type=["png","jpg","jpeg"], key="uplogo")
        if up is not None:
            set_logo(up.getbuffer().tobytes())
            st.success("Logo atualizada.")
        if st.button("Remover logo"):
            clear_logo(); st.warning("Logo removida.")

auth_box()

menu = st.sidebar.radio("Menu", ["➕ Nova RNC", "🔎 Consultar/Editar", "🏷️ PEPs", "⬇️⬆️ CSV"])

# ----------------- Nova RNC -----------------
if menu == "➕ Nova RNC":
    st.title("Nova RNC (RNC Nº automático)")

    # Preview seguro do número
    try:
        with engine.connect() as c:
            rnc_preview = next_rnc_num_sql(c)
    except Exception:
        rnc_preview = f"{datetime.now().year}-001"

    with st.form("form_rnc"):
        col0, col1, col2 = st.columns(3)
        emitente = col0.text_input("Emitente")
        data_insp = col1.date_input("Data", value=date.today())
        col2.text_input("RNC Nº (automático)", value=rnc_preview, disabled=True)

        area = st.text_input("Área/Local", placeholder="Ex.: Correia TR-2011KS-07")
        categoria = st.selectbox("Categoria", ["Segurança","Qualidade","Meio Ambiente","Operação","Manutenção","Outros"])
        severidade = st.selectbox("Severidade", ["Baixa","Média","Alta","Crítica"])
        pep = st.selectbox("PEP (código — descrição)", options=[""] + list_peps())

        causador = st.selectbox("Causador", ["Solda","Pintura","Engenharia","Fornecedor","Cliente","Caldeiraria","Usinagem","Planejamento","Qualidade","RH","Outros"])
        processo = st.selectbox("Processo envolvido", ["Comercial","Compras","Planejamento","Recebimento","Produção","Inspeção Final","Segurança","Meio Ambiente","5S","RH","Outros"])
        origem = st.selectbox("Origem", ["Pintura","Orçamento","Usinagem","Almoxarifado","Solda","Montagem","Cliente","Expedição","Preparação","RH","Outros"])

        titulo = st.text_input("Título", placeholder="Resumo curto da não conformidade")
        descricao = st.text_area("Descrição da não conformidade", height=160)
        referencias = st.text_area("Referências", height=80)

        fotos_ab = st.file_uploader("Fotos da abertura", type=["jpg","jpeg","png"], accept_multiple_files=True)

        submitted = st.form_submit_button("Salvar RNC")

    if submitted:
        if not is_quality():
            st.error("Somente Qualidade pode salvar. Faça login na barra lateral.")
        else:
            with engine.begin() as conn:
                real_num = next_rnc_num_sql(conn)
                if DB_KIND == "postgresql":
                    new_id = conn.exec_driver_sql("""
                        INSERT INTO inspecoes
                        (data, rnc_num, emitente, area, pep, titulo, responsavel, descricao, referencias, causador,
                         processo_envolvido, origem, severidade, categoria, acoes, status)
                        VALUES (:data, :rnc, :emit, :area, :pep, :tit, '', :desc, :refs, :cau, :proc, :ori, :sev, :cat, '', 'Aberta')
                        RETURNING id
                    """, {
                        "data": datetime.combine(data_insp, datetime.min.time()),
                        "rnc": real_num, "emit": emitente, "area": area, "pep": pep, "tit": titulo,
                        "desc": descricao, "refs": referencias, "cau": causador, "proc": processo, "ori": origem,
                        "sev": severidade, "cat": categoria
                    }).scalar_one()
                else:
                    conn.exec_driver_sql("""
                        INSERT INTO inspecoes
                        (data, rnc_num, emitente, area, pep, titulo, responsavel, descricao, referencias, causador,
                         processo_envolvido, origem, severidade, categoria, acoes, status)
                        VALUES (:data, :rnc, :emit, :area, :pep, :tit, '', :desc, :refs, :cau, :proc, :ori, :sev, :cat, '', 'Aberta')
                    """, {
                        "data": datetime.combine(data_insp, datetime.min.time()),
                        "rnc": real_num, "emit": emitente, "area": area, "pep": pep, "tit": titulo,
                        "desc": descricao, "refs": referencias, "cau": causador, "proc": processo, "ori": origem,
                        "sev": severidade, "cat": categoria
                    })
                    new_id = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()

            metas = upload_photos(fotos_ab or [], real_num, "abertura")
            with engine.begin() as conn:
                for m in metas:
                    conn.exec_driver_sql("""
                        INSERT INTO fotos (inspecao_id, tipo, url, path, filename, mimetype)
                        VALUES (:i,:t,:u,:p,:n,:m)
                    """, {"i": new_id, "t": m["tipo"], "u": m["url"], "p": m["path"], "n": m["filename"], "m": m["mimetype"]})

            st.success(f"RNC salva! Nº {real_num} (ID {new_id})")

# ----------------- Consultar/Editar -----------------
elif menu == "🔎 Consultar/Editar":
    st.title("Consultar / Editar RNCs")
    df = pd.read_sql("SELECT id, data, rnc_num, titulo, emitente, area, pep, categoria, severidade, status FROM inspecoes ORDER BY id DESC", engine)
    st.dataframe(df, use_container_width=True, height=320)
    if df.empty:
        st.info("Sem registros.")
    else:
        sel = st.number_input("Ver RNC (ID)", min_value=int(df["id"].min()), max_value=int(df["id"].max()), value=int(df["id"].iloc[0]), step=1)
        with engine.begin() as conn:
            row = conn.exec_driver_sql("SELECT * FROM inspecoes WHERE id=:i", {"i": int(sel)}).mappings().first()
            fotosA = conn.exec_driver_sql("SELECT * FROM fotos WHERE inspecao_id=:i AND tipo='abertura'", {"i": int(sel)}).mappings().all()
            fotosE = conn.exec_driver_sql("SELECT * FROM fotos WHERE inspecao_id=:i AND tipo='encerramento'", {"i": int(sel)}).mappings().all()
            fotosR = conn.exec_driver_sql("SELECT * FROM fotos WHERE inspecao_id=:i AND tipo='reabertura'", {"i": int(sel)}).mappings().all()

        if not row:
            st.error("ID não encontrado.")
        else:
            st.subheader(f"RNC {row['rnc_num']} — {row['status']}")
            st.write(f"**Título:** {row['titulo']}")
            st.write(f"**Descrição:** {row['descricao']}")
            st.write(f"**Referências:** {row['referencias']}")

            cols = st.columns(4)
            for i, fo in enumerate(fotosA[:8]):
                with cols[i % 4]:
                    st.image(fo["url"] or fo["path"], use_column_width=True, caption="Abertura")
            for i, fo in enumerate(fotosE[:8]):
                with cols[i % 4]:
                    st.image(fo["url"] or fo["path"], use_column_width=True, caption="Encerramento")
            for i, fo in enumerate(fotosR[:8]):
                with cols[i % 4]:
                    st.image(fo["url"] or fo["path"], use_column_width=True, caption="Reabertura")

            st.markdown("---")
            if is_quality():
                with st.expander("✅ Encerrar RNC"):
                    encerr_por = st.text_input("Encerrada por", key=f"encpor_{row['id']}")
                    encerr_obs = st.text_area("Observações", key=f"encobs_{row['id']}")
                    encerr_desc = st.text_area("Descrição do fechamento", key=f"encdesc_{row['id']}")
                    eficacia = st.selectbox("Eficácia", ["A verificar","Eficaz","Não eficaz"], key=f"ef_{row['id']}")
                    fotos_enc = st.file_uploader("Evidências (fotos)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"encf_{row['id']}")
                    if st.button("Encerrar agora", key=f"encok_{row['id']}"):
                        metas = upload_photos(fotos_enc or [], row["rnc_num"], "encerramento")
                        with engine.begin() as conn:
                            conn.exec_driver_sql("""
                                UPDATE inspecoes SET status='Encerrada', encerrada_em=:dt, encerrada_por=:por,
                                    encerramento_obs=:obs, encerramento_desc=:desc, eficacia=:ef WHERE id=:i
                            """, {"dt": datetime.now(), "por": encerr_por, "obs": encerr_obs, "desc": encerr_desc, "ef": eficacia, "i": int(sel)})
                            for m in metas:
                                conn.exec_driver_sql("""
                                    INSERT INTO fotos (inspecao_id, tipo, url, path, filename, mimetype)
                                    VALUES (:i,:t,:u,:p,:n,:m)
                                """, {"i": int(sel), "t": m["tipo"], "u": m["url"], "p": m["path"], "n": m["filename"], "m": m["mimetype"]})
                        st.success("RNC encerrada.")

                with st.expander("♻️ Reabrir RNC"):
                    reab_por = st.text_input("Reaberta por", key=f"repor_{row['id']}")
                    reab_motivo = st.text_input("Motivo", key=f"remot_{row['id']}")
                    reab_desc = st.text_area("Descrição da reabertura", key=f"redesc_{row['id']}")
                    fotos_rea = st.file_uploader("Fotos (opcional)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"ref_{row['id']}")
                    if st.button("Reabrir agora", key=f"reok_{row['id']}"):
                        metas = upload_photos(fotos_rea or [], row["rnc_num"], "reabertura")
                        with engine.begin() as conn:
                            conn.exec_driver_sql("""
                                UPDATE inspecoes SET status='Em ação', reaberta_em=:dt, reaberta_por=:por,
                                    reabertura_motivo=:mot, reabertura_desc=:desc WHERE id=:i
                            """, {"dt": datetime.now(), "por": reab_por, "mot": reab_motivo, "desc": reab_desc, "i": int(sel)})
                            for m in metas:
                                conn.exec_driver_sql("""
                                    INSERT INTO fotos (inspecao_id, tipo, url, path, filename, mimetype)
                                    VALUES (:i,:t,:u,:p,:n,:m)
                                """, {"i": int(sel), "t": m["tipo"], "u": m["url"], "p": m["path"], "n": m["filename"], "m": m["mimetype"]})
                        st.success("RNC reaberta.")

                with st.expander("🚫 Cancelar RNC"):
                    c_por = st.text_input("Cancelada por", key=f"canpor_{row['id']}")
                    c_mot = st.text_area("Motivo", key=f"canmot_{row['id']}")
                    if st.button("Cancelar", key=f"canok_{row['id']}"):
                        with engine.begin() as conn:
                            conn.exec_driver_sql("""
                                UPDATE inspecoes SET status='Cancelada', cancelada_em=:dt, cancelada_por=:por, cancelamento_motivo=:mot WHERE id=:i
                            """, {"dt": datetime.now(), "por": c_por, "mot": c_mot, "i": int(sel)})
                        st.success("RNC cancelada.")

                with st.expander("🗑️ Excluir permanentemente"):
                    conf = st.text_input("Digite CONFIRMAR para excluir", key=f"del_{row['id']}")
                    if st.button("Excluir RNC", key=f"delok_{row['id']}"):
                        if conf.strip().upper() == "CONFIRMAR":
                            with engine.begin() as conn:
                                conn.exec_driver_sql("DELETE FROM fotos WHERE inspecao_id=:i", {"i": int(sel)})
                                conn.exec_driver_sql("DELETE FROM inspecoes WHERE id=:i", {"i": int(sel)})
                            st.success("RNC excluída.")
                        else:
                            st.warning("Digite CONFIRMAR exatamente.")
            else:
                st.info("Entre como Qualidade para encerrar/reabrir/cancelar/excluir.")

# ----------------- PEPs -----------------
elif menu == "🏷️ PEPs":
    st.title("Gerenciar PEPs")
    dfp = pd.read_sql("SELECT id, code FROM peps ORDER BY code", engine)
    st.dataframe(dfp, use_container_width=True, height=300)

    st.subheader("Adicionar PEPs por CSV")
    up_pep = st.file_uploader("CSV com 1 PEP por linha (coluna 'code' ou sem cabeçalho).", type=["csv"], key="up_pep")
    if up_pep and st.button("Importar PEPs do CSV"):
        try:
            # tenta ler com cabeçalho
            dfp_in = pd.read_csv(up_pep)
            if 'code' in dfp_in.columns:
                lst = [str(x) for x in dfp_in['code'].fillna('') if str(x).strip()]
            else:
                up_pep.seek(0)
                reader = csv.reader(io.StringIO(up_pep.getvalue().decode('utf-8')))
                lst = [row[0] for row in reader if row and str(row[0]).strip()]
        except Exception:
            up_pep.seek(0)
            reader = csv.reader(io.StringIO(up_pep.getvalue().decode('utf-8')))
            lst = [row[0] for row in reader if row and str(row[0]).strip()]
        n = add_peps_bulk(lst)
        st.success(f"{n} PEP(s) adicionados.")

    st.subheader("Adicionar PEPs manualmente")
    many = st.text_area("Vários (um por linha, formato livre: código — descrição).", height=140)
    if st.button("Adicionar em lote"):
        codes = [l.strip() for l in many.splitlines() if l.strip()]
        n = add_peps_bulk(codes)
        st.success(f"{n} PEP(s) adicionados.")
    c = st.text_input("Adicionar único PEP (código — descrição)")
    if st.button("Adicionar PEP"):
        n = add_peps_bulk([c])
        st.success(f"{n} adicionado(s).")

# ----------------- CSV -----------------
elif menu == "⬇️⬆️ CSV":
    st.title("Importar / Exportar CSV")
    df_all = pd.read_sql("SELECT * FROM inspecoes ORDER BY id DESC", engine)
    st.download_button("⬇️ Exportar CSV", data=df_all.to_csv(index=False).encode("utf-8-sig"), file_name="rnc_export_v08.csv", mime="text/csv")

    st.subheader("Importar CSV de RNCs")
    up = st.file_uploader("Selecione um CSV com colunas compatíveis com 'inspecoes' (não inclua 'id').", type=["csv"])
    if up and st.button("Importar agora"):
        try:
            imp = pd.read_csv(up)
        except Exception:
            up.seek(0)
            imp = pd.read_csv(up, sep=";")

        # remove coluna id se vier
        if 'id' in imp.columns:
            imp = imp.drop(columns=['id'])

        # lista de colunas válidas no banco
        cols_db = [c for c in df_all.columns if c != 'id'] if not df_all.empty else list(imp.columns)

        # mantêm apenas colunas que existem de fato
        use_cols = [c for c in imp.columns if c in cols_db]

        # normaliza datas (coluna 'data', 'encerrada_em', 'reaberta_em', 'cancelada_em')
        for dc in ['data','encerrada_em','reaberta_em','cancelada_em']:
            if dc in use_cols:
                try:
                    imp[dc] = pd.to_datetime(imp[dc], errors='coerce')
                except Exception:
                    pass

        with engine.begin() as conn:
            for _, r in imp.fillna("").iterrows():
                params = {k: r.get(k) for k in use_cols}
                # completar chaves ausentes com NULL
                for k in cols_db:
                    if k not in params:
                        params[k] = None
                placeholders = ", ".join([f":{k}" for k in cols_db])
                conn.exec_driver_sql(f"INSERT INTO inspecoes ({', '.join(cols_db)}) VALUES ({placeholders})", params)
        st.success("Importação concluída.")
