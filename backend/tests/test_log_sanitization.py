"""Tests for log file PII detection patterns.

Tests the new log-focused regex patterns against realistic log samples
from common log sources: Apache, syslog, JSON, K8s, CloudTrail, etc.
Each test includes both detection samples and false-positive guards.
"""

import pytest
from backend.detectors.regex_detector import RegexDetector


@pytest.fixture
def detector():
    return RegexDetector()


# ────────────────────────────────────────────────────────────
# Azure Connection Strings
# ────────────────────────────────────────────────────────────


class TestAzureConnectionStrings:
    def test_detect_storage_connection_string(self, detector):
        text = "DefaultEndpointsProtocol=https;AccountName=mystorageacct;AccountKey=abc123def456ghi789+/==;EndpointSuffix=core.windows.net"
        entities = detector.detect(text)
        types = [e.entity_type for e in entities]
        assert "CONNECTION_STRING" in types

    def test_detect_in_log_line(self, detector):
        text = '[2024-01-15 10:30:00] ERROR: Connection failed for DefaultEndpointsProtocol=https;AccountName=proddata;AccountKey=Xk9fP2mN+RwZ3Qa7vL5Yj8/=;EndpointSuffix=core.windows.net'
        entities = detector.detect(text)
        conn_strings = [e for e in entities if e.entity_type == "CONNECTION_STRING"]
        assert len(conn_strings) >= 1

    def test_no_false_positive_on_regular_url(self, detector):
        text = "protocol=https endpoint=storage.azure.com"
        entities = detector.detect(text)
        conn_strings = [e for e in entities if e.entity_type == "CONNECTION_STRING" and e.entity_subtype == "AZURE"]
        assert len(conn_strings) == 0


# ────────────────────────────────────────────────────────────
# Azure SAS Tokens
# ────────────────────────────────────────────────────────────


class TestAzureSASTokens:
    def test_detect_sas_token(self, detector):
        text = "https://myaccount.blob.core.windows.net/mycontainer?sv=2021-06-08&ss=bfqt&srt=sco&sp=rwdl&sig=abc123XYZ%3D"
        entities = detector.detect(text)
        types = [e.entity_type for e in entities]
        assert "API_KEY" in types or "URL" in types


# ────────────────────────────────────────────────────────────
# GCP API Keys
# ────────────────────────────────────────────────────────────


class TestGCPAPIKeys:
    def test_detect_gcp_api_key(self, detector):
        # AIza + exactly 35 alphanumeric/dash/underscore chars = 39 total
        text = "gcloud configured with key AIzaSyD-abcdefghijklmno1234567890ABCDEF"
        entities = detector.detect(text)
        api_keys = [e for e in entities if e.entity_type == "API_KEY" and e.entity_subtype == "GCP"]
        assert len(api_keys) >= 1

    def test_detect_in_config(self, detector):
        # AIza + 35 chars = 39 total, standalone (not after key= to avoid overlap)
        text = 'Using API key AIzaSyA1B2C3D4E5F6G7H8I9J0KLMNOPQRSTUVW for project'
        entities = detector.detect(text)
        api_keys = [e for e in entities if e.entity_type == "API_KEY"]
        assert len(api_keys) >= 1

    def test_no_false_positive_on_short_string(self, detector):
        text = "AIzaShort"
        entities = detector.detect(text)
        gcp_keys = [e for e in entities if e.entity_type == "API_KEY" and e.entity_subtype == "GCP"]
        assert len(gcp_keys) == 0


# ────────────────────────────────────────────────────────────
# GCP Service Account Emails
# ────────────────────────────────────────────────────────────


class TestGCPServiceAccounts:
    def test_detect_service_account_email(self, detector):
        text = "authenticating as my-service@my-project.iam.gserviceaccount.com"
        entities = detector.detect(text)
        emails = [e for e in entities if e.entity_type == "EMAIL"]
        assert len(emails) >= 1

    def test_detect_in_error_log(self, detector):
        text = '[ERROR] Permission denied for data-pipeline@analytics-prod-123.iam.gserviceaccount.com on resource'
        entities = detector.detect(text)
        emails = [e for e in entities if e.entity_type == "EMAIL"]
        assert len(emails) >= 1


