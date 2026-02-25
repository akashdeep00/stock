# 🛒 JioMart Stock Notifier – GitHub Actions + Gmail

Automatically checks if **Onion 1 Kg Pack** is in stock at pincode **844505**
every 30 minutes and sends you a Gmail alert when it becomes available.

---

## 📁 File Structure

```
your-repo/
├── check_stock.py                     ← main script
└── .github/
    └── workflows/
        └── stock_check.yml            ← GitHub Actions schedule
```

---

## 🚀 Setup Guide (Step by Step)

### Step 1 — Create a GitHub Repository

1. Go to https://github.com and sign in (or create a free account)
2. Click **"New repository"** (green button)
3. Name it e.g. `jiomart-notifier`
4. Set it to **Private** (recommended)
5. Click **Create repository**

---

### Step 2 — Upload the Files

Upload both files maintaining the folder structure:
- `check_stock.py` → root of repo
- `.github/workflows/stock_check.yml` → create those folders

**Easiest way using GitHub web UI:**

1. Click **"Add file" → "Upload files"** and upload `check_stock.py`
2. Then click **"Add file" → "Create new file"**
3. In the filename box type: `.github/workflows/stock_check.yml`
4. Paste the contents of `stock_check.yml`
5. Click **Commit changes**

---

### Step 3 — Get Your Gmail App Password

> ⚠️ You need a Gmail App Password (NOT your regular Gmail password)

1. Go to your Google Account → https://myaccount.google.com
2. Click **Security** in the left sidebar
3. Under "How you sign in to Google", enable **2-Step Verification** (if not already)
4. Then go to: https://myaccount.google.com/apppasswords
5. Select app: **Mail** | Select device: **Other** → type "JioMart Notifier"
6. Click **Generate** — copy the 16-character password shown (e.g. `abcd efgh ijkl mnop`)

---

### Step 4 — Add GitHub Secrets

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
2. Click **"New repository secret"** and add these 3 secrets:

| Secret Name      | Value                                  |
|-----------------|----------------------------------------|
| `GMAIL_SENDER`   | your Gmail address (e.g. you@gmail.com)|
| `GMAIL_PASSWORD` | the 16-char App Password from Step 3  |
| `NOTIFY_EMAIL`   | email to receive alerts (can be same) |

---

### Step 5 — Enable & Test the Action

1. Go to **Actions** tab in your repo
2. Click **"JioMart Stock Checker"** in the left panel
3. Click **"Run workflow"** → **"Run workflow"** (green button) to test it manually
4. Watch the logs — you should see the stock status printed

✅ If in stock → you'll get an email immediately  
✅ If not in stock → no email, just a log entry  

The workflow will now run **automatically every 30 minutes**.

---

## ⚙️ Customization

| What to change | Where |
|---|---|
| Check frequency | Edit `cron: "*/30 * * * *"` in `stock_check.yml` |
| Different product | Change `PRODUCT_ID` and `PRODUCT_URL` in `check_stock.py` |
| Different pincode | Change `PINCODE` in `check_stock.py` |

### Cron quick reference:
- Every 15 min: `*/15 * * * *`
- Every hour:   `0 * * * *`
- Every 30 min: `*/30 * * * *`

> ⚠️ GitHub Actions free tier = 2,000 minutes/month. Every 30 min = ~1,440 min/month — well within limits!

---

## 📧 Sample Email You'll Receive

```
Subject: 🛒 IN STOCK: Onion 1 Kg Pack – JioMart

Product: Onion 1 Kg Pack
Price: ₹35
Pincode: 844505
Checked at: 25 Feb 2026, 10:30 AM

[Buy Now on JioMart →]
```
