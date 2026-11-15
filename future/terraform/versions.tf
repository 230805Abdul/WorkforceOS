terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state - uncomment and point at a real bucket before first apply.
  # backend "s3" {
  #   bucket         = "workforceos-tfstate"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "workforceos-tf-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region
}