# ────────────────────────────────────────────────────────────
# AWS ARNs
# ────────────────────────────────────────────────────────────


class TestAWSARNs:
    def test_detect_iam_user_arn(self, detector):
        text = "arn:aws:iam::123456789012:user/johndoe"
        entities = detector.detect(text)
        arns = [e for e in entities if e.entity_type == "AWS_ARN"]
        assert len(arns) >= 1

    def test_detect_s3_arn(self, detector):
        text = "Resource: arn:aws:s3:::my-bucket/data/file.csv"
        entities = detector.detect(text)
        arns = [e for e in entities if e.entity_type == "AWS_ARN"]
        assert len(arns) >= 1

    def test_detect_lambda_arn(self, detector):
        text = "Invoking arn:aws:lambda:us-east-1:123456789012:function:my-function"
        entities = detector.detect(text)
        arns = [e for e in entities if e.entity_type == "AWS_ARN"]
        assert len(arns) >= 1

    def test_no_false_positive_on_bare_arn_prefix(self, detector):
        text = "the arn format is documented at docs.aws.com"
        entities = detector.detect(text)
        arns = [e for e in entities if e.entity_type == "AWS_ARN"]
        assert len(arns) == 0


# ────────────────────────────────────────────────────────────
# ODBC/JDBC Connection Strings
# ────────────────────────────────────────────────────────────


class TestConnectionStrings:
    def test_detect_odbc_with_password(self, detector):
        text = "Server=sql-prod-01.corp.local;Database=CustomerDB;User Id=admin;Password=S3cret!Pass"
        entities = detector.detect(text)
        conn_strings = [e for e in entities if e.entity_type == "CONNECTION_STRING"]
        assert len(conn_strings) >= 1

    def test_detect_jdbc_string(self, detector):
        text = "jdbc:postgresql://db.example.com:5432/mydb?user=admin&password=secret"
        entities = detector.detect(text)
        conn_strings = [e for e in entities if e.entity_type == "CONNECTION_STRING"]
        assert len(conn_strings) >= 1

    def test_detect_data_source_with_pwd(self, detector):
        text = "Data Source=10.0.1.50;Initial Catalog=Inventory;Pwd=MyP@ssw0rd"
        entities = detector.detect(text)
        conn_strings = [e for e in entities if e.entity_type == "CONNECTION_STRING"]
        assert len(conn_strings) >= 1


# ────────────────────────────────────────────────────────────
# CIDR Notation
# ────────────────────────────────────────────────────────────


class TestCIDRNotation:
    def test_detect_cidr(self, detector):
        text = "Allow traffic from 10.0.0.0/8 to 172.16.0.0/12"
        entities = detector.detect(text)
        ips = [e for e in entities if e.entity_type == "IP_ADDRESS"]
        assert len(ips) >= 2

    def test_detect_host_cidr(self, detector):
        text = "Source: 192.168.1.100/32"
        entities = detector.detect(text)
        ips = [e for e in entities if e.entity_type == "IP_ADDRESS"]
        assert len(ips) >= 1

    def test_no_false_positive_on_version(self, detector):
        # Version numbers like 3.2/10 shouldn't match
        text = "Score: 8.5/10"
        entities = detector.detect(text)
        cidr_ips = [e for e in entities if e.entity_type == "IP_ADDRESS" and e.entity_subtype == "CIDR"]
        assert len(cidr_ips) == 0


# ────────────────────────────────────────────────────────────
# Vendor API Keys
# ────────────────────────────────────────────────────────────


class TestVendorAPIKeys:
    def test_detect_sendgrid_key(self, detector):
        # SG. + 22 chars + . + 43 chars
        text = "SG.nOtReAlBuTvAlIdFoRmAt1.abcdefghijklmnopqrstuvwxyz12345678901234567"
        entities = detector.detect(text)
        keys = [e for e in entities if e.entity_type == "API_KEY" and e.entity_subtype == "SENDGRID"]
        assert len(keys) >= 1

    def test_detect_twilio_key(self, detector):
        text = "Twilio API SID: SK1234567890abcdef1234567890abcdef"
        entities = detector.detect(text)
        keys = [e for e in entities if e.entity_type == "API_KEY" and e.entity_subtype == "TWILIO"]
        assert len(keys) >= 1


