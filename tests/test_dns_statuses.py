import unittest
from pathlib import Path
from unittest.mock import patch

from wpe_dns_statuses import describe_dns_issue, detect_dns_elsewhere_rows, is_dns_error_domain


class DnsStatusesTests(unittest.TestCase):
    def test_active_network_status_is_not_error(self):
        domain = {
            "name": "example.com",
            "network_details": {"network_info": {"status": "ACTIVE"}},
        }

        self.assertFalse(is_dns_error_domain(domain))

    def test_not_pointed_network_status_is_error(self):
        domain = {
            "name": "example.com",
            "network_details": {"network_info": {"status": "DNS_NOT_POINTED"}},
        }

        self.assertTrue(is_dns_error_domain(domain))

    def test_error_dns_status_is_error(self):
        domain = {"name": "example.com", "dns_status": "Error"}

        self.assertTrue(is_dns_error_domain(domain))

    def test_aaaa_record_detected_message_is_error(self):
        domain = {"name": "example.com", "status_message": "AAAA record detected"}

        self.assertTrue(is_dns_error_domain(domain))

    def test_pending_txt_without_status_is_error(self):
        domain = {"name": "example.com", "ownership_status": "TXT_VERIFICATION_PENDING"}

        self.assertTrue(is_dns_error_domain(domain))

    def test_describes_network_status(self):
        domain = {
            "name": "example.com",
            "network_details": {"network_info": {"status": "NOT_POINTED"}},
        }

        self.assertEqual(describe_dns_issue(domain), "network_status=NOT_POINTED")

    @patch("wpe_dns_statuses.wpe_auth_header", return_value={})
    @patch("wpe_dns_statuses.find_accounts")
    @patch("wpe_dns_statuses.fetch_all")
    def test_environment_filter_limits_domain_checks(self, fetch_all, find_accounts, _auth):
        find_accounts.return_value = {"sociusdms3": {"id": "account-3"}}
        fetch_all.side_effect = [
            [{"name": "sociusdms3"}],
            [
                {
                    "name": "Spartan Emergency Water Removal",
                    "installs": [
                        {"id": "install-1", "name": "spartanewr"},
                        {"id": "install-2", "name": "otherenv"},
                    ],
                }
            ],
            [{"name": "www.example.com", "status_message": "AAAA record detected"}],
        ]

        rows = detect_dns_elsewhere_rows(
            Path("config.yml"),
            {"sociusdms3"},
            {"spartanewr"},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["environment"], "spartanewr")
        self.assertEqual(fetch_all.call_args_list[-1].args[0], "/installs/install-1/domains")


if __name__ == "__main__":
    unittest.main()
