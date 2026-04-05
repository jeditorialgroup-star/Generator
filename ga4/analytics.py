#!/usr/bin/env python3
"""
GA4 Data API client — inforeparto.com
Property ID: 515475107
"""

import os
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest, OrderBy, FilterExpression, Filter
)
from google.oauth2 import service_account

CREDENTIALS_PATH = "/home/devops/.credentials/gsc-serviceaccount.json"
PROPERTY_ID = "515475107"


def get_client():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    return BetaAnalyticsDataClient(credentials=creds)


def top_pages(days=28, limit=20):
    client = get_client()
    req = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="pagePath"), Dimension(name="pageTitle")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="engagementRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="bounceRate"),
        ],
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=limit,
    )
    return client.run_report(req)


def traffic_sources(days=28):
    client = get_client()
    req = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="sessionDefaultChannelGroup")],
        metrics=[Metric(name="sessions"), Metric(name="newUsers"), Metric(name="engagementRate")],
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
    )
    return client.run_report(req)


def top_landing_pages(days=28, limit=15):
    client = get_client()
    req = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="landingPage")],
        metrics=[Metric(name="sessions"), Metric(name="newUsers"), Metric(name="bounceRate")],
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=limit,
    )
    return client.run_report(req)


def print_report(response, title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    headers = [d.name for d in response.dimension_headers] + [m.name for m in response.metric_headers]
    print("  " + " | ".join(f"{h[:25]:<25}" for h in headers))
    print("  " + "-" * (28 * len(headers)))
    for row in response.rows:
        dims = [v.value for v in row.dimension_values]
        mets = [v.value for v in row.metric_values]
        values = dims + mets
        print("  " + " | ".join(f"{str(v)[:25]:<25}" for v in values))


if __name__ == "__main__":
    print("🔌 Conectando con GA4 (propiedad 515475107)...")
    try:
        r1 = traffic_sources(28)
        print_report(r1, "FUENTES DE TRÁFICO — últimos 28 días")

        r2 = top_pages(28, 20)
        print_report(r2, "TOP PÁGINAS — últimas 28 días (por sesiones)")

        r3 = top_landing_pages(28, 15)
        print_report(r3, "TOP LANDING PAGES — últimas 28 días")

    except Exception as e:
        print(f"❌ Error: {e}")
