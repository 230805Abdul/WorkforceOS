output "alb_dns_name" {
  description = "Point your domain's CNAME/ALIAS record at this"
  value       = aws_lb.main.dns_name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "rds_endpoint" {
  value     = aws_db_instance.postgres.endpoint
  sensitive = true
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "resumes_bucket_name" {
  value = aws_s3_bucket.resumes.id
}

output "github_actions_deploy_role_arn" {
  description = "Put this in the GitHub repo as AWS_DEPLOY_ROLE_ARN for OIDC-based CI deploys"
  value       = aws_iam_role.github_actions_deploy.arn
}
