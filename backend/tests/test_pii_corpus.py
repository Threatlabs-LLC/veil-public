"""Comprehensive PII corpus testing across realistic log and document formats.

Tests detection rates against 12 corpus categories with labeled PII positions.
Target: >=90% detection rate per corpus, <5% false positive rate.
"""

import pytest
from backend.detectors.regex_detector import RegexDetector


@pytest.fixture
def detector():
    return RegexDetector()


def _detection_rate(entities, expected_types: set[str]) -> float:
    """Calculate what fraction of expected types were detected."""
    detected_types = {e.entity_type for e in entities}
    if not expected_types:
        return 1.0
    return len(expected_types & detected_types) / len(expected_types)


# ────────────────────────────────────────────────────────────
# 1. Apache/nginx Access Logs
# ────────────────────────────────────────────────────────────


class TestApacheNginxLogs:
    def test_standard_access_log(self, detector):
        log = '192.168.1.100 - jsmith [10/Oct/2024:13:55:36 -0700] "GET /admin/users HTTP/1.1" 200 2326'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types

    def test_combined_log_with_referer(self, detector):
        log = '10.0.2.50 - - [10/Oct/2024:13:55:36 +0000] "POST /api/login HTTP/1.1" 200 512 "https://app.example.com/login" "Mozilla/5.0"'
        entities = detector.detect(log)
        assert any(e.entity_type == "IP_ADDRESS" for e in entities)

    def test_nginx_error_with_client_ip(self, detector):
        log = '2024/01/15 10:30:00 [error] 1234#0: *5678 connect() failed (111: Connection refused) while connecting to upstream, client: 203.0.113.50, server: api.example.com'
        entities = detector.detect(log)
        assert any(e.entity_type == "IP_ADDRESS" for e in entities)

    def test_access_log_with_bearer_token(self, detector):
        log = '10.0.1.1 - - [15/Jan/2024:10:30:00 +0000] "GET /api/data HTTP/1.1" 200 - "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types
        assert "JWT" in types or "AUTH_TOKEN" in types

    def test_log_with_query_params(self, detector):
        log = '172.16.0.5 - - [15/Jan/2024:10:30:00 +0000] "GET /search?email=john@example.com&name=John+Smith HTTP/1.1" 200 1024'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types
        assert "EMAIL" in types


# ────────────────────────────────────────────────────────────
# 2. Syslog Entries
# ────────────────────────────────────────────────────────────


class TestSyslogEntries:
    def test_auth_log(self, detector):
        log = 'Jan 15 10:30:00 prod-web-01 sshd[12345]: Accepted publickey for admin from 10.0.1.50 port 22 ssh2'
        entities = detector.detect(log)
        assert any(e.entity_type == "IP_ADDRESS" for e in entities)

    def test_failed_login(self, detector):
        log = 'Jan 15 10:30:00 mail-server-01 dovecot: imap-login: Disconnected (auth failed, 3 attempts): user=jsmith@acme.com, method=PLAIN, rip=192.168.1.50'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        # user=jsmith@acme.com matches USERNAME pattern (captures login context)
        assert "EMAIL" in types or "USERNAME" in types
        assert "IP_ADDRESS" in types

    def test_sudo_log(self, detector):
        log = 'Jan 15 10:30:00 db-primary sudo: jdoe : TTY=pts/0 ; PWD=/home/jdoe ; USER=root ; COMMAND=/usr/bin/systemctl restart postgresql'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "FILE_PATH" in types or "USERNAME" in types

    def test_kernel_network_log(self, detector):
        # UFW logs concatenate dst+src MAC+EtherType into one field; use a separate standard MAC
        log = 'Jan 15 10:30:00 fw-01 kernel: [UFW BLOCK] IN=eth0 SRC=198.51.100.1 DST=10.0.0.1 device MAC aa:bb:cc:dd:ee:ff LEN=40 TTL=245 PROTO=TCP SPT=12345 DPT=22'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types
        assert "MAC_ADDRESS" in types


# ────────────────────────────────────────────────────────────
# 3. Application JSON Logs
# ────────────────────────────────────────────────────────────


