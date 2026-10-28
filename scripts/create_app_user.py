"""One-time RDS setup to create a limited collegeapp DB account.
Run on EC2 after RDS is ready and AWS's CA bundle has been downloaded.
Uses interactive passwords and never writes/admin-logs them.
"""
from getpass import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
import pymysql

if __name__ == "__main__":
    host = os.environ.get("DB_HOST", "")
    ca = os.environ.get("DB_SSL_CA", "/etc/ssl/certs/rds-global-bundle.pem")
    if not host or not os.path.isfile(ca):
        raise SystemExit("Set DB_HOST and download RDS CA bundle first.")
    admin_pwd = getpass("RDS master password for ccadmin (not stored): ")
    app_pwd = getpass("New collegeapp database password: ")
    app_pwd2 = getpass("Confirm collegeapp password: ")
    if not app_pwd or len(app_pwd) < 16 or app_pwd != app_pwd2:
        raise SystemExit("Use a matching application password of at least 16 characters.")
    with pymysql.connect(
        host=host, port=int(os.getenv("DB_PORT", "3306")), user="ccadmin", password=admin_pwd,
        database="collegeconnect", ssl_ca=ca, ssl_verify_cert=True, ssl_verify_identity=True,
        autocommit=True, connect_timeout=10
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("CREATE USER IF NOT EXISTS 'collegeapp'@'%' IDENTIFIED BY %s", (app_pwd,))
            cursor.execute("ALTER USER 'collegeapp'@'%' IDENTIFIED BY %s", (app_pwd,))
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, REFERENCES "
                "ON collegeconnect.* TO 'collegeapp'@'%'"
            )
    print("Application database user created. Put its password in your protected .env file.")
