#!/usr/bin/env bash
# Run ON THE EC2 INSTANCE with: bash aws/deploy_on_ec2.sh
# Assumes CollegeConnect code is already copied/cloned to /home/ec2-user/CollegeConnect_AWS
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="ec2-user"
if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "ERROR: Copy .env.example to .env and set STORAGE_BACKEND=sql, DB_HOST, DB_USER, DB_PASSWORD, DB_SSL_CA, SECRET_KEY, ADMIN_PASSWORD." >&2
  exit 1
fi
if [[ "$(stat -c '%a' "$APP_DIR/.env")" != "600" ]]; then
  echo 'Use chmod 600 .env before deployment.' >&2
  exit 1
fi
if ! grep -q '^STORAGE_BACKEND=sql$' "$APP_DIR/.env"; then
  echo 'Set STORAGE_BACKEND=sql in .env before deploying.' >&2
  exit 1
fi
if [[ "$APP_DIR" != "/home/$APP_USER/CollegeConnect_AWS" ]]; then
  echo "Place this code at /home/$APP_USER/CollegeConnect_AWS so the systemd unit points to the correct folder." >&2
  exit 1
fi
sudo dnf install -y python3 python3-pip nginx git
# AL2023 ships curl-minimal by default; installing full curl conflicts with it.
command -v curl >/dev/null || { echo "curl is required (curl-minimal works on AL2023)" >&2; exit 1; }
sudo curl -fL --retry 3 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o /etc/ssl/certs/rds-global-bundle.pem
sudo chmod 644 /etc/ssl/certs/rds-global-bundle.pem
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
"$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/init_db.py"
sudo mkdir -p /var/www/collegeconnect
sudo cp -a "$APP_DIR/static" /var/www/collegeconnect/static
sudo chmod -R a+rX /var/www/collegeconnect/static
sudo install -m 644 "$APP_DIR/aws/collegeconnect.service" /etc/systemd/system/collegeconnect.service
sudo install -m 644 "$APP_DIR/aws/nginx-collegeconnect.conf" /etc/nginx/conf.d/collegeconnect.conf
# Remove the default Nginx web server file if it conflicts with this config.
sudo systemctl daemon-reload
sudo systemctl enable --now collegeconnect
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl restart nginx
curl -fsS http://127.0.0.1/healthz
echo -e "\nDeployed. Check http://<EC2-public-IP>/ with synthetic demo data only."