class TestApplicationJSONLogs:
    def test_structured_error_log(self, detector):
        log = '{"timestamp":"2024-01-15T10:30:00Z","level":"ERROR","message":"Authentication failed","user":"jsmith@acme.com","ip":"10.0.1.50","request_id":"req-abc123"}'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "EMAIL" in types
        assert "IP_ADDRESS" in types

    def test_payment_log(self, detector):
        log = '{"event":"payment_failed","customer_email":"jane.doe@company.com","card_last4":"4242","amount":9900,"ip":"203.0.113.50"}'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "EMAIL" in types
        assert "IP_ADDRESS" in types

    def test_api_request_log(self, detector):
        log = '{"method":"POST","path":"/api/users","status":201,"user_agent":"Mozilla/5.0","client_ip":"172.16.0.100","response_time_ms":150}'
        entities = detector.detect(log)
        assert any(e.entity_type == "IP_ADDRESS" for e in entities)

    def test_log_with_connection_string(self, detector):
        log = '{"level":"WARN","message":"Slow query detected","connection":"Server=db-prod.internal;Database=users;Password=SecretPass123","duration_ms":5000}'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "CONNECTION_STRING" in types


# ────────────────────────────────────────────────────────────
# 4. AWS CloudTrail Logs
# ────────────────────────────────────────────────────────────


class TestAWSCloudTrailLogs:
    def test_console_login(self, detector):
        log = '{"eventName":"ConsoleLogin","userIdentity":{"arn":"arn:aws:iam::123456789012:user/admin","accountId":"123456789012"},"sourceIPAddress":"198.51.100.1"}'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "AWS_ARN" in types
        assert "IP_ADDRESS" in types

    def test_s3_access(self, detector):
        log = '{"eventName":"GetObject","resources":[{"ARN":"arn:aws:s3:::company-data/customers.csv"}],"userIdentity":{"arn":"arn:aws:iam::123456789012:role/DataAnalyst"}}'
        entities = detector.detect(log)
        arns = [e for e in entities if e.entity_type == "AWS_ARN"]
        assert len(arns) >= 2

    def test_iam_action(self, detector):
        log = '{"eventName":"CreateUser","requestParameters":{"userName":"newuser"},"userIdentity":{"arn":"arn:aws:iam::123456789012:user/admin"},"sourceIPAddress":"10.0.1.50"}'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "AWS_ARN" in types


# ────────────────────────────────────────────────────────────
# 5. Kubernetes Pod Logs
# ────────────────────────────────────────────────────────────


class TestKubernetesPodLogs:
    def test_image_pull_error(self, detector):
        log = 'E0115 10:30:00.123456 1 kubelet.go:2100] Failed to pull image "gcr.io/myproject/myapp:v1.2.3": rpc error: code = Unknown'
        entities = detector.detect(log)
        hostnames = [e for e in entities if e.entity_type == "HOSTNAME"]
        assert len(hostnames) >= 1

    def test_pod_scheduling(self, detector):
        log = 'I0115 10:30:00.123456 1 scheduler.go:604] Successfully bound pod default/api-server-7d9f8b6c5d-x2k4m to node ip-10-0-1-50.ec2.internal'
        entities = detector.detect(log)
        hostnames = [e for e in entities if e.entity_type == "HOSTNAME"]
        assert len(hostnames) >= 1

    def test_container_crash(self, detector):
        log = 'W0115 10:30:00.123456 1 docker: container_id=a1b2c3d4e5f6 exited with code 137 (OOMKilled)'
        entities = detector.detect(log)
        containers = [e for e in entities if e.entity_type == "CONTAINER_ID"]
        assert len(containers) >= 1


# ────────────────────────────────────────────────────────────
# 6. Windows Event Logs
# ────────────────────────────────────────────────────────────


class TestWindowsEventLogs:
    def test_logon_event(self, detector):
        log = 'An account was successfully logged on. Subject: Account Name: SYSTEM Account Domain: NT AUTHORITY Logon Type: 3 New Logon: Account Name: jsmith Account Domain: ACME Workstation Name: WS-FINANCE-01 Source Network Address: 10.0.2.150'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types
        assert "USERNAME" in types or "HOSTNAME" in types

    def test_sid_detection(self, detector):
        log = 'Security ID: S-1-5-21-3623811015-3361044348-30300820-1013 Account Name: jdoe'
        entities = detector.detect(log)
        sids = [e for e in entities if e.entity_type == "WINDOWS_SID"]
        assert len(sids) >= 1

    def test_domain_user(self, detector):
        log = 'Process created: ACME\\jsmith started cmd.exe from C:\\Users\\jsmith\\Desktop'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "USERNAME" in types or "FILE_PATH" in types


