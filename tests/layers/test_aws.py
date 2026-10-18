"""Wspólna konfiguracja boto3: src/layers/common/python/codzis_common/aws.py."""

import boto3
from botocore.config import Config

from codzis_common.aws import AWS_CONFIG


def test_aws_config_timeouts_and_retries():
    assert AWS_CONFIG.connect_timeout == 2
    assert AWS_CONFIG.read_timeout == 5
    # botocore: max_attempts = liczba ponowień, więc razem do 4 prób (total_max_attempts)
    assert AWS_CONFIG.retries["mode"] == "standard"
    assert AWS_CONFIG.retries["total_max_attempts"] == 4


def test_aws_config_merge_keeps_own_options():
    merged = AWS_CONFIG.merge(Config(signature_version="s3v4"))
    assert merged.signature_version == "s3v4"
    assert merged.read_timeout == 5
    client = boto3.client("s3", config=merged)
    assert client.meta.config.connect_timeout == 2
