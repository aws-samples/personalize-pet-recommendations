#!/usr/bin/env python3
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import os, yaml, re, json

from aws_cdk import (
    aws_iam as iam,
    aws_ssm as ssm,
    aws_lambda as _lambda,
    aws_stepfunctions as stepfunctions,
    aws_stepfunctions_tasks as tasks,
    aws_dynamodb as dynamodb,
    aws_ecr as ecr,
    custom_resources as cr,
    aws_codebuild as codebuild,
    aws_s3 as s3,
    aws_logs as logs,
    aws_kms as kms,
    aws_sns as sns,
    aws_events as events,
    aws_kinesis as kinesis,
    aws_kinesisfirehose as kinesisfirehose,
    aws_personalize as personalize,
    aws_cloudformation as cloudformation,
)

import aws_cdk as cdk

CDK_ENVIRONMENT = os.environ.get("CDK_ENVIRONMENT", "dev")
ACCOUNT_ID = os.environ.get("ACCOUNT_ID", "123456789012")
DEPLOY_REGION = os.environ.get("CDK_DEPLOY_REGION", "us-east-1")
SEED_BUCKET = os.environ.get(
    "S3_SEED_BUCKET", f"{CDK_ENVIRONMENT}-recommender-seed-data-bucket-s3b"
)

# Set ENV_PREFIX for resource naming
ENV_PREFIX = ""
if CDK_ENVIRONMENT.casefold() == "dev":
    ENV_PREFIX = "dev"


def resource_suffix(resourceType):
    suffix = "err"
    if resourceType is iam.Role:
        suffix = "rol"
    if resourceType is iam.Policy:
        suffix = "plc"
    if resourceType is ssm.StringParameter:
        suffix = "ssm"
    if resourceType is _lambda.Function:
        suffix = "lbd"
    if resourceType is stepfunctions.StateMachine:
        suffix = "stm"
    if resourceType is tasks.LambdaInvoke:
        suffix = "sfn"
    if resourceType is dynamodb.Table:
        suffix = "ddb"
    if resourceType is ecr.Repository:
        suffix = "ecr"
    if resourceType is cr.AwsCustomResource:
        suffix = "cfr"
    if resourceType is cr.Provider:
        suffix = "pvd"
    if resourceType is cdk.CustomResource:
        suffix = "crs"
    if resourceType is codebuild.Project:
        suffix = "cbp"
    if resourceType is s3.Bucket:
        suffix = "s3b"
    if resourceType is tasks.SageMakerCreateTrainingJob:
        suffix = "smr"
    if resourceType is logs.LogGroup:
        suffix = "log"
    if resourceType is logs.LogStream:
        suffix = "lgs"
    if resourceType is kms.Key:
        suffix = "key"
    if resourceType is sns.Topic:
        suffix = "sns"
    if resourceType is events.Rule:
        suffix = "evt"
    if resourceType is kinesis.Stream:
        suffix = "kss"
    if resourceType is kinesisfirehose.CfnDeliveryStream:
        suffix = "ksf"
    if resourceType is kinesis.CfnStreamConsumer:
        suffix = "ksc"
    if resourceType is personalize.CfnDatasetGroup:
        suffix = "pdg"
    if resourceType is personalize.CfnSchema:
        suffix = "psc"
    if resourceType is personalize.CfnDataset:
        suffix = "pds"
    if resourceType is personalize.CfnSolution:
        suffix = "pss"
    if resourceType is cr.Provider:
        suffix = "crp"
    if resourceType is cdk.CustomResource:
        suffix = "ccr"
    if resourceType is cloudformation.CfnWaitCondition:
        suffix = "cwc"
    if resourceType is cloudformation.CfnWaitConditionHandle:
        suffix = "cwh"

    return suffix


def resource_name(type, context):
    return f"{ENV_PREFIX}-" + context + "-" + resource_suffix(type)


def get_config():
    config_path = os.path.join("config", f"{CDK_ENVIRONMENT}.yaml")
    with open(config_path) as fr:
        return yaml.safe_load(fr)
