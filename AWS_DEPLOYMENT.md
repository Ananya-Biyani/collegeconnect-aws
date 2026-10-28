# CollegeConnect: AWS deployment guide

**Status:** Application prepared for AWS. The ZIP does **not** deploy or create cloud resources by itself. Create the AWS stack in your own account, install the app on EC2, and verify it using the instructions below.

## Architecture (required four AWS services + security groups)

```text
Student/Admin browser
        |
   Internet (HTTP demo only)
        |
   Internet Gateway
        |
  AWS VPC 10.42.0.0/16
        |
  Public subnet 10.42.1.0/24
        |
  EC2 (Amazon Linux 2023, Nginx -> Gunicorn -> Flask)
        |  TCP/3306 ONLY from EC2 security group
  RDS MySQL (not publicly reachable)
        |
  DB subnet group: two private subnets in separate AZs
  10.42.11.0/24 and 10.42.12.0/24

IAM: EC2 instance role with AmazonSSMManagedInstanceCore (Session Manager)
```

### Real integrations made in this package

- `app.py`: selects original memory services in development, persistent SQL service layer in AWS production via `STORAGE_BACKEND=sql`.
- `services/sql_db.py`: SQLAlchemy engine for MySQL/PyMySQL, TLS CA validation, SQL schema (`events`, `registrations`), indexes and uniqueness constraints.
- `services/sql_event_service.py`: events, categories, update, open/close and seat statistics backed by SQL.
- `services/sql_registration_service.py`: durable registration, email lookup, attendee exports, duplicate control. In **MySQL** transactions lock the event row with `SELECT ... FOR UPDATE` and count available seats before inserting, protecting against concurrent overbooking.
- `scripts/init_db.py`: one-time schema setup; inserts the original five sample events if the events table is empty. **No demo student registration records are seeded to RDS**.
- `scripts/create_app_user.py`: one-time restricted MySQL user creation using an interactively entered RDS master password.
- `aws/collegeconnect-stack.yaml`: CloudFormation VPC, subnets, IGW, routing, security groups, IAM role/profile, EC2 instance and **private** RDS instance. RDS master password is managed by Secrets Manager.
- `aws/deploy_on_ec2.sh`, `aws/collegeconnect.service`, `aws/nginx-collegeconnect.conf`: EC2 install and service deployment.

## 0. Cost and data warnings