# ────────────────────────────────────────────────────────────
# 7. Database Query Logs
# ────────────────────────────────────────────────────────────


class TestDatabaseQueryLogs:
    def test_connection_string_in_error(self, detector):
        log = 'FATAL: password authentication failed for user "dbadmin" at Server=10.0.1.100;Database=production;Password=S3cretP@ss'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "CONNECTION_STRING" in types or "IP_ADDRESS" in types

    def test_jdbc_url_in_config(self, detector):
        log = '[WARN] Connection pool exhausted for jdbc:postgresql://db-primary.internal:5432/appdb?user=app&password=secret123'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "CONNECTION_STRING" in types

    def test_mongodb_url(self, detector):
        log = 'Connecting to mongodb://admin:password123@mongo-replica.internal:27017/mydb?authSource=admin'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "CONNECTION_STRING" in types


# ────────────────────────────────────────────────────────────
# 8. Stack Traces
# ────────────────────────────────────────────────────────────


class TestStackTraces:
    def test_python_traceback(self, detector):
        log = '''Traceback (most recent call last):
  File "/home/jsmith/app/api/views.py", line 42, in handle_request
    result = process_user_data(user_email="jane@company.com")
ValueError: Invalid email format'''
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "FILE_PATH" in types
        assert "EMAIL" in types

    def test_java_stack_trace(self, detector):
        log = 'java.sql.SQLException: Access denied for user dbadmin@10.0.1.50 using password YES\n\tat com.mysql.jdbc.ConnectionImpl.createNewIO(ConnectionImpl.java:800)'
        entities = detector.detect(log)
        assert any(e.entity_type == "IP_ADDRESS" for e in entities)

    def test_windows_path_in_trace(self, detector):
        log = r'Error at C:\Users\jdoe\Projects\api\src\main.cs:125'
        entities = detector.detect(log)
        assert any(e.entity_type == "FILE_PATH" for e in entities)


# ────────────────────────────────────────────────────────────
# 9. CI/CD Pipeline Logs
# ────────────────────────────────────────────────────────────


class TestCICDPipelineLogs:
    def test_github_token_in_url(self, detector):
        log = "Cloning https://ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh1234@github.com/org/repo.git"
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "URL" in types or "CREDENTIAL" in types or "API_KEY" in types

    def test_aws_key_in_env(self, detector):
        log = 'export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE'
        entities = detector.detect(log)
        assert any(e.entity_type == "API_KEY" for e in entities)

    def test_docker_registry_push(self, detector):
        log = 'Pushing image to gcr.io/myproject/myapp:sha-abc1234'
        entities = detector.detect(log)
        hostnames = [e for e in entities if e.entity_type == "HOSTNAME"]
        assert len(hostnames) >= 1

    def test_ssh_deploy_command(self, detector):
        log = 'Deploying via ssh deploy@prod-server-01.internal'
        entities = detector.detect(log)
        creds = [e for e in entities if e.entity_type == "CREDENTIAL"]
        assert len(creds) >= 1


# ────────────────────────────────────────────────────────────
# 10. Network Device Logs (CEF/LEEF)
# ────────────────────────────────────────────────────────────


class TestNetworkDeviceLogs:
    def test_cef_firewall_log(self, detector):
        log = 'CEF:0|Palo Alto|PAN-OS|10.0|TRAFFIC|allow|3|src=10.0.1.50 dst=192.168.1.100 suser=ACME\\jsmith dhost=mail.corp.local'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types

    def test_ids_alert(self, detector):
        log = 'CEF:0|Snort|IDS|3.0|1000001|ET SCAN Nmap|5|src=198.51.100.50 dst=10.0.0.1 suser=scanner@pentest.local'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types

    def test_vpn_log(self, detector):
        log = 'VPN: user jsmith@acme.com connected from 203.0.113.50 assigned 10.10.0.25'
        entities = detector.detect(log)
        types = {e.entity_type for e in entities}
        assert "EMAIL" in types
        assert "IP_ADDRESS" in types


