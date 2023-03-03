## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
from platform import node
from aws_cdk import (
    Duration,
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_kinesis as kinesis,
    aws_kinesisfirehose as firehose,
    aws_lambda_event_sources as event_sources,
    aws_kms as kms,
    aws_logs as logs,
    aws_lambda as _lambda,
    aws_personalize as personalize,
    aws_codebuild as codebuild,
    aws_cloudformation as cloudformation,
    aws_events_targets as targets,
)
import aws_cdk as cdk
from constructs import Construct
from animal_recommender.utils.constants import *

config = get_config()
from _version import __version__ as VERSION


class AnimalRecommenderStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, seed_bucket_name: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.create_kms_key()
        self.create_sns_topic()
        self.create_s3_bucket()
        self.create_iam_policies(seed_bucket_name)
        self.create_kinesis_role(seed_bucket_name)
        self.create_logs()
        self.create_kinesis_stream()
        self.create_iam_roles()
        self.create_personalize(seed_bucket_name)
        self.create_solution_version_cr()
        self.create_event_tracker_cr()
        self.create_campaign_cr(seed_bucket_name)
        self.create_reranking_solution()
        self.create_reranking_solution_version()
        self.create_reranking_campaign_cr()
        self.create_lambdas()
        self.create_state_machine_tasks()
        self.create_state_machine_definition()

    def create_kms_key(self):
        self.kms_key = kms.Key.from_lookup(
            self,
            "Recommender-Key",
            alias_name=f"alias/{ENV_PREFIX}-recommender-key-key",
        )

        self.aws_kms_s3 = kms.Key.from_lookup(
            self,
            "AWS-Managed-S3-Key",
            alias_name=f"alias/aws/s3",
        )

    def create_s3_bucket(self):
        self.s3_bucket = s3.Bucket(
            self,
            resource_name(s3.Bucket, "recommender-bucket"),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.kms_key,
            server_access_logs_prefix="logs",
            versioned=True,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        self.personalize_bucket_policy = iam.PolicyStatement(
            actions=["s3:GetObject", "s3:ListBucket"],
            resources=[
                f"arn:aws:s3:::{self.s3_bucket.bucket_name}",
                f"arn:aws:s3:::{self.s3_bucket.bucket_name}/*",
            ],
            principals=[iam.ServicePrincipal("personalize.amazonaws.com")],
        )

        self.s3_bucket.add_to_resource_policy(self.personalize_bucket_policy)

        ssm_s3_bucket = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "recommender-s3bucket-ssm"),
            string_value=self.s3_bucket.bucket_name,
            parameter_name=config["s3NameSsmPath"],
        )

    # Create Log groups
    def create_logs(self):
        self.firehose_log_group = logs.LogGroup(
            self,
            "Recommender Firehose Log Group",
            log_group_name=resource_name(logs.LogGroup, "recommender-firehose-logs"),
            encryption_key=self.kms_key,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        self.firehose_log_stream = logs.LogStream(
            self,
            "MyLogStream",
            log_group=self.firehose_log_group,
            # the properties below are optional
            log_stream_name=resource_name(
                logs.LogStream, "recommender-firehose-logstream"
            ),
        )

    # SNS topic for notifications
    def create_sns_topic(self):
        self.sns_topic = sns.Topic(
            self,
            resource_name(sns.Topic, "recommender-topic"),
            topic_name=resource_name(sns.Topic, "recommender-topic"),
            master_key=self.kms_key,
        )
        self.sns_topic.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[iam.ServicePrincipal("events.amazonaws.com")],
                actions=[
                    "sns:Publish",
                ],
                resources=[
                    f"arn:aws:sns:{DEPLOY_REGION}:{ACCOUNT_ID}:{ENV_PREFIX}-recommender-topic-sns",
                ],
            ),
        )

    def create_iam_policies(self, seed_bucket_name):
        self.kinesis_policy = iam.Policy(
            self,
            "Kinesis policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "kinesis:Describe*",
                        "kinesis:Put*",
                        "kinesis:List*",
                        "kinesis:Get*",
                        "kinesis:Register*",
                        "kinesis:Subscribe*",
                    ],
                    resources=[
                        f"arn:aws:kinesis:{DEPLOY_REGION}:{ACCOUNT_ID}:stream/{ENV_PREFIX}-recommender-stream-kss",
                    ],
                )
            ],
        )

        self.s3_policy = iam.Policy(
            self,
            "S3 policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "s3:List*",
                        "s3:Get*",
                        "s3:Put*",
                        "s3:Delete*",
                        "s3:AbortMultipartUpload",
                    ],
                    resources=[
                        f"arn:aws:s3:::{self.s3_bucket.bucket_name}",
                        f"arn:aws:s3:::{self.s3_bucket.bucket_name}/*",
                    ],
                ),
            ],
        )

        self.s3_seed_bucket_policy = iam.Policy(
            self,
            "S3 seed bucket policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "s3:List*",
                        "s3:Get*",
                        "s3:Put*",
                        "s3:Delete*",
                        "s3:AbortMultipartUpload",
                    ],
                    resources=[
                        f"arn:aws:s3:::{seed_bucket_name}",
                        f"arn:aws:s3:::{seed_bucket_name}/*",
                    ],
                ),
            ],
        )

        self.cloudwatch_put_list_policy = iam.Policy(
            self,
            "Cloudwatch Policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "cloudwatch:Put*",
                        "cloudwatch:List*",
                    ],
                    resources=[
                        f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-recommender*",
                    ],
                ),
            ],
        )

        self.kms_logs_policy = iam.Policy(
            self,
            "KMS logs policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "kms:Encrypt*",
                        "kms:Decrypt*",
                        "kms:ReEncrypt*",
                        "kms:GenerateDataKey*",
                        "kms:Describe*",
                    ],
                    resources=[
                        self.kms_key.key_arn,
                        f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-recommender*",
                        f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-recommender-firehose-logs-log:*",
                    ],
                )
            ],
        )

        self.ssm_policy = iam.Policy(
            self,
            "SSM Policy",
            statements=[
                iam.PolicyStatement(
                    actions=["ssm:Get*", "ssm:Put*"],
                    resources=[
                        f"arn:aws:ssm:{DEPLOY_REGION}:{ACCOUNT_ID}:parameter/animal-recommender*"
                    ],
                ),
            ],
        )

        self.lambda_invoke_policy = iam.Policy(
            self,
            "Lambda Invoke Policy",
            statements=[
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[
                        f"arn:aws:lambda:{DEPLOY_REGION}:{ACCOUNT_ID}:function:{ENV_PREFIX}-recommender*",
                        f"arn:aws:lambda:{DEPLOY_REGION}:{ACCOUNT_ID}:function:{ENV_PREFIX}-reranking*",
                    ],
                ),
            ],
        )

        self.personalize_policy = iam.Policy(
            self,
            "Personalize Policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "personalize:Create*",
                        "personalize:Get*",
                        "personalize:Delete*",
                        "personalize:CreateEventTracker",
                        "personalize:Describe*",
                        "personalize:List*",
                        "personalize:Update*",
                        "personalize:Start*",
                    ],
                    resources=[
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:dataset-group/{ENV_PREFIX}-recommender-datasetgroup-pdg",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:dataset/{ENV_PREFIX}-recommender-datasetgroup-pdg/ITEMS",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:dataset/{ENV_PREFIX}-recommender-datasetgroup-pdg/INTERACTIONS",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:campaign/{ENV_PREFIX}-recommender-personalize-campaign-cpn",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:campaign/{ENV_PREFIX}-reranking-personalize-campaign-cpn",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:solution/{ENV_PREFIX}-recommender-solution-pss",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:solution/{ENV_PREFIX}-recommender-solution-pss/*",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:solution/{ENV_PREFIX}-reranking-solution-pss",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:solution/{ENV_PREFIX}-reranking-solution-pss/*",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:event-tracker/{ENV_PREFIX}-recommender-personalize-event-tracker-tkr",
                    ],
                )
            ],
        )

        self.code_build_policy = iam.Policy(
            self,
            "Codebuild Policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "codebuild:List*",
                        "codebuild:Start*",
                        "codebuild:Update*",
                        "codebuild:Get*",
                    ],
                    resources=[
                        f"arn:aws:codebuild:{DEPLOY_REGION}:{ACCOUNT_ID}:project/{ENV_PREFIX}-recommender-create-campaign-cbp",
                        f"arn:aws:codebuild:{DEPLOY_REGION}:{ACCOUNT_ID}:build/{ENV_PREFIX}-recommender-create-campaign*",
                    ],
                ),
            ],
        )

        self.kms_use_policy = iam.Policy(
            self,
            "KMS Use Policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "kms:Encrypt*",
                        "kms:Decrypt*",
                        "kms:ReEncrypt*",
                        "kms:GenerateDataKey*",
                        "kms:Describe*",
                    ],
                    resources=[
                        self.aws_kms_s3.key_arn,
                        self.kms_key.key_arn,
                        f"arn:aws:kinesis:{DEPLOY_REGION}:{ACCOUNT_ID}:stream/{ENV_PREFIX}-recommender-stream-kss",
                        f"arn:aws:s3:::{self.s3_bucket.bucket_name}",
                        f"arn:aws:s3:::{self.s3_bucket.bucket_name}/*",
                        f"arn:aws:s3:::{seed_bucket_name}",
                        f"arn:aws:s3:::{seed_bucket_name}/*",
                        f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-recommender-firehose-logs-log:*",
                        f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-recommender-state-machine-logs-log:*",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:campaign/{ENV_PREFIX}-recommender-personalize-campaign-cpn",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:campaign/{ENV_PREFIX}-reranking-personalize-campaign-cpn",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:dataset-group/{ENV_PREFIX}-recommender-datasetgroup-pdg",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:dataset/{ENV_PREFIX}-recommender-datasetgroup-pdg/ITEMS",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:dataset/{ENV_PREFIX}-recommender-datasetgroup-pdg/INTERACTIONS",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:solution/{ENV_PREFIX}-recommender-solution-pss",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:solution/{ENV_PREFIX}-recommender-solution-pss/*",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:solution/{ENV_PREFIX}-reranking-solution-pss",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:solution/{ENV_PREFIX}-reranking-solution-pss/*",
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:event-tracker/{ENV_PREFIX}-recommender-personalize-event-tracker-tkr",
                    ],
                ),
            ],
        )

        self.personalize_put_event_policy = iam.Policy(
            self,
            "Personalize Put Event Policy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "personalize:PutEvents",
                    ],
                    resources=[
                        f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:event-tracker/{ENV_PREFIX}-recommender-personalize-event-tracker-tkr",
                    ],
                ),
            ],
        )

    # Role for kinesis
    def create_kinesis_role(self, seed_bucket_name):
        self.kinesis_role = iam.Role(
            self,
            resource_name(iam.Role, "recommender-kinesis-role"),
            role_name=resource_name(iam.Role, "recommender-kinesis-role"),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("kinesis.amazonaws.com"),
                iam.ServicePrincipal("firehose.amazonaws.com"),
            ),
        )

        self.kinesis_role.attach_inline_policy(self.kinesis_policy)
        self.kinesis_role.attach_inline_policy(self.s3_policy)
        self.kinesis_role.attach_inline_policy(self.cloudwatch_put_list_policy)
        self.kinesis_role.attach_inline_policy(self.kms_logs_policy)

        # Role for personalize
        self.personalize_role = iam.Role(
            self,
            resource_name(iam.Role, "recommender-personalize-role"),
            role_name=resource_name(iam.Role, "recommender-personalize-role"),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("personalize.amazonaws.com"),
            ),
            managed_policies=[
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    resource_name(iam.Policy, "recommender-execution-policy"),
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole",
                ),
            ],
        )
        self.personalize_role.attach_inline_policy(self.s3_policy)
        self.personalize_role.attach_inline_policy(self.s3_seed_bucket_policy)
        self.personalize_role.attach_inline_policy(self.ssm_policy)
        self.personalize_role.attach_inline_policy(self.lambda_invoke_policy)
        self.personalize_role.attach_inline_policy(self.personalize_policy)
        self.personalize_role.attach_inline_policy(self.code_build_policy)
        self.personalize_role.attach_inline_policy(self.kms_use_policy)

        # Role for codebuild
        self.codebuild_role = iam.Role(
            self,
            resource_name(iam.Role, "recommender-codebuild-role"),
            role_name=resource_name(iam.Role, "recommender-codebuild-role"),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("codebuild.amazonaws.com"),
            ),
        )

        self.codebuild_role.attach_inline_policy(self.s3_policy)
        self.codebuild_role.attach_inline_policy(self.s3_seed_bucket_policy)
        self.codebuild_role.attach_inline_policy(self.ssm_policy)
        self.codebuild_role.attach_inline_policy(self.personalize_policy)
        self.codebuild_role.attach_inline_policy(self.code_build_policy)
        self.codebuild_role.attach_inline_policy(self.kms_use_policy)

        # Role for dataset import job
        self.dataset_role = iam.Role(
            self,
            resource_name(iam.Role, "recommender-dataset-role"),
            role_name=resource_name(iam.Role, "recommender-dataset-role"),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("personalize.amazonaws.com"),
            ),
        )

        self.dataset_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonPersonalizeFullAccess"
            )
        )
        self.dataset_role.attach_inline_policy(self.kms_use_policy)
        self.dataset_role.attach_inline_policy(self.s3_policy)
        self.dataset_role.attach_inline_policy(self.s3_seed_bucket_policy)
        self.dataset_role.attach_inline_policy(self.personalize_policy)

    def create_iam_roles(self):
        # Role for put_events lambda
        self.put_events_role = iam.Role(
            self,
            resource_name(iam.Role, "recommender-putevents-role"),
            role_name=resource_name(iam.Role, "recommender-putevents-role"),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("apigateway.amazonaws.com"),
            ),
            managed_policies=[
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    resource_name(iam.Policy, "recommender-putevents-policy"),
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole",
                ),
            ],
        )

        self.put_events_role.attach_inline_policy(self.personalize_put_event_policy)
        self.put_events_role.attach_inline_policy(self.ssm_policy)
        self.put_events_role.attach_inline_policy(self.cloudwatch_put_list_policy)

        # Role for get recs and reranking lambda
        self.get_recommendations_role = iam.Role(
            self,
            resource_name(iam.Role, "recommender-getrecs-role"),
            role_name=resource_name(iam.Role, "recommender-getrecs-role"),
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    resource_name(iam.Policy, "recommender-getrecs-policy"),
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole",
                ),
            ],
            inline_policies={
                "Lambda": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "personalize:Get*",
                                "personalize:List*",
                                "personalize:Describe*",
                            ],
                            resources=[
                                f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:campaign/{ENV_PREFIX}-recommender-personalize-campaign-cpn",
                                f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:campaign/{ENV_PREFIX}-reranking-personalize-campaign-cpn",
                            ],
                        ),
                    ]
                )
            },
        )
        self.get_recommendations_role.attach_inline_policy(self.ssm_policy)
        self.get_recommendations_role.attach_inline_policy(self.kms_use_policy)
        self.get_recommendations_role.attach_inline_policy(
            self.cloudwatch_put_list_policy
        )

    # Create kinesis stream
    def create_kinesis_stream(self):

        self.kinesis_stream = kinesis.Stream(
            self,
            resource_name(kinesis.Stream, "recommender-stream"),
            stream_name=resource_name(kinesis.Stream, "recommender-stream"),
            retention_period=Duration.hours(48),
            encryption=kinesis.StreamEncryption.KMS,
            encryption_key=self.kms_key,
            stream_mode=kinesis.StreamMode.ON_DEMAND,
        )

        ssm_kinesis_stream = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "recommender-kinesis-stream-ssm"),
            string_value=self.kinesis_stream.stream_name,
            parameter_name=config["kinesisStreamNameSsmPath"],
        )

        self.kinesis_stream_consumer = kinesis.CfnStreamConsumer(
            self,
            resource_name(kinesis.CfnStreamConsumer, "recommender-streamconsumer"),
            consumer_name=resource_name(
                kinesis.CfnStreamConsumer, "recommender-streamconsumer"
            ),
            stream_arn=self.kinesis_stream.stream_arn,
        )
        # Record historical events in s3
        self.delivery_stream = firehose.CfnDeliveryStream(
            self,
            resource_name(kinesisfirehose.CfnDeliveryStream, "recommender-firehose"),
            delivery_stream_type="KinesisStreamAsSource",
            extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                bucket_arn=self.s3_bucket.bucket_arn,
                prefix="YYYY/MM/DD/HH",
                error_output_prefix="error/!{firehose:error-output-type}/",
                role_arn=self.kinesis_role.role_arn,
                compression_format="UNCOMPRESSED",
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    interval_in_seconds=300, size_in_m_bs=50
                ),
            ),
            kinesis_stream_source_configuration=kinesisfirehose.CfnDeliveryStream.KinesisStreamSourceConfigurationProperty(
                kinesis_stream_arn=self.kinesis_stream.stream_arn,
                role_arn=self.kinesis_role.role_arn,
            ),
        )
        self.delivery_stream.node.add_dependency(self.kinesis_policy)

    def create_lambdas(self):
        # have kinesis trigger put events lambda
        self.kinesis_event_source = event_sources.KinesisEventSource(
            stream=self.kinesis_stream,
            starting_position=lambda_.StartingPosition.LATEST,
            batch_size=50,
        )

        self.put_events_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-put-events-lambda"),
            function_name=resource_name(
                _lambda.Function, "recommender-put-events-lambda"
            ),
            handler="put_personalize_events.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/api"),
            role=self.put_events_role,
            events=[self.kinesis_event_source],
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "event_tracker_ssm_path": config["eventTrackerIdSsmPath"],
            },
        )
        # Get Recs api lambda
        self.get_recommendation_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-get-recommendation-lambda"),
            function_name=resource_name(
                _lambda.Function, "recommender-get-recommendation-lambda"
            ),
            handler="get_recommendation.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/api"),
            role=self.get_recommendations_role,
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "campaign_arn_ssm_path": config["recommendationCampaignArnSsmPath"],
            },
        )

        ssm_recommendation_lambda_name = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "recommender-get-recommender-ssm"),
            string_value=self.get_recommendation_lambda.function_name,
            parameter_name=config["getRecommendationNamePath"],
        )
        # Get reranking lambda
        self.get_reranking_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-get-reranking-lambda"),
            function_name=resource_name(
                _lambda.Function, "recommender-get-reranking-lambda"
            ),
            handler="get_reranking.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/api"),
            role=self.get_recommendations_role,
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "reranking_campaign_arn_ssm_path": config[
                    "rerankingCampaignArnSsmPath"
                ],
            },
        )

        self.get_reranking_lambda.add_permission(
            "Api-Gateway Invocation",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
        )

        ssm_reranking_lambda_name = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "recommender-get-reranking-ssm"),
            string_value=self.get_reranking_lambda.function_name,
            parameter_name=config["getRerankingNamePath"],
        )

    def create_personalize(self, seed_bucket_name):
        # Items and interaction schema
        self.personalize_interaction_schema = personalize.CfnSchema(
            self,
            resource_name(personalize.CfnSchema, "recommender-interaction-schema"),
            name=resource_name(personalize.CfnSchema, "recommender-interaction-schema"),
            schema='{"type": "record", "name": "Interactions", "namespace": "com.amazonaws.personalize.schema", "fields": [{"name": "USER_ID", "type": "string"}, {"name": "ITEM_ID", "type": "string"}, {"name": "TIMESTAMP", "type": "long"}], "version": "1.0"}',
        )

        self.personalize_item_schema = personalize.CfnSchema(
            self,
            resource_name(personalize.CfnSchema, "recommender-item-schema"),
            name=resource_name(personalize.CfnSchema, "recommender-item-schema"),
            schema='{"type": "record", "name": "Items", "namespace": "com.amazonaws.personalize.schema", "fields": [{"name": "ITEM_ID", "type": "string"}, {"name": "ANIMAL_BREED", "type": "string", "categorical": true}, {"name": "ANIMAL_AGE", "type": "string", "categorical": true}, {"name": "ANIMAL_TYPE", "type": "string", "categorical": true}, {"name": "ANIMAL_SIZE", "type": "string", "categorical": true}, {"name": "item_value", "type": "float", "categorical": false}, {"name": "CREATION_TIMESTAMP", "type": "long"}], "version": "1.0"}',
        )
        # Dataset group which holds all our personalize resources
        self.personalize_dataset_group = personalize.CfnDatasetGroup(
            self,
            resource_name(personalize.CfnDatasetGroup, "recommender-datasetgroup"),
            name=resource_name(personalize.CfnDatasetGroup, "recommender-datasetgroup"),
            kms_key_arn=self.kms_key.key_arn,
            role_arn=self.personalize_role.role_arn,
        )
        self.personalize_dataset_group.node.add_dependency(self.kms_key)
        self.personalize_dataset_group.node.add_dependency(self.personalize_role)

        # Interactions dataset which points to seed bucket
        self.personalize_interaction_dataset = personalize.CfnDataset(
            self,
            resource_name(personalize.CfnDataset, "recommender-interaction-dataset"),
            dataset_group_arn=self.personalize_dataset_group.attr_dataset_group_arn,
            name=resource_name(
                personalize.CfnDataset, "recommender-interaction-dataset"
            ),
            schema_arn=self.personalize_interaction_schema.attr_schema_arn,
            dataset_type="Interactions",
            dataset_import_job=personalize.CfnDataset.DatasetImportJobProperty(
                data_source={
                    "DataLocation": f"s3://{seed_bucket_name}/seed_data/interactions"
                },
                job_name=f"{ENV_PREFIX}-recommender-dataimport-interactions-job",
                role_arn=self.dataset_role.role_arn,
            ),
        )
        self.personalize_interaction_dataset.node.add_dependency(
            self.personalize_dataset_group
        )
        # Items dataset which points to seed bucket
        self.personalize_items_dataset = personalize.CfnDataset(
            self,
            resource_name(personalize.CfnDataset, "recommender-items-dataset"),
            dataset_group_arn=self.personalize_dataset_group.attr_dataset_group_arn,
            name=resource_name(personalize.CfnDataset, "recommender-items-dataset"),
            schema_arn=self.personalize_item_schema.attr_schema_arn,
            dataset_type="Items",
            dataset_import_job=personalize.CfnDataset.DatasetImportJobProperty(
                data_source={
                    "DataLocation": f"s3://{seed_bucket_name}/seed_data/items"
                },
                job_name=f"{ENV_PREFIX}-recommender-dataimport-items-job",
                role_arn=self.dataset_role.role_arn,
            ),
        )
        self.personalize_items_dataset.node.add_dependency(
            self.personalize_dataset_group
        )
        # Recommender Solution
        self.personalize_solution = personalize.CfnSolution(
            self,
            resource_name(personalize.CfnSolution, "recommender-solution"),
            dataset_group_arn=self.personalize_dataset_group.attr_dataset_group_arn,
            name=resource_name(personalize.CfnSolution, "recommender-solution"),
            recipe_arn="arn:aws:personalize:::recipe/aws-user-personalization",
            solution_config=personalize.CfnSolution.SolutionConfigProperty(
                algorithm_hyper_parameters={
                    "bptt": "29",
                    "hidden_dimension": "239",
                    "recency_mask": "true",
                },
            ),
        )
        self.personalize_solution.node.add_dependency(self.personalize_items_dataset)
        self.personalize_solution.node.add_dependency(
            self.personalize_interaction_dataset
        )

        ssm_personalize_solution_arn = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "recommender-solution-ssm"),
            string_value=self.personalize_solution.attr_solution_arn,
            parameter_name="/animal-recommender/solution/arn",
        )

    def create_reranking_solution(self):
        # Reranking solution
        self.personalize_reranking_solution = personalize.CfnSolution(
            self,
            resource_name(personalize.CfnSolution, "reranking-solution"),
            dataset_group_arn=self.personalize_dataset_group.attr_dataset_group_arn,
            name=resource_name(personalize.CfnSolution, "reranking-solution"),
            recipe_arn="arn:aws:personalize:::recipe/aws-personalized-ranking",
            solution_config=personalize.CfnSolution.SolutionConfigProperty(
                algorithm_hyper_parameters={
                    "bptt": "29",
                    "hidden_dimension": "239",
                    "recency_mask": "true",
                },
            ),
        )
        self.personalize_reranking_solution.node.add_dependency(
            self.personalize_items_dataset
        )
        self.personalize_reranking_solution.node.add_dependency(
            self.personalize_interaction_dataset
        )

    def create_reranking_solution_version(self):
        # Reranking solution version lambda
        self.create_reranking_solution_version_cr_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "reranking-create-solution-version"),
            function_name=resource_name(
                _lambda.Function, "reranking-create-solution-version"
            ),
            handler="create_solution_version.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/custom_resources"),
            role=self.personalize_role,
            environment_encryption=self.kms_key,
            environment={
                "solution_arn": self.personalize_reranking_solution.attr_solution_arn,
                "solution_version_arn_ssm_path": config[
                    "rerankingSolutionVersionSsmPath"
                ],
            },
            timeout=Duration.seconds(30),
            memory_size=256,
        )
        # Reranking custom resource which calls the above lambda
        self.create_reranking_solution_version_cr = cr.AwsCustomResource(
            self,
            resource_name(cr.AwsCustomResource, "recommender-rerank-version-cr"),
            function_name=resource_name(
                cr.AwsCustomResource, "recommender-rerank-version-cr"
            ),
            role=self.personalize_role,
            install_latest_aws_sdk=False,
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": self.create_reranking_solution_version_cr_lambda.function_name,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    resource_name(personalize.CfnSolution, "reranking-solution"),
                ),
                assumed_role_arn=self.personalize_role.role_arn,
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:*"]
            ),
        )

        self.create_reranking_solution_version_cr.node.add_dependency(
            self.personalize_reranking_solution
        )

    def create_solution_version_cr(self):
        # Create recommender solution version lambda
        self.create_personalize_solution_version_cr_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-create-solution-version"),
            function_name=resource_name(
                _lambda.Function, "recommender-create-solution-version"
            ),
            handler="create_solution_version.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/custom_resources"),
            role=self.personalize_role,
            environment_encryption=self.kms_key,
            environment={
                "solution_arn": self.personalize_solution.attr_solution_arn,
                "solution_version_arn_ssm_path": config[
                    "recommendationSolutionVersionSsmPath"
                ],
            },
            timeout=Duration.seconds(30),
            memory_size=256,
        )
        # Create recommender solution version custom resource which calls above lambda
        self.create_personalize_solution_version_cr = cr.AwsCustomResource(
            self,
            resource_name(cr.AwsCustomResource, "recommender-solution-version-cr"),
            function_name=resource_name(
                cr.AwsCustomResource, "recommender-solution-version-cr"
            ),
            role=self.personalize_role,
            install_latest_aws_sdk=False,
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": self.create_personalize_solution_version_cr_lambda.function_name,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    resource_name(personalize.CfnSolution, "recommender-solution"),
                ),
                assumed_role_arn=self.personalize_role.role_arn,
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:*"]
            ),
        )

        self.create_personalize_solution_version_cr.node.add_dependency(
            self.personalize_solution
        )

    def create_event_tracker_cr(self):
        # Create event tracker for event ingestion, this posts event tracker id to ssm
        self.create_personalize_event_tracker_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-event-tracker-lambda"),
            function_name=resource_name(_lambda.Function, "recommender-event-tracker"),
            handler="create_event_tracker.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/custom_resources"),
            role=self.personalize_role,
            environment_encryption=self.kms_key,
            environment={
                "event_tracker_id_ssm": config["eventTrackerIdSsmPath"],
                "env": ENV_PREFIX,
                "data_set_group_arn": self.personalize_dataset_group.attr_dataset_group_arn,
            },
            timeout=Duration.seconds(120),
            memory_size=256,
        )
        # event tracker cr that calls abov e lambda
        self.create_personalize_event_tracker_cr = cr.AwsCustomResource(
            self,
            resource_name(cr.AwsCustomResource, "recommender-event-tracker"),
            function_name=resource_name(
                cr.AwsCustomResource, "recommender-event-tracker"
            ),
            role=self.personalize_role,
            install_latest_aws_sdk=False,
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": self.create_personalize_event_tracker_lambda.function_name,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    resource_name(
                        personalize.CfnDatasetGroup, "recommender-datasetgroup"
                    ),
                ),
                assumed_role_arn=self.personalize_role.role_arn,
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[
                    f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:event-tracker/{ENV_PREFIX}-recommender-personalize-event-tracker-tkr",
                    f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:dataset-group/{ENV_PREFIX}-recommender-datasetgroup-pdg",
                    f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:campaign/{ENV_PREFIX}-recommender-personalize-campaign-cpn",
                    f"arn:aws:personalize:{DEPLOY_REGION}:{ACCOUNT_ID}:campaign/{ENV_PREFIX}-reranking-personalize-campaign-cpn",
                ]
            ),
        )
        self.create_personalize_event_tracker_cr.node.add_dependency(
            self.personalize_dataset_group
        )

    def create_campaign_cr(self, seed_bucket_name):
        # Wait condition for recommender campaign
        self.cfn_wait_campaign_create_handle = cloudformation.CfnWaitConditionHandle(
            self,
            resource_name(
                cloudformation.CfnWaitConditionHandle, "campaign-wait-handle"
            ),
        )

        self.cfn_wait_campaign_creation = cloudformation.CfnWaitCondition(
            self,
            resource_name(cloudformation.CfnWaitCondition, "campaign-waiter"),
            count=1,
            handle=self.cfn_wait_campaign_create_handle.ref,
            timeout="28800",
        )

        self.seed_bucket = s3.Bucket.from_bucket_name(
            self,
            f"Seed Data Bucket",
            f"{seed_bucket_name}",
        )
        # Codebuild project used for creating recommender and rerank campaign
        self.create_campaign_project = codebuild.Project(
            self,
            resource_name(codebuild.Project, "recommender-create-campaign"),
            project_name=resource_name(
                codebuild.Project, "recommender-create-campaign"
            ),
            source=codebuild.Source.s3(
                bucket=self.seed_bucket,
                path=f"{VERSION}/scripts.zip",
            ),
            role=self.codebuild_role,
            timeout=Duration.minutes(480),
            build_spec=codebuild.BuildSpec.from_source_filename(
                filename="animal_recommender/code_build/create_campaign_spec.yml"
            ),
            environment=codebuild.BuildEnvironment(
                compute_type=codebuild.ComputeType.LARGE,
                build_image=codebuild.LinuxBuildImage.STANDARD_4_0,
            ),
            environment_variables={
                "min_tps": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=config["minProvisionedTPS"],
                ),
                "exploration_weight": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=config["explorationWeight"],
                ),
                "exploration_item_age_cut_off": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=config["explorationItemAgeCutOff"],
                ),
                "campaign_arn_ssm_path": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=config["recommendationCampaignArnSsmPath"],
                ),
                "solution_version_ssm_path": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=config["recommendationSolutionVersionSsmPath"],
                ),
                "env": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=ENV_PREFIX,
                ),
                "campaign_type": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value="recommender",
                ),
                "cfn_signal_url": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=self.cfn_wait_campaign_create_handle.ref,
                ),
            },
            encryption_key=self.kms_key,
        )
        # Custom resource which calls above codebuild project, creates recommender campaign after waiting for solution version to be ready
        self.create_campaign_codebuild = cr.AwsCustomResource(
            self,
            "create-campaign",
            function_name=resource_name(
                cr.AwsCustomResource, "recommender-campaign-cr"
            ),
            log_retention=logs.RetentionDays.INFINITE,
            on_create=cr.AwsSdkCall(
                service="CodeBuild",
                action="startBuild",
                parameters={
                    "projectName": self.create_campaign_project.project_name,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    resource_name(
                        personalize.CfnSolution, "recommender-solution-version-cr"
                    ),
                ),
                assumed_role_arn=self.personalize_role.role_arn,
                output_paths=["build.buildStatus"],
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[
                    f"arn:aws:codebuild:{DEPLOY_REGION}:{ACCOUNT_ID}:project/{ENV_PREFIX}-recommender-create-campaign-cbp",
                    f"arn:aws:codebuild:{DEPLOY_REGION}:{ACCOUNT_ID}:build/{ENV_PREFIX}-recommender-create-campaign*",
                ]
            ),
            role=self.personalize_role,
        )

        self.create_campaign_codebuild.node.add_dependency(
            self.create_personalize_solution_version_cr
        )

        self.cfn_wait_campaign_creation.node.add_dependency(
            self.create_campaign_project
        )

    def create_reranking_campaign_cr(self):
        # Waiter for reranking campaign
        self.cfn_wait_rerank_campaign_create_handle = (
            cloudformation.CfnWaitConditionHandle(
                self,
                resource_name(
                    cloudformation.CfnWaitConditionHandle, "campaign-rerank-wait-handle"
                ),
            )
        )

        self.cfn_wait_rerank_campaign_creation = cloudformation.CfnWaitCondition(
            self,
            resource_name(cloudformation.CfnWaitCondition, "campaign-rerank-waiter"),
            count=1,
            handle=self.cfn_wait_rerank_campaign_create_handle.ref,
            timeout="28800",
        )
        # Custom resource which calls the codebuild project, creates rerank campaign after waiting for rerank solution version to be ready
        # overwrites things like campaign_type so that we create rerank campaign instead of recommender campaign
        self.create_reranking_campaign_codebuild = cr.AwsCustomResource(
            self,
            "create-reranking-campaign",
            function_name=resource_name(
                cr.AwsCustomResource, "recommender-reraking-campaign-cr"
            ),
            log_retention=logs.RetentionDays.INFINITE,
            on_create=cr.AwsSdkCall(
                service="CodeBuild",
                action="startBuild",
                parameters={
                    "projectName": self.create_campaign_project.project_name,
                    "environmentVariablesOverride": [
                        {
                            "name": "campaign_arn_ssm_path",
                            "value": config["rerankingCampaignArnSsmPath"],
                            "type": "PLAINTEXT",
                        },
                        {
                            "name": "solution_version_ssm_path",
                            "value": config["rerankingSolutionVersionSsmPath"],
                            "type": "PLAINTEXT",
                        },
                        {
                            "name": "campaign_type",
                            "value": "reranking",
                            "type": "PLAINTEXT",
                        },
                        {
                            "name": "cfn_signal_url",
                            "value": self.cfn_wait_rerank_campaign_create_handle.ref,
                            "type": "PLAINTEXT",
                        },
                    ],
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    resource_name(
                        personalize.CfnSolution, "recommender-solution-version-cr"
                    ),
                ),
                assumed_role_arn=self.personalize_role.role_arn,
                output_paths=["build.buildStatus"],
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[
                    f"arn:aws:codebuild:{DEPLOY_REGION}:{ACCOUNT_ID}:project/{ENV_PREFIX}-recommender-create-campaign-cbp",
                    f"arn:aws:codebuild:{DEPLOY_REGION}:{ACCOUNT_ID}:build/{ENV_PREFIX}-recommender-create-campaign*",
                ]
            ),
            role=self.personalize_role,
        )

        self.create_reranking_campaign_codebuild.node.add_dependency(
            self.create_reranking_solution_version_cr
        )

        self.create_reranking_campaign_codebuild.node.add_dependency(
            self.create_campaign_project
        )

    def create_state_machine_tasks(self):
        # Statemachine role for underlying lambdas
        self.state_machine_execution_role = iam.Role(
            self,
            resource_name(iam.Role, "recommender-statemachine-execution-role"),
            role_name=resource_name(
                iam.Role, "recommender-statemachine-execution-role"
            ),
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    resource_name(
                        iam.Policy, "recommender-statemachine-execution-policy"
                    ),
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole",
                ),
            ],
            inline_policies={
                "LambdaPermission": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["sns:Publish*"],
                            resources=[self.sns_topic.topic_arn],
                        ),
                    ]
                )
            },
        )
        self.state_machine_execution_role.attach_inline_policy(self.ssm_policy)
        self.state_machine_execution_role.attach_inline_policy(self.personalize_policy)
        self.state_machine_execution_role.attach_inline_policy(self.kms_logs_policy)

        # statemachine role for kicing off machine
        self.state_machine_role = iam.Role(
            self,
            resource_name(iam.Role, "recommender-statemachine-role"),
            role_name=resource_name(iam.Role, "recommender-statemachine-role"),
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            inline_policies={
                "StateMachine": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "kms:Encrypt*",
                                "kms:Decrypt*",
                                "kms:ReEncrypt*",
                                "kms:GenerateDataKey*",
                                "kms:Describe*",
                            ],
                            resources=[
                                self.kms_key.key_arn,
                                f"arn:aws:kinesis:{DEPLOY_REGION}:{ACCOUNT_ID}:stream/{ENV_PREFIX}-recommender-stream-kss",
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-recommender-state-machine-logs-log",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=["sns:Publish*"],
                            resources=[self.sns_topic.topic_arn],
                        ),
                    ]
                )
            },
        )
        self.state_machine_role.attach_inline_policy(self.lambda_invoke_policy)
        self.state_machine_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")
        )
        # skip state
        self.job_pass = stepfunctions.Succeed(
            self,
            "Skip Training",
            comment=f"No New Users",
        )

        self.skip_training_message = tasks.SnsPublish(
            self,
            "Notify Skip Training",
            topic=self.sns_topic,
            message=stepfunctions.TaskInput.from_object(
                {"default": {"Status": "Skipping Recommender Training"}}
            ),
            subject=f"Recommender {ENV_PREFIX} Skipping Recommender Training",
        )

        # Create solution version
        self.create_solution_version_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-sm-create-version"),
            function_name=resource_name(
                _lambda.Function, "recommender-sm-create-version"
            ),
            handler="create_solution_version.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/state_machine"),
            role=self.state_machine_execution_role,
            environment_encryption=self.kms_key,
            environment={
                "solution_arn": self.personalize_solution.attr_solution_arn,
                "sns_arn": self.sns_topic.topic_arn,
                "rerank_solution_arn": self.personalize_reranking_solution.attr_solution_arn,
                "rerank_enabled": f"{config['rerankingEnabled']}",
            },
        )

        self.create_solution_version_job = tasks.LambdaInvoke(
            self,
            "Create Solution Version",
            lambda_function=self.create_solution_version_lambda,
            output_path="$.Payload",
        )
        # check if solution version is finished training
        self.describe_solution_version_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-sm-describe-version"),
            function_name=resource_name(
                _lambda.Function, "recommender-sm-describe-version"
            ),
            handler="describe_solution_version.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/state_machine"),
            role=self.state_machine_execution_role,
            environment_encryption=self.kms_key,
            environment={
                "sns_arn": self.sns_topic.topic_arn,
                "rerank_enabled": f"{config['rerankingEnabled']}",
            },
        )

        self.describe_solution_version_job = tasks.LambdaInvoke(
            self,
            "Wait For Solution Version Active",
            lambda_function=self.describe_solution_version_lambda,
            output_path="$.Payload",
        )
        # Retries for waiting for solution version to finish training
        self.describe_solution_version_job.add_retry(
            backoff_rate=1.0,
            interval=Duration.minutes(5),
            # check every 5 minutes for 24 hours
            max_attempts=288,
        )
        # Check solution version metrics
        self.evaluate_solution_version_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-sm-evaluate-solution"),
            function_name=resource_name(
                _lambda.Function, "recommender-sm-evaluate-solution"
            ),
            handler="evaluate_solution_version.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/state_machine"),
            role=self.state_machine_execution_role,
            environment_encryption=self.kms_key,
            environment={
                "sns_arn": self.sns_topic.topic_arn,
                "promotion_threshold": f"{config['promotionThreshold']}",
                "rerank_enabled": f"{config['rerankingEnabled']}",
            },
        )

        self.evalute_solution_version_job = tasks.LambdaInvoke(
            self,
            "Evaluate Solution Version",
            lambda_function=self.evaluate_solution_version_lambda,
            output_path="$.Payload",
        )

        self.do_not_promote = stepfunctions.Succeed(
            self,
            "Do Not Promote Model",
            comment="Check Model Performance",
        )

        self.do_promote = stepfunctions.Succeed(
            self,
            "Do Promote Model",
            comment="Model promoted",
        )
        # Update campaign with new solution version
        self.update_campaign_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-sm-update-campaign"),
            function_name=resource_name(
                _lambda.Function, "recommender-sm-update-campaign"
            ),
            handler="update_campaign.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/state_machine"),
            role=self.state_machine_execution_role,
            environment_encryption=self.kms_key,
            environment={
                "sns_arn": self.sns_topic.topic_arn,
                "campaign_arn_ssm_path": config["recommendationCampaignArnSsmPath"],
                "rerank_campaign_arn_ssm_path": config["rerankingCampaignArnSsmPath"],
                "rerank_min_tps": f"{config['reRankMinProvisionedTPS']}",
                "rerank_enabled": f"{config['rerankingEnabled']}",
                "min_tps": f"{config['minProvisionedTPS']}",
                "exploration_weight": f"{config['explorationWeight']}",
                "exploration_item_age_cut_off": f"{config['explorationItemAgeCutOff']}",
            },
        )

        self.update_campaign_job = tasks.LambdaInvoke(
            self,
            "Update Campaign with new Solution Version",
            lambda_function=self.update_campaign_lambda,
            output_path="$.Payload",
        )
        # Wait till campaign is finished updating
        self.describe_campaign_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "recommender-sm-describe-campaign"),
            function_name=resource_name(
                _lambda.Function, "recommender-sm-describe-campaign"
            ),
            handler="describe_campaign.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("animal_recommender/lambda/state_machine"),
            role=self.state_machine_execution_role,
            environment_encryption=self.kms_key,
            environment={
                "sns_arn": self.sns_topic.topic_arn,
                "campaign_arn_ssm": config["recommendationCampaignArnSsmPath"],
                "rerank_enabled": f"{config['rerankingEnabled']}",
                "rerank_campaign_arn_ssm_path": config["rerankingCampaignArnSsmPath"],
            },
        )

        self.describe_campaign_job = tasks.LambdaInvoke(
            self,
            "Wait For Campaign Update to Complete",
            lambda_function=self.describe_campaign_lambda,
            output_path="$.Payload",
        )

        self.describe_campaign_job.add_retry(
            backoff_rate=1.0,
            interval=Duration.minutes(1),
            max_attempts=30,
        )

    def create_state_machine_definition(self):
        # This defines how the tasks and lambdas are orchestrated
        self.state_machine_definition = self.create_solution_version_job.next(
            self.describe_solution_version_job.next(
                self.evalute_solution_version_job.next(
                    stepfunctions.Choice(self, "Promote Model Choice")
                    .when(
                        stepfunctions.Condition.boolean_equals("$.promote", False),
                        self.do_not_promote,
                    )
                    .when(
                        stepfunctions.Condition.boolean_equals("$.promote", True),
                        self.update_campaign_job.next(
                            self.describe_campaign_job.next(self.do_promote)
                        ),
                    )
                )
            )
        )

        self.state_machine_log_group = logs.LogGroup(
            self,
            "Recommender State Machine Log Group",
            log_group_name=resource_name(
                logs.LogGroup, "recommender-state-machine-logs"
            ),
            encryption_key=self.kms_key,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        # Create state machine using above definition
        self.training_state_machine = stepfunctions.StateMachine(
            self,
            "Recommender Training State Machine",
            state_machine_name=resource_name(
                stepfunctions.StateMachine, "recommender-state-machine"
            ),
            definition=self.state_machine_definition,
            logs=stepfunctions.LogOptions(
                destination=self.state_machine_log_group,
                level=stepfunctions.LogLevel.ALL,
            ),
            timeout=Duration.hours(24),
            role=self.state_machine_role.without_policy_updates(),
        )

        self.training_state_machine.node.add_dependency(self.state_machine_role)

        self.trigger_role = iam.Role(
            self,
            "recommender-trigger-role",
            role_name=resource_name(iam.Role, "recommender-trigger-role"),
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
        )

        # Send notificatino for FAILED, ABORTED, or timedout machine execution
        self.failure_notification = events.Rule(
            self,
            "recommender-failure-notification",
            rule_name=resource_name(events.Rule, "recommender-failure-notification"),
            event_pattern=events.EventPattern(
                source=["aws.states"],
                detail={
                    "stateMachineArn": [self.training_state_machine.state_machine_arn],
                    "status": ["FAILED", "ABORTED", "TIMED_OUT"],
                },
                detail_type=["Step Functions Execution Status Change"],
            ),
        )

        self.failure_notification.add_target(targets.SnsTopic(self.sns_topic))

        # Trigger machine once a day
        self.event_trigger = events.Rule(
            self,
            "recommender-statemachine-trigger",
            rule_name=resource_name(events.Rule, "recommender-statemachine-trigger"),
            schedule=events.Schedule.rate(cdk.Duration.days(1)),
        )
        self.event_trigger.add_target(
            targets.SfnStateMachine(
                self.training_state_machine,
                input=events.RuleTargetInput.from_object({"": ""}),
                role=self.trigger_role,
            )
        )
