"""Menu Vision CDK Stack — S3 buckets, Lambda functions, IAM roles, S3 event trigger,
API Gateway with Cognito authorizer."""

from aws_cdk import (
    CfnOutput,
    Duration,
    Fn,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigw,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_budgets as budgets,
    aws_s3_notifications as s3n,
)
from constructs import Construct


class MenuVisionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---------------------------------------------------------------
        # S3 Buckets
        # ---------------------------------------------------------------

        uploads_bucket = s3.Bucket(
            self,
            "UploadsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3600,
                ),
            ],
        )

        images_bucket = s3.Bucket(
            self,
            "ImagesBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(expiration=Duration.days(30)),
            ],
        )

        results_bucket = s3.Bucket(
            self,
            "ResultsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ---------------------------------------------------------------
        # Lambda Functions
        # ---------------------------------------------------------------

        # All Lambdas use the backend package from the parent directory.
        lambda_code = _lambda.Code.from_asset(
            path="..",
            exclude=["infra", ".kiro", ".hypothesis", ".pytest_cache", "tests", "**/__pycache__"],
        )

        submit_lambda = _lambda.Function(
            self,
            "SubmitLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.submit.handler",
            code=lambda_code,
            memory_size=256,
            timeout=Duration.seconds(30),
            environment={
                "UPLOAD_BUCKET": uploads_bucket.bucket_name,
                "RESULTS_BUCKET": results_bucket.bucket_name,
            },
        )

        processing_lambda = _lambda.Function(
            self,
            "ProcessingLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.process.handler",
            code=lambda_code,
            memory_size=1024,
            timeout=Duration.seconds(900),
            reserved_concurrent_executions=1,
            environment={
                "IMAGES_BUCKET": images_bucket.bucket_name,
                "RESULTS_BUCKET": results_bucket.bucket_name,
            },
        )

        status_lambda = _lambda.Function(
            self,
            "StatusLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.handlers.status.handler",
            code=lambda_code,
            memory_size=256,
            timeout=Duration.seconds(30),
            environment={
                "RESULTS_BUCKET": results_bucket.bucket_name,
            },
        )

        # ---------------------------------------------------------------
        # IAM Permissions
        # ---------------------------------------------------------------

        # Submit Lambda: put objects in uploads & results, get from uploads (pre-signed URLs)
        uploads_bucket.grant_put(submit_lambda)
        uploads_bucket.grant_read(submit_lambda)
        results_bucket.grant_put(submit_lambda)

        # Processing Lambda: read uploads, write images & results, call Textract + Bedrock
        uploads_bucket.grant_read(processing_lambda)
        images_bucket.grant_read_write(processing_lambda)
        results_bucket.grant_put(processing_lambda)

        processing_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["textract:DetectDocumentText"],
                resources=["*"],
            )
        )
        processing_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )

        # Status Lambda: read from results bucket
        results_bucket.grant_read(status_lambda)

        # ---------------------------------------------------------------
        # S3 Event Notification — uploads → Processing Lambda
        # ---------------------------------------------------------------

        uploads_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(processing_lambda),
        )

        # ---------------------------------------------------------------
        # Cognito User Pool
        # ---------------------------------------------------------------

        user_pool = cognito.UserPool(
            self,
            "MenuVisionUserPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=False,
                require_uppercase=False,
                require_digits=False,
                require_symbols=False,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        user_pool_domain = user_pool.add_domain(
            "MenuVisionDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix="menu-vision-app",
            ),
        )

        user_pool_client = user_pool.add_client(
            "MenuVisionAppClient",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=True,
                ),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=["https://localhost:3000/callback"],
                logout_urls=["https://localhost:3000/"],
            ),
            auth_flows=cognito.AuthFlow(user_srp=True),
        )

        # ---------------------------------------------------------------
        # API Gateway (REST) with Cognito Authorizer
        # ---------------------------------------------------------------

        api = apigw.RestApi(
            self,
            "MenuVisionApi",
            rest_api_name="MenuVisionApi",
            deploy_options=apigw.StageOptions(
                throttling_burst_limit=10,
                throttling_rate_limit=5,
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        cognito_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "MenuVisionCognitoAuthorizer",
            cognito_user_pools=[user_pool],
        )

        # POST /jobs → Submit Lambda
        jobs_resource = api.root.add_resource("jobs")
        jobs_resource.add_method(
            "POST",
            apigw.LambdaIntegration(submit_lambda),
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO,
        )

        # GET /jobs/{jobId} → Status Lambda
        job_id_resource = jobs_resource.add_resource("{jobId}")
        job_id_resource.add_method(
            "GET",
            apigw.LambdaIntegration(status_lambda),
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO,
        )

        # ---------------------------------------------------------------
        # CloudFront Distribution with Origin Access Control
        # ---------------------------------------------------------------

        # Origin Access Control for the frontend S3 bucket
        oac = cloudfront.S3OriginAccessControl(
            self,
            "FrontendOAC",
            signing=cloudfront.Signing.SIGV4_NO_OVERRIDE,
        )

        # S3 origin for the frontend bucket (using OAC)
        frontend_origin = origins.S3BucketOrigin.with_origin_access_control(
            frontend_bucket,
            origin_access_control=oac,
        )

        # Extract the API Gateway domain from the api.url
        # api.url looks like https://<id>.execute-api.<region>.amazonaws.com/prod/
        api_domain = Fn.select(2, Fn.split("/", api.url))

        api_origin = origins.HttpOrigin(
            domain_name=api_domain,
            origin_path=Fn.join("", ["/", Fn.select(3, Fn.split("/", api.url))]),
        )

        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=frontend_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                ),
            },
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
        )

        # ---------------------------------------------------------------
        # AWS Budget Alarm — $10/month with 80% and 100% notifications
        # ---------------------------------------------------------------

        notification_email = self.node.try_get_context("notification_email") or "user@example.com"

        budgets.CfnBudget(
            self,
            "MenuVisionMonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=10,
                    unit="USD",
                ),
                budget_name="MenuVisionMonthlyBudget",
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        comparison_operator="GREATER_THAN",
                        notification_type="ACTUAL",
                        threshold=80,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            address=notification_email,
                            subscription_type="EMAIL",
                        ),
                    ],
                ),
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        comparison_operator="GREATER_THAN",
                        notification_type="ACTUAL",
                        threshold=100,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            address=notification_email,
                            subscription_type="EMAIL",
                        ),
                    ],
                ),
            ],
        )

        # ---------------------------------------------------------------
        # Outputs
        # ---------------------------------------------------------------

        CfnOutput(self, "ApiUrl", value=api.url, description="API Gateway URL")
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id, description="Cognito User Pool ID")
        CfnOutput(self, "AppClientId", value=user_pool_client.user_pool_client_id, description="Cognito App Client ID")
        CfnOutput(
            self,
            "CognitoDomain",
            value=user_pool_domain.base_url(),
            description="Cognito Hosted UI Domain",
        )
        CfnOutput(
            self,
            "CloudFrontDomainName",
            value=distribution.distribution_domain_name,
            description="CloudFront Distribution Domain Name",
        )
        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=distribution.distribution_id,
            description="CloudFront Distribution ID",
        )
