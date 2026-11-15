variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "workforceos"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro" # free-tier-eligible; bump for real prod load
}

variable "db_username" {
  type      = string
  default   = "workforceos"
  sensitive = true
}

variable "db_password" {
  description = "Set via TF_VAR_db_password or a secrets manager - never commit a real value"
  type        = string
  sensitive   = true
}

variable "api_image" {
  description = "Full ECR/GHCR image URI:tag for the API container"
  type        = string
}

variable "worker_image" {
  description = "Full ECR/GHCR image URI:tag for the Celery worker container"
  type        = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "api_desired_count" {
  type    = number
  default = 2 # 2+ for zero-downtime rolling deploys and basic HA
}

variable "acm_certificate_arn" {
  description = "ARN of an ACM certificate for the ALB's HTTPS listener (request one via `aws acm request-certificate` first)"
  type        = string
}