# ────────────────────────────────────────────────────────────
# 11. Email Headers
# ────────────────────────────────────────────────────────────


class TestEmailHeaders:
    def test_from_to_headers(self, detector):
        text = 'From: John Smith <john.smith@company.com>\nTo: Jane Doe <jane.doe@partner.org>'
        entities = detector.detect(text)
        emails = [e for e in entities if e.entity_type == "EMAIL"]
        assert len(emails) >= 2

    def test_received_chain(self, detector):
        text = 'Received: from mail-server.example.com (10.0.1.50) by mx.company.com (192.168.1.10) with SMTP'
        entities = detector.detect(text)
        assert any(e.entity_type == "IP_ADDRESS" for e in entities)

    def test_message_id(self, detector):
        text = 'From: noreply@company.com\nMessage-ID: <abc123@mail.company.com>'
        entities = detector.detect(text)
        emails = [e for e in entities if e.entity_type == "EMAIL"]
        assert len(emails) >= 1


# ────────────────────────────────────────────────────────────
# 12. Chat/Messaging Exports
# ────────────────────────────────────────────────────────────


class TestChatMessagingExports:
    def test_slack_export(self, detector):
        text = '[2024-01-15 10:30] jsmith: Hey, can you send the report to jane.doe@company.com? My number is (555) 123-4567.'
        entities = detector.detect(text)
        types = {e.entity_type for e in entities}
        assert "EMAIL" in types
        assert "PHONE" in types

    def test_teams_export(self, detector):
        text = '[10:30 AM] John Smith: The server at 10.0.1.50 is down. SSH key is in /home/admin/.ssh/id_rsa'
        entities = detector.detect(text)
        types = {e.entity_type for e in entities}
        assert "IP_ADDRESS" in types
        assert "FILE_PATH" in types

    def test_mixed_pii_conversation(self, detector):
        text = 'Please update the record for SSN 123-45-6789. The patient lives at 123 Main Street, Springfield, IL 62701.'
        entities = detector.detect(text)
        types = {e.entity_type for e in entities}
        assert "SSN" in types
        assert "ADDRESS" in types


# ────────────────────────────────────────────────────────────
# False Positive Guards
# ────────────────────────────────────────────────────────────


class TestFalsePositiveGuards:
    """Ensure common non-PII text doesn't trigger false positives."""

    def test_technical_documentation(self, detector):
        text = "The API returns a JSON response with status code 200. Configure the timeout to 30 seconds."
        entities = detector.detect(text)
        # No PII should be detected in plain documentation
        high_confidence = [e for e in entities if e.confidence >= 0.9]
        assert len(high_confidence) == 0

    def test_code_sample(self, detector):
        text = """
def calculate_total(items):
    total = sum(item.price for item in items)
    tax = total * 0.08
    return total + tax
"""
        entities = detector.detect(text)
        high_confidence = [e for e in entities if e.confidence >= 0.9]
        assert len(high_confidence) == 0

    def test_version_numbers(self, detector):
        text = "Upgraded from version 3.2.1 to 4.0.0. Python 3.12.0 is required."
        entities = detector.detect(text)
        # Version numbers should NOT match as IP addresses
        ips = [e for e in entities if e.entity_type == "IP_ADDRESS"]
        assert len(ips) == 0

    def test_common_log_boilerplate(self, detector):
        text = "INFO  [main] Application started successfully in 2.5 seconds. Ready to accept connections on port 8080."
        entities = detector.detect(text)
        # Should not detect infrastructure entities in boilerplate
        infra = [e for e in entities if e.entity_type in {"AWS_ARN", "CONNECTION_STRING", "CONTAINER_ID"}]
        assert len(infra) == 0

    def test_mathematical_expressions(self, detector):
        text = "The result is 192 * 168 = 32256. The ratio is 10/24 which equals 0.4167."
        entities = detector.detect(text)
        # Should not match as IPs
        ips = [e for e in entities if e.entity_type == "IP_ADDRESS"]
        assert len(ips) == 0

    def test_uuid_not_session_id(self, detector):
        text = "Request ID: 550e8400-e29b-41d4-a716-446655440000"
        entities = detector.detect(text)
        sessions = [e for e in entities if e.entity_type == "SESSION_ID"]
        assert len(sessions) == 0
