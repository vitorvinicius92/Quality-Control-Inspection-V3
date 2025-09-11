# RNC App v08 — Supabase (GRÁTIS)

**O que muda nesta versão**
- **Banco de dados**: PostgreSQL do **Supabase** (plano free)
- **Fotos**: salvas no **Supabase Storage** (bucket `rnc-fotos`) e exibidas por link
- **PDF**: inclui textos e imagens direto da nuvem
- **Nunca perde os dados** quando o app "dorme" no Streamlit Cloud

## 1) Criar projeto no Supabase (grátis)
1. Acesse https://supabase.com/ e crie uma conta.
2. Crie um projeto → escolha **Region** e **Senha do banco**.
3. No Dashboard: **Project Settings → Database** → copie a URL do banco (ex.: `postgresql://...`) e guarde.
4. Em **Project Settings → API**: copie **Project URL** e **anon key**.

## 2) Criar bucket de Storage (fotos)
- Em **Storage → Create new bucket** → nome: `rnc-fotos` → marque **Public**.

## 3) Publicar no Streamlit Cloud
Suba os arquivos deste pacote para um repositório no GitHub e faça deploy apontando para `app.py`.

### Secrets (App settings → Secrets)
Cole e ajuste:
```
QUALITY_PASS="sua_senha_forte"

# Supabase
SUPABASE_URL="https://SEU-PROJECT-REF.supabase.co"
SUPABASE_KEY="sua_anon_key_ou_service_key"
SUPABASE_DB_URL="postgresql://usuario:senha@host:5432/postgres"  # de Project Settings → Database
SUPABASE_BUCKET="rnc-fotos"

# (opcional) E-mail SMTP
SMTP_HOST="smtp.office365.com"
SMTP_PORT="587"
SMTP_USER="seu.email@empresa.com"
SMTP_PASS="sua_senha_ou_app_password"
EMAIL_FROM="seu.email@empresa.com"
EMAIL_TO="qualidade@empresa.com, gestor@empresa.com"
```

> Dica: se quiser permissões mais fortes para Storage, use a **service_role key** em SUPABASE_KEY e mantenha segura no Secrets.

## 4) Pronto!
- Aberturas, encerramentos e reaberturas gravam no Postgres
- Fotos são enviadas ao bucket e o app guarda apenas o **link**
- PDF baixa as imagens direto do Storage

## Backup
Você ainda pode **Exportar CSV** pelo app quando quiser.