# ────────────────────────────────────────────────────────────
# Session IDs in URLs
# ────────────────────────────────────────────────────────────


class TestSessionIDs:
    def test_detect_jsessionid(self, detector):
        text = "GET /app/dashboard?JSESSIONID=ABCD1234EF567890ABCDEF1234567890 HTTP/1.1"
        entities = detector.detect(text)
        sessions = [e for e in entities if e.entity_type == "SESSION_ID"]
        assert len(sessions) >= 1

    def test_detect_phpsessid_in_url(self, detector):
        text = "GET /app/dashboard?PHPSESSID=abc123def456ghi789 HTTP/1.1"
        entities = detector.detect(text)
        sessions = [e for e in entities if e.entity_type == "SESSION_ID"]
        assert len(sessions) >= 1

    def test_detect_session_id_param(self, detector):
        text = "/api/data?session_id=abc123def456ghi789xyz012345"
        entities = detector.detect(text)
        sessions = [e for e in entities if e.entity_type == "SESSION_ID"]
        assert len(sessions) >= 1

    def test_no_false_positive_on_short_value(self, detector):
        text = "?sid=abc"  # Too short
        entities = detector.detect(text)
        sessions = [e for e in entities if e.entity_type == "SESSION_ID"]
        assert len(sessions) == 0


# ────────────────────────────────────────────────────────────
# X-Forwarded-For Chains
# ────────────────────────────────────────────────────────────


class TestXForwardedFor:
    def test_detect_forwarded_chain(self, detector):
        text = "X-Forwarded-For: 203.0.113.50, 70.41.3.18, 150.172.238.178"
        entities = detector.detect(text)
        ips = [e for e in entities if e.entity_type == "IP_ADDRESS"]
        assert len(ips) >= 1

    def test_detect_in_access_log(self, detector):
        text = '10.0.0.1 - - [15/Jan/2024:10:30:00 +0000] "GET /api HTTP/1.1" 200 X-Forwarded-For: 198.51.100.1, 203.0.113.2'
        entities = detector.detect(text)
        ips = [e for e in entities if e.entity_type == "IP_ADDRESS"]
        assert len(ips) >= 2


# ────────────────────────────────────────────────────────────
# Kubernetes Identifiers
# ────────────────────────────────────────────────────────────


class TestKubernetesIdentifiers:
    def test_detect_container_registry(self, detector):
        text = "Pulling image: gcr.io/my-project/my-app:v1.2.3"
        entities = detector.detect(text)
        hostnames = [e for e in entities if e.entity_type == "HOSTNAME" and e.entity_subtype == "CONTAINER_REGISTRY"]
        assert len(hostnames) >= 1

    def test_detect_ecr_registry(self, detector):
        text = "image: 123456789012.dkr.ecr.us-east-1.amazonaws.com/my-app:latest"
        entities = detector.detect(text)
        hostnames = [e for e in entities if e.entity_type == "HOSTNAME"]
        assert len(hostnames) >= 1

    def test_detect_ghcr_registry(self, detector):
        text = "docker pull ghcr.io/my-org/my-image:latest"
        entities = detector.detect(text)
        hostnames = [e for e in entities if e.entity_type == "HOSTNAME"]
        assert len(hostnames) >= 1


# ────────────────────────────────────────────────────────────
# Docker Container IDs
# ────────────────────────────────────────────────────────────


class TestDockerContainerIDs:
    def test_detect_container_id(self, detector):
        text = "container_id: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        entities = detector.detect(text)
        containers = [e for e in entities if e.entity_type == "CONTAINER_ID"]
        assert len(containers) >= 1

    def test_detect_docker_short_id(self, detector):
        text = "docker: cid=a1b2c3d4e5f6"
        entities = detector.detect(text)
        containers = [e for e in entities if e.entity_type == "CONTAINER_ID"]
        assert len(containers) >= 1


