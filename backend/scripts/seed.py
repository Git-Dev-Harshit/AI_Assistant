"""Load a handful of example support articles through the public API.

    docker compose exec backend python -m scripts.seed
    python -m scripts.seed --api http://localhost:8000      # natively

Re-running is safe: duplicates are reported as "exists" (HTTP 409) and skipped.
"""

import argparse
import sys

import httpx

ARTICLES = [
    {
        "title": "Refund Policy",
        "content": (
            "Customers can request a full refund within 30 days of the purchase date. "
            "After 30 days, purchases are eligible for store credit only, up to 90 days after purchase.\n\n"
            "To request a refund, the customer must provide the original order number and the email address "
            "used at checkout. Support agents create the refund in the billing console under Orders > Refund.\n\n"
            "Approved refunds are returned to the original payment method within 5 business days. "
            "Refunds for orders paid by bank transfer can take up to 10 business days.\n\n"
            "Digital products that have been downloaded more than three times are not eligible for a refund "
            "unless the product is defective."
        ),
    },
    {
        "title": "VPN Troubleshooting",
        "content": (
            "If the VPN client fails to connect, first check that the laptop has a working internet connection "
            "and that the system clock is correct. Certificate validation fails when the clock is off by more "
            "than five minutes.\n\n"
            "Error 809 means the connection was blocked by a firewall or router. Ask the user to switch to a "
            "different network, such as a mobile hotspot, to confirm.\n\n"
            "Error 691 means the username or password was rejected. Make sure the user signs in with their "
            "company email address, not their short username, and that their password has not expired.\n\n"
            "If the connection drops every few minutes, update the VPN client to the latest version from the "
            "self-service portal and disable battery saver mode."
        ),
    },
    {
        "title": "Password Reset Procedure",
        "content": (
            "Employees can reset their own password at the self-service portal using multi-factor "
            "authentication. Passwords expire every 90 days and must be at least 14 characters long.\n\n"
            "If a user is locked out after five failed attempts, the account unlocks automatically after "
            "30 minutes. Support agents can unlock it sooner in the identity admin console after verifying "
            "the user's identity with their employee ID and manager's name.\n\n"
            "Never ask a user to tell you their password, and never send a temporary password over chat."
        ),
    },
    {
        "title": "Shipping and Delivery FAQ",
        "content": (
            "Standard shipping takes 3 to 5 business days within the country. Express shipping takes 1 to 2 "
            "business days and costs an additional fee shown at checkout.\n\n"
            "Orders placed before 2 PM on a business day are dispatched the same day. Customers receive a "
            "tracking number by email once the parcel is dispatched.\n\n"
            "International shipping is available to 40 countries and takes 7 to 14 business days. Customs "
            "duties are paid by the recipient."
        ),
    },
    {
        "title": "Escalation Policy for Support Tickets",
        "content": (
            "Priority 1 tickets (service outage affecting many customers) must be acknowledged within 15 "
            "minutes and escalated to the on-call engineer immediately via the paging system.\n\n"
            "Priority 2 tickets (a major feature broken for one customer) must be acknowledged within 2 hours. "
            "Escalate to the product team if there is no workaround after 4 hours.\n\n"
            "Priority 3 and 4 tickets follow the normal queue with a target first response of one business day."
        ),
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000", help="Backend base URL")
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=60) as client:
        for article in ARTICLES:
            response = client.post("/documents", json=article)
            if response.status_code == 201:
                print(f"indexed  {article['title']} ({response.json()['chunk_count']} chunks)")
            elif response.status_code == 409:
                print(f"exists   {article['title']}")
            else:
                print(f"FAILED   {article['title']}: {response.status_code} {response.text}", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
