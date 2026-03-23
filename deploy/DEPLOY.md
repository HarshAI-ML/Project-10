# auto_invest_AI — Azure VM Deployment Guide 🚀

> Django + React + ML Models (LSTM/XGBoost) on Azure VM with Nginx, Gunicorn, PM2, DuckDNS & GitHub Actions

---

## Architecture

```
User Browser
     │
     ▼
Port 443 (HTTPS) → Nginx
     ├── https://autoinvest.duckdns.org/          → React dist/ (frontend)
     └── https://autoinvestapi.duckdns.org/api/   → Django via Unix socket (Gunicorn)
```

---

## 1. Create Azure VM

| Setting | Value |
|---|---|
| Size | Standard B2s (2 vCPU, 4 GB RAM) |
| OS | Ubuntu 22.04 LTS |
| Auth | SSH public key |
| Inbound ports | 22, 80, 443 |

Download the `.pem` key. Note the **Public IP**.

---

## 2. SSH into VM

```powershell
# Fix key permissions (PowerShell as Admin)
icacls "C:\path\to\autoinvestkeys.pem" /inheritance:r
icacls "C:\path\to\autoinvestkeys.pem" /remove "NT AUTHORITY\Authenticated Users"
icacls "C:\path\to\autoinvestkeys.pem" /remove "BUILTIN\Users"
icacls "C:\path\to\autoinvestkeys.pem" /grant:r "$env:USERNAME:(R)"

# Connect
ssh -i "C:\path\to\autoinvestkeys.pem" azureuser@YOUR_VM_IP
```

---

## 3. Clone the Project

```bash
cd ~
git clone https://github.com/your-username/auto_invest_AI.git
cd auto_invest_AI
```

---

## 4. Upload ML Models & Database (from your local machine)

> ⚠️ These are gitignored — must be uploaded manually once.

```powershell
# Run these from PowerShell on your Windows machine
$PEM = "C:\path\to\autoinvestkeys.pem"
$VM  = "azureuser@YOUR_VM_IP"
$PRJ = "~/auto_invest_AI"

# Upload trained model files
scp -i $PEM -r backend/predictions/ "${VM}:${PRJ}/backend/"

# Upload database
scp -i $PEM backend/db.sqlite3 "${VM}:${PRJ}/backend/"
```

---

## 5. Set Up Python Virtual Environment

```bash
cd ~/auto_invest_AI/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-prod.txt
deactivate
```

> ⏳ TensorFlow install takes 5–10 min on a fresh VM. Be patient.

---

## 6. Create Backend `.env` File on VM

```bash
nano ~/auto_invest_AI/backend/.env
```

Paste (replace values):
```
DJANGO_SECRET_KEY=your-long-random-secret-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=YOUR_VM_IP autoinvestapi.duckdns.org
CORS_ALLOWED_ORIGINS=https://autoinvest.duckdns.org http://localhost:5173
```

Generate a secret key:
```bash
source venv/bin/activate
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
deactivate
```

---

## 7. Run Django Setup

```bash
cd ~/auto_invest_AI/backend
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser   # optional
deactivate
```

---

## 8. Install Node.js & Build Frontend

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pm2

cd ~/auto_invest_AI/frontend
npm install
echo "VITE_API_URL=https://autoinvestapi.duckdns.org" > .env
npm run build
```

---

## 9. Start Gunicorn with PM2

```bash
chmod +x ~/auto_invest_AI/deploy/rungunicorn.sh
pm2 start ~/auto_invest_AI/deploy/rungunicorn.sh --name autoinvest
pm2 save
pm2 startup   # copy & run the command it outputs
```

Check:
```bash
pm2 list      # status should be: online
pm2 logs autoinvest
```

---

## 10. Configure Nginx

```bash
sudo apt install nginx -y

# Split the combined nginx.conf into two site files
sudo nano /etc/nginx/sites-available/autoinvest
# (paste the FRONTEND server block from deploy/nginx.conf)

sudo nano /etc/nginx/sites-available/autoinvestapi
# (paste the BACKEND server block from deploy/nginx.conf)

sudo ln -s /etc/nginx/sites-available/autoinvest    /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/autoinvestapi /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 11. Set Up DuckDNS Domains

1. Go to [duckdns.org](https://www.duckdns.org/) → log in
2. Create two subdomains:
   - `autoinvest` → YOUR_VM_IP (frontend)
   - `autoinvestapi` → YOUR_VM_IP (backend)
3. Click **Update IP**

---

## 12. Get SSL Certificates

```bash
sudo apt install certbot -y
sudo systemctl stop nginx

sudo certbot certonly --standalone -d autoinvest.duckdns.org
sudo certbot certonly --standalone -d autoinvestapi.duckdns.org

sudo systemctl start nginx
sudo nginx -t && sudo systemctl restart nginx
```

---

## 13. Set Up GitHub Actions CI/CD

### Add GitHub Secrets
`Repo → Settings → Secrets → Actions → New secret`

| Secret | Value |
|---|---|
| `SERVER_IP` | `autoinvestapi.duckdns.org` |
| `SERVER_USER` | `azureuser` |
| `SSH_PRIVATE_KEY` | Full contents of your `.pem` file |
| `SERVER_PATH` | `/home/azureuser/auto_invest_AI` |

### Enable Workflow Permissions
`Repo → Settings → Actions → General → Read and write permissions ✅`

Now every `git push` to `main` auto-deploys! 🎉

---

## 14. URLs

| | URL |
|---|---|
| 🌐 Frontend | https://autoinvest.duckdns.org |
| 🔌 Backend API | https://autoinvestapi.duckdns.org/api/ |
| ⚙️ Django Admin | https://autoinvestapi.duckdns.org/admin/ |

---

## Useful Commands

```bash
pm2 list                          # Check app status
pm2 restart autoinvest            # Restart Django
pm2 logs autoinvest               # View Django logs
sudo systemctl restart nginx      # Restart Nginx
sudo tail -f /var/log/nginx/error.log  # Nginx errors
sudo nginx -t                     # Test Nginx config
```

---

*auto_invest_AI — Azure Deployment 2026*