# ────────────────────────────────────────────────────────────
# SSH/SCP User@Host
# ────────────────────────────────────────────────────────────


class TestSSHCredentials:
    def test_detect_ssh_login(self, detector):
        text = "ssh admin@prod-server-01.corp.local"
        entities = detector.detect(text)
        creds = [e for e in entities if e.entity_type == "CREDENTIAL"]
        assert len(creds) >= 1

    def test_detect_scp_command(self, detector):
        text = "scp -r deploy@192.168.1.50:/opt/app ."
        entities = detector.detect(text)
        creds = [e for e in entities if e.entity_type == "CREDENTIAL"]
        assert len(creds) >= 1

    def test_detect_ssh_with_options(self, detector):
        text = "ssh -i key.pem -p 2222 ubuntu@ec2-1-2-3-4.compute-1.amazonaws.com"
        entities = detector.detect(text)
        creds = [e for e in entities if e.entity_type == "CREDENTIAL"]
        assert len(creds) >= 1


# ────────────────────────────────────────────────────────────
# Realistic Log Corpus Tests
# ────────────────────────────────────────────────────────────


class TestRealisticLogCorpus:
    """End-to-end tests with realistic log samples."""

    def test_apache_access_log(self, detector):
        log = '192.168.1.50 - jsmith [15/Jan/2024:10:30:00 +0000] "GET /api/users?token=abc123 HTTP/1.1" 200 4523'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types

    def test_json_structured_log(self, detector):
        log = '{"timestamp":"2024-01-15T10:30:00Z","level":"ERROR","message":"Auth failed","user_email":"jsmith@acme.com","source_ip":"10.0.1.50","request_id":"abc-123"}'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "EMAIL" in types
        assert "IP_ADDRESS" in types

    def test_stack_trace_with_path(self, detector):
        log = 'File "/home/jsmith/app/api/views.py", line 42, in handle_request'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "FILE_PATH" in types

    def test_ci_cd_log_with_git_token(self, detector):
        log = "fatal: Authentication failed for 'https://ghp_1234567890abcdefghijklmnopqrstuvwxyz@github.com/org/repo.git'"
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        # ghp_ token inside URL is detected as URL or CREDENTIAL (basic auth in URL)
        assert "URL" in types or "API_KEY" in types or "CREDENTIAL" in types

    def test_aws_cloudtrail_log(self, detector):
        log = '{"userIdentity":{"arn":"arn:aws:iam::123456789012:user/admin","accountId":"123456789012"},"sourceIPAddress":"198.51.100.1"}'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "AWS_ARN" in types
        assert "IP_ADDRESS" in types

    def test_kubernetes_event_log(self, detector):
        log = 'E0115 10:30:00.123456 1 reflector.go:178] Failed to pull image gcr.io/production/api-server:v2.1.0 for pod default/api-server-7d9f8b6c5d-x2k4m'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "HOSTNAME" in types  # Container registry or pod name

    def test_windows_event_log(self, detector):
        log = 'An account was successfully logged on. Account Name: jsmith Workstation Name: WS-FINANCE-01 Source Network Address: 10.0.2.150'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "USERNAME" in types or "PERSON" in types

    def test_database_error_log(self, detector):
        log = "FATAL: password authentication failed for user 'dbadmin' connection from 10.0.1.100:5432"
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types

    def test_network_device_cef_log(self, detector):
        log = 'CEF:0|Vendor|Product|1.0|100|Connection|5|src=10.0.1.50 dst=192.168.1.100 suser=ACME\\jsmith dhost=mail-server.corp.local'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types

    def test_no_false_positive_on_benign_text(self, detector):
        """Ensure normal text doesn't trigger log patterns."""
        text = "The server configuration was updated. Please review the deployment guide for version 3.2 release notes."
        entities = detector.detect(text)
        # Should not detect any infrastructure-specific entities
        infra_types = {"AWS_ARN", "CONNECTION_STRING", "CONTAINER_ID", "SESSION_ID"}
        detected_infra = [e for e in entities if e.entity_type in infra_types]
        assert len(detected_infra) == 0
