## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import logging
import boto3
import os
import json
import sys
import uuid
from botocore.exceptions import ClientError

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, "../animal_recommender/utils"))

from constants import *

config = get_config()

# Create KMS Key, which we pass to cdk stack
def create_kms_key(key_name, kms):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT_ID}:root"},
                "Action": "kms:*",
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": [
                        "personalize.amazonaws.com",
                        f"logs.{DEPLOY_REGION}.amazonaws.com",
                        "events.amazonaws.com",
                    ]
                },
                "Action": [
                    "kms:Encrypt*",
                    "kms:Decrypt*",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:Describe*",
                ],
                "Resource": [
                    "*",
                ],
            },
        ],
    }

    kms_key = kms.create_key(
        Policy=json.dumps(policy),
        KeyUsage="ENCRYPT_DECRYPT",
        CustomerMasterKeySpec="SYMMETRIC_DEFAULT",
        Origin="AWS_KMS",
    )
    kms.create_alias(
        AliasName="alias/" + key_name, TargetKeyId=kms_key["KeyMetadata"]["KeyId"]
    )


def key_exist(kms, key_name):
    key_exist = False
    try:
        key = kms.describe_key(KeyId="alias/" + key_name)
        enabled = key["KeyMetadata"]["Enabled"]
        if enabled == True:
            key_exist = True
    except Exception as e:
        print(f"Key does not exist: {e}")

    return key_exist


def bucket_exist(ssm):

    bucket_ssm_path = config["s3SeedNameSsmPath"]
    try:
        bucket_name = ssm.get_parameter(Name=bucket_ssm_path)["Parameter"]["Value"]
        return True
    except Exception as e:
        return False


def get_key_arn(kms, key_name):
    arn = ""
    try:
        key = kms.describe_key(KeyId="alias/" + key_name)
        arn = key["KeyMetadata"]["Arn"]
    except Exception as e:
        print(f"Key does not exist: {e}")

    return arn


def get_key_id(kms, key_name):
    id = ""
    try:
        key = kms.describe_key(KeyId="alias/" + key_name)
        id = key["KeyMetadata"]["KeyId"]
    except Exception as e:
        print(f"Key does not exist: {e}")

    return id


# Create seed bucket for seed data used for personalize datasets
def create_bucket(s3_resource, s3_client, ssm_client, key_id):

    bucket_name = f"{ENV_PREFIX}-recommender-seed-data-bucket" + str(uuid.uuid4())[:8]

    s3_resource.create_bucket(ACL="private", Bucket=bucket_name)

    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AddPersonalizePolicy",
                "Effect": "Allow",
                "Principal": {"Service": "personalize.amazonaws.com"},
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ],
            }
        ],
    }

    bucket_policy = json.dumps(bucket_policy)
    put_policy = s3_client.put_bucket_policy(Bucket=bucket_name, Policy=bucket_policy)
    print(f"Put policy: {put_policy}")
    response_public = s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print(response_public)

    put_encryption = s3_client.put_bucket_encryption(
        Bucket=bucket_name,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "aws:kms",
                        "KMSMasterKeyID": key_id,
                    },
                },
            ]
        },
    )
    print(f"Put encryption: {put_encryption}")

    put_bucket_name_ssm = ssm_client.put_parameter(
        Name=config["s3SeedNameSsmPath"],
        Value=bucket_name,
        Type="String",
        Overwrite=True,
        DataType="text",
    )

    print("Bucket Created")


def main():
    s3_resource = boto3.resource("s3")
    s3_client = boto3.client("s3", region_name=DEPLOY_REGION)
    kms_client = boto3.client("kms", region_name=DEPLOY_REGION)
    ssm_client = boto3.client("ssm", region_name=DEPLOY_REGION)
    key_name = resource_name(kms.Key, "recommender-key")
    key_arn = ""
    key_id = ""

    if key_exist(kms_client, key_name) == True:
        print("Key Exists")
        key_arn = get_key_arn(kms_client, key_name)
        key_id = get_key_id(kms_client, key_name)
        print(f"ID: {key_id}")
        print(f"ARN: {key_arn}")
    else:
        create_kms_key(key_name, kms_client)
        key_id = get_key_id(kms_client, key_name)

    if bucket_exist(ssm_client) == True:
        print("Bucket exists")
    else:
        create_bucket(
            s3_resource,
            s3_client,
            ssm_client,
            key_id,
        )
        print("Bucket Created")


main()