**This stack creates billable AWS resources**, including EC2, RDS, EBS storage, a public IPv4 address and an RDS-managed Secrets Manager secret. Check [AWS Pricing](https://aws.amazon.com/pricing/) and your account's Free Tier eligibility; do not assume these are free. Set AWS Budgets alerts first. Shut down and delete resources when the project ends. Deleting this template's database destroys its stored data; make backups if you need them.

**Do not upload real student information to a plain HTTP public-IP demo.** The existing app has no student account login/email verification. Anyone knowing a college email can retrieve that email's registration entries on the `My Registrations` page. Until account verification and HTTPS with a trusted certificate are added, use only invented demo names/emails. This project is suitable as an academic demonstration, not an internet-facing production student portal.

## 1. Create your AWS resources (CloudFormation)

1. Log in to AWS Console. Select **Asia Pacific (Mumbai) / ap-south-1**, or another supported Region, and stay in the same Region for every service.
2. Create a small **AWS Budget** with email alerts before proceeding.
3. Open **CloudFormation > Stacks > Create stack > With new resources (standard)**.
4. Select **Upload a template file** and choose `aws/collegeconnect-stack.yaml` from this project.
5. Give the stack a name such as `collegeconnect-demo`. Leave the default EC2/RDS sizes if your account supports them, or adjust the allowed template parameters. **Instance eligibility and cost vary by account/Region.**
6. Review all resource costs and check **I acknowledge that AWS CloudFormation might create IAM resources** (`CAPABILITY_IAM`) before creating the stack. Do not create the stack if charges are unacceptable.
7. Wait until stack status shows `CREATE_COMPLETE`. The CloudFormation **Outputs** tab lists `Ec2InstanceId`, `WebPublicIp`, `RdsEndpoint`, `RdsAdminSecretArn` and `VpcId`.
8. Verify in console:
   - EC2: named `collegeconnect-web`, a public IP assigned.
   - RDS: MySQL instance is private (`Publicly accessible: No`). RDS subnet group spans two private subnets in two AZs.
   - VPC: public subnet routed to IGW, two private database subnets without direct internet routes.
   - EC2 Security Group: inbound TCP/80 from the internet. **No SSH port open.**
   - RDS Security Group: TCP/3306 **only from EC2 Security Group**, not `0.0.0.0/0`.
   - IAM: EC2 role grants `AmazonSSMManagedInstanceCore`, used to manage EC2 with Session Manager.

AWS references: [RDS network requirements](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_CreateDBInstance.html), [RDS Secrets Manager](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html), [Amazon Linux AMI public parameters](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/finding-an-ami-parameter-store.html).

## 2. Connect to EC2 securely with Session Manager

Open **EC2 > Instances > collegeconnect-web > Connect > Session Manager > Connect**. EC2 must have an SSM agent online and an instance role; the template provides the IAM role and uses Amazon Linux 2023, which normally has the agent installed.

If Session Manager is not yet available, check instance status, outbound internet/SSM endpoints, and IAM policy. You do not need to expose inbound SSH.

The Session Manager shell may start as `ssm-user` with sufficient sudo permissions. Switch to ec2-user before cloning:

```bash
sudo dnf install -y git
sudo su - ec2-user
```

Transfer your source code to EC2 **without the `.env` file**. For example, push this extracted project to a GitHub repository without secrets and clone it:

```bash
cd /home/ec2-user
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git CollegeConnect_AWS
cd CollegeConnect_AWS
```

If you use a private repository, authenticate using your normal secure GitHub workflow. Do not place a personal access token in the URL or shell history.

## 3. Download trusted RDS certificate and install dependencies

```bash
sudo dnf install -y python3 python3-pip nginx git
# Amazon Linux 2023 already supplies curl-minimal; do not install full curl.
sudo curl -fL --retry 3 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
  -o /etc/ssl/certs/rds-global-bundle.pem
sudo chmod 644 /etc/ssl/certs/rds-global-bundle.pem
cd /home/ec2-user/CollegeConnect_AWS
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 4. Retrieve master DB password and create a limited application user

1. In CloudFormation **Outputs**, copy `RdsAdminSecretArn`.
2. Open **Secrets Manager** in the same Region. Find that secret and select **Retrieve secret value**. You need permission to view it. AWS generates and manages this master password; **do not upload or commit it**.
3. Set up your `.env` with the real endpoint **before** running the user-creation script:

```bash
cd /home/ec2-user/CollegeConnect_AWS
cp .env.example .env
chmod 600 .env
nano .env
```

Update at least `DB_HOST=<RdsEndpoint output>` and `DB_SSL_CA=/etc/ssl/certs/rds-global-bundle.pem`. Save the file. Then run:

```bash
.venv/bin/python scripts/create_app_user.py
```

Enter the RDS master password only at its interactive prompt. Choose a separate, unique password of at least 16 characters for the database account `collegeapp`. **Do not reuse the RDS master password**. Save that new password securely: it belongs in `.env`, not in GitHub.

The script grants only the database-level privileges necessary for this simplified application and schema initialization. The instance IAM role is not given Secrets Manager read permission; setup uses your explicit AWS Console authorization.

## 5. Complete `.env` for AWS SQL mode

```dotenv
STORAGE_BACKEND=sql
FLASK_DEBUG=0
SECRET_KEY=REPLACE_WITH_A_NEW_RANDOM_SECRET
ADMIN_USERNAME=admin
ADMIN_PASSWORD=REPLACE_WITH_A_LONG_UNIQUE_ADMIN_PASSWORD
DB_HOST=REPLACE_WITH_RDS_ENDPOINT_FROM_CLOUDFORMATION
DB_PORT=3306
DB_NAME=collegeconnect
DB_USER=collegeapp
DB_PASSWORD=REPLACE_WITH_COLLEGEAPP_PASSWORD_FROM_STEP_4
DB_SSL_CA=/etc/ssl/certs/rds-global-bundle.pem
DB_REQUIRE_TLS=1
SESSION_COOKIE_SECURE=0
```

Generate a Flask session secret on the EC2 shell using:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Set a different long admin password. Do **not** use the old default `admin@collegeconnect2026`. Environment-file parsing: quote values containing spaces or `#`, and never print `.env` into your reports. The demo uses `SESSION_COOKIE_SECURE=0` because it is plain HTTP; for an actual HTTPS deployment, change that to `1` and secure the website behind a valid TLS certificate/domain. **Don't input real credentials or student data over HTTP.**

## 6. Deploy and initialize the database

Run from the EC2 shell **as `ec2-user`**:

```bash
cd /home/ec2-user/CollegeConnect_AWS
chmod 600 .env
bash aws/deploy_on_ec2.sh
```

This installs dependencies and the RDS CA bundle, initializes the SQL schema, seeds the original five events (only if no events exist), sets up Gunicorn via systemd, configures Nginx on port 80, and checks `/healthz`.

Useful logs and diagnostics:

```bash
sudo systemctl status collegeconnect
sudo journalctl -u collegeconnect -n 80 --no-pager
sudo nginx -t
curl -i http://127.0.0.1/healthz
```

Once deployment is successful, visit `http://<WebPublicIp>/` for a **synthetic-data demo**. EC2 public IP may change after stopping/restarting the instance, unless you attach a separately billed Elastic IP.

## 7. Live demonstration and verification

1. Show the website homepage and its five seeded events.
2. Register a fictitious student using an invented email address.
3. Verify the confirmation reference and check **My Registrations** with that same demo email.
4. Verify duplicate registration rejected and seating decreased correctly.
5. Log into the admin dashboard using your configured admin password; show the attendee and new event creation.
6. Demonstrate database persistence by restarting the Gunicorn service:

```bash
sudo systemctl restart collegeconnect
```

7. Refresh the website: the registration still exists because records live in RDS, **not in EC2 RAM**.
8. Open **RDS** and show the private endpoint, engine and networking. Open **VPC** and show subnets, IGW and SG rules. Open **IAM** and show the EC2 instance role and SSM policy. In EC2 shell, query registration counts via Python without exposing real student emails:

```bash
cd /home/ec2-user/CollegeConnect_AWS
.venv/bin/python -c 'from dotenv import load_dotenv;load_dotenv();from services.sql_registration_service import get_registration_counts_by_event;print(get_registration_counts_by_event())'
```

9. Show a successful health check `curl -i http://127.0.0.1/healthz`.

## 8. Automated tests

Original in-memory Flask routes remain available for local development:

```bash
python -m pytest tests/test_registration.py tests/test_admin.py -v
```

New SQL adapter persistence tests use SQLite locally (no AWS fees):

```bash
python -m pytest tests/test_sql_persistence.py -v
```

**Important:** SQLite confirms adapter logic but does **not** prove TLS connectivity or MySQL concurrency behavior. Verify full registration and capacity behavior on the live RDS instance during your demonstration. The tests are not a substitute for provisioning and testing real AWS services.

## 9. Cleanup after the project

Open CloudFormation > Stacks > `collegeconnect-demo` > **Delete** when the project ends. **The template's RDS deletion policy destroys the database and its data**. If you need records, export or back up them first. Verify EC2, RDS, EBS volumes, RDS snapshots, Elastic IPs (if independently created), and secrets in that Region afterward; independently created resources are not deleted with the stack. Stopping EC2 alone does **not** end RDS or disk charges.

## 10. Production-hardening backlog (outside academic scope)

- Student authentication or email ownership verification for "My Registrations".
- HTTPS/TLS with a valid domain; set `SESSION_COOKIE_SECURE=1`.
- Admin brute-force protection; stronger authentication rather than a single static password.
- Rate limiting, audit logging, backups and recovery testing.
- App DB user privilege reduction after one-time schema creation, automatic secret rotation, and user-data protections.
- Monitoring via CloudWatch and alerting via AWS Budgets.
